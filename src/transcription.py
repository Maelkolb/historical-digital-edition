"""
Transcription / Description (Step 2)
=====================================
Transcribes text regions and describes visual regions individually,
using a Gemini multimodal model.  Takes the detected regions from Step 1
and the original page image, then produces detailed content for each region.
"""

import base64
import json
import logging
from pathlib import Path
from typing import Any, Dict, List

from google import genai
from google.genai import types

from .json_utils import parse_json_robust
from .models import Region
from .region_detection import load_image_as_base64

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

TRANSCRIPTION_PROMPT = """\
You are an expert at transcribing historical documents (including Fraktur script).

You are given a page image and a list of regions detected on it.
For EACH region, produce the appropriate content:

FOR TEXT REGIONS (has_text = true):
- Transcribe the text EXACTLY as it appears, preserving historical spellings.
- Use modern umlauts (ä, ö, ü) instead of historical variants.
- Resolve ligatures (e.g. ſ → s).
- Preserve original punctuation.
- For tables: provide structured data with rows/cols/cells.

FOR VISUAL REGIONS (has_text = false):
- Provide a detailed description of what the image/illustration shows.
- Note artistic style, subjects, and any visible labels.

DETECTED REGIONS:
{regions_json}

Respond ONLY with a JSON array matching each region (same order, same indices):
[
    {{
        "region_index": 0,
        "region_type": "header",
        "is_visual": false,
        "content": "Transcribed text here...",
        "table_data": null
    }},
    {{
        "region_index": 1,
        "region_type": "table",
        "is_visual": false,
        "content": "Brief description of table content",
        "table_data": {{ "rows": 3, "cols": 2, "cells": [["Header1", "Header2"], ["r1c1", "r1c2"], ["r2c1", "r2c2"]], "caption": null }}
    }},
    {{
        "region_index": 2,
        "region_type": "image",
        "is_visual": true,
        "content": "Detailed description of the illustration...",
        "table_data": null
    }}
]

IMPORTANT:
- table_data should ONLY be set for table regions, null for all others.
- is_visual should be true ONLY for image/illustration regions that have no readable text.
- Maintain the exact region_index from the input.
"""


# ---------------------------------------------------------------------------
# Core function
# ---------------------------------------------------------------------------


def transcribe_regions(
    client: genai.Client,
    image_path: str | Path,
    detected_regions: List[Dict[str, Any]],
    model_id: str,
    thinking_level: str = "low",
) -> List[Region]:
    """
    Transcribe or describe each detected region on a page.

    Args:
        client:           Authenticated google.genai.Client instance.
        image_path:       Path to the page image.
        detected_regions: Output from detect_regions() (list of region dicts).
        model_id:         Gemini model identifier.
        thinking_level:   "none" | "low" | "medium" | "high"

    Returns:
        List of Region objects with transcribed/described content.
    """
    if not detected_regions:
        return []

    image_data, mime_type = load_image_as_base64(image_path)
    image_bytes = base64.b64decode(image_data)

    regions_json = json.dumps(detected_regions, ensure_ascii=False, indent=2)
    prompt = TRANSCRIPTION_PROMPT.format(regions_json=regions_json)

    max_attempts = 2
    data: List[Dict] = []

    for attempt in range(1, max_attempts + 1):
        try:
            response = client.models.generate_content(
                model=model_id,
                contents=[
                    types.Content(
                        parts=[
                            types.Part(text=prompt),
                            types.Part(
                                inline_data=types.Blob(
                                    mime_type=mime_type,
                                    data=image_bytes,
                                )
                            ),
                        ]
                    )
                ],
                config=types.GenerateContentConfig(
                    thinking_config=types.ThinkingConfig(thinking_level=thinking_level),
                    response_mime_type="application/json",
                ),
            )

            data = parse_json_robust(response.text)
            if not isinstance(data, list):
                data = []
            break

        except json.JSONDecodeError as exc:
            logger.error("JSON parse error during transcription (attempt %d/%d): %s",
                         attempt, max_attempts, exc)
        except Exception as exc:  # noqa: BLE001
            logger.error("Transcription error (attempt %d/%d): %s",
                         attempt, max_attempts, exc)

    # Build Region objects, falling back to detected_regions metadata if needed
    regions: List[Region] = []
    data_by_index = {item.get("region_index", i): item for i, item in enumerate(data)}

    for det in detected_regions:
        idx = det["region_index"]
        transcribed = data_by_index.get(idx, {})

        region_type = transcribed.get("region_type", det.get("region_type", "paragraph"))
        content = transcribed.get("content", det.get("summary", ""))
        is_visual = transcribed.get("is_visual", not det.get("has_text", True))
        table_data = transcribed.get("table_data")

        regions.append(Region(
            region_type=region_type,
            region_index=idx,
            content=content,
            is_visual=is_visual,
            table_data=table_data,
        ))

    regions.sort(key=lambda r: r.region_index)
    return regions

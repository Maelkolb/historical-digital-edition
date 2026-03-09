"""
Region Detection (Step 1)
=========================
Detects and classifies distinct regions on a page image using a
Gemini multimodal model.  Returns a list of region dicts in reading order,
each tagged with a region_type.
"""

import base64
import io
import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List

from PIL import Image
from google import genai
from google.genai import types

from .json_utils import parse_json_robust

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Image utilities
# ---------------------------------------------------------------------------


def load_image_as_base64(image_path: str | Path) -> tuple[str, str]:
    """Load an image file and return (base64_string, mime_type)."""
    with Image.open(image_path) as img:
        if img.mode != "RGB":
            img = img.convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=95)
        raw = buf.getvalue()
    return base64.b64encode(raw).decode("utf-8"), "image/jpeg"


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

REGION_DETECTION_PROMPT = """\
You are an expert at analysing historical document page images.

Examine this page image and identify ALL distinct regions in reading order.
For each region, determine its type from the following list:

REGION TYPES:
- heading: Main title or chapter heading
- subheading: Secondary heading or section title
- paragraph: Body text / running prose
- table: Tabular data
- footnote: Footnote text (usually at the bottom, smaller font, with a marker)
- date: Standalone date or date range
- image: Illustration, figure, map, diagram, or decorative element
- caption: Caption text accompanying an image or table
- list: Enumerated or bulleted list
- page_number: Printed page number
- header: Running header / column title at top of page
- marginalia: Marginal notes or annotations

IMPORTANT INSTRUCTIONS:
1. Return regions in exact reading order (top to bottom, left to right).
2. Each region should be a coherent, self-contained unit.
3. For text regions, provide a BRIEF summary (first ~20 words) so the region
   can be identified later for full transcription.
4. For image regions, briefly note what the image depicts.
5. Mark whether each region contains readable text or is purely visual.

Respond ONLY with a JSON array (no markdown, no commentary):
[
    {
        "region_index": 0,
        "region_type": "header",
        "has_text": true,
        "summary": "Brief summary or first words..."
    },
    {
        "region_index": 1,
        "region_type": "paragraph",
        "has_text": true,
        "summary": "First words of this paragraph..."
    },
    {
        "region_index": 2,
        "region_type": "image",
        "has_text": false,
        "summary": "Woodcut illustration showing a river landscape"
    }
]
"""


# ---------------------------------------------------------------------------
# Core function
# ---------------------------------------------------------------------------


def detect_regions(
    client: genai.Client,
    image_path: str | Path,
    model_id: str,
    thinking_level: str = "low",
) -> List[Dict[str, Any]]:
    """
    Detect regions on a page image.

    Args:
        client:        Authenticated google.genai.Client instance.
        image_path:    Path to the page image.
        model_id:      Gemini model identifier.
        thinking_level: "none" | "low" | "medium" | "high"

    Returns:
        List of region dicts with keys: region_index, region_type,
        has_text, summary.  On failure, returns an empty list.
    """
    image_data, mime_type = load_image_as_base64(image_path)
    image_bytes = base64.b64decode(image_data)

    max_attempts = 2
    regions: List[Dict[str, Any]] = []

    for attempt in range(1, max_attempts + 1):
        try:
            response = client.models.generate_content(
                model=model_id,
                contents=[
                    types.Content(
                        parts=[
                            types.Part(text=REGION_DETECTION_PROMPT),
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

            regions = parse_json_robust(response.text)
            if not isinstance(regions, list):
                regions = []
            break

        except json.JSONDecodeError as exc:
            logger.error("JSON parse error during region detection (attempt %d/%d): %s",
                         attempt, max_attempts, exc)
        except Exception as exc:  # noqa: BLE001
            logger.error("Region detection error (attempt %d/%d): %s",
                         attempt, max_attempts, exc)

    # Re-index sequentially
    for idx, region in enumerate(regions):
        region["region_index"] = idx

    return regions

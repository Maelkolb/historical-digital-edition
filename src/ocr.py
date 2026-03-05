"""
OCR Stage
=========
Transcribes historical German (Fraktur) book pages using a Gemini multimodal model.
Returns a structured dict with page_number_printed, header, content_blocks, and footnotes.
"""

import base64
import io
import json
import logging
import re
from pathlib import Path
from typing import Any, Dict

from PIL import Image
from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

_JSON_DECODER = json.JSONDecoder()

# ---------------------------------------------------------------------------
# Robust JSON parsing
# ---------------------------------------------------------------------------


def _parse_json_robust(text: str) -> Any:
    """
    Parse JSON from an LLM response, tolerating common issues:
    1. Markdown code fences (```json ... ```)
    2. Extra trailing data after valid JSON (Extra data error)
    3. Leading/trailing whitespace or explanation text
    """
    # Strip markdown code fences
    text = re.sub(r"^```(?:json)?\n?", "", text.strip())
    text = re.sub(r"\n?```$", "", text)

    # Try strict parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try raw_decode: parses the first valid JSON value, ignoring trailing data
    # Find the first '{' or '[' to skip any leading text
    for i, ch in enumerate(text):
        if ch in ('{', '['):
            try:
                result, _ = _JSON_DECODER.raw_decode(text, i)
                logger.debug("Recovered JSON via raw_decode at position %d", i)
                return result
            except json.JSONDecodeError:
                continue

    # Last resort: extract the outermost {...} or [...] with a regex
    for pattern in [r'\{[\s\S]*\}', r'\[[\s\S]*\]']:
        m = re.search(pattern, text)
        if m:
            try:
                result = json.loads(m.group())
                logger.debug("Recovered JSON via regex extraction")
                return result
            except json.JSONDecodeError:
                continue

    raise json.JSONDecodeError("No valid JSON found in LLM response", text, 0)


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

OCR_PROMPT = """\
Du bist ein Experte für die Transkription historischer deutscher Texte in Frakturschrift.

Analysiere das Bild dieser historischen Buchseite und extrahiere den Text MIT seiner originalen Struktur.

WICHTIGE ANWEISUNGEN:
1. Transkribiere den Text EXAKT wie er erscheint, einschließlich historischer Schreibweisen.
2. Verwende moderne Umlaute (ä, ö, ü) anstelle historischer Varianten.
3. Löse Ligaturen auf (z. B. ſ → s).
4. Behalte die originale Interpunktion bei.

STRUKTURELEMENTE – WICHTIG: REIHENFOLGE MUSS DER SEITE ENTSPRECHEN:
Gib alle Seitenelemente in einem einzigen Array "content_blocks" zurück.
Die Reihenfolge der Blöcke muss exakt der Lesereihenfolge auf der Seite entsprechen.

Jeder Block hat folgendes Format:
  { "block_type": "paragraph" | "heading" | "list" | "table", "block_index": <int>, "content": <value> }

- paragraph/heading: "content" ist ein String
- list:              "content" ist ein Array von Strings
- table:             "content" ist { "rows": int, "cols": int, "cells": [[...]], "caption": str|null }

Antworte NUR mit einem JSON-Objekt (kein Markdown, kein Kommentar):
{
    "page_number_printed": "4" | null,
    "header": "Kolumnentitel" | null,
    "content_blocks": [
        { "block_type": "paragraph", "block_index": 0, "content": "Erster Absatz..." },
        { "block_type": "table",     "block_index": 1, "content": { "rows": 2, "cols": 3, "cells": [...], "caption": null } },
        { "block_type": "paragraph", "block_index": 2, "content": "Text nach der Tabelle..." }
    ],
    "footnotes": [ { "marker": "*)", "text": "Fußnotentext" } ]
}
"""

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
# Core OCR function
# ---------------------------------------------------------------------------


def perform_ocr(
    client: genai.Client,
    image_path: str | Path,
    model_id: str,
    thinking_level: str = "high",
) -> Dict[str, Any]:
    """
    Run OCR on a single page image.

    Args:
        client:        Authenticated google.genai.Client instance.
        image_path:    Path to the page image.
        model_id:      Gemini model identifier.
        thinking_level: "none" | "low" | "medium" | "high"

    Returns:
        Dict with keys: page_number_printed, header, content_blocks, footnotes.
        On failure, returns safe defaults.
    """
    image_data, mime_type = load_image_as_base64(image_path)
    image_bytes = base64.b64decode(image_data)

    max_attempts = 2
    result: Dict[str, Any] = {}

    for attempt in range(1, max_attempts + 1):
        try:
            response = client.models.generate_content(
                model=model_id,
                contents=[
                    types.Content(
                        parts=[
                            types.Part(text=OCR_PROMPT),
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

            result = _parse_json_robust(response.text)
            break  # success

        except json.JSONDecodeError as exc:
            logger.error("JSON parse error during OCR (attempt %d/%d): %s",
                         attempt, max_attempts, exc)
            if attempt < max_attempts:
                logger.info("Retrying OCR…")
        except Exception as exc:  # noqa: BLE001
            logger.error("OCR error (attempt %d/%d): %s",
                         attempt, max_attempts, exc)
            if attempt < max_attempts:
                logger.info("Retrying OCR…")

    # Ensure required keys with sane defaults
    defaults: Dict[str, Any] = {
        "page_number_printed": None,
        "header": None,
        "content_blocks": [],
        "footnotes": [],
    }
    for key, default in defaults.items():
        if key not in result or result[key] is None:
            result[key] = default

    # Re-index content_blocks sequentially in case the model skipped indices
    for idx, block in enumerate(result.get("content_blocks", [])):
        block["block_index"] = idx

    return result

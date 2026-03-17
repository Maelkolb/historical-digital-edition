"""
JSON Utilities
==============
Robust JSON parsing for LLM responses.
"""

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

_JSON_DECODER = json.JSONDecoder()


def parse_json_robust(text: str) -> Any:
    """
    Parse JSON from an LLM response, tolerating common issues:
    1. Markdown code fences (```json ... ```)
    2. Extra trailing data after valid JSON
    3. Leading/trailing whitespace or explanation text
    """
    text = re.sub(r"^```(?:json)?\n?", "", text.strip())
    text = re.sub(r"\n?```$", "", text)

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    for i, ch in enumerate(text):
        if ch in ('{', '['):
            try:
                result, _ = _JSON_DECODER.raw_decode(text, i)
                logger.debug("Recovered JSON via raw_decode at position %d", i)
                return result
            except json.JSONDecodeError:
                continue

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

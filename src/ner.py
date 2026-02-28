"""
NER Stage
=========
Performs Named Entity Recognition on the OCR text using a Gemini model.
Returns a list of Entity objects with strict criteria for Person and Location.
"""

import json
import logging
import re
from typing import List

from google import genai
from google.genai import types

from .models import Entity

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompt template
# ---------------------------------------------------------------------------

NER_PROMPT_TEMPLATE = """\
Du bist ein Experte für Named Entity Recognition (NER) in historischen deutschen Texten.

Analysiere den folgenden Text und identifiziere alle Entitäten der unten genannten Kategorien.

ENTITÄTSKATEGORIEN:
{entity_descriptions}

WICHTIGE ANWEISUNGEN – BITTE GENAU BEACHTEN:

1. STRENGE KRITERIEN FÜR "Person":
   - NUR einzelne, namentlich genannte historische Persönlichkeiten annotieren.
   - Korrekte Beispiele: "Kaiser Karl IV.", "Herzog Ernst", "Fürst Reuß", "Martin Luther"
   - NICHT annotieren: Berufsgruppen (Bauern, Bergleute), Bevölkerungsgruppen (Einwohner),
     generische Begriffe (Volk, Menschen), Ethnien (Sorben, Germanen).
   - Im Zweifel: NICHT als Person annotieren!

2. STRENGE KRITERIEN FÜR "Location":
   - NUR konkret identifizierbare geographische Orte mit Eigennamen.
   - Korrekte Beispiele: "Weimar", "Thüringen", "Böhmen", "Sachsen", "Magdeburg"
   - NICHT annotieren: abstrakte Gebietsbezeichnungen (Unterland, Hochfläche),
     generische Landschaftsbegriffe (Thal, Plateau), relative Ortsangaben (im Osten).
   - Im Zweifel: NICHT als Location annotieren!

3. ALLGEMEINE REGELN:
   - Annotiere nur EINDEUTIGE Entitäten.
   - Gib die EXAKTE Zeichenposition (start_char, end_char) im Text an.
   - Der extrahierte Text muss EXAKT mit dem Originaltext übereinstimmen.
   - Bei überlappenden Entitäten: wähle die spezifischere Kategorie.

TEXT ZUR ANALYSE:
```
{text}
```

Antworte NUR mit einem JSON-Array (kein Markdown, kein Kommentar):
[
    {{
        "text": "exakter Text der Entität",
        "entity_type": "Kategorie aus der Liste oben",
        "start_char": 0,
        "end_char": 10,
        "context": "...kurzer Kontext..."
    }}
]

Gib ein leeres Array [] zurück, wenn keine Entitäten gefunden werden.
"""


# ---------------------------------------------------------------------------
# Core NER function
# ---------------------------------------------------------------------------


def perform_ner(
    client: genai.Client,
    text: str,
    entity_types: dict[str, str],
    model_id: str,
    thinking_level: str = "high",
) -> List[Entity]:
    """
    Run NER on plain text.

    Args:
        client:        Authenticated google.genai.Client instance.
        text:          The OCR text to annotate.
        entity_types:  Dict mapping entity type name → German definition.
        model_id:      Gemini model identifier.
        thinking_level: "none" | "low" | "medium" | "high"

    Returns:
        List of Entity objects sorted by start_char.
    """
    if not text.strip():
        return []

    entity_descriptions = "\n".join(
        f"- **{etype}**: {desc}" for etype, desc in entity_types.items()
    )
    prompt = NER_PROMPT_TEMPLATE.format(
        entity_descriptions=entity_descriptions,
        text=text,
    )

    try:
        response = client.models.generate_content(
            model=model_id,
            contents=prompt,
            config=types.GenerateContentConfig(
                thinking_config=types.ThinkingConfig(thinking_level=thinking_level),
                response_mime_type="application/json",
            ),
        )

        raw = response.text.strip()
        raw = re.sub(r"^```(?:json)?\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)
        data = json.loads(raw)

    except json.JSONDecodeError as exc:
        logger.error("JSON parse error during NER: %s", exc)
        return []
    except Exception as exc:  # noqa: BLE001
        logger.error("NER error: %s", exc)
        return []

    entities: List[Entity] = []
    valid_types = set(entity_types.keys())

    for item in data:
        if not isinstance(item, dict):
            continue
        entity_type = item.get("entity_type", "")
        if entity_type not in valid_types:
            logger.debug("Skipping unknown entity type: %s", entity_type)
            continue
        try:
            entities.append(
                Entity(
                    text=str(item.get("text", "")),
                    entity_type=entity_type,
                    start_char=int(item.get("start_char", 0)),
                    end_char=int(item.get("end_char", 0)),
                    context=item.get("context"),
                )
            )
        except (TypeError, ValueError) as exc:
            logger.warning("Skipping malformed entity %s: %s", item, exc)

    entities.sort(key=lambda e: e.start_char)
    return entities

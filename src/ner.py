"""
NER Stage (Step 3)
==================
Performs Named Entity Recognition on the combined text from all regions
using a Gemini model.  Returns a list of Entity objects.

Entity placement uses text matching (not character offsets) for robust
rendering — LLMs are unreliable at exact character counting.
"""

import json
import logging
from typing import List

from google import genai
from google.genai import types

from .models import Entity
from .json_utils import parse_json_robust

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
   - Der "text"-Wert muss EXAKT mit dem Originaltext übereinstimmen (Groß-/Kleinschreibung beachten).
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
        "context": "...kurzer Satz in dem die Entität vorkommt..."
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
    thinking_level: str = "low",
) -> List[Entity]:
    """
    Run NER on plain text.

    Returns Entity objects.  The start_char / end_char fields are set to -1
    because the renderer uses text matching rather than offsets (LLMs are
    unreliable at character counting).
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

    max_attempts = 2
    data = []

    for attempt in range(1, max_attempts + 1):
        try:
            response = client.models.generate_content(
                model=model_id,
                contents=prompt,
                config=types.GenerateContentConfig(
                    thinking_config=types.ThinkingConfig(thinking_level=thinking_level),
                    response_mime_type="application/json",
                ),
            )

            data = parse_json_robust(response.text)
            break

        except json.JSONDecodeError as exc:
            logger.error("JSON parse error during NER (attempt %d/%d): %s",
                         attempt, max_attempts, exc)
        except Exception as exc:  # noqa: BLE001
            logger.error("NER error (attempt %d/%d): %s",
                         attempt, max_attempts, exc)

    entities: List[Entity] = []
    valid_types = set(entity_types.keys())
    seen_texts: set[tuple[str, str]] = set()

    for item in data:
        if not isinstance(item, dict):
            continue
        entity_type = item.get("entity_type", "")
        entity_text = str(item.get("text", "")).strip()
        if entity_type not in valid_types:
            logger.debug("Skipping unknown entity type: %s", entity_type)
            continue
        if not entity_text:
            continue

        # Deduplicate: same text + type only once
        key = (entity_text, entity_type)
        if key in seen_texts:
            continue
        seen_texts.add(key)

        entities.append(
            Entity(
                text=entity_text,
                entity_type=entity_type,
                start_char=-1,
                end_char=-1,
                context=item.get("context"),
            )
        )

    return entities

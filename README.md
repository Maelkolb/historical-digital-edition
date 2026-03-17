# Historical Digital Edition Pipeline

A reproducible, generalized workflow for turning digital images of book/document pages into an interactive digital edition. Uses **Google Gemini** multimodal models for all AI-powered steps.

## Pipeline

| Step | Module | Description |
|------|--------|-------------|
| 1. Region Detection | `region_detection.py` | Identifies distinct regions on each page (headings, paragraphs, tables, footnotes, images, dates, etc.) |
| 2. Transcription | `transcription.py` | Transcribes text regions (including Fraktur), describes visual regions |
| 3. Entity Annotation | `ner.py` | Named Entity Recognition on combined page text |
| 4. Georeferencing | `geocoding.py` | Resolves Location entities to coordinates via Nominatim |
| 5. Digital Edition | `html_generator.py` | Generates interactive HTML with region indicators, entity highlighting, maps |

## Region Types

The pipeline detects and visually differentiates these region types:

- **Heading** / **Subheading** - Section titles
- **Paragraph** - Body text
- **Table** - Tabular data (structured extraction)
- **Footnote** - Footnote text with markers
- **Date** - Standalone dates or date ranges
- **Image** - Illustrations, figures, maps (described rather than transcribed)
- **Caption** - Image/table captions
- **List** - Enumerated or bulleted content
- **Page Number** / **Header** - Page metadata
- **Marginalia** - Marginal notes

## Repository Layout

```
historical-digital-edition/
├── src/
│   ├── __init__.py            # Public API
│   ├── config.py              # All settings
│   ├── models.py              # Data structures (Region, Entity, PageResult, etc.)
│   ├── json_utils.py          # Robust JSON parsing for LLM responses
│   ├── region_detection.py    # Step 1: detect regions via Gemini
│   ├── transcription.py       # Step 2: transcribe/describe regions
│   ├── ner.py                 # Step 3: entity annotation via Gemini
│   ├── geocoding.py           # Step 4: geocode locations via Nominatim
│   ├── html_generator.py      # Step 5: generate HTML digital edition
│   ├── pipeline.py            # Orchestrates all steps
│   └── downloader.py          # IIIF image downloader
├── scripts/
│   ├── process_book.py        # CLI: run full pipeline
│   ├── download_images.py     # CLI: download page images
│   └── export_entities.py     # CLI: export entities to CSV
├── output/                    # Created at runtime (gitignored)
├── images/                    # Created at runtime (gitignored)
├── requirements.txt
└── .gitignore
```

## Quick Start

### 1. Install

```bash
git clone <repo-url>
cd historical-digital-edition
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Set your API key

```bash
cp .env.example .env
# Edit .env and set GEMINI_API_KEY from https://aistudio.google.com/
```

### 3. Download page images (optional, for IIIF sources)

```bash
python scripts/download_images.py --manifest <IIIF_MANIFEST_URL> --start 1 --end 50 --out images/
```

### 4. Run the pipeline

```bash
# Process all pages
python scripts/process_book.py --images images/ --out output/

# Process a subset (good for testing)
python scripts/process_book.py --images images/ --out output/ --end 5

# Embed facsimile images in the HTML
python scripts/process_book.py --images images/ --out output/ --embed-images
```

Open `output/digital_edition.html` in your browser.

### 5. Export entities to CSV

```bash
python scripts/export_entities.py --json output/digital_edition_complete.json
```

## Configuration

All settings are in `src/config.py`:

| Variable | Default | Purpose |
|---|---|---|
| `MODEL_ID` | `gemini-3-flash-preview` | Gemini model to use |
| `THINKING_LEVEL` | `"low"` | `"none"` / `"low"` / `"medium"` / `"high"` |
| `IMAGE_FOLDER` | `./images` | Source images (env var override) |
| `OUTPUT_FOLDER` | `./output` | Output directory (env var override) |
| `ENTITY_TYPES` | 11 types | German definitions for each entity category |
| `ENTITY_COLORS` | Archival palette | Hex colours for entity highlighting |
| `REGION_COLORS` | Per-type colours | Hex colours for region type indicators |

To customize entity types, edit `ENTITY_TYPES`, `ENTITY_COLORS`, and `ENTITY_LABELS` in `config.py`.

## Using as a Library

```python
import os
from google import genai
from src import config, process_book, generate_html_edition

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

results = process_book(
    client=client,
    image_folder="images/",
    output_folder="output/",
    entity_types=config.ENTITY_TYPES,
    model_id=config.MODEL_ID,
)

generate_html_edition(
    results=results,
    output_path="output/my_edition.html",
    title="My Digital Edition",
    entity_colors=config.ENTITY_COLORS,
    entity_labels=config.ENTITY_LABELS,
    region_colors=config.REGION_COLORS,
    region_labels=config.REGION_LABELS,
)
```

## Output Files

```
output/
├── json/
│   ├── page_0001.json                 # Per-page result with regions + entities
│   └── ...
├── digital_edition_complete.json      # All pages combined
├── digital_edition.html               # Interactive HTML viewer
└── geocode_cache.json                 # Cached geocoding results
```

## License

MIT

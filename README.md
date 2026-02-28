# 📜 Historical Digital Edition Pipeline

An LLM-powered pipeline that transforms scanned historical German books into richly annotated interactive digital editions. It uses **Google Gemini** for two sequential tasks:

1. **OCR** — transcribes Fraktur/historical script images into structured text while preserving the exact reading order of paragraphs, headings, lists, and tables.
2. **NER** — annotates 11 environmental and historical entity types with strict criteria for accuracy.

The final output is a single self-contained HTML file you can open in any browser — no server required.

---

## ✨ Features

| Feature | Detail |
|---|---|
| Fraktur OCR | Handles old German script, ligatures, and historical orthography |
| Structured extraction | Content blocks (paragraphs, headings, tables, lists) preserved in page order |
| 11 entity types | Animals, Plants, Locations, Persons, Organisations, Resources, Climate, … |
| Strict NER criteria | Separate rules for Person vs. group nouns, proper place names vs. generic terms |
| Interactive HTML viewer | Entity filter legend, keyboard navigation, optional facsimile toggle |
| IIIF downloader | Downloads images straight from any IIIF Presentation API v2 manifest |
| CSV export | All entities exportable for further analysis in any tool |
| Fully configurable | Swap model, entity types, colours, paths — all in one `config.py` |

---

## 🗂 Repository Layout

```
historical-digital-edition/
├── src/
│   ├── __init__.py          # Public API
│   ├── config.py            # ← All settings live here
│   ├── models.py            # Typed data structures
│   ├── downloader.py        # IIIF image downloader
│   ├── ocr.py               # Stage 1 – OCR with Gemini
│   ├── ner.py               # Stage 2 – NER with Gemini
│   ├── pipeline.py          # Orchestrates OCR → NER for a whole book
│   └── html_generator.py    # Renders results to interactive HTML
├── scripts/
│   ├── download_images.py   # CLI: download page images
│   ├── process_book.py      # CLI: run full pipeline
│   └── export_entities.py   # CLI: export entities to CSV
├── notebooks/
│   └── digital_edition_workflow.ipynb  # Interactive Colab/Jupyter walkthrough
├── output/                  # Created at runtime – gitignored
├── images/                  # Created at runtime – gitignored
├── requirements.txt
├── .env.example
└── .gitignore
```

---

## 🚀 Quick Start

### 1. Clone & install

```bash
git clone https://github.com/your-org/historical-digital-edition.git
cd historical-digital-edition
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Set your API key

```bash
cp .env.example .env
# Edit .env and paste your GEMINI_API_KEY from https://aistudio.google.com/
```

### 3. Download page images (IIIF)

```bash
python scripts/download_images.py --book-id bsb11005578 --start 15 --end 102 --out images/
```

This fetches images from the [Bayerische Staatsbibliothek MDZ](https://www.digitale-sammlungen.de/) IIIF manifest. Substitute your own `--book-id` or pass `--manifest <URL>` for any other IIIF v2 source.

### 4. Run the pipeline

```bash
# Process all pages and generate HTML edition
python scripts/process_book.py --images images/ --out output/

# Process only the first 10 pages (good for testing)
python scripts/process_book.py --images images/ --out output/ --end 10

# Embed facsimile images directly in the HTML (larger file, fully self-contained)
python scripts/process_book.py --images images/ --out output/ --embed-images
```

Open `output/digital_edition.html` in your browser. Done.

### 5. Export entities to CSV

```bash
python scripts/export_entities.py --json output/digital_edition_complete.json
```

---

## ⚙️ Configuration

Everything is in **`src/config.py`**. Key settings:

| Variable | Default | Purpose |
|---|---|---|
| `MODEL_ID` | `gemini-2.5-flash-preview-04-17` | Gemini model to use |
| `THINKING_LEVEL` | `"high"` | `"none"` / `"low"` / `"medium"` / `"high"` |
| `IMAGE_FOLDER` | `./images` | Source images (overridable via `IMAGE_FOLDER` env var) |
| `OUTPUT_FOLDER` | `./output` | Output directory (overridable via `OUTPUT_FOLDER` env var) |
| `BOOK_ID` | `bsb11005578` | BSB book identifier for the IIIF downloader |
| `ENTITY_TYPES` | 11 types | German definitions for each entity category |
| `ENTITY_COLORS` | archival palette | Hex colours for the HTML legend |

To add or rename entity types, edit `ENTITY_TYPES` and `ENTITY_COLORS` in `config.py` — no other file needs to change.

---

## 🏷 Entity Types

| Type | German definition (excerpt) |
|---|---|
| **Animal** | Tier, Tiergruppe oder Tierart (Wolf, Forelle, Rinderherde) |
| **Plant** | Pflanze/Pflanzenart (Eiche, Buche, Weizen) |
| **Location** | Konkrete geographische Orte mit Eigennamen (Weimar, Thüringen) |
| **Person** | Namentlich identifizierbare historische Persönlichkeiten (Kaiser Karl IV.) |
| **Organisation** | Organisation/Institution (Universität Jena, Forstamt Saalfeld) |
| **Natural Object** | Natürlich vorkommendes Objekt (Donau, Fichtelgebirge, Brocken) |
| **Resource** | Natürliche Ressource (Holz, Erz, Kohle) |
| **Environment** | Biotop/Habitat (Wald, Uferzone, Auenlandschaft) |
| **Environmental Impact** | Umweltauswirkung (Überschwemmung, Erosion, Abholzung) |
| **Climate** | Klimaphänomen (Frost, Dürre, Schneesturm) |
| **Artefact** | Menschengemachtes Artefakt (Brücke, Mühle, Eisenbahn) |

---

## 📓 Notebook

`notebooks/digital_edition_workflow.ipynb` walks through the entire pipeline step-by-step and is designed to run in **Google Colab** with your Google Drive as storage. It mirrors all the script functionality and is the best place to experiment with prompts and inspect intermediate results.

---

## 🔌 Using as a Library

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
    thinking_level="medium",   # faster, slightly less accurate
    start_page=0,
    end_page=10,               # None = all pages
)

generate_html_edition(
    results=results,
    output_path="output/my_edition.html",
    title="Reuss-Thüringen 1865",
    entity_colors=config.ENTITY_COLORS,
    entity_labels=config.ENTITY_LABELS,
    image_folder="images/",   # set to None to skip facsimile embedding
)
```

---

## 📊 Output Files

After a run, `output/` contains:

```
output/
├── json/
│   ├── page_0015.json       # Per-page result with full structure + entities
│   ├── page_0016.json
│   └── …
├── digital_edition_complete.json   # All pages combined
├── digital_edition.html            # ← Open this in your browser
└── digital_edition_complete.csv    # (after running export_entities.py)
```

---

## 🛠 Tips & Troubleshooting

**Slow processing?** Set `--thinking none` or `--thinking low` — much faster, marginally less accurate.

**JSON parse errors?** The pipeline logs warnings and skips malformed model responses. Re-run `--start <page>` to resume from the failed page.

**Images not found?** Check `IMAGE_FOLDER` in `config.py` or pass `--images <path>` explicitly to the script.

**Rate limits?** The IIIF downloader respects a configurable `--delay` (default 0.5 s). For the Gemini API, consider processing pages in smaller batches with `--start` / `--end`.

---

## 📄 License

MIT — see `LICENSE` for details.

---

## 🙏 Acknowledgements

- [Bayerische Staatsbibliothek / MDZ](https://www.digitale-sammlungen.de/) for openly publishing historical documents via IIIF
- [Google Gemini](https://ai.google.dev/) multimodal API
- The digital humanities community for NER schema inspiration

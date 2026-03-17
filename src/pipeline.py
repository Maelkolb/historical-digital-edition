"""
Processing Pipeline
===================
Orchestrates the 5-step pipeline over a folder of page images:

1. Region Detection   – identify regions on the page
2. Transcription      – transcribe text / describe images per region
3. Entity Annotation  – NER on combined text
4. Georeferencing     – geocode Location entities
5. Digital Edition    – generate HTML output

Results are persisted as JSON after each page.
"""

import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from tqdm import tqdm
from google import genai

from .models import Entity, GeoLocation, Region, PageResult
from .region_detection import detect_regions
from .transcription import transcribe_regions
from .ner import perform_ner
from .geocoding import geocode_entities

logger = logging.getLogger(__name__)

VALID_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tiff", ".tif", ".bmp"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def get_image_files(folder: str | Path) -> List[Path]:
    """Return all image files from *folder*, sorted by name."""
    folder = Path(folder)
    files = [
        folder / f
        for f in os.listdir(folder)
        if Path(f).suffix.lower() in VALID_IMAGE_EXTENSIONS
    ]
    return sorted(files)


def extract_page_number(filename: str) -> int:
    """
    Try to extract a page number from *filename*.
    Handles patterns like page_001.jpg, 0001.jpg, seq_021_page_9.jpg.
    Returns 0 if no number is found.
    """
    patterns = [r"page[_-]?(\d+)", r"seq[_-]?(\d+)", r"(\d+)\.[a-z]+$"]
    for pattern in patterns:
        match = re.search(pattern, filename, re.IGNORECASE)
        if match:
            return int(match.group(1))
    return 0


def build_full_text(regions: List[Region]) -> str:
    """Combine text from all non-visual regions into a single string for NER."""
    parts: List[str] = []
    for region in regions:
        if region.is_visual:
            continue
        if region.region_type == "table" and region.table_data:
            for row in region.table_data.get("cells", []):
                parts.extend(cell for cell in row if cell)
        elif region.content:
            parts.append(region.content)
    return "\n\n".join(parts)


def load_results_from_json(source: str | Path) -> List[PageResult]:
    """
    Load previously processed PageResult objects from JSON.

    Args:
        source: Either a combined JSON file or a directory of page_NNNN.json files.
    """
    source = Path(source)
    if source.is_file():
        with open(source, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        results = [PageResult.from_dict(d) for d in data]
    elif source.is_dir():
        json_files = sorted(source.glob("page_*.json"))
        results = []
        for jf in json_files:
            with open(jf, "r", encoding="utf-8") as fh:
                results.append(PageResult.from_dict(json.load(fh)))
    else:
        raise FileNotFoundError(f"No file or directory at {source}")

    results.sort(key=lambda r: r.page_number)
    logger.info("Loaded %d page results.", len(results))
    return results


# ---------------------------------------------------------------------------
# Single-page processor
# ---------------------------------------------------------------------------


def process_page(
    client: genai.Client,
    image_path: str | Path,
    page_number: int,
    entity_types: dict,
    model_id: str,
    thinking_level: str = "low",
    geo_cache: Optional[Dict] = None,
) -> PageResult:
    """
    Run the full pipeline for one page:
    1. Region Detection -> 2. Transcription -> 3. NER -> 4. Geocoding
    """
    image_path = Path(image_path)
    logger.info("Processing page %d: %s", page_number, image_path.name)

    # Step 1 – Region Detection
    logger.info("  Step 1: Region detection...")
    detected = detect_regions(client, image_path, model_id, thinking_level)
    logger.info("  Detected %d regions", len(detected))

    # Step 2 – Transcription / Description
    logger.info("  Step 2: Transcription...")
    regions = transcribe_regions(client, image_path, detected, model_id, thinking_level)
    logger.info("  Transcribed %d regions", len(regions))

    # Step 3 – NER
    full_text = build_full_text(regions)
    logger.info("  Step 3: NER on %d chars...", len(full_text))
    entities = perform_ner(client, full_text, entity_types, model_id, thinking_level)
    logger.info("  Found %d entities", len(entities))

    # Step 4 – Geocoding
    logger.info("  Step 4: Geocoding...")
    locations = geocode_entities(entities, cache=geo_cache)
    logger.info("  Geocoded %d locations", len(locations))

    return PageResult(
        page_number=page_number,
        image_filename=image_path.name,
        regions=regions,
        full_text=full_text,
        entities=entities,
        locations=locations,
        processing_timestamp=datetime.now().isoformat(),
        model_used=model_id,
    )


# ---------------------------------------------------------------------------
# Book-level processor
# ---------------------------------------------------------------------------


def process_book(
    client: genai.Client,
    image_folder: str | Path,
    output_folder: str | Path,
    entity_types: dict,
    model_id: str,
    thinking_level: str = "low",
    start_page: Optional[int] = None,
    end_page: Optional[int] = None,
) -> List[PageResult]:
    """
    Process all pages in *image_folder* through the full pipeline.

    Args:
        client:        Authenticated google.genai.Client instance.
        image_folder:  Folder containing page images.
        output_folder: Root output directory (json/ subdir will be created).
        entity_types:  Dict mapping entity type name -> definition.
        model_id:      Gemini model identifier.
        thinking_level: Gemini thinking level.
        start_page:    0-based start index (inclusive).
        end_page:      0-based end index (exclusive).

    Returns:
        List of PageResult objects sorted by page number.
    """
    image_folder = Path(image_folder)
    output_folder = Path(output_folder)
    json_folder = output_folder / "json"
    json_folder.mkdir(parents=True, exist_ok=True)

    image_files = get_image_files(image_folder)
    if not image_files:
        logger.error("No images found in %s", image_folder)
        return []

    logger.info("Found %d images in %s", len(image_files), image_folder)

    subset = image_files[start_page:end_page]
    logger.info("Processing %d pages...", len(subset))

    geo_cache: Dict = {}
    results: List[PageResult] = []

    for idx, image_path in enumerate(tqdm(subset, desc="Pages", unit="pg")):
        page_num = extract_page_number(image_path.name) or (idx + 1)
        try:
            result = process_page(
                client, image_path, page_num, entity_types,
                model_id, thinking_level, geo_cache,
            )
            results.append(result)

            # Persist individual page JSON
            page_json = json_folder / f"page_{page_num:04d}.json"
            with open(page_json, "w", encoding="utf-8") as fh:
                json.dump(result.to_dict(), fh, ensure_ascii=False, indent=2)

        except Exception as exc:  # noqa: BLE001
            logger.error("Error processing %s: %s", image_path.name, exc, exc_info=True)

    results.sort(key=lambda r: r.page_number)

    # Save combined JSON
    combined_json = output_folder / "digital_edition_complete.json"
    with open(combined_json, "w", encoding="utf-8") as fh:
        json.dump([r.to_dict() for r in results], fh, ensure_ascii=False, indent=2)
    logger.info("Combined JSON saved: %s", combined_json)

    # Save geocode cache
    if geo_cache:
        cache_path = output_folder / "geocode_cache.json"
        with open(cache_path, "w", encoding="utf-8") as fh:
            json.dump(geo_cache, fh, ensure_ascii=False, indent=2)

    logger.info(
        "Done. Pages: %d | Entities: %d | Locations: %d",
        len(results),
        sum(len(r.entities) for r in results),
        sum(len(r.locations) for r in results),
    )
    return results

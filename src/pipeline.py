"""
Processing Pipeline
===================
Orchestrates the two-stage OCR → NER pipeline over a folder of page images
and persists the results as JSON.
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

from .models import Entity, Footnote, PageResult, PageStructure
from .ocr import perform_ocr
from .ner import perform_ner

logger = logging.getLogger(__name__)

VALID_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tiff", ".tif", ".bmp"}


# ---------------------------------------------------------------------------
# Loading previous results
# ---------------------------------------------------------------------------


def load_results_from_json(source: str | Path) -> List[PageResult]:
    """
    Load previously processed PageResult objects from JSON.

    Args:
        source: Either a combined JSON file (list of page dicts) or a
                directory containing individual ``page_NNNN.json`` files.

    Returns:
        List of PageResult objects sorted by page number.
    """
    source = Path(source)
    if source.is_file():
        logger.info("Loading combined results from %s", source)
        with open(source, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        results = [PageResult.from_dict(d) for d in data]
    elif source.is_dir():
        logger.info("Loading individual page JSONs from %s", source)
        json_files = sorted(source.glob("page_*.json"))
        results = []
        for jf in json_files:
            with open(jf, "r", encoding="utf-8") as fh:
                results.append(PageResult.from_dict(json.load(fh)))
    else:
        raise FileNotFoundError(f"No file or directory at {source}")

    results.sort(key=lambda r: r.page_number)
    logger.info("Loaded %d previous page results.", len(results))
    return results


def merge_results(*result_lists: List[PageResult]) -> List[PageResult]:
    """
    Merge multiple lists of PageResult, keeping the latest version if a
    page number appears more than once, then sort by page number.
    """
    by_page: Dict[int, PageResult] = {}
    for result_list in result_lists:
        for r in result_list:
            by_page[r.page_number] = r  # later lists overwrite earlier
    merged = sorted(by_page.values(), key=lambda r: r.page_number)
    logger.info("Merged result: %d unique pages.", len(merged))
    return merged


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


def _build_ocr_text(ocr_result: dict) -> str:
    """Flatten content_blocks into a single string for NER."""
    parts: List[str] = []
    if ocr_result.get("header"):
        parts.append(ocr_result["header"])
    for block in ocr_result.get("content_blocks", []):
        content = block.get("content", "")
        block_type = block.get("block_type", "paragraph")
        if block_type == "table":
            for row in content.get("cells", []):
                parts.extend(cell for cell in row if cell)
        elif isinstance(content, list):
            parts.extend(content)
        elif isinstance(content, str):
            parts.append(content)
    for fn in ocr_result.get("footnotes", []):
        parts.append(fn.get("text", ""))
    return "\n\n".join(parts)


def _build_page_structure(ocr_result: dict) -> PageStructure:
    """Convert the raw OCR dict into a typed PageStructure."""
    footnotes = [
        Footnote(marker=fn.get("marker", ""), text=fn.get("text", ""))
        for fn in ocr_result.get("footnotes", [])
    ]
    return PageStructure(
        page_number_printed=ocr_result.get("page_number_printed"),
        header=ocr_result.get("header"),
        content_blocks=ocr_result.get("content_blocks", []),
        footnotes=footnotes,
    )


# ---------------------------------------------------------------------------
# Single-page processor
# ---------------------------------------------------------------------------


def process_page(
    client: genai.Client,
    image_path: str | Path,
    page_number: int,
    entity_types: dict,
    model_id: str,
    thinking_level: str = "high",
) -> PageResult:
    """
    Run the full OCR → NER pipeline for one page.

    Returns:
        A populated PageResult object.
    """
    image_path = Path(image_path)
    logger.info("Processing page %d: %s", page_number, image_path.name)

    # Stage 1 – OCR
    logger.info("  Stage 1: OCR…")
    ocr_result = perform_ocr(client, image_path, model_id, thinking_level)
    ocr_text = _build_ocr_text(ocr_result)
    structure = _build_page_structure(ocr_result)
    logger.info(
        "  OCR complete: %d chars, %d blocks, %d footnotes",
        len(ocr_text),
        len(structure.content_blocks),
        len(structure.footnotes),
    )

    # Stage 2 – NER
    logger.info("  Stage 2: NER…")
    entities: List[Entity] = perform_ner(
        client, ocr_text, entity_types, model_id, thinking_level
    )
    logger.info("  NER complete: %d entities", len(entities))

    return PageResult(
        page_number=page_number,
        image_filename=image_path.name,
        structure=structure,
        ocr_text=ocr_text,
        entities=entities,
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
    thinking_level: str = "high",
    start_page: Optional[int] = None,
    end_page: Optional[int] = None,
) -> List[PageResult]:
    """
    Process all pages in *image_folder* through the OCR → NER pipeline.

    Args:
        client:        Authenticated google.genai.Client instance.
        image_folder:  Folder containing page images.
        output_folder: Root output directory (json/ subdir will be created).
        entity_types:  Dict mapping entity type name → German definition.
        model_id:      Gemini model identifier.
        thinking_level: Gemini thinking level.
        start_page:    0-based start index (inclusive). None = start from 0.
        end_page:      0-based end index (exclusive). None = all pages.

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

    # Apply slice
    subset = image_files[start_page:end_page]
    logger.info("Processing %d pages (slice %s:%s)…", len(subset), start_page, end_page)

    results: List[PageResult] = []

    for idx, image_path in enumerate(tqdm(subset, desc="Pages", unit="pg")):
        page_num = extract_page_number(image_path.name) or (idx + 1)
        try:
            result = process_page(
                client, image_path, page_num, entity_types, model_id, thinking_level
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

    logger.info(
        "Done. Pages: %d | Entities: %d",
        len(results),
        sum(len(r.entities) for r in results),
    )
    return results

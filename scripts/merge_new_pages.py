#!/usr/bin/env python3
"""
CLI: Merge newly processed pages into the existing V1 Digital Edition.

Loads page results from JSON, geocodes Location entities, renders V1-styled
page articles, and injects them into Digital_Edition_V1.html.

Usage:
    python scripts/merge_new_pages.py \
        --json output/digital_edition_complete.json \
        --v1 Digital_Edition_V1.html \
        --images /path/to/images/ \
        --out /path/to/Digital_Edition_Complete.html

Geocoding uses OpenStreetMap Nominatim (free, no API key required).
"""

import argparse
import json
import logging
import sys
from pathlib import Path

# Allow running from repo root without installing
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.models import PageResult
from src.geocoding import geocode_entities, build_page_map_data
from src.v1_renderer import render_v1_page
from src.v1_merger import merge_into_v1

logger = logging.getLogger(__name__)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    parser = argparse.ArgumentParser(
        description="Merge new pages into the V1 Digital Edition."
    )
    parser.add_argument(
        "--json", required=True,
        help="Path to digital_edition_complete.json (or a folder of page_NNNN.json files)",
    )
    parser.add_argument(
        "--v1", required=True,
        help="Path to the existing Digital_Edition_V1.html",
    )
    parser.add_argument(
        "--out", default=None,
        help="Output path for the merged HTML (default: digital_edition_complete.html next to --v1)",
    )
    parser.add_argument(
        "--images", default=None,
        help="Folder containing facsimile images. Images are referenced via "
             "relative or absolute path in the HTML.",
    )
    parser.add_argument(
        "--image-prefix", default=None,
        help="URL or path prefix for facsimile images (e.g. 'images/' or "
             "'https://...'). If not set, computed from --images relative to --out.",
    )
    parser.add_argument(
        "--start-page", type=int, default=None,
        help="Only include pages >= this number (inclusive).",
    )
    parser.add_argument(
        "--geocode-delay", type=float, default=1.0,
        help="Seconds between Nominatim requests (default: 1.0, respect rate limit).",
    )
    parser.add_argument(
        "--geocode-cache", default=None,
        help="Path to geocode cache JSON file (loaded/saved for reuse).",
    )
    parser.add_argument(
        "--skip-geocoding", action="store_true",
        help="Skip geocoding entirely (no maps will be generated).",
    )
    args = parser.parse_args()

    # --- Load page results ---
    json_path = Path(args.json)
    if json_path.is_file():
        logger.info("Loading results from %s", json_path)
        with open(json_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        results = [PageResult.from_dict(d) for d in data]
    elif json_path.is_dir():
        logger.info("Loading page JSONs from %s", json_path)
        results = []
        for jf in sorted(json_path.glob("page_*.json")):
            with open(jf, "r", encoding="utf-8") as fh:
                results.append(PageResult.from_dict(json.load(fh)))
    else:
        print(f"Error: {json_path} not found.")
        sys.exit(1)

    results.sort(key=lambda r: r.page_number)
    logger.info("Loaded %d page results.", len(results))

    # --- Filter by start page ---
    if args.start_page is not None:
        results = [r for r in results if r.page_number >= args.start_page]
        logger.info("After filtering (>= page %d): %d pages.", args.start_page, len(results))

    if not results:
        print("No pages to merge.")
        sys.exit(0)

    # --- Build image filename → path mapping ---
    image_map: dict[str, str] = {}
    if args.images:
        image_folder = Path(args.images)
        out_path = Path(args.out) if args.out else Path(args.v1).parent / "digital_edition_complete.html"

        if args.image_prefix:
            prefix = args.image_prefix.rstrip("/")
        else:
            # Compute relative path from output HTML to image folder
            try:
                prefix = str(image_folder.resolve().relative_to(out_path.resolve().parent))
            except ValueError:
                # Not relative — use absolute path
                prefix = str(image_folder.resolve())

        # Map each image filename to its full src path
        for img in image_folder.iterdir():
            if img.suffix.lower() in {".jpg", ".jpeg", ".png", ".tiff", ".tif", ".bmp"}:
                image_map[img.name] = f"{prefix}/{img.name}"

        logger.info("Mapped %d images with prefix: %s", len(image_map), prefix)

    # --- Geocoding ---
    geo_cache: dict[str, dict | None] = {}
    page_map_data: dict[int, dict] = {}

    if args.geocode_cache:
        cache_path = Path(args.geocode_cache)
        if cache_path.exists():
            with open(cache_path, "r", encoding="utf-8") as fh:
                geo_cache = json.load(fh)
            logger.info("Loaded geocode cache: %d entries.", len(geo_cache))

    if not args.skip_geocoding:
        # Collect all Location entities across all pages
        all_entities = []
        for r in results:
            all_entities.extend(r.entities)

        logger.info("Geocoding location entities…")
        geo_cache = geocode_entities(
            all_entities, cache=geo_cache, delay=args.geocode_delay
        )

        # Build per-page map data
        for r in results:
            md = build_page_map_data(r.page_number, r.entities, geo_cache)
            if md:
                page_map_data[r.page_number] = md

        logger.info("Map data generated for %d pages.", len(page_map_data))

        # Save geocode cache
        if args.geocode_cache:
            with open(args.geocode_cache, "w", encoding="utf-8") as fh:
                json.dump(geo_cache, fh, ensure_ascii=False, indent=2)
            logger.info("Saved geocode cache: %d entries.", len(geo_cache))

    # --- Render page articles ---
    logger.info("Rendering %d V1-styled page articles…", len(results))
    articles: list[str] = []
    for r in results:
        img_src = image_map.get(r.image_filename)
        md = page_map_data.get(r.page_number)
        article = render_v1_page(
            result=r,
            map_data=md,
            image_src=img_src,
        )
        articles.append(article)

    # --- Merge into V1 HTML ---
    output = merge_into_v1(
        v1_html_path=args.v1,
        new_page_articles=articles,
        new_map_data=page_map_data if page_map_data else None,
        output_path=args.out,
    )

    total_entities = sum(len(r.entities) for r in results)
    print(f"\nMerged {len(results)} pages ({total_entities} entities) into V1 edition.")
    print(f"Output: {output}")
    if page_map_data:
        print(f"Maps: {len(page_map_data)} pages with geocoded locations.")


if __name__ == "__main__":
    main()

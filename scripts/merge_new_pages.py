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
from src.tei_generator import build_tei_data

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
        help="Folder containing facsimile images (on mounted Google Drive).",
    )
    parser.add_argument(
        "--image-prefix", default=None,
        help="URL or path prefix for facsimile images (fallback when Drive "
             "file IDs cannot be resolved).",
    )
    parser.add_argument(
        "--image-manifest", default=None,
        help="Path to a JSON file mapping image filename → Drive file ID. "
             "If provided, skips Drive file ID resolution.",
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
    parser.add_argument(
        "--skip-tei", action="store_true",
        help="Skip TEI XML generation for new pages.",
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

    # --- Resolve image file IDs ---
    drive_file_ids: dict[str, str] = {}  # filename → Drive file ID
    image_map: dict[str, str] = {}       # filename → path/URL fallback

    if args.image_manifest:
        # Load pre-built manifest
        manifest_path = Path(args.image_manifest)
        if manifest_path.exists():
            with open(manifest_path, "r", encoding="utf-8") as fh:
                drive_file_ids = json.load(fh)
            logger.info("Loaded image manifest: %d entries.", len(drive_file_ids))

    if not drive_file_ids and args.images:
        # Try to resolve Drive file IDs automatically (Colab only)
        try:
            from src.drive_utils import get_drive_file_ids, save_image_manifest
            drive_file_ids = get_drive_file_ids(args.images)
            if drive_file_ids and args.image_manifest:
                save_image_manifest(drive_file_ids, args.image_manifest)
        except Exception as exc:
            logger.info("Drive file ID resolution not available: %s", exc)

    if not drive_file_ids and args.images:
        # Fallback: use path-based image references
        image_folder = Path(args.images)
        out_path = Path(args.out) if args.out else Path(args.v1).parent / "digital_edition_complete.html"

        if args.image_prefix:
            prefix = args.image_prefix.rstrip("/")
        else:
            try:
                prefix = str(image_folder.resolve().relative_to(out_path.resolve().parent))
            except ValueError:
                prefix = str(image_folder.resolve())

        for img in image_folder.iterdir():
            if img.suffix.lower() in {".jpg", ".jpeg", ".png", ".tiff", ".tif", ".bmp"}:
                image_map[img.name] = f"{prefix}/{img.name}"
        logger.info("Mapped %d images with path prefix: %s", len(image_map), prefix)

    # Build page-number → file ID manifest for the merger
    page_image_manifest: dict[str, str] = {}
    if drive_file_ids:
        for r in results:
            fid = drive_file_ids.get(r.image_filename)
            if fid:
                page_image_manifest[str(r.page_number)] = fid
        logger.info("Built page image manifest: %d entries.", len(page_image_manifest))

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
        all_entities = []
        for r in results:
            all_entities.extend(r.entities)

        logger.info("Geocoding location entities…")
        geo_cache = geocode_entities(
            all_entities, cache=geo_cache, delay=args.geocode_delay
        )

        for r in results:
            md = build_page_map_data(r.page_number, r.entities, geo_cache)
            if md:
                page_map_data[r.page_number] = md

        logger.info("Map data generated for %d pages.", len(page_map_data))

        if args.geocode_cache:
            with open(args.geocode_cache, "w", encoding="utf-8") as fh:
                json.dump(geo_cache, fh, ensure_ascii=False, indent=2)
            logger.info("Saved geocode cache: %d entries.", len(geo_cache))

    # --- TEI data ---
    tei_data = None
    if not args.skip_tei:
        logger.info("Generating TEI data for %d pages…", len(results))
        tei_data = build_tei_data(results)
        logger.info("TEI generated: %d pages.", len(tei_data["pages"]))

    # --- Render page articles ---
    logger.info("Rendering %d V1-styled page articles…", len(results))
    articles: list[str] = []
    for r in results:
        # Prefer Drive file ID; fall back to path-based image src
        fid = drive_file_ids.get(r.image_filename)
        img_src = image_map.get(r.image_filename) if not fid else None
        md = page_map_data.get(r.page_number)
        article = render_v1_page(
            result=r,
            map_data=md,
            drive_file_id=fid,
            image_src=img_src,
        )
        articles.append(article)

    # --- Merge into V1 HTML ---
    output = merge_into_v1(
        v1_html_path=args.v1,
        new_page_articles=articles,
        new_map_data=page_map_data if page_map_data else None,
        new_image_manifest=page_image_manifest if page_image_manifest else None,
        new_tei_data=tei_data,
        output_path=args.out,
    )

    total_entities = sum(len(r.entities) for r in results)
    print(f"\nMerged {len(results)} pages ({total_entities} entities) into V1 edition.")
    print(f"Output: {output}")
    if page_map_data:
        print(f"Maps: {len(page_map_data)} pages with geocoded locations.")
    if page_image_manifest:
        print(f"Images: {len(page_image_manifest)} Drive file IDs resolved.")
    elif image_map:
        print(f"Images: {len(image_map)} path-based references (download images folder with HTML).")


if __name__ == "__main__":
    main()

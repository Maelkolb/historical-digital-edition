#!/usr/bin/env python3
"""
CLI: Run the OCR → NER pipeline and generate the HTML digital edition.

Usage:
    python scripts/process_book.py [--images images/] [--out output/] [--start 0] [--end 10]

Requires GEMINI_API_KEY in environment or .env file.
"""

import argparse
import logging
import os
import sys
from pathlib import Path

# Allow running from repo root without installing
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Load .env if present
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from google import genai
from src import config, process_book, generate_html_edition, find_incomplete_pages, reprocess_pages


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    parser = argparse.ArgumentParser(
        description="Run the OCR → NER pipeline and generate an HTML digital edition."
    )
    parser.add_argument(
        "--images", default=str(config.IMAGE_FOLDER),
        help="Folder containing page images",
    )
    parser.add_argument(
        "--out", default=str(config.OUTPUT_FOLDER),
        help="Output folder (json/ and digital_edition.html will be created here)",
    )
    parser.add_argument(
        "--start", type=int, default=None,
        help="0-based start index (inclusive). Default: 0",
    )
    parser.add_argument(
        "--end", type=int, default=None,
        help="0-based end index (exclusive). Default: all pages",
    )
    parser.add_argument(
        "--model", default=config.MODEL_ID,
        help=f"Gemini model ID (default: {config.MODEL_ID})",
    )
    parser.add_argument(
        "--thinking", default=config.THINKING_LEVEL,
        choices=["none", "low", "medium", "high"],
        help="Thinking level for the model",
    )
    parser.add_argument(
        "--embed-images", action="store_true",
        help="Embed facsimile images in the HTML (makes file larger)",
    )
    parser.add_argument(
        "--image-ref-prefix", default=None,
        help="Reference images via this path prefix instead of embedding "
             "(e.g. 'images/' or a URL). Mutually exclusive with --embed-images.",
    )
    parser.add_argument(
        "--title", default="Historische Digitalausgabe",
        help="Title shown in the HTML edition",
    )
    parser.add_argument(
        "--retry-incomplete", action="store_true",
        help="Auto-detect and re-process pages with empty/minimal OCR output",
    )
    parser.add_argument(
        "--pages", type=str, default=None,
        help="Comma-separated page numbers to re-process (e.g. '551,563,580')",
    )
    parser.add_argument(
        "--min-ocr-chars", type=int, default=50,
        help="Minimum OCR characters to consider a page complete (default: 50)",
    )
    args = parser.parse_args()

    api_key = os.environ.get("GEMINI_API_KEY") or config.GEMINI_API_KEY
    if not api_key:
        print("❌  GEMINI_API_KEY not set. Add it to your environment or .env file.")
        sys.exit(1)

    client = genai.Client(api_key=api_key)
    print(f"✅  Gemini client ready – model: {args.model}")

    # Determine which pages to (re-)process
    page_numbers: list[int] | None = None

    if args.retry_incomplete:
        json_folder = Path(args.out) / "json"
        if not json_folder.is_dir():
            print(f"❌  No json/ folder found at {json_folder}. Run the full pipeline first.")
            sys.exit(1)
        page_numbers = find_incomplete_pages(json_folder, min_ocr_chars=args.min_ocr_chars)
        if not page_numbers:
            print("✅  All existing pages look complete – nothing to retry.")
            sys.exit(0)
        print(f"🔄  Found {len(page_numbers)} incomplete pages: {page_numbers}")

    if args.pages:
        explicit = [int(p.strip()) for p in args.pages.split(",") if p.strip()]
        if page_numbers is not None:
            # Combine with auto-detected incomplete pages
            page_numbers = sorted(set(page_numbers) | set(explicit))
        else:
            page_numbers = sorted(explicit)
        print(f"🔄  Will re-process pages: {page_numbers}")

    if page_numbers is not None:
        results = reprocess_pages(
            client=client,
            image_folder=args.images,
            output_folder=args.out,
            entity_types=config.ENTITY_TYPES,
            page_numbers=page_numbers,
            model_id=args.model,
            thinking_level=args.thinking,
        )
    else:
        results = process_book(
            client=client,
            image_folder=args.images,
            output_folder=args.out,
            entity_types=config.ENTITY_TYPES,
            model_id=args.model,
            thinking_level=args.thinking,
            start_page=args.start,
            end_page=args.end,
        )

    if results:
        html_path = generate_html_edition(
            results=results,
            output_path=Path(args.out) / "digital_edition.html",
            title=args.title,
            entity_colors=config.ENTITY_COLORS,
            entity_labels=config.ENTITY_LABELS,
            image_folder=args.images if args.embed_images else None,
            image_ref_prefix=args.image_ref_prefix,
        )
        print(f"\n📖  Digital edition: {html_path}")

    total_ents = sum(len(r.entities) for r in results)
    print(f"🏷   Total entities annotated: {total_ents}")
    print(f"📄  Pages processed: {len(results)}")


if __name__ == "__main__":
    main()

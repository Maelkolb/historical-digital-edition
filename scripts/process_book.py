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
from src import config, process_book, generate_html_edition


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
        "--title", default="Historische Digitalausgabe",
        help="Title shown in the HTML edition",
    )
    args = parser.parse_args()

    api_key = os.environ.get("GEMINI_API_KEY") or config.GEMINI_API_KEY
    if not api_key:
        print("❌  GEMINI_API_KEY not set. Add it to your environment or .env file.")
        sys.exit(1)

    client = genai.Client(api_key=api_key)
    print(f"✅  Gemini client ready – model: {args.model}")

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
        )
        print(f"\n📖  Digital edition: {html_path}")

    total_ents = sum(len(r.entities) for r in results)
    print(f"🏷   Total entities annotated: {total_ents}")
    print(f"📄  Pages processed: {len(results)}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Build an image manifest mapping filenames to Google Drive file IDs.

Run this in Google Colab BEFORE merge_new_pages.py to enable
portable facsimile images that work even when the HTML is downloaded.

Usage (in Colab):
    from google.colab import auth
    auth.authenticate_user()

    !python scripts/build_image_manifest.py \
        --folder "/content/drive/MyDrive/Thuringia_digital_edition_output/images" \
        --out "/content/drive/MyDrive/Thuringia_digital_edition_output/image_manifest.json"
"""

import argparse
import json
import sys
from pathlib import Path


def get_drive_folder_id(service, folder_path: str) -> str:
    """Navigate Drive folder hierarchy to get folder ID."""
    # /content/drive/MyDrive/path/to/folder → path/to/folder
    if "/MyDrive/" in folder_path:
        relative = folder_path.split("/MyDrive/", 1)[1]
    else:
        print(f"Error: Path must be under /content/drive/MyDrive/")
        sys.exit(1)

    parent_id = "root"
    for part in relative.split("/"):
        if not part:
            continue
        query = (
            f"name='{part}' and '{parent_id}' in parents "
            f"and mimeType='application/vnd.google-apps.folder' and trashed=false"
        )
        results = service.files().list(q=query, fields="files(id, name)").execute()
        files = results.get("files", [])
        if not files:
            print(f"Error: Folder '{part}' not found in Drive.")
            sys.exit(1)
        parent_id = files[0]["id"]
        print(f"  📁 {part} → {parent_id}")

    return parent_id


def list_files_in_folder(service, folder_id: str) -> dict:
    """List all files in a Drive folder, returning name → ID mapping."""
    file_ids = {}
    page_token = None

    while True:
        query = f"'{folder_id}' in parents and trashed=false"
        results = service.files().list(
            q=query,
            fields="nextPageToken, files(id, name)",
            pageSize=1000,
            pageToken=page_token,
        ).execute()

        for f in results.get("files", []):
            file_ids[f["name"]] = f["id"]

        page_token = results.get("nextPageToken")
        if not page_token:
            break

    return file_ids


def main():
    parser = argparse.ArgumentParser(
        description="Build image manifest with Google Drive file IDs."
    )
    parser.add_argument(
        "--folder", required=True,
        help="Path to the image folder on mounted Google Drive",
    )
    parser.add_argument(
        "--out", required=True,
        help="Output path for the manifest JSON file",
    )
    args = parser.parse_args()

    # Import and build Drive service (requires prior auth.authenticate_user())
    try:
        from googleapiclient.discovery import build
        service = build("drive", "v3")
    except Exception as exc:
        print(f"Error: Could not create Drive API client: {exc}")
        print("\nMake sure you run this in Colab and authenticate first:")
        print("  from google.colab import auth")
        print("  auth.authenticate_user()")
        sys.exit(1)

    print(f"🔍 Navigating to folder: {args.folder}")
    folder_id = get_drive_folder_id(service, args.folder)
    print(f"✅ Folder ID: {folder_id}")

    print("📋 Listing files...")
    file_ids = list_files_in_folder(service, folder_id)
    print(f"✅ Found {len(file_ids)} files.")

    # Save manifest
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(file_ids, fh, ensure_ascii=False, indent=2)

    print(f"💾 Saved manifest: {out_path}")
    print(f"\nNow use --image-manifest {args.out} with merge_new_pages.py")


if __name__ == "__main__":
    main()

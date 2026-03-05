"""
Google Drive Utilities
======================
Helpers for resolving Google Drive file IDs from mounted Drive paths
in Google Colab. Falls back gracefully when not running in Colab.
"""

import json
import logging
import os
import re
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)


def get_drive_file_ids(
    folder_path: str | Path,
    extensions: Optional[set] = None,
) -> Dict[str, str]:
    """
    Get Google Drive file IDs for all files in a Drive-mounted folder.

    Uses the ``xattr`` command to read the ``user.drive.id`` extended
    attribute that Google Drive FUSE sets on mounted files in Colab.

    Args:
        folder_path: Path to a folder on mounted Google Drive
                     (e.g. ``/content/drive/MyDrive/images``).
        extensions:  Set of file extensions to include (e.g. ``{'.jpg', '.png'}``).
                     If *None*, includes all files.

    Returns:
        Dict mapping filename → Google Drive file ID.
        Empty dict if not running in Colab or xattr fails.
    """
    folder = Path(folder_path)
    if not folder.is_dir():
        logger.warning("Folder not found: %s", folder)
        return {}

    if extensions is None:
        extensions = {".jpg", ".jpeg", ".png", ".tiff", ".tif", ".bmp"}

    file_ids: Dict[str, str] = {}

    try:
        import subprocess
        for f in sorted(folder.iterdir()):
            if f.suffix.lower() not in extensions:
                continue
            try:
                result = subprocess.run(
                    ["xattr", "-p", "user.drive.id", str(f)],
                    capture_output=True, text=True, timeout=5,
                )
                if result.returncode == 0 and result.stdout.strip():
                    file_ids[f.name] = result.stdout.strip()
            except (subprocess.TimeoutExpired, FileNotFoundError):
                continue

        if file_ids:
            logger.info("Resolved %d Drive file IDs via xattr.", len(file_ids))
            return file_ids

    except Exception as exc:
        logger.debug("xattr approach failed: %s", exc)

    # Fallback: try Google Drive API (available in Colab)
    try:
        file_ids = _get_ids_via_drive_api(folder)
        if file_ids:
            logger.info("Resolved %d Drive file IDs via Drive API.", len(file_ids))
            return file_ids
    except Exception as exc:
        logger.debug("Drive API approach failed: %s", exc)

    logger.warning(
        "Could not resolve Drive file IDs. Images will use path-based references."
    )
    return {}


def _get_ids_via_drive_api(folder: Path) -> Dict[str, str]:
    """Try to get file IDs using the Google Drive API in Colab."""
    from google.colab import auth
    from googleapiclient.discovery import build

    auth.authenticate_user()
    service = build("drive", "v3")

    # Find the folder ID by traversing the path
    # /content/drive/MyDrive/path/to/folder -> path/to/folder
    drive_path = str(folder)
    if "/MyDrive/" in drive_path:
        relative = drive_path.split("/MyDrive/", 1)[1]
    else:
        return {}

    # Navigate to the target folder
    parent_id = "root"
    for part in relative.split("/"):
        if not part:
            continue
        query = f"name='{part}' and '{parent_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false"
        results = service.files().list(q=query, fields="files(id)").execute()
        files = results.get("files", [])
        if not files:
            return {}
        parent_id = files[0]["id"]

    # List files in the target folder
    file_ids: Dict[str, str] = {}
    page_token = None
    while True:
        query = f"'{parent_id}' in parents and trashed=false"
        results = service.files().list(
            q=query, fields="nextPageToken, files(id, name)",
            pageSize=1000, pageToken=page_token,
        ).execute()
        for f in results.get("files", []):
            file_ids[f["name"]] = f["id"]
        page_token = results.get("nextPageToken")
        if not page_token:
            break

    return file_ids


def save_image_manifest(
    file_ids: Dict[str, str],
    output_path: str | Path,
) -> None:
    """Save file ID mapping to JSON for reuse."""
    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(file_ids, fh, ensure_ascii=False, indent=2)
    logger.info("Saved image manifest: %d entries to %s", len(file_ids), output_path)


def load_image_manifest(path: str | Path) -> Dict[str, str]:
    """Load a previously saved file ID mapping."""
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    logger.info("Loaded image manifest: %d entries from %s", len(data), path)
    return data


def build_page_image_manifest(
    file_ids: Dict[str, str],
    results: list,
) -> Dict[str, str]:
    """
    Build a page-number-keyed image manifest from filename-keyed file IDs.

    Args:
        file_ids: Dict mapping image filename → Drive file ID.
        results:  List of PageResult objects.

    Returns:
        Dict mapping page number (str) → Drive file ID.
    """
    manifest: Dict[str, str] = {}
    for r in results:
        fid = file_ids.get(r.image_filename)
        if fid:
            manifest[str(r.page_number)] = fid
    logger.info("Built page image manifest: %d entries.", len(manifest))
    return manifest

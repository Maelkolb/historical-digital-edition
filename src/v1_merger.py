"""
V1 HTML Merger
==============
Injects newly processed page articles, map data, and image manifest
entries into an existing Digital_Edition_V1.html file to produce the
complete combined edition.
"""

import json
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


def _find_and_replace(html: str, marker: str, replacement: str) -> str:
    """Replace the first occurrence of *marker* with *replacement*."""
    idx = html.find(marker)
    if idx == -1:
        logger.warning("Marker not found: %s", marker[:60])
        return html
    return html[:idx] + replacement + html[idx + len(marker):]


def _merge_js_object(html: str, var_pattern: str, new_entries: Dict) -> str:
    """
    Find a JavaScript object literal (``var X = { ... };`` or
    ``const X = { ... };``) and merge *new_entries* into it.
    """
    # Match:  var pageMapData = { ... };  or  const imageManifest = { ... };
    pattern = re.compile(
        rf'({re.escape(var_pattern)}\s*=\s*)\{{(.*?)\}};',
        re.DOTALL,
    )
    match = pattern.search(html)
    if not match:
        logger.warning("JS object not found for pattern: %s", var_pattern)
        return html

    prefix = match.group(1)
    existing_body = match.group(2)

    # Parse existing entries by extracting the JSON-like content
    try:
        existing_obj = json.loads("{" + existing_body + "}")
    except json.JSONDecodeError:
        # Fallback: try to fix trailing commas etc.
        cleaned = re.sub(r',\s*}', '}', "{" + existing_body + "}")
        try:
            existing_obj = json.loads(cleaned)
        except json.JSONDecodeError:
            logger.error("Could not parse existing JS object for %s", var_pattern)
            return html

    # Merge
    for key, value in new_entries.items():
        existing_obj[str(key)] = value

    new_json = json.dumps(existing_obj, ensure_ascii=False, indent=4)
    replacement = f"{prefix}{new_json};"
    return html[:match.start()] + replacement + html[match.end():]


def merge_into_v1(
    v1_html_path: str | Path,
    new_page_articles: List[str],
    new_map_data: Optional[Dict[int, Dict]] = None,
    new_image_manifest: Optional[Dict[str, str]] = None,
    new_tei_data: Optional[Dict] = None,
    output_path: Optional[str | Path] = None,
) -> Path:
    """
    Merge new page articles into an existing V1 Digital Edition HTML.

    Args:
        v1_html_path:        Path to the existing Digital_Edition_V1.html.
        new_page_articles:   List of ``<article>`` HTML strings from
                             :func:`render_v1_page`.
        new_map_data:        Dict mapping page number → map data dict
                             (output of :func:`build_page_map_data`).
        new_image_manifest:  Dict mapping page number (str) → Google Drive
                             file ID for facsimile images.
        new_tei_data:        Dict with ``{"fullBook": str, "pages": {...}}``
                             from :func:`build_tei_data`.
        output_path:         Destination file.  Defaults to
                             ``digital_edition_complete.html`` next to the
                             V1 file.

    Returns:
        Path to the written HTML file.
    """
    v1_path = Path(v1_html_path)
    if output_path is None:
        output_path = v1_path.parent / "digital_edition_complete.html"
    output_path = Path(output_path)

    logger.info("Reading V1 edition: %s", v1_path)
    html = v1_path.read_text(encoding="utf-8")

    # 1. Insert new page articles before </div></main>
    #    The last </article> is followed by \n</div>\n</main>
    insertion_marker = "</div>\n</main>"
    articles_html = "\n".join(new_page_articles)
    new_content = articles_html + "\n" + insertion_marker
    html = _find_and_replace(html, insertion_marker, new_content)
    logger.info("Inserted %d new page articles.", len(new_page_articles))

    # 2. Add new page options to the <select> page selector
    #    Find the closing </select> in the nav bar and insert before it
    new_options = ""
    for article in new_page_articles:
        # Extract page number from data-page="N"
        m = re.search(r'data-page="(\d+)"', article)
        if m:
            pn = m.group(1)
            new_options += f'<option value="{pn}">Seite {pn}</option>'

    select_close = "</select>"
    # Find the page selector specifically (there may be other selects)
    selector_pattern = r'(<select[^>]*id="pageSelector"[^>]*>)(.*?)(</select>)'
    selector_match = re.search(selector_pattern, html, re.DOTALL)
    if selector_match:
        existing_select = selector_match.group(0)
        new_select = (
            selector_match.group(1)
            + selector_match.group(2)
            + new_options
            + selector_match.group(3)
        )
        html = html.replace(existing_select, new_select, 1)
        logger.info("Updated page selector with new options.")

    # 3. Merge pageMapData
    if new_map_data:
        str_keyed = {str(k): v for k, v in new_map_data.items() if v is not None}
        if str_keyed:
            html = _merge_js_object(html, "var pageMapData", str_keyed)
            logger.info("Merged %d map data entries.", len(str_keyed))

    # 4. Merge imageManifest
    if new_image_manifest:
        html = _merge_js_object(html, "const imageManifest", new_image_manifest)
        logger.info("Merged %d image manifest entries.", len(new_image_manifest))

    # 5. Update sidebar stats (page count and annotation count)
    # Count total pages and entities from the merged HTML
    total_pages = len(re.findall(r'class="page-article"', html))
    total_entities = len(re.findall(r'class="entity"', html))

    # Update page count
    page_stat_pattern = (
        r'(<span class="label"><span class="bilingual-de">Seiten</span>'
        r'<span class="bilingual-en">Pages</span></span>\s*'
        r'<span class="value">)\d+(?:,\d+)*(</span>)'
    )
    html = re.sub(
        page_stat_pattern,
        rf'\g<1>{total_pages:,}\2',
        html,
        count=1,
    )

    # Update annotation count
    annot_stat_pattern = (
        r'(<span class="label"><span class="bilingual-de">Annotationen</span>'
        r'<span class="bilingual-en">Annotations</span></span>\s*'
        r'<span class="value">)\d+(?:,\d+)*(</span>)'
    )
    html = re.sub(
        annot_stat_pattern,
        rf'\g<1>{total_entities:,}\2',
        html,
        count=1,
    )
    logger.info("Updated sidebar stats: %d pages, %d entities.", total_pages, total_entities)

    # 6. Merge TEI data into the embedded <script id="tei-xml-data"> block
    if new_tei_data:
        tei_script_pattern = re.compile(
            r'(<script\s+id="tei-xml-data"\s+type="application/json">)(.*?)(</script>)',
            re.DOTALL,
        )
        tei_match = tei_script_pattern.search(html)
        if tei_match:
            try:
                existing_tei = json.loads(tei_match.group(2))
            except json.JSONDecodeError:
                existing_tei = {"fullBook": None, "pages": {}}

            # Merge page TEI entries
            if "pages" not in existing_tei:
                existing_tei["pages"] = {}
            existing_tei["pages"].update(new_tei_data.get("pages", {}))

            # Update full book TEI (combine old body + new pages)
            if new_tei_data.get("fullBook"):
                existing_tei["fullBook"] = new_tei_data["fullBook"]

            new_tei_json = json.dumps(existing_tei, ensure_ascii=False)
            replacement = tei_match.group(1) + new_tei_json + tei_match.group(3)
            html = html[:tei_match.start()] + replacement + html[tei_match.end():]
            logger.info("Merged TEI data: %d pages.", len(existing_tei["pages"]))
        else:
            logger.warning("TEI data script block not found in V1 HTML.")

    # 7. Inject CSS fixes for wide tables and content overflow
    css_fixes = """
<style>
/* Fix: wide tables should scroll horizontally, not clip */
.table-wrapper { overflow-x: auto !important; overflow-y: hidden; }
/* Fix: transcription pane must contain overflow */
.transcription-pane { overflow-x: hidden; }
.transcription-body { overflow-wrap: break-word; word-wrap: break-word; }
/* Fix: content paragraphs should not exceed pane width */
.content-paragraph { overflow-wrap: break-word; word-wrap: break-word; max-width: 100%; }
</style>
"""
    # Inject before </head>
    html = _find_and_replace(html, "</head>", css_fixes + "</head>")
    logger.info("Injected CSS fixes for table/content overflow.")

    # Write output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    size_mb = output_path.stat().st_size / 1e6
    logger.info("Combined edition written: %s (%.1f MB)", output_path, size_mb)

    return output_path

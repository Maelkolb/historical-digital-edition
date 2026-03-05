"""
V1-Compatible Page Renderer
============================
Generates ``<article class="page-article">`` HTML that matches the
structure and styling of Digital_Edition_V1.html exactly, including
bilingual DE/EN labels, Leaflet map containers, GBIF links, entity
highlighting with CSS custom properties, and side-by-side facsimile.
"""

import json
import logging
from html import escape
from typing import Dict, List, Optional
from urllib.parse import quote_plus

from .models import Entity, PageResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# V1 entity colours  (must match Digital_Edition_V1.html)
# ---------------------------------------------------------------------------

V1_ENTITY_COLORS: Dict[str, str] = {
    "Animal":               "#c62828",
    "Artefact":             "#e65100",
    "Climate":              "#546e7a",
    "Environment":          "#00838f",
    "Environmental Impact": "#bf360c",
    "Location":             "#1565c0",
    "Natural Object":       "#5d4037",
    "Organisation":         "#37474f",
    "Person":               "#6a1b9a",
    "Plant":                "#2e7d32",
    "Resource":             "#f9a825",
}

# Bilingual stat labels  (German / English)
V1_STAT_LABELS: Dict[str, tuple] = {
    "Animal":               ("Tiere:", "Animals:"),
    "Artefact":             ("Artefakte:", "Artifacts:"),
    "Climate":              ("Klima:", "Climate:"),
    "Environment":          ("Umgebung:", "Environment:"),
    "Environmental Impact": ("Umwelteinflüsse:", "Env. Impacts:"),
    "Location":             ("Orte:", "Places:"),
    "Natural Object":       ("Naturobjekte:", "Natural Objects:"),
    "Organisation":         ("Organisationen:", "Organizations:"),
    "Person":               ("Personen:", "Persons:"),
    "Plant":                ("Pflanzen:", "Plants:"),
    "Resource":             ("Ressourcen:", "Resources:"),
}

GBIF_TYPES = {"Animal", "Plant"}


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------


def _bilingual(de: str, en: str) -> str:
    return (
        f'<span class="bilingual-de">{de}</span>'
        f'<span class="bilingual-en">{en}</span>'
    )


def _entity_mark(text: str, entity_type: str, context: str) -> str:
    """Render one entity as a ``<mark>`` tag matching V1 style."""
    color = V1_ENTITY_COLORS.get(entity_type, "#9e9e9e")
    safe_title = escape(f"{entity_type}: {context}", quote=True)
    mark = (
        f'<mark class="entity" data-type="{escape(entity_type)}" '
        f'style="--entity-color: {color};" '
        f'title="{safe_title}">{escape(text)}</mark>'
    )
    # Add GBIF link for Animal / Plant
    if entity_type in GBIF_TYPES:
        gbif_url = f"https://www.gbif.org/species/search?q={quote_plus(text)}"
        mark += f'<a class="gbif-link" href="{gbif_url}" target="_blank" rel="noopener">🔗</a>'
    return mark


def _annotate_text(text: str, entities: List[Entity]) -> str:
    """Insert entity ``<mark>`` tags into *text*, skipping overlaps."""
    if not entities:
        return escape(text).replace("\n", "<br>")

    sorted_ents = sorted(entities, key=lambda e: e.start_char)
    parts: List[str] = []
    cursor = 0

    for ent in sorted_ents:
        if ent.start_char < cursor:
            continue
        if ent.start_char > cursor:
            parts.append(escape(text[cursor:ent.start_char]).replace("\n", "<br>"))
        parts.append(_entity_mark(ent.text, ent.entity_type, ent.context or ""))
        cursor = ent.end_char

    if cursor < len(text):
        parts.append(escape(text[cursor:]).replace("\n", "<br>"))

    return "".join(parts)


def _render_table(table_dict: dict) -> str:
    rows: List[str] = []
    for i, row in enumerate(table_dict.get("cells", [])):
        tag = "th" if i == 0 else "td"
        cells = "".join(f"<{tag}>{escape(str(c))}</{tag}>" for c in row)
        rows.append(f"<tr>{cells}</tr>")
    caption = table_dict.get("caption", "")
    cap_html = f'<div class="table-caption">{escape(caption)}</div>' if caption else ""
    csv_btn = (
        '<button class="csv-download-btn" onclick="downloadTableAsCSV(this)" '
        'data-title-de="Als CSV herunterladen" data-title-en="Download as CSV">'
        '\U0001f4e5 CSV</button>'
    )
    return (
        f'<div class="table-wrapper">'
        f'{csv_btn}{cap_html}'
        f'<table class="content-table">{"".join(rows)}</table>'
        f'</div>'
    )


# ---------------------------------------------------------------------------
# Main page renderer
# ---------------------------------------------------------------------------


def render_v1_page(
    result: PageResult,
    map_data: Optional[Dict] = None,
    drive_file_id: Optional[str] = None,
    image_src: Optional[str] = None,
) -> str:
    """
    Render a single :class:`PageResult` as a V1-compatible
    ``<article class="page-article">`` HTML string.

    Args:
        result:        The processed page.
        map_data:      Output of :func:`build_page_map_data` for this page,
                       or *None* if no geocoded locations.
        drive_file_id: Google Drive file ID for the facsimile image, or
                       *None* for a "missing" placeholder.
        image_src:     Direct image URL/path for the facsimile. Takes
                       precedence over *drive_file_id* when set.

    Returns:
        HTML string for the page article.
    """
    pn = result.page_number

    # --- Block info ---
    block_counts: Dict[str, int] = {}
    for block in result.structure.content_blocks:
        bt = block.get("block_type", "paragraph")
        block_counts[bt] = block_counts.get(bt, 0) + 1
    block_info = " | ".join(f"{k}: {v}" for k, v in sorted(block_counts.items()))

    # --- Entity stats ---
    etype_counts: Dict[str, int] = {}
    for e in result.entities:
        etype_counts[e.entity_type] = etype_counts.get(e.entity_type, 0) + 1

    stat_spans = []
    for etype, count in sorted(etype_counts.items(), key=lambda x: -x[1]):
        color = V1_ENTITY_COLORS.get(etype, "#555")
        de_label, en_label = V1_STAT_LABELS.get(etype, (etype + ":", etype + ":"))
        stat_spans.append(
            f'<span class="page-stat" style="--stat-color: {color}">'
            f'{_bilingual(de_label, en_label)} {count}</span>'
        )

    # Map toggle button
    loc_count = etype_counts.get("Location", 0)
    map_btn = ""
    if map_data and loc_count > 0:
        map_btn = (
            f'<button class="map-toggle-btn-v3" id="map-btn-{pn}" '
            f'onclick="toggleMapV3({pn})" title="{loc_count} Orte auf dieser Seite">'
            f'{_bilingual("📍 Karte öffnen", "📍 Open Map")}</button>'
        )

    # TEI export button
    tei_btn = (
        f'<button class="tei-export-btn tei-export-btn-page" '
        f'onclick=\'exportPageTei("{pn}")\' title="Download TEI XML for page {pn}">'
        f'{_bilingual("📄 TEI", "📄 TEI")}</button>'
    )

    stats_html = (
        f'<div class="page-stats">'
        f'{"".join(stat_spans)}'
        f'{map_btn}{tei_btn}'
        f'</div>'
    )

    # --- Map container ---
    map_container = ""
    if map_data:
        loc_total = map_data["count"]
        map_container = (
            f'<div class="embedded-map-container" id="map-container-{pn}">'
            f'<div class="map-header">'
            f'<h4>{_bilingual(f"Seite {pn}", f"Page {pn}")}</h4>'
            f'<small>{_bilingual(f"{loc_total} Orte", f"{loc_total} Places")}</small>'
            f'</div>'
            f'<button class="map-close-btn" onclick="closeMapV3({pn})" '
            f'data-title-de="Karte schließen" data-title-en="Close map" '
            f'title="Karte schließen">×</button>'
            f'<div class="embedded-map" id="map-{pn}"></div>'
            f'</div>'
        )

    # --- Transcription body ---
    body_parts: List[str] = []
    for block in result.structure.content_blocks:
        btype = block.get("block_type", "paragraph")
        content = block.get("content", "")

        if btype == "heading":
            body_parts.append(
                f'<h3 class="content-heading">{escape(content or "")}</h3>'
            )
        elif btype == "paragraph":
            annotated = _annotate_text(content or "", result.entities)
            body_parts.append(f'<p class="content-paragraph">{annotated}</p>')
        elif btype == "table":
            body_parts.append(_render_table(content))
        elif btype == "list":
            if isinstance(content, list):
                items = "".join(f"<li>{escape(item)}</li>" for item in content)
                body_parts.append(f"<ul>{items}</ul>")

    # --- Footnotes ---
    fn_html = ""
    if result.structure.footnotes:
        fn_items = []
        for fn in result.structure.footnotes:
            fn_text = _annotate_text(fn.text or "", result.entities)
            fn_items.append(
                f'<div class="footnote">'
                f'<span class="fn-marker">{escape(fn.marker or "")}</span>'
                f'<span class="fn-text">{fn_text}</span></div>'
            )
        fn_html = (
            f'<div class="footnotes-section">'
            f'<div class="footnotes-divider"></div>'
            f'{"".join(fn_items)}</div>'
        )

    # --- Running header ---
    header_text = escape(result.structure.header or "")
    running_header = f'<div class="running-header">{header_text}</div>'

    # --- Facsimile pane ---
    has_image = image_src or drive_file_id
    if has_image:
        # Direct src (image_src) takes precedence; Drive images use
        # lazy-loading via imageManifest JS (src="" initially).
        img_url = escape(image_src, quote=True) if image_src else ""
        loaded = "true" if image_src else "false"
        opacity = "1" if image_src else "0"
        facs_inner = (
            f'<div class="facsimile-container">'
            f'<div class="facsimile-label">'
            f'{_bilingual("ORIGINALFAKSIMILE", "ORIGINAL FACSIMILE")}</div>'
            f'<div class="facsimile-viewer" onclick="this.classList.toggle(\'zoomed\')">'
            f'<img alt="Seite {pn}" data-loaded="{loaded}" id="facsimile-img-{pn}" '
            f'src="{img_url}" style="opacity:{opacity}; transition: opacity 0.5s;"/>'
            f'</div>'
            f'<div class="zoom-hint">'
            f'{_bilingual("Klicken zum Vergrößern", "Click to zoom")}</div>'
            f'</div>'
        )
    else:
        facs_inner = (
            f'<div class="facsimile-missing">'
            f'{_bilingual("Faksimile nicht verfügbar", "Facsimile not available")}'
            f'</div>'
        )

    # --- Assemble article ---
    article = (
        f'<article class="page-article" data-page="{pn}" id="page-{pn}">\n'
        f'<header class="page-header">\n'
        f'<div class="page-number-badge">{_bilingual(f"Seite {pn}", f"Page {pn}")}</div>\n'
        f'<div class="page-filename">{escape(result.image_filename)}</div>\n'
        f'<div class="block-info">{block_info}</div>\n'
        f'{stats_html}\n'
        f'</header>\n'
        f'{map_container}\n'
        f'<div class="page-content-grid">\n'
        f'<section class="transcription-pane">\n'
        f'{running_header}\n'
        f'<div class="transcription-body">\n'
        f'{"".join(body_parts)}\n'
        f'</div>\n'
        f'{fn_html}\n'
        f'</section>\n'
        f'<aside class="facsimile-pane">\n'
        f'{facs_inner}\n'
        f'</aside>\n'
        f'</div>\n'
        f'</article>'
    )

    return article

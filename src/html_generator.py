"""
HTML Generator
==============
Renders processed PageResult objects into an interactive single-file
HTML digital edition with entity highlighting, facsimile toggle, and
keyboard navigation.
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

from .models import Entity, PageResult
from .ocr import load_image_as_base64

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Low-level renderers
# ---------------------------------------------------------------------------


def render_entity_span(text: str, entity_type: str, context: str, color: str) -> str:
    safe_ctx = (context or "").replace('"', "&quot;")
    return (
        f'<span class="entity" data-type="{entity_type}" '
        f'style="background:{color}20;border-bottom:2px solid {color};" '
        f'title="{entity_type}: {safe_ctx}">{text}</span>'
    )


def render_annotated_text(text: str, entities: List[Entity], entity_colors: dict) -> str:
    """Return HTML string with non-overlapping entity spans inserted."""
    if not entities:
        return text.replace("\n", "<br>")

    sorted_ents = sorted(entities, key=lambda e: e.start_char)
    parts: List[str] = []
    cursor = 0

    for ent in sorted_ents:
        if ent.start_char < cursor:
            continue  # skip overlapping
        if ent.start_char > cursor:
            parts.append(text[cursor : ent.start_char].replace("\n", "<br>"))
        color = entity_colors.get(ent.entity_type, "#9e9e9e")
        parts.append(
            render_entity_span(ent.text, ent.entity_type, ent.context or "", color)
        )
        cursor = ent.end_char

    if cursor < len(text):
        parts.append(text[cursor:].replace("\n", "<br>"))

    return "".join(parts)


def render_table_html(table_dict: dict) -> str:
    rows_html: List[str] = []
    for row_idx, row in enumerate(table_dict.get("cells", [])):
        tag = "th" if row_idx == 0 else "td"
        cells = "".join(f"<{tag}>{cell}</{tag}>" for cell in row)
        rows_html.append(f"<tr>{cells}</tr>")

    caption = table_dict.get("caption", "")
    caption_html = f'<caption class="table-caption">{caption}</caption>' if caption else ""
    return (
        f'<div class="table-wrapper">'
        f'<table class="page-table">{caption_html}{"".join(rows_html)}</table>'
        f"</div>"
    )


def render_content_blocks(
    content_blocks: List[dict],
    entities: List[Entity],
    entity_colors: dict,
) -> str:
    """Render content_blocks in order, annotating text blocks with NER spans."""
    parts: List[str] = []
    for block in content_blocks:
        btype = block.get("block_type", "paragraph")
        content = block.get("content", "")

        if btype == "paragraph":
            annotated = render_annotated_text(content, entities, entity_colors)
            parts.append(f'<p class="body-paragraph">{annotated}</p>')
        elif btype == "heading":
            parts.append(f'<h3 class="section-heading">{content}</h3>')
        elif btype == "table":
            parts.append(render_table_html(content))
        elif btype == "list":
            if isinstance(content, list):
                items = "".join(f"<li>{item}</li>" for item in content)
                parts.append(f'<ul class="body-list">{items}</ul>')
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Full-edition generator
# ---------------------------------------------------------------------------

_CSS = """
:root {
    --bg: #faf8f5; --bg2: #f5f2ed; --fg: #2d2a26; --fg2: #5c5955;
    --accent: #8b7355; --border: #d4cec4; --nav-h: 3.5rem;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: 'Source Serif 4', Georgia, serif; background: var(--bg);
       color: var(--fg); font-size: 1rem; line-height: 1.75; }
/* --- Navigation bar --- */
#navbar { position: sticky; top: 0; z-index: 100; height: var(--nav-h);
          background: var(--bg2); border-bottom: 1px solid var(--border);
          display: flex; align-items: center; gap: 1rem; padding: 0 1.5rem; }
#navbar h1 { font-size: 1rem; font-weight: 600; color: var(--accent); flex: 1;
             white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
#page-select { padding: .3rem .6rem; border: 1px solid var(--border);
               border-radius: 4px; background: white; cursor: pointer; }
.nav-btn { padding: .3rem .7rem; border: 1px solid var(--border); border-radius: 4px;
           background: white; cursor: pointer; }
.nav-btn:hover { background: var(--border); }
/* --- Entity filter legend --- */
#legend { background: var(--bg2); border-bottom: 1px solid var(--border);
          padding: .5rem 1.5rem; display: flex; flex-wrap: wrap; gap: .5rem; }
.leg-btn { display: inline-flex; align-items: center; gap: .4rem; padding: .25rem .6rem;
           border: 1px solid var(--border); border-radius: 20px; cursor: pointer;
           font-size: .8rem; background: white; transition: opacity .15s; }
.leg-btn.inactive { opacity: .3; }
.leg-dot { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }
/* --- Page container --- */
.book-page { display: none; max-width: 900px; margin: 2rem auto; padding: 0 1rem 4rem; }
.book-page.active { display: block; }
.page-meta { font-size: .8rem; color: var(--fg2); margin-bottom: 1rem;
             display: flex; gap: 1.5rem; flex-wrap: wrap; }
.page-header { font-family: 'EB Garamond', serif; font-size: .95rem; color: var(--fg2);
               border-bottom: 1px solid var(--border); padding-bottom: .5rem; margin-bottom: 1.5rem;
               display: flex; justify-content: space-between; }
.body-paragraph { margin-bottom: 1.1em; text-align: justify; hyphens: auto; }
.section-heading { font-family: 'EB Garamond', serif; font-size: 1.3rem;
                   margin: 1.5rem 0 .75rem; color: var(--accent); }
.body-list { margin: .5rem 0 1rem 1.5rem; }
/* --- Tables --- */
.table-wrapper { overflow-x: auto; margin: 1.5rem 0; }
.page-table { border-collapse: collapse; width: 100%; font-size: .9rem; }
.page-table th, .page-table td { border: 1px solid var(--border);
    padding: .4rem .7rem; text-align: left; }
.page-table th { background: var(--bg2); font-weight: 600; }
.table-caption { caption-side: bottom; text-align: left; font-size: .8rem;
                 color: var(--fg2); padding-top: .4rem; }
/* --- Footnotes --- */
.footnotes { border-top: 1px solid var(--border); margin-top: 2rem; padding-top: 1rem;
             font-size: .85rem; color: var(--fg2); }
.fn-marker { font-weight: 600; margin-right: .3rem; }
/* --- Facsimile --- */
.facsimile-toggle { margin: 1.5rem 0 .5rem; }
.facsimile-toggle button { padding: .4rem .9rem; border: 1px solid var(--border);
    border-radius: 4px; cursor: pointer; background: white; }
.facsimile { display: none; margin-bottom: 1rem; }
.facsimile img { max-width: 100%; border: 1px solid var(--border); border-radius: 4px; }
/* --- Entity spans --- */
.entity { border-radius: 2px; cursor: help; }
.entity.hidden-type { background: transparent !important; border-bottom: none !important; }
/* --- Stats panel --- */
.stats-panel { font-size: .8rem; color: var(--fg2); margin-bottom: 1.5rem; }
.stats-panel table { border-collapse: collapse; }
.stats-panel td { padding: .1rem .5rem; }
"""

_JS = """
const pages = document.querySelectorAll('.book-page');
const sel   = document.getElementById('page-select');
let current = 0;

function showPage(idx) {
    if (idx < 0 || idx >= pages.length) return;
    pages[current].classList.remove('active');
    current = idx;
    pages[current].classList.add('active');
    sel.value = idx;
    window.scrollTo(0, 0);
}

sel.addEventListener('change', () => showPage(parseInt(sel.value)));
document.getElementById('btn-prev').addEventListener('click', () => showPage(current - 1));
document.getElementById('btn-next').addEventListener('click', () => showPage(current + 1));

document.addEventListener('keydown', e => {
    if (e.key === 'ArrowRight') showPage(current + 1);
    if (e.key === 'ArrowLeft')  showPage(current - 1);
});

// Entity filter
const hiddenTypes = new Set();
document.querySelectorAll('.leg-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        const t = btn.dataset.type;
        if (hiddenTypes.has(t)) {
            hiddenTypes.delete(t);
            btn.classList.remove('inactive');
        } else {
            hiddenTypes.add(t);
            btn.classList.add('inactive');
        }
        document.querySelectorAll('.entity').forEach(el => {
            el.classList.toggle('hidden-type', hiddenTypes.has(el.dataset.type));
        });
    });
});

// Facsimile toggle
document.querySelectorAll('.facsimile-toggle button').forEach(btn => {
    btn.addEventListener('click', () => {
        const target = document.getElementById(btn.dataset.target);
        if (target) target.style.display = target.style.display === 'none' ? 'block' : 'none';
    });
});

showPage(0);
"""


def generate_html_edition(
    results: List[PageResult],
    output_path: str | Path,
    title: str = "Historische Digitalausgabe",
    entity_colors: Optional[Dict[str, str]] = None,
    entity_labels: Optional[Dict[str, str]] = None,
    image_folder: Optional[str | Path] = None,
    image_ref_prefix: Optional[str] = None,
) -> Path:
    """
    Generate a single self-contained HTML edition from *results*.

    Args:
        results:          Processed page results.
        output_path:      Destination .html file.
        title:            Edition title shown in the nav bar.
        entity_colors:    Dict mapping entity type → hex colour.
        entity_labels:    Dict mapping entity type → German display label.
        image_folder:     If provided, embeds facsimile images as base64.
                          Mutually exclusive with *image_ref_prefix*.
        image_ref_prefix: If provided, reference images via this path prefix
                          instead of embedding (e.g. ``"images/"`` or a full
                          URL).  The final ``src`` will be
                          ``{image_ref_prefix}{image_filename}``.

    Returns:
        Path to the written HTML file.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    ec = entity_colors or {}
    el = entity_labels or {}

    # Build legend
    legend_html = "".join(
        f'<button class="leg-btn" data-type="{etype}">'
        f'<span class="leg-dot" style="background:{color};"></span>'
        f'{el.get(etype, etype)}</button>'
        for etype, color in ec.items()
    )

    # Build page <option> list
    options_html = "".join(
        f'<option value="{i}">Seite {r.structure.page_number_printed or r.page_number}'
        f" – {r.structure.header or r.image_filename}</option>"
        for i, r in enumerate(results)
    )

    # Build page divs
    page_divs: List[str] = []
    for idx, result in enumerate(results):
        # Facsimile
        facs_html = ""
        if image_ref_prefix is not None:
            # Reference mode: point to external image file
            prefix = image_ref_prefix.rstrip("/") + "/" if image_ref_prefix else ""
            img_src = f"{prefix}{result.image_filename}"
            facs_html = (
                f'<div class="facsimile-toggle">'
                f'<button data-target="facs-{idx}">Original einblenden / ausblenden</button></div>'
                f'<div class="facsimile" id="facs-{idx}">'
                f'<img src="{img_src}" alt="Faksimile Seite {result.page_number}" loading="lazy"></div>'
            )
        elif image_folder:
            img_path = Path(image_folder) / result.image_filename
            if img_path.exists():
                b64, _ = load_image_as_base64(img_path)
                facs_html = (
                    f'<div class="facsimile-toggle">'
                    f'<button data-target="facs-{idx}">Original einblenden / ausblenden</button></div>'
                    f'<div class="facsimile" id="facs-{idx}">'
                    f'<img src="data:image/jpeg;base64,{b64}" alt="Faksimile Seite {result.page_number}"></div>'
                )

        # Header bar
        header_bar = ""
        if result.structure.header or result.structure.page_number_printed:
            header_bar = (
                f'<div class="page-header">'
                f'<span>{result.structure.header or ""}</span>'
                f'<span>{result.structure.page_number_printed or ""}</span>'
                f"</div>"
            )

        # Content blocks
        body_html = render_content_blocks(
            result.structure.content_blocks, result.entities, ec
        )

        # Footnotes
        fn_html = ""
        if result.structure.footnotes:
            items = "".join(
                f'<div><span class="fn-marker">{fn.marker}</span>{fn.text}</div>'
                for fn in result.structure.footnotes
            )
            fn_html = f'<div class="footnotes">{items}</div>'

        # Entity stats
        counts: Dict[str, int] = {}
        for e in result.entities:
            counts[e.entity_type] = counts.get(e.entity_type, 0) + 1
        stats_rows = "".join(
            '<tr><td style="color:{}">●&nbsp;{}</td><td>{}</td></tr>'.format(
                ec.get(t, "#555"), t, c
            )
            for t, c in sorted(counts.items(), key=lambda x: -x[1])
        )
        stats_panel = (
            f'<div class="stats-panel"><table>{stats_rows}</table></div>'
            if stats_rows
            else ""
        )

        page_divs.append(
            f'<div class="book-page" id="page-{idx}">'
            f'<div class="page-meta">'
            f'<span>📄 {result.image_filename}</span>'
            f'<span>🏷 {len(result.entities)} Entitäten</span>'
            f'<span>🕒 {result.processing_timestamp[:10]}</span>'
            f"</div>"
            f"{facs_html}"
            f"{header_bar}"
            f"{stats_panel}"
            f"{body_html}"
            f"{fn_html}"
            f"</div>"
        )

    html = f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=EB+Garamond:ital,wght@0,400;1,400&family=Source+Serif+4:ital,opsz,wght@0,8..60,400;1,8..60,400&display=swap" rel="stylesheet">
<style>{_CSS}</style>
</head>
<body>
<nav id="navbar">
  <h1>📜 {title}</h1>
  <button class="nav-btn" id="btn-prev">◀</button>
  <select id="page-select">{options_html}</select>
  <button class="nav-btn" id="btn-next">▶</button>
</nav>
<div id="legend">{legend_html}</div>
{"".join(page_divs)}
<script>{_JS}</script>
</body>
</html>"""

    with open(output_path, "w", encoding="utf-8") as fh:
        fh.write(html)

    logger.info("HTML edition written to %s (%.1f MB)", output_path, output_path.stat().st_size / 1e6)
    return output_path

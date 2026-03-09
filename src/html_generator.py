"""
HTML Generator (Step 5)
=======================
Renders processed PageResult objects into an interactive single-file
HTML digital edition with:
- Region-type visual indicators
- Entity highlighting with filter legend
- Facsimile toggle
- Leaflet map for geocoded locations
- Keyboard navigation
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

from .models import Entity, PageResult, Region
from .region_detection import load_image_as_base64

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Low-level renderers
# ---------------------------------------------------------------------------


def _render_entity_span(text: str, entity_type: str, context: str, color: str) -> str:
    safe_ctx = (context or "").replace('"', "&quot;")
    return (
        f'<span class="entity" data-type="{entity_type}" '
        f'style="background:{color}20;border-bottom:2px solid {color};" '
        f'title="{entity_type}: {safe_ctx}">{text}</span>'
    )


def _render_annotated_text(text: str, entities: List[Entity], entity_colors: dict) -> str:
    """Return HTML string with non-overlapping entity spans inserted."""
    if not entities:
        return text.replace("\n", "<br>")

    sorted_ents = sorted(entities, key=lambda e: e.start_char)
    parts: List[str] = []
    cursor = 0

    for ent in sorted_ents:
        if ent.start_char < cursor:
            continue
        if ent.start_char > cursor:
            parts.append(text[cursor:ent.start_char].replace("\n", "<br>"))
        color = entity_colors.get(ent.entity_type, "#9e9e9e")
        parts.append(
            _render_entity_span(ent.text, ent.entity_type, ent.context or "", color)
        )
        cursor = ent.end_char

    if cursor < len(text):
        parts.append(text[cursor:].replace("\n", "<br>"))

    return "".join(parts)


def _render_table_html(table_data: dict) -> str:
    rows_html: List[str] = []
    for row_idx, row in enumerate(table_data.get("cells", [])):
        tag = "th" if row_idx == 0 else "td"
        cells = "".join(f"<{tag}>{cell}</{tag}>" for cell in row)
        rows_html.append(f"<tr>{cells}</tr>")

    caption = table_data.get("caption", "")
    caption_html = f'<caption class="table-caption">{caption}</caption>' if caption else ""
    return (
        f'<div class="table-wrapper">'
        f'<table class="page-table">{caption_html}{"".join(rows_html)}</table>'
        f'</div>'
    )


def _render_region(region: Region, entities: List[Entity], entity_colors: dict,
                   region_colors: dict, region_labels: dict) -> str:
    """Render a single region as an HTML block with a type indicator."""
    rtype = region.region_type
    color = region_colors.get(rtype, "#546e7a")
    label = region_labels.get(rtype, rtype.title())

    indicator = (
        f'<span class="region-indicator" style="background:{color};">{label}</span>'
    )

    if region.is_visual:
        return (
            f'<div class="region region-visual" data-region-type="{rtype}">'
            f'{indicator}'
            f'<div class="visual-description">{region.content}</div>'
            f'</div>'
        )

    if rtype == "table" and region.table_data:
        return (
            f'<div class="region region-table" data-region-type="{rtype}">'
            f'{indicator}'
            f'{_render_table_html(region.table_data)}'
            f'</div>'
        )

    if rtype == "heading":
        return (
            f'<div class="region" data-region-type="{rtype}">'
            f'{indicator}'
            f'<h2 class="section-heading">{region.content}</h2>'
            f'</div>'
        )

    if rtype == "subheading":
        return (
            f'<div class="region" data-region-type="{rtype}">'
            f'{indicator}'
            f'<h3 class="section-subheading">{region.content}</h3>'
            f'</div>'
        )

    if rtype == "footnote":
        return (
            f'<div class="region region-footnote" data-region-type="{rtype}">'
            f'{indicator}'
            f'<div class="footnote-text">{region.content}</div>'
            f'</div>'
        )

    if rtype == "date":
        return (
            f'<div class="region region-date" data-region-type="{rtype}">'
            f'{indicator}'
            f'<div class="date-text">{region.content}</div>'
            f'</div>'
        )

    if rtype == "list":
        return (
            f'<div class="region" data-region-type="{rtype}">'
            f'{indicator}'
            f'<div class="list-content">{region.content}</div>'
            f'</div>'
        )

    if rtype in ("page_number", "header"):
        return (
            f'<div class="region region-meta" data-region-type="{rtype}">'
            f'{indicator}'
            f'<span class="meta-text">{region.content}</span>'
            f'</div>'
        )

    # Default: paragraph or any other text type
    annotated = _render_annotated_text(region.content, entities, entity_colors)
    return (
        f'<div class="region" data-region-type="{rtype}">'
        f'{indicator}'
        f'<p class="body-paragraph">{annotated}</p>'
        f'</div>'
    )


# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------

_CSS = """\
:root {
    --bg: #faf8f5; --bg2: #f5f2ed; --fg: #2d2a26; --fg2: #5c5955;
    --accent: #8b7355; --border: #d4cec4; --nav-h: 3.5rem;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: 'Source Serif 4', Georgia, serif; background: var(--bg);
       color: var(--fg); font-size: 1rem; line-height: 1.75; }

/* Navigation */
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

/* Legend bars */
.legend-bar { background: var(--bg2); border-bottom: 1px solid var(--border);
              padding: .5rem 1.5rem; display: flex; flex-wrap: wrap; gap: .5rem;
              align-items: center; }
.legend-bar .legend-title { font-size: .75rem; font-weight: 600; color: var(--fg2);
                            margin-right: .5rem; }
.leg-btn { display: inline-flex; align-items: center; gap: .4rem; padding: .25rem .6rem;
           border: 1px solid var(--border); border-radius: 20px; cursor: pointer;
           font-size: .8rem; background: white; transition: opacity .15s; }
.leg-btn.inactive { opacity: .3; }
.leg-dot { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }

/* Page container */
.book-page { display: none; max-width: 900px; margin: 2rem auto; padding: 0 1rem 4rem; }
.book-page.active { display: block; }
.page-meta { font-size: .8rem; color: var(--fg2); margin-bottom: 1rem;
             display: flex; gap: 1.5rem; flex-wrap: wrap; }

/* Regions */
.region { position: relative; margin-bottom: 1rem; padding-left: .75rem;
          border-left: 3px solid transparent; }
.region-indicator { display: inline-block; font-size: .65rem; font-weight: 600;
                    color: white; padding: .1rem .4rem; border-radius: 3px;
                    margin-bottom: .3rem; text-transform: uppercase; letter-spacing: .03em; }
.region-visual { background: #f3e5f5; border-radius: 6px; padding: .75rem; }
.visual-description { font-style: italic; color: var(--fg2); font-size: .9rem; }
.region-footnote { border-left-color: #4e342e; font-size: .85rem; color: var(--fg2); }
.region-date { border-left-color: #ad1457; }
.date-text { font-weight: 600; color: #ad1457; }
.region-meta { font-size: .8rem; color: var(--fg2); }
.region-table { border-left-color: #00695c; }

/* Typography */
.body-paragraph { margin-bottom: .5em; text-align: justify; hyphens: auto; }
.section-heading { font-family: 'EB Garamond', serif; font-size: 1.4rem;
                   margin: .5rem 0; color: var(--accent); }
.section-subheading { font-family: 'EB Garamond', serif; font-size: 1.15rem;
                      margin: .4rem 0; color: var(--accent); }

/* Tables */
.table-wrapper { overflow-x: auto; margin: .5rem 0; }
.page-table { border-collapse: collapse; width: 100%; font-size: .9rem; }
.page-table th, .page-table td { border: 1px solid var(--border);
    padding: .4rem .7rem; text-align: left; }
.page-table th { background: var(--bg2); font-weight: 600; }
.table-caption { caption-side: bottom; text-align: left; font-size: .8rem;
                 color: var(--fg2); padding-top: .4rem; }

/* Entity spans */
.entity { border-radius: 2px; cursor: help; }
.entity.hidden-type { background: transparent !important; border-bottom: none !important; }

/* Stats panel */
.stats-panel { font-size: .8rem; color: var(--fg2); margin-bottom: 1rem; }
.stats-panel table { border-collapse: collapse; }
.stats-panel td { padding: .1rem .5rem; }

/* Facsimile */
.facsimile-toggle { margin: 1rem 0 .5rem; }
.facsimile-toggle button { padding: .4rem .9rem; border: 1px solid var(--border);
    border-radius: 4px; cursor: pointer; background: white; }
.facsimile { display: none; margin-bottom: 1rem; }
.facsimile img { max-width: 100%; border: 1px solid var(--border); border-radius: 4px; }

/* Map */
.map-toggle { margin: .5rem 0; }
.map-toggle button { padding: .4rem .9rem; border: 1px solid var(--border);
    border-radius: 4px; cursor: pointer; background: white; }
.map-container { display: none; height: 350px; margin-bottom: 1rem;
                 border: 1px solid var(--border); border-radius: 6px; }
"""

# ---------------------------------------------------------------------------
# JavaScript
# ---------------------------------------------------------------------------

_JS = """\
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
document.querySelectorAll('#entity-legend .leg-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        const t = btn.dataset.type;
        if (hiddenTypes.has(t)) { hiddenTypes.delete(t); btn.classList.remove('inactive'); }
        else { hiddenTypes.add(t); btn.classList.add('inactive'); }
        document.querySelectorAll('.entity').forEach(el => {
            el.classList.toggle('hidden-type', hiddenTypes.has(el.dataset.type));
        });
    });
});

// Region filter
const hiddenRegions = new Set();
document.querySelectorAll('#region-legend .leg-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        const t = btn.dataset.type;
        if (hiddenRegions.has(t)) { hiddenRegions.delete(t); btn.classList.remove('inactive'); }
        else { hiddenRegions.add(t); btn.classList.add('inactive'); }
        document.querySelectorAll('.region').forEach(el => {
            el.style.display = hiddenRegions.has(el.dataset.regionType) ? 'none' : '';
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

// Map toggle
document.querySelectorAll('.map-toggle button').forEach(btn => {
    btn.addEventListener('click', () => {
        const container = document.getElementById(btn.dataset.target);
        if (!container) return;
        const isHidden = container.style.display === 'none';
        container.style.display = isHidden ? 'block' : 'none';
        if (isHidden && !container.dataset.initialized) {
            container.dataset.initialized = 'true';
            const mapData = JSON.parse(container.dataset.locations);
            const map = L.map(container).setView(mapData.center, 6);
            L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                attribution: '&copy; OpenStreetMap contributors'
            }).addTo(map);
            mapData.locations.forEach(loc => {
                L.marker([loc.lat, loc.lon]).addTo(map).bindPopup(
                    '<b>' + loc.name + '</b><br>' + loc.display
                );
            });
            setTimeout(() => map.invalidateSize(), 100);
        }
    });
});

showPage(0);
"""


# ---------------------------------------------------------------------------
# Full-edition generator
# ---------------------------------------------------------------------------


def generate_html_edition(
    results: List[PageResult],
    output_path: str | Path,
    title: str = "Digital Edition",
    entity_colors: Optional[Dict[str, str]] = None,
    entity_labels: Optional[Dict[str, str]] = None,
    region_colors: Optional[Dict[str, str]] = None,
    region_labels: Optional[Dict[str, str]] = None,
    image_folder: Optional[str | Path] = None,
    image_ref_prefix: Optional[str] = None,
) -> Path:
    """
    Generate a single self-contained HTML edition from *results*.

    Args:
        results:          Processed page results.
        output_path:      Destination .html file.
        title:            Edition title.
        entity_colors:    Dict mapping entity type -> hex colour.
        entity_labels:    Dict mapping entity type -> display label.
        region_colors:    Dict mapping region type -> hex colour.
        region_labels:    Dict mapping region type -> display label.
        image_folder:     Embed facsimile images as base64.
        image_ref_prefix: Reference images via path prefix.

    Returns:
        Path to the written HTML file.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    ec = entity_colors or {}
    el = entity_labels or {}
    rc = region_colors or {}
    rl = region_labels or {}

    # Entity legend
    entity_legend = "".join(
        f'<button class="leg-btn" data-type="{etype}">'
        f'<span class="leg-dot" style="background:{color};"></span>'
        f'{el.get(etype, etype)}</button>'
        for etype, color in ec.items()
    )

    # Region legend - only include types that actually appear
    used_region_types = set()
    for r in results:
        for reg in r.regions:
            used_region_types.add(reg.region_type)

    region_legend = "".join(
        f'<button class="leg-btn" data-type="{rtype}">'
        f'<span class="leg-dot" style="background:{rc.get(rtype, "#546e7a")};"></span>'
        f'{rl.get(rtype, rtype.title())}</button>'
        for rtype in sorted(used_region_types)
    )

    # Page options
    options_html = "".join(
        f'<option value="{i}">Page {r.page_number} - {r.image_filename}</option>'
        for i, r in enumerate(results)
    )

    # Build page divs
    page_divs: List[str] = []
    for idx, result in enumerate(results):
        # Facsimile
        facs_html = ""
        if image_ref_prefix is not None:
            prefix = image_ref_prefix.rstrip("/") + "/" if image_ref_prefix else ""
            img_src = f"{prefix}{result.image_filename}"
            facs_html = (
                f'<div class="facsimile-toggle">'
                f'<button data-target="facs-{idx}">Show / hide facsimile</button></div>'
                f'<div class="facsimile" id="facs-{idx}">'
                f'<img src="{img_src}" alt="Facsimile page {result.page_number}" loading="lazy"></div>'
            )
        elif image_folder:
            img_path = Path(image_folder) / result.image_filename
            if img_path.exists():
                b64, _ = load_image_as_base64(img_path)
                facs_html = (
                    f'<div class="facsimile-toggle">'
                    f'<button data-target="facs-{idx}">Show / hide facsimile</button></div>'
                    f'<div class="facsimile" id="facs-{idx}">'
                    f'<img src="data:image/jpeg;base64,{b64}" alt="Facsimile page {result.page_number}"></div>'
                )

        # Map (if locations exist)
        map_html = ""
        if result.locations:
            locs_data = {
                "locations": [
                    {"name": loc.name, "lat": loc.lat, "lon": loc.lon, "display": loc.display_name}
                    for loc in result.locations
                ],
                "center": [
                    sum(loc.lat for loc in result.locations) / len(result.locations),
                    sum(loc.lon for loc in result.locations) / len(result.locations),
                ],
            }
            locs_json = json.dumps(locs_data, ensure_ascii=False).replace('"', "&quot;")
            map_html = (
                f'<div class="map-toggle">'
                f'<button data-target="map-{idx}">'
                f'Show / hide map ({len(result.locations)} locations)</button></div>'
                f'<div class="map-container" id="map-{idx}" style="display:none;" '
                f'data-locations="{locs_json}"></div>'
            )

        # Render all regions
        regions_html_parts: List[str] = []
        for region in result.regions:
            regions_html_parts.append(
                _render_region(region, result.entities, ec, rc, rl)
            )
        body_html = "\n".join(regions_html_parts)

        # Entity stats
        counts: Dict[str, int] = {}
        for e in result.entities:
            counts[e.entity_type] = counts.get(e.entity_type, 0) + 1
        stats_rows = "".join(
            '<tr><td style="color:{}">&#9679;&nbsp;{}</td><td>{}</td></tr>'.format(
                ec.get(t, "#555"), t, c
            )
            for t, c in sorted(counts.items(), key=lambda x: -x[1])
        )
        stats_panel = (
            f'<div class="stats-panel"><table>{stats_rows}</table></div>'
            if stats_rows else ""
        )

        # Region type summary
        region_counts: Dict[str, int] = {}
        for reg in result.regions:
            region_counts[reg.region_type] = region_counts.get(reg.region_type, 0) + 1
        region_summary = " | ".join(f"{k}: {v}" for k, v in sorted(region_counts.items()))

        page_divs.append(
            f'<div class="book-page" id="page-{idx}">'
            f'<div class="page-meta">'
            f'<span>{result.image_filename}</span>'
            f'<span>{len(result.regions)} regions ({region_summary})</span>'
            f'<span>{len(result.entities)} entities</span>'
            f'<span>{result.processing_timestamp[:10]}</span>'
            f'</div>'
            f'{facs_html}'
            f'{map_html}'
            f'{stats_panel}'
            f'{body_html}'
            f'</div>'
        )

    # Check if any page has locations (to include Leaflet)
    has_maps = any(r.locations for r in results)
    leaflet_css = (
        '<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />'
        if has_maps else ""
    )
    leaflet_js = (
        '<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>'
        if has_maps else ""
    )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=EB+Garamond:ital,wght@0,400;1,400&family=Source+Serif+4:ital,opsz,wght@0,8..60,400;1,8..60,400&display=swap" rel="stylesheet">
{leaflet_css}
<style>{_CSS}</style>
</head>
<body>
<nav id="navbar">
  <h1>{title}</h1>
  <button class="nav-btn" id="btn-prev">&#9664;</button>
  <select id="page-select">{options_html}</select>
  <button class="nav-btn" id="btn-next">&#9654;</button>
</nav>
<div class="legend-bar" id="entity-legend">
  <span class="legend-title">Entities:</span>
  {entity_legend}
</div>
<div class="legend-bar" id="region-legend">
  <span class="legend-title">Regions:</span>
  {region_legend}
</div>
{"".join(page_divs)}
{leaflet_js}
<script>{_JS}</script>
</body>
</html>"""

    with open(output_path, "w", encoding="utf-8") as fh:
        fh.write(html)

    logger.info("HTML edition written to %s (%.1f MB)", output_path, output_path.stat().st_size / 1e6)
    return output_path

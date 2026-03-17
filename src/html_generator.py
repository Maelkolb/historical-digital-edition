"""
HTML Generator (Step 5)
=======================
Renders processed PageResult objects into an interactive single-file
HTML digital edition.

Entity placement uses text matching (not character offsets) for reliability.
"""

import html as html_lib
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .models import Entity, PageResult, Region
from .region_detection import load_image_as_base64

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Text-matching entity annotation
# ---------------------------------------------------------------------------


def _find_entity_spans(text: str, entities: List[Entity]) -> List[Tuple[int, int, Entity]]:
    """
    Find all entity occurrences in *text* using exact string matching.
    Returns list of (start, end, entity) sorted by start position,
    with overlaps resolved (longer match wins, earlier match wins on tie).
    """
    raw_spans: List[Tuple[int, int, Entity]] = []

    for ent in entities:
        needle = ent.text
        if not needle:
            continue
        start = 0
        while True:
            idx = text.find(needle, start)
            if idx == -1:
                break
            raw_spans.append((idx, idx + len(needle), ent))
            start = idx + 1  # find all occurrences

    # Sort by start position, then by length descending (prefer longer matches)
    raw_spans.sort(key=lambda s: (s[0], -(s[1] - s[0])))

    # Remove overlaps: greedily keep earliest / longest spans
    result: List[Tuple[int, int, Entity]] = []
    cursor = 0
    for start, end, ent in raw_spans:
        if start >= cursor:
            result.append((start, end, ent))
            cursor = end

    return result


def _annotate_text_with_entities(text: str, entities: List[Entity],
                                  entity_colors: dict) -> str:
    """
    Insert entity highlight spans into *text* using text matching.
    Returns HTML string.
    """
    if not entities or not text:
        return html_lib.escape(text).replace("\n", "<br>\n")

    spans = _find_entity_spans(text, entities)
    if not spans:
        return html_lib.escape(text).replace("\n", "<br>\n")

    parts: List[str] = []
    cursor = 0

    for start, end, ent in spans:
        # Text before this entity
        if start > cursor:
            parts.append(html_lib.escape(text[cursor:start]).replace("\n", "<br>\n"))

        # Entity span
        color = entity_colors.get(ent.entity_type, "#9e9e9e")
        safe_ctx = html_lib.escape(ent.context or "")
        entity_text = html_lib.escape(text[start:end])
        parts.append(
            f'<mark class="entity" data-type="{html_lib.escape(ent.entity_type)}" '
            f'style="--ent-color:{color};" '
            f'title="{html_lib.escape(ent.entity_type)}: {safe_ctx}">'
            f'{entity_text}</mark>'
        )
        cursor = end

    # Remaining text
    if cursor < len(text):
        parts.append(html_lib.escape(text[cursor:]).replace("\n", "<br>\n"))

    return "".join(parts)


# ---------------------------------------------------------------------------
# Region renderers
# ---------------------------------------------------------------------------


def _render_table_html(table_data: dict) -> str:
    rows_html: List[str] = []
    for row_idx, row in enumerate(table_data.get("cells", [])):
        tag = "th" if row_idx == 0 else "td"
        cells = "".join(f"<{tag}>{html_lib.escape(str(cell))}</{tag}>" for cell in row)
        rows_html.append(f"<tr>{cells}</tr>")

    caption = table_data.get("caption", "")
    caption_html = (
        f'<caption>{html_lib.escape(caption)}</caption>' if caption else ""
    )
    return (
        f'<table class="region-table">{caption_html}'
        f'<tbody>{"".join(rows_html)}</tbody></table>'
    )


def _render_region(region: Region, entities: List[Entity], entity_colors: dict,
                   region_colors: dict, region_labels: dict) -> str:
    """Render a single region as an HTML block."""
    rtype = region.region_type
    color = region_colors.get(rtype, "#546e7a")
    label = region_labels.get(rtype, rtype.replace("_", " ").title())

    tag_html = f'<span class="region-tag" style="--tag-color:{color};">{label}</span>'

    # Visual regions (images/illustrations)
    if region.is_visual:
        return (
            f'<div class="region region--visual" data-region-type="{rtype}">'
            f'{tag_html}'
            f'<p class="visual-desc">{html_lib.escape(region.content)}</p>'
            f'</div>'
        )

    # Tables
    if rtype == "table" and region.table_data:
        return (
            f'<div class="region region--table" data-region-type="{rtype}">'
            f'{tag_html}'
            f'{_render_table_html(region.table_data)}'
            f'</div>'
        )

    # Headings
    if rtype == "heading":
        annotated = _annotate_text_with_entities(region.content, entities, entity_colors)
        return (
            f'<div class="region" data-region-type="{rtype}">'
            f'{tag_html}'
            f'<h2 class="region-heading">{annotated}</h2>'
            f'</div>'
        )

    if rtype == "subheading":
        annotated = _annotate_text_with_entities(region.content, entities, entity_colors)
        return (
            f'<div class="region" data-region-type="{rtype}">'
            f'{tag_html}'
            f'<h3 class="region-subheading">{annotated}</h3>'
            f'</div>'
        )

    # Footnotes
    if rtype == "footnote":
        annotated = _annotate_text_with_entities(region.content, entities, entity_colors)
        return (
            f'<div class="region region--footnote" data-region-type="{rtype}">'
            f'{tag_html}'
            f'<p class="footnote-body">{annotated}</p>'
            f'</div>'
        )

    # Dates
    if rtype == "date":
        return (
            f'<div class="region region--date" data-region-type="{rtype}">'
            f'{tag_html}'
            f'<p class="date-body">{html_lib.escape(region.content)}</p>'
            f'</div>'
        )

    # Lists
    if rtype == "list":
        annotated = _annotate_text_with_entities(region.content, entities, entity_colors)
        return (
            f'<div class="region region--list" data-region-type="{rtype}">'
            f'{tag_html}'
            f'<div class="list-body">{annotated}</div>'
            f'</div>'
        )

    # Page numbers / running headers
    if rtype in ("page_number", "header"):
        return (
            f'<div class="region region--meta" data-region-type="{rtype}">'
            f'{tag_html}'
            f'<span class="meta-body">{html_lib.escape(region.content)}</span>'
            f'</div>'
        )

    # Marginalia
    if rtype == "marginalia":
        annotated = _annotate_text_with_entities(region.content, entities, entity_colors)
        return (
            f'<div class="region region--marginalia" data-region-type="{rtype}">'
            f'{tag_html}'
            f'<p class="marginalia-body">{annotated}</p>'
            f'</div>'
        )

    # Default: paragraph / caption / anything else
    annotated = _annotate_text_with_entities(region.content, entities, entity_colors)
    return (
        f'<div class="region" data-region-type="{rtype}">'
        f'{tag_html}'
        f'<p class="region-paragraph">{annotated}</p>'
        f'</div>'
    )


# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------

_CSS = """\
/* ── Reset & Base ─────────────────────────────────────────────── */
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

:root {
  --bg:      #fcfaf7;
  --bg-warm: #f6f3ee;
  --bg-card: #ffffff;
  --fg:      #1a1a1a;
  --fg-dim:  #6b6560;
  --fg-faint:#9e9892;
  --accent:  #7c5e3c;
  --accent2: #a07850;
  --border:  #e2ddd6;
  --border-l:#ece8e2;
  --radius:  8px;
  --shadow:  0 1px 3px rgba(0,0,0,.06), 0 1px 2px rgba(0,0,0,.04);
  --shadow-l:0 4px 12px rgba(0,0,0,.08);
}

html { scroll-behavior: smooth; }
body {
  font-family: 'Source Serif 4', 'Noto Serif', Georgia, serif;
  background: var(--bg);
  color: var(--fg);
  font-size: 17px;
  line-height: 1.8;
  -webkit-font-smoothing: antialiased;
}

/* ── Top Navigation ───────────────────────────────────────────── */
.top-bar {
  position: sticky; top: 0; z-index: 100;
  background: var(--bg-card);
  border-bottom: 1px solid var(--border);
  box-shadow: var(--shadow);
}
.nav-inner {
  max-width: 1000px; margin: 0 auto;
  padding: .65rem 1.5rem;
  display: flex; align-items: center; gap: .75rem;
}
.nav-title {
  font-family: 'EB Garamond', 'Noto Serif', serif;
  font-size: 1.15rem; font-weight: 500; color: var(--accent);
  flex: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.nav-btn {
  display: inline-flex; align-items: center; justify-content: center;
  width: 2rem; height: 2rem;
  border: 1px solid var(--border); border-radius: var(--radius);
  background: var(--bg); color: var(--fg-dim); cursor: pointer;
  font-size: .85rem; transition: all .15s;
}
.nav-btn:hover { background: var(--border); color: var(--fg); }
#page-select {
  padding: .35rem .75rem; font-size: .85rem;
  border: 1px solid var(--border); border-radius: var(--radius);
  background: var(--bg); color: var(--fg); cursor: pointer;
  max-width: 280px;
}
.page-counter {
  font-size: .8rem; color: var(--fg-faint); white-space: nowrap;
}

/* ── Legend Panels ─────────────────────────────────────────────── */
.legend-panel {
  background: var(--bg-warm);
  border-bottom: 1px solid var(--border-l);
}
.legend-inner {
  max-width: 1000px; margin: 0 auto;
  padding: .45rem 1.5rem;
  display: flex; flex-wrap: wrap; gap: .4rem; align-items: center;
}
.legend-label {
  font-size: .7rem; font-weight: 600; color: var(--fg-faint);
  text-transform: uppercase; letter-spacing: .06em; margin-right: .3rem;
}
.chip {
  display: inline-flex; align-items: center; gap: .35rem;
  padding: .2rem .55rem; font-size: .75rem;
  border: 1px solid var(--border); border-radius: 100px;
  background: var(--bg-card); color: var(--fg-dim);
  cursor: pointer; transition: all .15s; user-select: none;
}
.chip:hover { border-color: var(--accent2); }
.chip.inactive { opacity: .25; }
.chip-dot {
  width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0;
}

/* ── Page Content ─────────────────────────────────────────────── */
.book-page {
  display: none;
  max-width: 760px; margin: 0 auto;
  padding: 2.5rem 1.5rem 5rem;
}
.book-page.active { display: block; }

/* Page header bar */
.page-header {
  display: flex; align-items: baseline; gap: 1rem; flex-wrap: wrap;
  margin-bottom: 1.75rem;
  padding-bottom: .75rem;
  border-bottom: 2px solid var(--accent);
}
.page-num {
  font-family: 'EB Garamond', serif;
  font-size: 1.5rem; font-weight: 500; color: var(--accent);
}
.page-info {
  font-size: .78rem; color: var(--fg-faint);
}

/* Toolbar buttons */
.toolbar {
  display: flex; gap: .5rem; flex-wrap: wrap;
  margin-bottom: 1.5rem;
}
.tool-btn {
  display: inline-flex; align-items: center; gap: .4rem;
  padding: .4rem .8rem; font-size: .8rem;
  border: 1px solid var(--border); border-radius: var(--radius);
  background: var(--bg-card); color: var(--fg-dim);
  cursor: pointer; transition: all .15s;
}
.tool-btn:hover { background: var(--bg-warm); border-color: var(--accent2); color: var(--fg); }
.tool-btn svg { width: 14px; height: 14px; }

/* Stats row */
.stats-row {
  display: flex; flex-wrap: wrap; gap: .5rem;
  margin-bottom: 1.5rem;
}
.stat-chip {
  display: inline-flex; align-items: center; gap: .3rem;
  padding: .15rem .5rem; font-size: .72rem;
  background: var(--bg-warm); border-radius: 100px;
  color: var(--fg-dim);
}
.stat-dot { width: 7px; height: 7px; border-radius: 50%; }

/* Facsimile & Map */
.facsimile-wrap {
  display: none; margin-bottom: 1.5rem;
  border: 1px solid var(--border); border-radius: var(--radius);
  overflow: hidden; box-shadow: var(--shadow);
}
.facsimile-wrap img { display: block; width: 100%; height: auto; }

.map-wrap {
  display: none; height: 360px; margin-bottom: 1.5rem;
  border: 1px solid var(--border); border-radius: var(--radius);
  overflow: hidden; box-shadow: var(--shadow);
}

/* ── Regions ──────────────────────────────────────────────────── */
.region {
  position: relative;
  margin-bottom: 1.25rem;
}

.region-tag {
  display: inline-block;
  font-size: .6rem; font-weight: 700;
  text-transform: uppercase; letter-spacing: .08em;
  color: var(--tag-color, #546e7a);
  opacity: .55;
  margin-bottom: .25rem;
}

.region-paragraph {
  text-align: justify;
  hyphens: auto;
  -webkit-hyphens: auto;
}

.region-heading {
  font-family: 'EB Garamond', serif;
  font-size: 1.65rem; font-weight: 500; line-height: 1.35;
  color: var(--accent);
  margin: .25rem 0 .5rem;
}

.region-subheading {
  font-family: 'EB Garamond', serif;
  font-size: 1.25rem; font-weight: 500; line-height: 1.4;
  color: var(--accent2);
  margin: .15rem 0 .35rem;
}

/* Visual regions (images) */
.region--visual {
  background: var(--bg-warm);
  border: 1px dashed var(--border);
  border-radius: var(--radius);
  padding: 1rem 1.25rem;
}
.visual-desc {
  font-style: italic; color: var(--fg-dim);
  font-size: .92rem; line-height: 1.6;
}

/* Footnotes */
.region--footnote {
  padding-left: 1rem;
  border-left: 3px solid #8d6e63;
}
.footnote-body {
  font-size: .88rem; color: var(--fg-dim); line-height: 1.65;
}

/* Dates */
.region--date {
  padding-left: 1rem;
  border-left: 3px solid #ad1457;
}
.date-body {
  font-weight: 600; color: #ad1457; font-size: .95rem;
}

/* Lists */
.region--list {
  padding-left: 1rem;
}
.list-body {
  font-size: .95rem;
}

/* Meta (page numbers, headers) */
.region--meta {
  text-align: center;
  padding: .35rem 0;
}
.meta-body {
  font-size: .8rem; color: var(--fg-faint); letter-spacing: .03em;
}

/* Marginalia */
.region--marginalia {
  background: #fffde7; border-radius: var(--radius);
  padding: .75rem 1rem;
  border-left: 3px solid #f9a825;
}
.marginalia-body {
  font-size: .88rem; font-style: italic; color: #5d4037;
}

/* Tables */
.region--table {
  overflow-x: auto;
}
.region-table {
  width: 100%; border-collapse: collapse; font-size: .88rem;
  margin-top: .4rem;
}
.region-table th, .region-table td {
  border: 1px solid var(--border);
  padding: .45rem .75rem; text-align: left;
}
.region-table th {
  background: var(--bg-warm); font-weight: 600; font-size: .82rem;
  text-transform: uppercase; letter-spacing: .03em; color: var(--fg-dim);
}
.region-table caption {
  caption-side: bottom; text-align: left;
  font-size: .78rem; color: var(--fg-faint);
  padding-top: .4rem;
}

/* ── Entity Highlights ────────────────────────────────────────── */
.entity {
  background: color-mix(in srgb, var(--ent-color) 12%, transparent);
  border-bottom: 2px solid var(--ent-color);
  border-radius: 2px;
  padding: 0 1px;
  cursor: help;
  text-decoration: none;
  color: inherit;
  transition: background .15s;
}
.entity:hover {
  background: color-mix(in srgb, var(--ent-color) 25%, transparent);
}
.entity.hidden-type {
  background: transparent !important;
  border-bottom-color: transparent !important;
}

/* ── Responsive ───────────────────────────────────────────────── */
@media (max-width: 640px) {
  body { font-size: 15px; }
  .book-page { padding: 1.5rem 1rem 3rem; }
  .nav-inner { padding: .5rem 1rem; }
  .legend-inner { padding: .35rem 1rem; }
  .region-heading { font-size: 1.35rem; }
}
"""


# ---------------------------------------------------------------------------
# JavaScript
# ---------------------------------------------------------------------------

_JS = """\
(function(){
  const pages = document.querySelectorAll('.book-page');
  const sel   = document.getElementById('page-select');
  const ctr   = document.getElementById('page-counter');
  let cur = 0;

  function show(i) {
    if (i < 0 || i >= pages.length) return;
    pages[cur].classList.remove('active');
    cur = i;
    pages[cur].classList.add('active');
    sel.value = i;
    ctr.textContent = (i + 1) + ' / ' + pages.length;
    window.scrollTo({top: 0});
  }

  sel.addEventListener('change', () => show(+sel.value));
  document.getElementById('btn-prev').addEventListener('click', () => show(cur - 1));
  document.getElementById('btn-next').addEventListener('click', () => show(cur + 1));
  document.addEventListener('keydown', e => {
    if (e.target.tagName === 'SELECT' || e.target.tagName === 'INPUT') return;
    if (e.key === 'ArrowRight') show(cur + 1);
    if (e.key === 'ArrowLeft')  show(cur - 1);
  });

  // Entity filter
  const hiddenEnt = new Set();
  document.querySelectorAll('#ent-legend .chip').forEach(btn => {
    btn.addEventListener('click', () => {
      const t = btn.dataset.type;
      if (hiddenEnt.has(t)) { hiddenEnt.delete(t); btn.classList.remove('inactive'); }
      else { hiddenEnt.add(t); btn.classList.add('inactive'); }
      document.querySelectorAll('.entity').forEach(el => {
        el.classList.toggle('hidden-type', hiddenEnt.has(el.dataset.type));
      });
    });
  });

  // Region filter
  const hiddenReg = new Set();
  document.querySelectorAll('#reg-legend .chip').forEach(btn => {
    btn.addEventListener('click', () => {
      const t = btn.dataset.type;
      if (hiddenReg.has(t)) { hiddenReg.delete(t); btn.classList.remove('inactive'); }
      else { hiddenReg.add(t); btn.classList.add('inactive'); }
      document.querySelectorAll('.region').forEach(el => {
        el.style.display = hiddenReg.has(el.dataset.regionType) ? 'none' : '';
      });
    });
  });

  // Toggle helpers (facsimile + map)
  document.querySelectorAll('[data-toggle]').forEach(btn => {
    btn.addEventListener('click', () => {
      const target = document.getElementById(btn.dataset.toggle);
      if (!target) return;
      const showing = target.style.display === 'none';
      target.style.display = showing ? 'block' : 'none';
      // Initialise Leaflet map on first show
      if (showing && target.classList.contains('map-wrap') && !target.dataset.init) {
        target.dataset.init = '1';
        const d = JSON.parse(target.dataset.locations);
        const map = L.map(target).setView(d.center, 6);
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
          attribution: '\\u00a9 OpenStreetMap'
        }).addTo(map);
        d.locations.forEach(l => {
          L.marker([l.lat, l.lon]).addTo(map)
           .bindPopup('<b>' + l.name + '</b><br><span style=\"font-size:.85em;color:#666\">' + l.display + '</span>');
        });
        setTimeout(() => map.invalidateSize(), 120);
      }
    });
  });

  show(0);
})();
"""


# ---------------------------------------------------------------------------
# SVG icons (tiny, inline)
# ---------------------------------------------------------------------------

_ICON_IMAGE = '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="2" y="2" width="16" height="16" rx="2"/><circle cx="7" cy="7" r="1.5"/><path d="M2 14l4-4 3 3 4-5 5 6"/></svg>'
_ICON_MAP = '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M10 17s-6-5.2-6-9a6 6 0 1112 0c0 3.8-6 9-6 9z"/><circle cx="10" cy="8" r="2"/></svg>'


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
    """Generate a single self-contained HTML edition from *results*."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    ec = entity_colors or {}
    el = entity_labels or {}
    rc = region_colors or {}
    rl = region_labels or {}

    # ── Entity legend chips ──
    ent_chips = "".join(
        f'<span class="chip" data-type="{etype}">'
        f'<span class="chip-dot" style="background:{color};"></span>'
        f'{el.get(etype, etype)}</span>'
        for etype, color in ec.items()
    )

    # ── Region legend chips (only types that appear) ──
    used_rtypes = set()
    for r in results:
        for reg in r.regions:
            used_rtypes.add(reg.region_type)

    reg_chips = "".join(
        f'<span class="chip" data-type="{rtype}">'
        f'<span class="chip-dot" style="background:{rc.get(rtype, "#546e7a")};"></span>'
        f'{rl.get(rtype, rtype.replace("_", " ").title())}</span>'
        for rtype in sorted(used_rtypes)
    )

    # ── Page select options ──
    options = "".join(
        f'<option value="{i}">Page {r.page_number}</option>'
        for i, r in enumerate(results)
    )

    # ── Build page divs ──
    page_divs: List[str] = []
    for idx, result in enumerate(results):

        # Facsimile button + image
        facs_html = ""
        if image_ref_prefix is not None:
            prefix = (image_ref_prefix.rstrip("/") + "/") if image_ref_prefix else ""
            facs_html = (
                f'<button class="tool-btn" data-toggle="facs-{idx}">'
                f'{_ICON_IMAGE} Facsimile</button>'
            )
            facs_html += (
                f'<div class="facsimile-wrap" id="facs-{idx}">'
                f'<img src="{prefix}{result.image_filename}" '
                f'alt="Page {result.page_number}" loading="lazy"></div>'
            )
        elif image_folder:
            img_path = Path(image_folder) / result.image_filename
            if img_path.exists():
                b64, _ = load_image_as_base64(img_path)
                facs_html = (
                    f'<button class="tool-btn" data-toggle="facs-{idx}">'
                    f'{_ICON_IMAGE} Facsimile</button>'
                )
                facs_html += (
                    f'<div class="facsimile-wrap" id="facs-{idx}">'
                    f'<img src="data:image/jpeg;base64,{b64}" '
                    f'alt="Page {result.page_number}"></div>'
                )

        # Map button + container
        map_html = ""
        if result.locations:
            locs = {
                "locations": [
                    {"name": l.name, "lat": l.lat, "lon": l.lon,
                     "display": l.display_name}
                    for l in result.locations
                ],
                "center": [
                    sum(l.lat for l in result.locations) / len(result.locations),
                    sum(l.lon for l in result.locations) / len(result.locations),
                ],
            }
            locs_json = html_lib.escape(json.dumps(locs, ensure_ascii=False))
            map_html = (
                f'<button class="tool-btn" data-toggle="map-{idx}">'
                f'{_ICON_MAP} Map ({len(result.locations)})</button>'
            )
            map_html += (
                f'<div class="map-wrap" id="map-{idx}" '
                f'data-locations="{locs_json}"></div>'
            )

        # Toolbar
        toolbar = ""
        if facs_html or map_html:
            toolbar = f'<div class="toolbar">{facs_html}{map_html}</div>'

        # Entity stats
        counts: Dict[str, int] = {}
        for e in result.entities:
            counts[e.entity_type] = counts.get(e.entity_type, 0) + 1
        stats_html = ""
        if counts:
            chips = "".join(
                f'<span class="stat-chip">'
                f'<span class="stat-dot" style="background:{ec.get(t, "#999")};"></span>'
                f'{t} ({c})</span>'
                for t, c in sorted(counts.items(), key=lambda x: -x[1])
            )
            stats_html = f'<div class="stats-row">{chips}</div>'

        # Render regions
        regions_html = "\n".join(
            _render_region(region, result.entities, ec, rc, rl)
            for region in result.regions
        )

        page_divs.append(
            f'<div class="book-page" id="page-{idx}">'
            f'<div class="page-header">'
            f'<span class="page-num">Page {result.page_number}</span>'
            f'<span class="page-info">{result.image_filename}</span>'
            f'<span class="page-info">{len(result.regions)} regions &middot; '
            f'{len(result.entities)} entities</span>'
            f'</div>'
            f'{toolbar}'
            f'{stats_html}'
            f'{regions_html}'
            f'</div>'
        )

    # Leaflet (only if maps needed)
    has_maps = any(r.locations for r in results)
    leaflet_head = (
        '<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">'
        if has_maps else ""
    )
    leaflet_foot = (
        '<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>'
        if has_maps else ""
    )

    final_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{html_lib.escape(title)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=EB+Garamond:ital,wght@0,400..800;1,400..800&family=Source+Serif+4:ital,opsz,wght@0,8..60,300..900;1,8..60,300..900&display=swap" rel="stylesheet">
{leaflet_head}
<style>{_CSS}</style>
</head>
<body>

<div class="top-bar">
  <div class="nav-inner">
    <span class="nav-title">{html_lib.escape(title)}</span>
    <button class="nav-btn" id="btn-prev" title="Previous page">&#9664;</button>
    <select id="page-select">{options}</select>
    <button class="nav-btn" id="btn-next" title="Next page">&#9654;</button>
    <span class="page-counter" id="page-counter">1 / {len(results)}</span>
  </div>
</div>

<div class="legend-panel" id="ent-legend">
  <div class="legend-inner">
    <span class="legend-label">Entities</span>
    {ent_chips}
  </div>
</div>

<div class="legend-panel" id="reg-legend">
  <div class="legend-inner">
    <span class="legend-label">Regions</span>
    {reg_chips}
  </div>
</div>

{"".join(page_divs)}

{leaflet_foot}
<script>{_JS}</script>
</body>
</html>"""

    with open(output_path, "w", encoding="utf-8") as fh:
        fh.write(final_html)

    size_mb = output_path.stat().st_size / 1e6
    logger.info("HTML edition written to %s (%.1f MB)", output_path, size_mb)
    return output_path

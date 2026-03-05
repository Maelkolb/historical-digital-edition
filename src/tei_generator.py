"""
TEI Generator
=============
Generates TEI XML for PageResult objects, compatible with the V1 Digital
Edition's embedded ``tei-xml-data`` script block.
"""

import logging
from html import escape
from typing import Dict, List, Optional

from .models import Entity, PageResult

logger = logging.getLogger(__name__)


def _tei_entity_tag(text: str, entity: Entity) -> str:
    """Wrap entity text in a TEI ``<rs>`` tag."""
    etype = entity.entity_type
    tei_type_map = {
        "Person": "person",
        "Location": "place",
        "Organisation": "org",
        "Animal": "animal",
        "Plant": "plant",
        "Natural Object": "object",
        "Artefact": "object",
        "Resource": "object",
        "Environment": "place",
        "Environmental Impact": "event",
        "Climate": "climate",
    }
    tei_type = tei_type_map.get(etype, "misc")
    context = escape(entity.context or "")
    return f'<rs type="{tei_type}" ana="{context}">{escape(text)}</rs>'


def _annotate_tei(text: str, entities: List[Entity]) -> str:
    """Insert TEI ``<rs>`` tags into *text*, skipping overlaps."""
    if not entities:
        return escape(text)

    sorted_ents = sorted(entities, key=lambda e: e.start_char)
    parts: list[str] = []
    cursor = 0

    for ent in sorted_ents:
        if ent.start_char < cursor:
            continue
        if ent.start_char > cursor:
            parts.append(escape(text[cursor:ent.start_char]))
        parts.append(_tei_entity_tag(text[ent.start_char:ent.end_char], ent))
        cursor = ent.end_char

    if cursor < len(text):
        parts.append(escape(text[cursor:]))

    return "".join(parts)


def generate_page_tei(result: PageResult) -> str:
    """Generate TEI XML for a single page."""
    pn = result.page_number
    parts: list[str] = []

    parts.append(f'<div type="page" n="{pn}" xml:id="page-{pn}">')
    parts.append(f'  <pb n="{pn}"/>')

    for block in result.structure.content_blocks:
        btype = block.get("block_type", "paragraph")
        content = block.get("content", "")

        if btype == "heading":
            parts.append(f"  <head>{escape(content or '')}</head>")
        elif btype == "paragraph":
            annotated = _annotate_tei(content or "", result.entities)
            parts.append(f"  <p>{annotated}</p>")
        elif btype == "table":
            cells = content.get("cells", []) if isinstance(content, dict) else []
            if cells:
                parts.append("  <table>")
                for i, row in enumerate(cells):
                    tag = "cell" if i > 0 else "cell"
                    role = ' role="label"' if i == 0 else ""
                    row_parts = [f"<{tag}{role}>{escape(str(c))}</{tag}>" for c in row]
                    parts.append(f"    <row>{''.join(row_parts)}</row>")
                parts.append("  </table>")
        elif btype == "list":
            if isinstance(content, list):
                parts.append("  <list>")
                for item in content:
                    parts.append(f"    <item>{escape(item)}</item>")
                parts.append("  </list>")

    # Footnotes
    for fn in result.structure.footnotes:
        marker = escape(fn.marker or "") if fn.marker else ""
        text = _annotate_tei(fn.text or "", result.entities)
        parts.append(f'  <note type="footnote" n="{marker}">{text}</note>')

    parts.append("</div>")
    return "\n".join(parts)


def generate_full_book_tei(results: List[PageResult]) -> str:
    """Generate complete TEI XML for all pages."""
    header = """\
<?xml version="1.0" encoding="UTF-8"?>
<?xml-model href="http://www.tei-c.org/release/xml/tei/custom/schema/relaxng/tei_all.rng" type="application/xml" schematypens="http://relaxng.org/ns/structure/1.0"?>
<TEI xmlns="http://www.tei-c.org/ns/1.0" xml:lang="de">
<teiHeader>
  <fileDesc>
    <titleStmt>
      <title>Volks- und Landeskunde des Fürstenthums Reuß j.L. - Digital Edition</title>
      <author>Ludwig Pfeiffer</author>
      <respStmt>
        <resp>Digital edition</resp>
        <name>Thuringia Digital Edition</name>
      </respStmt>
    </titleStmt>
    <publicationStmt>
      <publisher>Digital Edition - Chair of Computational Humanities - University of Passau - Creator: Tobias Perschl</publisher>
      <date>2026</date>
      <availability>
        <licence>Creative Commons Attribution</licence>
      </availability>
    </publicationStmt>
    <sourceDesc>
      <bibl>
        <title>Volks- und Landeskunde des Fürstenthums Reuß j.L.</title>
        <author>Georg Brückner</author>
        <date>1880</date>
        <pubPlace>Gera</pubPlace>
      </bibl>
    </sourceDesc>
  </fileDesc>
  <encodingDesc>
    <projectDesc>
      <p>Digital edition with annotated entities including locations, organisms, natural objects, and environmental features.</p>
    </projectDesc>
  </encodingDesc>
  <profileDesc>
    <langUsage>
      <language ident="de">German</language>
      <language ident="en">English</language>
    </langUsage>
  </profileDesc>
</teiHeader>
<text>
<body>"""

    footer = """\
</body>
</text>
</TEI>"""

    page_xmls = [generate_page_tei(r) for r in sorted(results, key=lambda r: r.page_number)]
    return header + "\n" + "\n".join(page_xmls) + "\n" + footer


def build_tei_data(results: List[PageResult]) -> Dict:
    """
    Build a TEI data dict compatible with the V1 edition's
    ``tei-xml-data`` script block.

    Returns:
        ``{"fullBook": str, "pages": {"N": str, ...}}``
    """
    pages: Dict[str, str] = {}
    for r in results:
        pages[str(r.page_number)] = generate_page_tei(r)

    return {
        "fullBook": generate_full_book_tei(results),
        "pages": pages,
    }

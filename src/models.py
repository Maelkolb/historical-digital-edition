"""
Data structures for the Historical Digital Edition pipeline.
"""

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Any, Optional
from datetime import datetime


@dataclass
class TableData:
    """Represents table content extracted from a page."""
    rows: int
    cols: int
    cells: List[List[str]]
    caption: Optional[str] = None

    def to_dict(self) -> Dict:
        return {
            "rows": self.rows,
            "cols": self.cols,
            "cells": self.cells,
            "caption": self.caption,
        }


@dataclass
class Footnote:
    """Represents a footnote with its marker and text."""
    marker: str
    text: str


@dataclass
class PageStructure:
    """
    Represents a page's structural elements in their original reading order.
    content_blocks is an interleaved list of paragraphs, headings, lists, and tables.
    """
    page_number_printed: Optional[str]
    header: Optional[str]
    content_blocks: List[Dict[str, Any]]  # ordered sequence of blocks
    footnotes: List[Footnote]


@dataclass
class Entity:
    """Represents a single annotated named entity."""
    text: str
    entity_type: str
    start_char: int
    end_char: int
    context: Optional[str] = None


@dataclass
class PageResult:
    """Stores the complete processing result for a single page."""
    page_number: int
    image_filename: str
    structure: PageStructure
    ocr_text: str
    entities: List[Entity]
    processing_timestamp: str
    model_used: str

    def to_dict(self) -> Dict:
        """Convert to a JSON-serialisable dictionary."""
        return {
            "page_number": self.page_number,
            "image_filename": self.image_filename,
            "structure": {
                "page_number_printed": self.structure.page_number_printed,
                "header": self.structure.header,
                "content_blocks": self.structure.content_blocks,
                "footnotes": [
                    {"marker": fn.marker, "text": fn.text}
                    for fn in self.structure.footnotes
                ],
            },
            "ocr_text": self.ocr_text,
            "entities": [asdict(e) for e in self.entities],
            "processing_timestamp": self.processing_timestamp,
            "model_used": self.model_used,
        }

    @classmethod
    def from_dict(cls, d: Dict) -> "PageResult":
        """Reconstruct a PageResult from a dictionary (e.g. loaded from JSON)."""
        struct = d["structure"]
        footnotes = [
            Footnote(marker=fn.get("marker", ""), text=fn.get("text", ""))
            for fn in struct.get("footnotes", [])
        ]
        structure = PageStructure(
            page_number_printed=struct.get("page_number_printed"),
            header=struct.get("header"),
            content_blocks=struct.get("content_blocks", []),
            footnotes=footnotes,
        )
        entities = [
            Entity(
                text=e["text"],
                entity_type=e["entity_type"],
                start_char=e["start_char"],
                end_char=e["end_char"],
                context=e.get("context"),
            )
            for e in d.get("entities", [])
        ]
        return cls(
            page_number=d["page_number"],
            image_filename=d["image_filename"],
            structure=structure,
            ocr_text=d.get("ocr_text", ""),
            entities=entities,
            processing_timestamp=d.get("processing_timestamp", ""),
            model_used=d.get("model_used", ""),
        )

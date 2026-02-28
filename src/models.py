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

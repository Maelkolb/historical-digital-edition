"""
Data structures for the Historical Digital Edition pipeline.
"""

from dataclasses import dataclass, asdict
from typing import Dict, List, Any, Optional
from enum import Enum


class RegionType(str, Enum):
    """Types of regions that can be detected on a page."""
    HEADING = "heading"
    SUBHEADING = "subheading"
    PARAGRAPH = "paragraph"
    TABLE = "table"
    FOOTNOTE = "footnote"
    DATE = "date"
    IMAGE = "image"
    CAPTION = "caption"
    LIST = "list"
    PAGE_NUMBER = "page_number"
    HEADER = "header"
    MARGINALIA = "marginalia"


@dataclass
class Region:
    """A detected region on a page with its type and reading order."""
    region_type: str
    region_index: int
    content: str  # transcription for text regions, description for images
    is_visual: bool = False  # True if region is an image/illustration (described, not transcribed)
    table_data: Optional[Dict[str, Any]] = None  # rows, cols, cells for tables

    def to_dict(self) -> Dict:
        d = {
            "region_type": self.region_type,
            "region_index": self.region_index,
            "content": self.content,
            "is_visual": self.is_visual,
        }
        if self.table_data is not None:
            d["table_data"] = self.table_data
        return d

    @classmethod
    def from_dict(cls, d: Dict) -> "Region":
        return cls(
            region_type=d["region_type"],
            region_index=d["region_index"],
            content=d.get("content", ""),
            is_visual=d.get("is_visual", False),
            table_data=d.get("table_data"),
        )


@dataclass
class Entity:
    """Represents a single annotated named entity."""
    text: str
    entity_type: str
    start_char: int
    end_char: int
    context: Optional[str] = None


@dataclass
class GeoLocation:
    """Geographic coordinates for a location entity."""
    name: str
    lat: float
    lon: float
    display_name: str


@dataclass
class PageResult:
    """Stores the complete processing result for a single page."""
    page_number: int
    image_filename: str
    regions: List[Region]
    full_text: str  # combined text from all text regions for NER
    entities: List[Entity]
    locations: List[GeoLocation]
    processing_timestamp: str
    model_used: str

    def to_dict(self) -> Dict:
        return {
            "page_number": self.page_number,
            "image_filename": self.image_filename,
            "regions": [r.to_dict() for r in self.regions],
            "full_text": self.full_text,
            "entities": [asdict(e) for e in self.entities],
            "locations": [asdict(loc) for loc in self.locations],
            "processing_timestamp": self.processing_timestamp,
            "model_used": self.model_used,
        }

    @classmethod
    def from_dict(cls, d: Dict) -> "PageResult":
        regions = [Region.from_dict(r) for r in d.get("regions", [])]
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
        locations = [
            GeoLocation(
                name=loc["name"],
                lat=loc["lat"],
                lon=loc["lon"],
                display_name=loc["display_name"],
            )
            for loc in d.get("locations", [])
        ]
        return cls(
            page_number=d["page_number"],
            image_filename=d["image_filename"],
            regions=regions,
            full_text=d.get("full_text", ""),
            entities=entities,
            locations=locations,
            processing_timestamp=d.get("processing_timestamp", ""),
            model_used=d.get("model_used", ""),
        )

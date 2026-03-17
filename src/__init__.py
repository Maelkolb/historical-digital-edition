"""historical-digital-edition – LLM pipeline for historical document digitization."""
from .models import Entity, GeoLocation, Region, RegionType, PageResult
from .pipeline import process_book, process_page, load_results_from_json
from .html_generator import generate_html_edition
from .geocoding import geocode_entities
from .region_detection import detect_regions
from .transcription import transcribe_regions
from .ner import perform_ner

__all__ = [
    "Entity",
    "GeoLocation",
    "Region",
    "RegionType",
    "PageResult",
    "process_book",
    "process_page",
    "load_results_from_json",
    "generate_html_edition",
    "geocode_entities",
    "detect_regions",
    "transcribe_regions",
    "perform_ner",
]

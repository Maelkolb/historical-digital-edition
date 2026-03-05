"""historical-digital-edition – LLM pipeline for historical German text."""
from .models import Entity, Footnote, PageResult, PageStructure, TableData
from .pipeline import (
    process_book,
    process_page,
    load_results_from_json,
    merge_results,
    find_incomplete_pages,
    reprocess_pages,
)
from .html_generator import generate_html_edition
from .geocoding import geocode_entities, build_page_map_data
from .v1_renderer import render_v1_page
from .v1_merger import merge_into_v1
from .tei_generator import build_tei_data, generate_page_tei, generate_full_book_tei

__all__ = [
    "Entity",
    "Footnote",
    "PageResult",
    "PageStructure",
    "TableData",
    "process_book",
    "process_page",
    "load_results_from_json",
    "merge_results",
    "find_incomplete_pages",
    "reprocess_pages",
    "generate_html_edition",
    "geocode_entities",
    "build_page_map_data",
    "render_v1_page",
    "merge_into_v1",
    "build_tei_data",
    "generate_page_tei",
    "generate_full_book_tei",
]

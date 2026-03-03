"""historical-digital-edition – LLM pipeline for historical German text."""
from .models import Entity, Footnote, PageResult, PageStructure, TableData
from .pipeline import process_book, process_page, load_results_from_json, merge_results
from .html_generator import generate_html_edition

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
    "generate_html_edition",
]

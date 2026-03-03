"""
Geocoding Module
================
Resolves Location entity names to geographic coordinates using the
OpenStreetMap Nominatim API, and builds per-page map data structures
compatible with the V1 Digital Edition's Leaflet integration.
"""

import logging
import time
from typing import Dict, List, Optional
from urllib.parse import quote_plus

import requests

from .models import Entity

logger = logging.getLogger(__name__)

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "HistoricalDigitalEdition/1.0 (academic research)"


def geocode_location(
    name: str,
    delay: float = 1.0,
    session: Optional[requests.Session] = None,
) -> Optional[Dict]:
    """
    Query Nominatim for a single location name.

    Returns:
        ``{"lat": float, "lon": float, "display_name": str}`` or *None*.
    """
    sess = session or requests.Session()
    params = {
        "q": name,
        "format": "json",
        "limit": 1,
        "accept-language": "de,en",
    }
    headers = {"User-Agent": USER_AGENT}

    try:
        resp = sess.get(NOMINATIM_URL, params=params, headers=headers, timeout=10)
        resp.raise_for_status()
        results = resp.json()
        if results:
            hit = results[0]
            return {
                "lat": float(hit["lat"]),
                "lon": float(hit["lon"]),
                "display_name": hit.get("display_name", name),
            }
    except (requests.RequestException, ValueError, KeyError) as exc:
        logger.warning("Geocode failed for %r: %s", name, exc)

    return None


def geocode_entities(
    entities: List[Entity],
    cache: Optional[Dict[str, Optional[Dict]]] = None,
    delay: float = 1.0,
) -> Dict[str, Optional[Dict]]:
    """
    Geocode all *Location* entities, reusing *cache* for repeated names.

    Args:
        entities: List of Entity objects (only ``entity_type == "Location"``
                  will be queried).
        cache:    Mutable dict mapping location name → geocode result (or
                  *None* for failed lookups).  Updated in-place.
        delay:    Seconds to wait between Nominatim requests.

    Returns:
        The (updated) cache dict.
    """
    if cache is None:
        cache = {}

    session = requests.Session()
    location_names = list(dict.fromkeys(
        e.text for e in entities if e.entity_type == "Location"
    ))

    new_queries = [n for n in location_names if n not in cache]
    if new_queries:
        logger.info("Geocoding %d new location names…", len(new_queries))

    for name in new_queries:
        result = geocode_location(name, delay=delay, session=session)
        cache[name] = result
        if result:
            logger.debug("  %s → %.4f, %.4f", name, result["lat"], result["lon"])
        else:
            logger.debug("  %s → not found", name)
        time.sleep(delay)

    return cache


def build_page_map_data(
    page_number: int,
    entities: List[Entity],
    cache: Dict[str, Optional[Dict]],
) -> Optional[Dict]:
    """
    Build a V1-compatible map data entry for one page.

    Returns a dict like::

        {
            "locations": [{"name": ..., "lat": ..., "lon": ..., "display": ...}, ...],
            "center": [lat, lon],
            "count": N,
        }

    or *None* if no locations could be geocoded.
    """
    locations = []
    seen = set()

    for e in entities:
        if e.entity_type != "Location":
            continue
        if e.text in seen:
            continue
        seen.add(e.text)

        geo = cache.get(e.text)
        if geo is None:
            continue
        locations.append({
            "name": e.text,
            "lat": geo["lat"],
            "lon": geo["lon"],
            "display": geo["display_name"],
        })

    if not locations:
        return None

    avg_lat = sum(loc["lat"] for loc in locations) / len(locations)
    avg_lon = sum(loc["lon"] for loc in locations) / len(locations)

    return {
        "locations": locations,
        "center": [avg_lat, avg_lon],
        "count": len(locations),
    }

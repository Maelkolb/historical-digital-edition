"""
Geocoding (Step 4)
==================
Resolves Location entity names to geographic coordinates using the
OpenStreetMap Nominatim API.
"""

import logging
import time
from typing import Dict, List, Optional

import requests

from .models import Entity, GeoLocation

logger = logging.getLogger(__name__)

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "HistoricalDigitalEdition/2.0 (academic research)"


def geocode_location(
    name: str,
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
) -> List[GeoLocation]:
    """
    Geocode all Location entities, returning GeoLocation objects.

    Args:
        entities: List of Entity objects (only Location types are queried).
        cache:    Mutable dict mapping location name -> geocode result.
                  Updated in-place for reuse across pages.
        delay:    Seconds between Nominatim requests (rate limiting).

    Returns:
        List of GeoLocation objects for successfully geocoded locations.
    """
    if cache is None:
        cache = {}

    session = requests.Session()
    location_names = list(dict.fromkeys(
        e.text for e in entities if e.entity_type == "Location"
    ))

    new_queries = [n for n in location_names if n not in cache]
    if new_queries:
        logger.info("Geocoding %d new location names...", len(new_queries))

    for name in new_queries:
        result = geocode_location(name, session=session)
        cache[name] = result
        if result:
            logger.debug("  %s -> %.4f, %.4f", name, result["lat"], result["lon"])
        else:
            logger.debug("  %s -> not found", name)
        time.sleep(delay)

    locations: List[GeoLocation] = []
    seen = set()
    for name in location_names:
        if name in seen:
            continue
        seen.add(name)
        geo = cache.get(name)
        if geo:
            locations.append(GeoLocation(
                name=name,
                lat=geo["lat"],
                lon=geo["lon"],
                display_name=geo["display_name"],
            ))

    return locations

import json
import time
import urllib.parse
import urllib.request

_cache = {}


def _label(properties):
    first = properties.get("name") or properties.get("street") or properties.get("city") or "Posizione"
    house = properties.get("housenumber")
    if house and house not in first:
        first = f"{first} {house}"
    parts = [first]
    for key in ("district", "city", "county", "state"):
        value = properties.get(key)
        if value and value not in parts and value not in first:
            parts.append(value)
    return ", ".join(parts[:3])


def search_places(query, limit=6):
    normalized = " ".join(query.strip().split())
    if len(normalized) < 3:
        return []
    cache_key = normalized.lower()
    cached = _cache.get(cache_key)
    if cached and time.time() - cached[0] < 3600:
        return cached[1]
    # Il server pubblico Photon non accetta sempre il parametro `lang`.
    # Il bias geografico mantiene comunque i risultati vicini alla Puglia.
    params = urllib.parse.urlencode({
        "q": normalized, "limit": limit,
        "lat": 40.6327, "lon": 17.9418,
    })
    request = urllib.request.Request(
        f"https://photon.komoot.io/api/?{params}",
        headers={"User-Agent": "BusBrindisiPersonal/1.0"},
    )
    with urllib.request.urlopen(request, timeout=8) as response:
        payload = json.load(response)
    results = []
    for feature in payload.get("features", []):
        coordinates = feature.get("geometry", {}).get("coordinates", [])
        if len(coordinates) < 2:
            continue
        properties = feature.get("properties", {})
        # Mantiene risultati italiani; Photon può omettere countrycode su alcuni POI.
        country = (properties.get("countrycode") or "IT").upper()
        if country != "IT":
            continue
        results.append({
            "type": "place", "name": _label(properties),
            "lat": coordinates[1], "lon": coordinates[0],
            "category": properties.get("type") or properties.get("osm_value") or "luogo",
        })
    _cache[cache_key] = (time.time(), results)
    if len(_cache) > 250:
        oldest = min(_cache, key=lambda key: _cache[key][0])
        _cache.pop(oldest, None)
    return results

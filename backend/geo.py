"""Coordinates for United States zip codes and cities, from the bundled GeoNames file.

backend/geo/US.txt is the unmodified GeoNames postal code dump (CC BY 4.0,
https://www.geonames.org). It loads on first use. Nothing here touches the network.
"""
import csv
import re
import threading
from pathlib import Path

FILE = Path(__file__).resolve().parent / "geo" / "US.txt"

_lock = threading.Lock()
_zips = None    # "63101" -> (lat, lon)
_cities = None  # ("saintlouis", "MO") -> (lat, lon), the mean of the city's zips
_counts = None  # ("saintlouis", "MO") -> how many zips the city has
_names = None   # "saintlouis" -> {"MO", ...}
_states = None  # "missouri" -> "MO"
_boxes = None   # "MO" -> [min_lat, max_lat, min_lon, max_lon]


def norm_city(name):
    s = re.sub(r"[^a-z0-9 ]+", " ", (name or "").lower())
    words = ["saint" if w == "st" else "fort" if w == "ft" else "mount" if w == "mt" else w for w in s.split()]
    return "".join(words)


def _load():
    global _zips, _cities, _counts, _names, _states, _boxes
    with _lock:
        if _zips is not None:
            return
        zips, sums, names, states, boxes = {}, {}, {}, {}, {}
        with open(FILE, encoding="utf-8", newline="") as f:
            for r in csv.reader(f, delimiter="\t", quoting=csv.QUOTE_NONE):
                if len(r) < 11:
                    continue
                try:
                    lat, lon = float(r[9]), float(r[10])
                except ValueError:
                    continue
                postal, city, state_name, state = r[1], r[2], r[3], r[4].upper()
                zips.setdefault(postal, (lat, lon))
                if not state:
                    continue
                states[norm_city(state_name)] = state
                key = (norm_city(city), state)
                s = sums.setdefault(key, [0.0, 0.0, 0])
                s[0] += lat; s[1] += lon; s[2] += 1
                names.setdefault(key[0], set()).add(state)
                b = boxes.setdefault(state, [lat, lat, lon, lon])
                b[0], b[1], b[2], b[3] = min(b[0], lat), max(b[1], lat), min(b[2], lon), max(b[3], lon)
        _cities = {k: (round(v[0] / v[2], 5), round(v[1] / v[2], 5)) for k, v in sums.items()}
        _counts = {k: v[2] for k, v in sums.items()}
        _names, _states, _boxes = names, states, boxes
        _zips = zips


def state_code(region):
    """'CO' or 'Colorado' -> 'CO'. Unknown -> None."""
    _load()
    r = (region or "").strip()
    if not r:
        return None
    if len(r) == 2 and r.upper() in _boxes:
        return r.upper()
    return _states.get(norm_city(r))


def by_zip(postal):
    _load()
    m = re.match(r"\s*(\d{5})", str(postal or ""))
    return _zips.get(m.group(1)) if m else None


def by_city(city, region=None, prefer=None):
    """City center.

    With no state: the only state that has a city of that name. When several do, the
    preferred state if it has one, else the state where that city has the most zip codes.
    """
    _load()
    name = norm_city(city)
    if not name:
        return None
    state = state_code(region)
    if state:
        return _cities.get((name, state))
    if (region or "").strip():
        return None
    found = _names.get(name) or ()
    if not found:
        return None
    home = state_code(prefer)
    best = home if home in found else max(sorted(found), key=lambda s: _counts[(name, s)])
    return _cities.get((name, best))


def state_box(state):
    """(min_lat, max_lat, min_lon, max_lon) of a state's zip codes, or None."""
    _load()
    b = _boxes.get((state or "").upper())
    return tuple(b) if b else None

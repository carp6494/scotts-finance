"""Local business lookup against an Overture Maps Places extract.

scripts/fetch_places.py writes data/overture.db once. This module only reads it.
With no file, every lookup returns None and the app works as before.

A lookup answers only when exactly one business fits. A longer or shorter form of the
name fits too ("Lowe's" and "Lowe's Home Improvement"), so two branches of a chain
listed under different forms cancel each other out. It looks:
  1. in the same city
  2. within about 10 km of the city center, because banks and map data often
     disagree on which suburb a shop is in
With no city, only an exact name that is unique in the whole extract counts.
"""
import logging
import re
import sqlite3
import threading

from db import DATA
from geo import norm_city

log = logging.getLogger("overture")
DB_PATH = DATA / "overture.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS places (
  id TEXT PRIMARY KEY, name TEXT, name_norm TEXT, address TEXT, city TEXT, city_norm TEXT, region TEXT,
  postal TEXT, country TEXT, lat REAL, lon REAL, website TEXT, category TEXT, brand TEXT, confidence REAL
);
CREATE INDEX IF NOT EXISTS ix_places_name ON places(name_norm);
CREATE INDEX IF NOT EXISTS ix_places_city ON places(city_norm);
CREATE INDEX IF NOT EXISTS ix_places_lat ON places(lat);
"""

MIN_LOOSE = 5        # shortest name allowed to match a longer or shorter form
NEAR_LAT = 0.09      # about 10 km
NEAR_LON = 0.11

_lock = threading.Lock()
_con = None
_opened = False
_cache = {}

_PREFIX = re.compile(r"^(sq|tst|pp|paypal|sp|dd|py|fsp|in)\s*\*\s*", re.I)
_DROP = {"the", "inc", "llc", "co", "corp", "ltd", "company"}


def norm_name(name):
    """'SQ *The Joe's BBQ #12' -> 'joesbbq'."""
    s = _PREFIX.sub("", (name or "").strip()).lower()
    s = s.replace("&", " and ").replace("'", "").replace("’", "")
    s = re.sub(r"[#]\s*\d+\s*$", " ", s)
    s = re.sub(r"\s-\s*\w$", " ", s)  # a stray code after a dash: "Island Grill - K"
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    words = [w for w in s.split() if w not in _DROP]
    while len(words) > 1 and words[-1].isdigit():
        words.pop()
    return "".join(words)


def reset():
    """Forget the open file. Tests and the fetch script call this after writing a new one."""
    global _con, _opened
    with _lock:
        if _con is not None:
            _con.close()
        _con, _opened = None, False
        _cache.clear()


def _db():
    global _con, _opened
    if not _opened:
        _opened = True
        if DB_PATH.exists():
            try:
                _con = sqlite3.connect(f"file:{DB_PATH.as_posix()}?mode=ro", uri=True, check_same_thread=False)
                _con.row_factory = sqlite3.Row
            except sqlite3.Error as e:
                log.warning("could not open %s: %s", DB_PATH.name, e)
                _con = None
    return _con


def available():
    with _lock:
        return _db() is not None


_EXACT = "name_norm=?"
_LOOSE = "length(name_norm)>=? AND (name_norm LIKE ? OR ? LIKE name_norm || '%')"


def _one(con, name_sql, name_args, where_sql, where_args):
    """(row or None, how many fit, capped at 2)."""
    rows = con.execute(f"SELECT * FROM places WHERE {where_sql} AND {name_sql} LIMIT 2", list(where_args) + list(name_args)).fetchall()
    return (dict(rows[0]) if len(rows) == 1 else None), len(rows)


def _search(con, key, city, region, center):
    exact = (_EXACT, [key])
    loose = (_LOOSE, [MIN_LOOSE, key + "%", key]) if len(key) >= MIN_LOOSE else None
    if not city:
        return _one(con, *exact, "1=1", [])[0]
    areas = []
    where, args = "city_norm=?", [norm_city(city)]
    if region:
        where += " AND UPPER(COALESCE(region,''))=?"
        args.append(region.strip().upper())
    areas.append((where, args))
    if center:
        lat, lon = center
        areas.append(("lat BETWEEN ? AND ? AND lon BETWEEN ? AND ?", [lat - NEAR_LAT, lat + NEAR_LAT, lon - NEAR_LON, lon + NEAR_LON]))
    # Longer and shorter forms count as rivals too. A chain often lists one branch under the
    # short name and the rest under a long one, and picking the short one would be a guess.
    for where, args in areas:
        row, n = _one(con, *(loose or exact), where, args)
        if row:
            return row
        if n > 1:
            return None  # several fit, so a wider search would only be a guess
    return None


def candidates(name, city, region=None, center=None, limit=60):
    """Every business that fits, from the first area that has any: the city, then near its center."""
    key = norm_name(name)
    if len(key) < 3 or not city:
        return []
    name_sql, name_args = (_LOOSE, [MIN_LOOSE, key + "%", key]) if len(key) >= MIN_LOOSE else (_EXACT, [key])
    areas = [("city_norm=?" + (" AND UPPER(COALESCE(region,''))=?" if region else ""),
              [norm_city(city)] + ([region.strip().upper()] if region else []))]
    if center:
        lat, lon = center
        areas.append(("lat BETWEEN ? AND ? AND lon BETWEEN ? AND ?", [lat - NEAR_LAT, lat + NEAR_LAT, lon - NEAR_LON, lon + NEAR_LON]))
    with _lock:
        con = _db()
        if con is None:
            return []
        try:
            for where, args in areas:
                rows = con.execute(f"SELECT * FROM places WHERE {where} AND {name_sql} LIMIT ?", args + name_args + [limit]).fetchall()
                if rows:
                    return [dict(r) for r in rows]
        except sqlite3.Error as e:
            log.warning("place lookup failed: %s", e)
    return []


def match(name, city=None, region=None, center=None):
    """The one business that fits, or None. center is the (lat, lon) of the city, when known."""
    key = norm_name(name)
    if len(key) < 3:
        return None
    ck = (key, norm_city(city) if city else None, (region or "").strip().upper(), center)
    with _lock:
        con = _db()
        if con is None:
            return None
        if ck not in _cache:
            try:
                _cache[ck] = _search(con, key, city, region, center)
            except sqlite3.Error as e:
                log.warning("place lookup failed: %s", e)
                return None
        hit = _cache[ck]
    return dict(hit) if hit else None

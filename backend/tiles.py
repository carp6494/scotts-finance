"""Map squares for the satellite, hybrid, terrain and 3D building views.

The browser never talks to a map service. It asks this app, and this app fetches from a
short fixed list of free public services, then keeps each square in data/tiles so it
loads from disk the next time. A request to a service carries only the square's zoom
and position and a generic user agent. Nothing about the owner or any purchase.

Each group has a setting. With a setting off, squares already on disk still load and
nothing new is fetched.

  usgs       Aerial photos and labeled photos. U.S. Geological Survey, The National Map. Public domain.
  terrain    Ground elevation. Terrain Tiles open data hosted by Amazon Web Services.
  buildings  Building outlines and heights. OpenFreeMap, from OpenStreetMap data.
"""
import logging
import threading
import time

import httpx

import db
from db import DATA

log = logging.getLogger("tiles")

TILES = DATA / "tiles"
AGENT = "Mozilla/5.0 (compatible; map-tiles)"
MAX_BYTES = 3 * 1024 * 1024
USGS = "https://basemap.nationalmap.gov/arcgis/rest/services/{name}/MapServer/tile/{z}/{y}/{x}"
OFM_INDEX = "https://tiles.openfreemap.org/planet"

SOURCES = {
    "imagery": {"group": "usgs", "url": USGS.replace("{name}", "USGSImageryOnly"), "ext": "jpg", "type": "image/jpeg", "maxzoom": 16},
    "hybrid": {"group": "usgs", "url": USGS.replace("{name}", "USGSImageryTopo"), "ext": "jpg", "type": "image/jpeg", "maxzoom": 16},
    "dem": {"group": "terrain", "url": "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png", "ext": "png", "type": "image/png", "maxzoom": 14},
    "buildings": {"group": "buildings", "url": None, "ext": "pbf", "type": "application/x-protobuf", "maxzoom": 14},
}
# Scott approved the USGS photos on 2026-11-13. The other two start off until switched on in Settings.
GROUPS = {"usgs": True, "terrain": False, "buildings": False}

_client = None
_lock = threading.Lock()
_ofm = {"url": None, "at": 0.0}

db.run("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")


class Refused(Exception):
    """The square is not on disk and its service is switched off."""


def settings():
    rows = {r["key"]: r["value"] for r in db.q("SELECT key, value FROM settings WHERE key LIKE 'tiles_%'")}
    return {g: (rows.get(f"tiles_{g}", "1" if default else "0") == "1") for g, default in GROUPS.items()}


def set_setting(group, on):
    if group not in GROUPS:
        raise ValueError(f"Unknown map setting: {group}")
    db.run("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (f"tiles_{group}", "1" if on else "0"))


def _http():
    global _client
    with _lock:
        if _client is None:
            _client = httpx.Client(timeout=20, follow_redirects=False, headers={"User-Agent": AGENT},
                                   limits=httpx.Limits(max_connections=16, max_keepalive_connections=8))
        return _client


def _fetch(url):
    """GET one address. Returns the body, or None for anything but a plain 200 within the size cap."""
    try:
        r = _http().get(url)
    except httpx.HTTPError as e:
        log.info("map square fetch failed: %s", type(e).__name__)
        return None
    if r.status_code != 200 or not r.content or len(r.content) > MAX_BYTES:
        return None
    return r.content


def _buildings_url():
    """OpenFreeMap puts a dated folder in its address, so read the current one from its index once a day."""
    with _lock:
        fresh = _ofm["url"] and time.time() - _ofm["at"] < 86400
    if fresh:
        return _ofm["url"]
    try:
        r = _http().get(OFM_INDEX)
        url = r.json()["tiles"][0] if r.status_code == 200 else None
    except (httpx.HTTPError, ValueError, KeyError, IndexError):
        url = None
    if not (isinstance(url, str) and url.startswith("https://tiles.openfreemap.org/") and all(k in url for k in ("{z}", "{x}", "{y}"))):
        return _ofm["url"]
    with _lock:
        _ofm["url"], _ofm["at"] = url, time.time()
    return url


def path_for(source, z, x, y):
    return TILES / source / str(z) / str(x) / f"{y}.{SOURCES[source]['ext']}"


def get(source, z, x, y):
    """(bytes, media type) for one square, or None when it does not exist. Raises Refused or ValueError."""
    spec = SOURCES.get(source)
    if not spec:
        raise ValueError("Unknown map source")
    if not (0 <= z <= spec["maxzoom"] and 0 <= x < 2 ** z and 0 <= y < 2 ** z):
        raise ValueError("No such map square")
    f = path_for(source, z, x, y)
    if f.exists():
        return f.read_bytes(), spec["type"]
    if not settings()[spec["group"]]:
        raise Refused(spec["group"])
    template = spec["url"] or _buildings_url()
    if not template:
        return None
    body = _fetch(template.replace("{z}", str(z)).replace("{x}", str(x)).replace("{y}", str(y)))
    if body is None:
        return None
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(f".{threading.get_ident()}.tmp")
    tmp.write_bytes(body)
    tmp.replace(f)
    return body, spec["type"]


def saved():
    """How much disk the saved squares use."""
    count = size = 0
    if TILES.exists():
        for f in TILES.rglob("*"):
            if f.is_file() and f.suffix != ".tmp":
                count += 1
                size += f.stat().st_size
    return {"count": count, "bytes": size}


def clear():
    """Delete every saved square. Returns how many were removed."""
    n = 0
    if TILES.exists():
        for f in sorted(TILES.rglob("*"), reverse=True):
            if f.is_file():
                f.unlink()
                n += 1
            else:
                try:
                    f.rmdir()
                except OSError:
                    pass
    return n

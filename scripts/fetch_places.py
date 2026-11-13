"""One-time download of local businesses from Overture Maps Places.

Usage, from the app folder:
    .venv\\Scripts\\python -m pip install -r requirements-tools.txt
    .venv\\Scripts\\python scripts\\fetch_places.py --states XX YY

It downloads every place inside the bounding box of the named states and writes
data\\overture.db. That file stays on this PC. The app reads it to turn a merchant
name and city into a street address. Run it again any time to refresh.

Overture Places is open data: CDLA Permissive 2.0, with some records under Apache 2.0.
See https://docs.overturemaps.org/guides/places
"""
import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

import geo  # noqa: E402
import overture  # noqa: E402

MIN_CONFIDENCE = 0.5
COLUMNS = ("id", "names", "addresses", "websites", "brand", "basic_category", "confidence", "operating_status", "bbox")


def box_for(states):
    boxes = []
    for s in states:
        code = geo.state_code(s)
        if not code:
            raise SystemExit(f"Unknown state: {s}. Use a two-letter code such as CO.")
        boxes.append(geo.state_box(code))
    pad = 0.05
    return (min(b[2] for b in boxes) - pad, min(b[0] for b in boxes) - pad,
            max(b[3] for b in boxes) + pad, max(b[1] for b in boxes) + pad)  # west, south, east, north


def to_row(r):
    """One Overture record -> one places row, or None when it is not worth keeping."""
    name = ((r.get("names") or {}).get("primary") or "").strip()
    conf = r.get("confidence") or 0
    box = r.get("bbox") or {}
    if not name or conf < MIN_CONFIDENCE or box.get("xmin") is None or box.get("ymin") is None:
        return None
    if (r.get("operating_status") or "open") not in ("open", "temporarily_closed"):
        return None
    addr = ((r.get("addresses") or [None])[0]) or {}
    city = (addr.get("locality") or "").strip()
    key = overture.norm_name(name)
    if not key or not city:
        return None
    sites = r.get("websites") or []
    brand = ((r.get("brand") or {}).get("names") or {}).get("primary")
    return (r["id"], name, key, addr.get("freeform"), city, overture.norm_city(city), (addr.get("region") or "").upper() or None,
            addr.get("postcode"), addr.get("country"), round(box["ymin"], 6), round(box["xmin"], 6),
            sites[0] if sites else None, r.get("basic_category"), brand, round(conf, 3))


def main():
    ap = argparse.ArgumentParser(description="Download local businesses for the place lookup.")
    ap.add_argument("--states", nargs="+", required=True, help="two-letter state codes")
    args = ap.parse_args()
    try:
        from overturemaps import core
    except ImportError:
        raise SystemExit("Install the tool first: .venv\\Scripts\\python -m pip install -r requirements-tools.txt")

    bbox = box_for(args.states)
    print(f"Downloading places for {len(args.states)} state(s). This can take a few minutes.")
    reader = core.record_batch_reader("place", bbox)
    if reader is None:
        raise SystemExit("Overture returned nothing. Check the internet connection and try again.")

    tmp = overture.DB_PATH.with_suffix(".new")
    tmp.unlink(missing_ok=True)
    con = sqlite3.connect(tmp)
    con.executescript(overture.SCHEMA)
    seen = kept = 0
    for batch in reader:
        cols = [c for c in COLUMNS if c in batch.schema.names]
        rows = []
        for r in batch.select(cols).to_pylist():
            seen += 1
            row = to_row(r)
            if row:
                rows.append(row)
        con.executemany("INSERT OR REPLACE INTO places VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
        kept += len(rows)
        print(f"  read {seen:,}, kept {kept:,}", end="\r")
    con.commit()
    con.close()
    overture.reset()
    tmp.replace(overture.DB_PATH)
    print(f"\nDone. {kept:,} places saved to data\\{overture.DB_PATH.name}. Restart the app to use them.")


if __name__ == "__main__":
    main()

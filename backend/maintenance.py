"""Daily backups (keep 30) and retention purge (transactions older than 7 years)."""
import logging
import sqlite3
from datetime import date, timedelta

import db

log = logging.getLogger("maintenance")
BACKUPS = db.ROOT / "backups"
KEEP = 30
RETENTION_YEARS = 7


def backup():
    BACKUPS.mkdir(exist_ok=True)
    dest = BACKUPS / f"finance-{date.today().isoformat()}.db"
    if not dest.exists():
        with db._lock:
            out = sqlite3.connect(dest)
            db._con.backup(out)
            out.close()
        log.info("backup written: %s", dest.name)
    files = sorted(BACKUPS.glob("finance-*.db"))
    for old in files[:-KEEP]:
        try:
            old.unlink()
        except OSError:
            pass


def purge():
    cutoff = (date.today() - timedelta(days=365 * RETENTION_YEARS)).isoformat()
    n = db.one("SELECT COUNT(*) AS n FROM transactions WHERE date < ?", (cutoff,))["n"]
    if n:
        db.run("DELETE FROM transactions WHERE date < ?", (cutoff,))
        log.info("retention purge removed %s transactions older than %s", n, cutoff)


def daily():
    try:
        backup()
        purge()
    except Exception as e:
        log.warning("maintenance failed: %s", e)

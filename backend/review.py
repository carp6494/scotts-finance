"""Review queue: posted transactions the owner has not looked at yet.

New rows arrive with reviewed=0. A pending charge waits until it posts.
"""
import db

KEY = "review_started"
KEEP_NEW = 5
WAITING = "COALESCE(reviewed,0)=0 AND COALESCE(pending,0)=0"

db.run("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")


def start() -> bool:
    """Run once, the first time the queue exists. Every transaction already stored counts as
    reviewed, except the newest few, which stay in the queue so it has something to show.
    Returns True when it did the work."""
    if db.one("SELECT 1 FROM settings WHERE key=?", (KEY,)):
        return False
    db.run("UPDATE transactions SET reviewed=1")
    db.run(f"""UPDATE transactions SET reviewed=0 WHERE transaction_id IN (
                 SELECT transaction_id FROM transactions WHERE COALESCE(pending,0)=0
                 ORDER BY date DESC, transaction_id LIMIT {KEEP_NEW})""")
    db.run("INSERT OR REPLACE INTO settings (key, value) VALUES (?, '1')", (KEY,))
    return True


def count() -> int:
    return db.one(f"SELECT COUNT(*) AS n FROM transactions WHERE {WAITING}")["n"]


def mark(transaction_id, reviewed=True):
    db.run("UPDATE transactions SET reviewed=? WHERE transaction_id=?", (1 if reviewed else 0, transaction_id))


def mark_all() -> int:
    return db.run(f"UPDATE transactions SET reviewed=1 WHERE {WAITING}").rowcount


def mark_item(item_id):
    """A bank's first sync brings up to two years of history. None of it goes to the queue."""
    db.run("UPDATE transactions SET reviewed=1 WHERE item_id=?", (item_id,))

"""Tags: short labels on transactions. A transaction has one category and any number of tags.

A tag the owner takes off a transaction is remembered in removed_tags, so a rule never puts it back.
"""
import re

import db

# Colors are handed out in this order. Each reads on both the light and the dark theme.
PALETTE = ("#2563eb", "#16a34a", "#d97706", "#db2777", "#7c3aed", "#0891b2", "#dc2626", "#65a30d", "#c026d3", "#4f46e5")
MAX_NAME = 32


def clean_name(raw) -> str:
    """Trim and collapse spaces. Raises ValueError when nothing is left or the name is too long."""
    name = re.sub(r"\s+", " ", str(raw or "")).strip().strip(",")
    if not name:
        raise ValueError("Tag name cannot be empty")
    if len(name) > MAX_NAME:
        raise ValueError(f"Tag name is longer than {MAX_NAME} characters")
    return name


def get(tag_id):
    return db.one("SELECT id, name, color FROM tags WHERE id=?", (tag_id,))


def by_name(name):
    return db.one("SELECT id, name, color FROM tags WHERE name=?", (name,))


def ensure(raw) -> dict:
    """Return the tag with this name, making it with the next color when it is new. Names ignore case."""
    name = clean_name(raw)
    row = by_name(name)
    if row:
        return row
    n = db.one("SELECT COALESCE(MAX(id),0) AS n FROM tags")["n"]
    db.run("INSERT OR IGNORE INTO tags (name, color) VALUES (?,?)", (name, PALETTE[n % len(PALETTE)]))
    return by_name(name)


def all_tags():
    """Every tag with how many transactions carry it, by name."""
    return db.q("""SELECT g.id, g.name, g.color,
                          (SELECT COUNT(*) FROM transaction_tags x JOIN transactions t ON t.transaction_id=x.transaction_id
                           WHERE x.tag_id=g.id) AS count
                   FROM tags g ORDER BY g.name COLLATE NOCASE""")


def rename(tag_id, raw) -> dict:
    name = clean_name(raw)
    other = by_name(name)
    if other and other["id"] != tag_id:
        raise ValueError("Another tag already has that name")
    db.run("UPDATE tags SET name=? WHERE id=?", (name, tag_id))
    return get(tag_id)


def recolor(tag_id, color) -> dict:
    if color not in PALETTE:
        raise ValueError("Pick one of the listed colors")
    db.run("UPDATE tags SET color=? WHERE id=?", (color, tag_id))
    return get(tag_id)


def delete(tag_id):
    for table in ("transaction_tags", "removed_tags"):
        db.run(f"DELETE FROM {table} WHERE tag_id=?", (tag_id,))
    db.run("DELETE FROM tags WHERE id=?", (tag_id,))


def add(transaction_id, raw, source="user") -> dict:
    """Put a tag on a transaction. Doing it by hand also forgets an earlier removal."""
    tag = ensure(raw)
    db.run("DELETE FROM removed_tags WHERE transaction_id=? AND tag_id=?", (transaction_id, tag["id"]))
    db.run("INSERT OR IGNORE INTO transaction_tags (transaction_id, tag_id, source) VALUES (?,?,?)", (transaction_id, tag["id"], source))
    return tag


def remove(transaction_id, tag_id):
    """Take a tag off a transaction and remember it, so a rule does not add it again."""
    db.run("DELETE FROM transaction_tags WHERE transaction_id=? AND tag_id=?", (transaction_id, tag_id))
    db.run("INSERT OR IGNORE INTO removed_tags (transaction_id, tag_id) VALUES (?,?)", (transaction_id, tag_id))


def for_transactions(transaction_ids) -> dict:
    """{transaction_id: [{id, name, color}]} for the given ids, tags in name order."""
    ids = list(dict.fromkeys(transaction_ids))
    out = {}
    for i in range(0, len(ids), 500):
        chunk = ids[i:i + 500]
        rows = db.q(f"""SELECT x.transaction_id, g.id, g.name, g.color FROM transaction_tags x JOIN tags g ON g.id=x.tag_id
                        WHERE x.transaction_id IN ({','.join('?' * len(chunk))}) ORDER BY g.name COLLATE NOCASE""", chunk)
        for r in rows:
            out.setdefault(r["transaction_id"], []).append({"id": r["id"], "name": r["name"], "color": r["color"]})
    return out


def prune():
    """Drop tag links and removal notes for transactions that no longer exist."""
    for table in ("transaction_tags", "removed_tags"):
        db.run(f"DELETE FROM {table} WHERE transaction_id NOT IN (SELECT transaction_id FROM transactions)")

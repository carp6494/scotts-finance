"""SQLite storage. One local file: data/finance.db."""
import json
import sqlite3
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)
DB_PATH = DATA / "finance.db"

_lock = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
  item_id TEXT PRIMARY KEY,
  access_token_enc TEXT NOT NULL,
  institution_id TEXT,
  institution_name TEXT,
  institution_color TEXT,
  cursor TEXT,
  status TEXT DEFAULT 'ok',
  error TEXT,
  last_sync TEXT,
  created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS accounts (
  account_id TEXT PRIMARY KEY,
  item_id TEXT,
  name TEXT,
  official_name TEXT,
  mask TEXT,
  type TEXT,
  subtype TEXT,
  current REAL,
  available REAL,
  limit_amt REAL,
  currency TEXT,
  hidden INTEGER DEFAULT 0,
  manual INTEGER DEFAULT 0,
  linked_account_id TEXT,
  updated_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS transactions (
  transaction_id TEXT PRIMARY KEY,
  account_id TEXT,
  item_id TEXT,
  date TEXT,
  authorized_date TEXT,
  amount REAL,
  name TEXT,
  merchant_name TEXT,
  pending INTEGER,
  category TEXT,
  category_detail TEXT,
  logo_url TEXT,
  website TEXT,
  payment_channel TEXT,
  user_category TEXT,
  notes TEXT,
  reviewed INTEGER DEFAULT 0,
  raw TEXT
);
CREATE INDEX IF NOT EXISTS ix_tx_account ON transactions(account_id, date);
CREATE INDEX IF NOT EXISTS ix_tx_date ON transactions(date);
CREATE TABLE IF NOT EXISTS liabilities (
  account_id TEXT PRIMARY KEY,
  kind TEXT,
  data TEXT,
  updated_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS holdings (
  account_id TEXT,
  security_id TEXT,
  name TEXT,
  ticker TEXT,
  type TEXT,
  quantity REAL,
  value REAL,
  cost_basis REAL,
  PRIMARY KEY (account_id, security_id)
);
CREATE TABLE IF NOT EXISTS sync_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  at TEXT DEFAULT (datetime('now')),
  item_id TEXT,
  added INTEGER, modified INTEGER, removed INTEGER,
  error TEXT
);
"""


def connect():
    con = sqlite3.connect(DB_PATH, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    return con


_con = connect()
_con.executescript(SCHEMA)
for _col in ("institution TEXT", "apr_override REAL", "limit_override REAL", "min_payment_override REAL"):
    try:
        _con.execute(f"ALTER TABLE accounts ADD COLUMN {_col}")
    except sqlite3.OperationalError:
        pass  # already there
_con.commit()


def q(sql, args=()):
    with _lock:
        return [dict(r) for r in _con.execute(sql, args).fetchall()]


def one(sql, args=()):
    rows = q(sql, args)
    return rows[0] if rows else None


def run(sql, args=()):
    with _lock:
        cur = _con.execute(sql, args)
        _con.commit()
        return cur


def many(sql, rows):
    with _lock:
        _con.executemany(sql, rows)
        _con.commit()


def dumps(obj):
    return json.dumps(obj, default=str)

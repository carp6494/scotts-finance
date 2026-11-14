"""The review queue: what waits in it and how rows leave."""
import os

os.environ.setdefault("OPEN_BROWSER", "0")

import app  # noqa: E402
import db  # noqa: E402
import review  # noqa: E402
from conftest import add_tx  # noqa: E402


def waiting():
    return [r["transaction_id"] for r in app.transactions(unreviewed=1)["rows"]]


def test_new_rows_wait_and_pending_rows_do_not(fresh):
    add_tx("a")
    add_tx("p")
    db.run("UPDATE transactions SET pending=1 WHERE transaction_id='p'")
    assert waiting() == ["a"] and review.count() == 1 and app.summary()["unreviewed"] == 1
    db.run("UPDATE transactions SET pending=0 WHERE transaction_id='p'")
    assert sorted(waiting()) == ["a", "p"]


def test_marking_one_reviewed_and_back(fresh):
    add_tx("a")
    add_tx("b")
    out = app.patch_transaction("a", app.TxPatch(reviewed=True))
    assert out["reviewed"] == 1 and waiting() == ["b"]
    app.patch_transaction("a", app.TxPatch(reviewed=False))
    assert sorted(waiting()) == ["a", "b"]


def test_mark_all_leaves_pending_rows_alone(fresh):
    add_tx("a")
    add_tx("b")
    add_tx("p")
    db.run("UPDATE transactions SET pending=1 WHERE transaction_id='p'")
    assert app.review_all() == {"marked": 2}
    assert review.count() == 0
    assert db.one("SELECT reviewed FROM transactions WHERE transaction_id='p'")["reviewed"] == 0


def test_start_keeps_only_the_newest_five_and_runs_once(fresh):
    db.run("DELETE FROM settings WHERE key=?", (review.KEY,))
    for i in range(1, 10):
        add_tx(f"t{i}", date=f"2026-11-{i:02d}")
    add_tx("pending", date="2026-11-30")
    db.run("UPDATE transactions SET pending=1 WHERE transaction_id='pending'")
    assert review.start() is True
    assert sorted(waiting()) == ["t5", "t6", "t7", "t8", "t9"]
    app.review_all()
    add_tx("later", date="2026-12-01")
    assert review.start() is False
    assert waiting() == ["later"]


def test_first_sync_of_a_bank_is_not_news(fresh):
    add_tx("a")
    db.run("UPDATE transactions SET item_id='item-9' WHERE transaction_id='a'")
    add_tx("b")
    review.mark_item("item-9")
    assert waiting() == ["b"]

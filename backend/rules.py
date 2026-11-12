"""Rules engine and categorization order.

Order for every transaction the user has not set by hand:
  1. enabled rules by priority (first that sets a category wins; flag-only rules keep going)
  2. merchant memory (the category the user last chose for this merchant)
  3. the Plaid category, inserting a category row if it is new
  4. UNCATEGORIZED
"""
import json
import logging

import categories
import db

log = logging.getLogger("rules")


def merchant_key(t) -> str:
    return (t.get("merchant_name") or t.get("name") or "").strip().lower()


def _contains(hay, needle) -> bool:
    return str(needle).lower() in (hay or "").lower()


def match(conditions, t) -> bool:
    """True when every condition present in the dict holds for transaction dict t."""
    c = conditions or {}
    if c.get("merchant"):
        if not any(_contains(t.get(k), c["merchant"]) for k in ("display_name", "merchant_name", "name")):
            return False
    if c.get("text") and not _contains(t.get("name"), c["text"]):
        return False
    amt = t.get("amount")
    if c.get("amount_min") is not None and (amt is None or amt < float(c["amount_min"])):
        return False
    if c.get("amount_max") is not None and (amt is None or amt > float(c["amount_max"])):
        return False
    if c.get("account_id") and t.get("account_id") != c["account_id"]:
        return False
    if c.get("day_min") is not None or c.get("day_max") is not None:
        try:
            day = int(str(t.get("date") or "")[8:10])
        except ValueError:
            return False
        if c.get("day_min") is not None and day < int(c["day_min"]):
            return False
        if c.get("day_max") is not None and day > int(c["day_max"]):
            return False
    return True

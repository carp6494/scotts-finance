"""Category taxonomy. Seeded from Plaid's personal finance categories, extended by the user.

Category ids are Plaid's detailed codes (FOOD_AND_DRINK_FAST_FOOD) so Plaid transactions map with no
lookup table. Custom categories get ids like custom-dog-stuff-3f2a.
"""
import re
import uuid

import db

UNCAT = "UNCATEGORIZED"

# Plaid primary code -> (readable group, type)
GROUPS = {
    "INCOME": ("Income", "income"),
    "TRANSFER_IN": ("Transfers in", "transfer"),
    "TRANSFER_OUT": ("Transfers out", "transfer"),
    "LOAN_PAYMENTS": ("Loan payments", "transfer"),
    "BANK_FEES": ("Bank fees", "expense"),
    "ENTERTAINMENT": ("Entertainment", "expense"),
    "FOOD_AND_DRINK": ("Food & drink", "expense"),
    "GENERAL_MERCHANDISE": ("Shopping", "expense"),
    "HOME_IMPROVEMENT": ("Home improvement", "expense"),
    "MEDICAL": ("Medical", "expense"),
    "PERSONAL_CARE": ("Personal care", "expense"),
    "GENERAL_SERVICES": ("Services", "expense"),
    "GOVERNMENT_AND_NON_PROFIT": ("Government & non-profit", "expense"),
    "TRANSPORTATION": ("Transportation", "expense"),
    "TRAVEL": ("Travel", "expense"),
    "RENT_AND_UTILITIES": ("Rent & utilities", "expense"),
    "OTHER": ("Other", "expense"),
}

# Plaid detailed suffixes per primary code
DETAILED = {
    "INCOME": ["DIVIDENDS", "INTEREST_EARNED", "RETIREMENT_PENSION", "TAX_REFUND", "UNEMPLOYMENT", "WAGES", "OTHER_INCOME"],
    "TRANSFER_IN": ["CASH_ADVANCES_AND_LOANS", "DEPOSIT", "INVESTMENT_AND_RETIREMENT_FUNDS", "SAVINGS", "ACCOUNT_TRANSFER", "OTHER_TRANSFER_IN"],
    "TRANSFER_OUT": ["INVESTMENT_AND_RETIREMENT_FUNDS", "SAVINGS", "WITHDRAWAL", "ACCOUNT_TRANSFER", "OTHER_TRANSFER_OUT"],
    "LOAN_PAYMENTS": ["CAR_PAYMENT", "CREDIT_CARD_PAYMENT", "PERSONAL_LOAN_PAYMENT", "MORTGAGE_PAYMENT", "STUDENT_LOAN_PAYMENT", "OTHER_PAYMENT"],
    "BANK_FEES": ["ATM_FEES", "FOREIGN_TRANSACTION_FEES", "INSUFFICIENT_FUNDS", "INTEREST_CHARGE", "OVERDRAFT_FEES", "OTHER_BANK_FEES"],
    "ENTERTAINMENT": ["CASINOS_AND_GAMBLING", "MUSIC_AND_AUDIO", "SPORTING_EVENTS_AMUSEMENT_PARKS_AND_MUSEUMS", "TV_AND_MOVIES", "VIDEO_GAMES", "OTHER_ENTERTAINMENT"],
    "FOOD_AND_DRINK": ["BEER_WINE_AND_LIQUOR", "COFFEE", "FAST_FOOD", "GROCERIES", "RESTAURANT", "VENDING_MACHINES", "OTHER_FOOD_AND_DRINK"],
    "GENERAL_MERCHANDISE": ["BOOKSTORES_AND_NEWSSTANDS", "CLOTHING_AND_ACCESSORIES", "CONVENIENCE_STORES", "DEPARTMENT_STORES", "DISCOUNT_STORES",
                            "ELECTRONICS", "GIFTS_AND_NOVELTIES", "OFFICE_SUPPLIES", "ONLINE_MARKETPLACES", "PET_SUPPLIES", "SPORTING_GOODS",
                            "SUPERSTORES", "TOBACCO_AND_VAPE", "OTHER_GENERAL_MERCHANDISE"],
    "HOME_IMPROVEMENT": ["FURNITURE", "HARDWARE", "REPAIR_AND_MAINTENANCE", "SECURITY", "OTHER_HOME_IMPROVEMENT"],
    "MEDICAL": ["DENTAL_CARE", "EYE_CARE", "NURSING_CARE", "PHARMACIES_AND_SUPPLEMENTS", "PRIMARY_CARE", "VETERINARY_SERVICES", "OTHER_MEDICAL"],
    "PERSONAL_CARE": ["GYMS_AND_FITNESS_CENTERS", "HAIR_AND_BEAUTY", "LAUNDRY_AND_DRY_CLEANING", "OTHER_PERSONAL_CARE"],
    "GENERAL_SERVICES": ["ACCOUNTING_AND_FINANCIAL_PLANNING", "AUTOMOTIVE", "CHILDCARE", "CONSULTING_AND_LEGAL", "EDUCATION", "INSURANCE",
                         "POSTAGE_AND_SHIPPING", "STORAGE", "OTHER_GENERAL_SERVICES"],
    "GOVERNMENT_AND_NON_PROFIT": ["DONATIONS", "GOVERNMENT_DEPARTMENTS_AND_AGENCIES", "TAX_PAYMENT", "OTHER_GOVERNMENT_AND_NON_PROFIT"],
    "TRANSPORTATION": ["BIKES_AND_SCOOTERS", "GAS", "PARKING", "PUBLIC_TRANSIT", "TAXIS_AND_RIDE_SHARES", "TOLLS", "OTHER_TRANSPORTATION"],
    "TRAVEL": ["FLIGHTS", "LODGING", "RENTAL_CARS", "OTHER_TRAVEL"],
    "RENT_AND_UTILITIES": ["GAS_AND_ELECTRICITY", "INTERNET_AND_CABLE", "RENT", "SEWAGE_AND_WASTE_MANAGEMENT", "TELEPHONE", "WATER", "OTHER_UTILITIES"],
    "OTHER": ["OTHER"],
}

NAME_OVERRIDES = {
    "ENTERTAINMENT_SPORTING_EVENTS_AMUSEMENT_PARKS_AND_MUSEUMS": "Events, parks and museums",
    "TRANSPORTATION_GAS": "Gas station",
    "RENT_AND_UTILITIES_GAS_AND_ELECTRICITY": "Gas and electric",
    "GENERAL_MERCHANDISE_TOBACCO_AND_VAPE": "Tobacco and vape",
    "OTHER_OTHER": "Other",
}

_PRIMARIES = sorted(GROUPS, key=len, reverse=True)  # longest first so FOOD_AND_DRINK beats OTHER


def primary_of(code: str) -> str:
    for p in _PRIMARIES:
        if code == p or code.startswith(p + "_"):
            return p
    return "OTHER"


def readable(code: str) -> str:
    """FOOD_AND_DRINK_FAST_FOOD -> 'Fast food'. A bare primary code gives the group name."""
    if code in NAME_OVERRIDES:
        return NAME_OVERRIDES[code]
    p = primary_of(code)
    suffix = code[len(p) + 1:] if code.startswith(p + "_") else ""
    if not suffix:
        return GROUPS.get(p, ("Other", "expense"))[0]
    words = suffix.lower().split("_")
    text = " ".join(words)
    return text[:1].upper() + text[1:]


def seed():
    rows = []
    for p, suffixes in DETAILED.items():
        group, typ = GROUPS[p]
        for i, s in enumerate(suffixes):
            code = f"{p}_{s}"
            rows.append((code, group, readable(code), typ, i))
    rows.append((UNCAT, "Uncategorized", "Uncategorized", "expense", 0))
    db.many("INSERT OR IGNORE INTO categories (id, group_name, name, type, sort) VALUES (?,?,?,?,?)", rows)


def ensure(code):
    """Return the category id for a Plaid or import code, inserting a row the first time it is seen."""
    if not code:
        return None
    if db.one("SELECT 1 FROM categories WHERE id=?", (code,)):
        return code
    group, typ = GROUPS.get(primary_of(code), ("Other", "expense"))
    db.run("INSERT OR IGNORE INTO categories (id, group_name, name, type, sort) VALUES (?,?,?,?,999)", (code, group, readable(code), typ))
    return code


def get(cat_id):
    return db.one("SELECT * FROM categories WHERE id=?", (cat_id,))


def grouped():
    """[{group_name, categories: [{id, name, type, hidden, custom}]}] in display order."""
    order = {g: i for i, g in enumerate(v[0] for v in GROUPS.values())}
    rows = db.q("SELECT id, group_name, name, type, hidden, custom FROM categories ORDER BY sort, name")
    groups = {}
    for r in rows:
        groups.setdefault(r["group_name"], []).append({k: r[k] for k in ("id", "name", "type", "hidden", "custom")})
    keys = sorted(groups, key=lambda g: (g == "Uncategorized", order.get(g, 500), g))
    return [{"group_name": g, "categories": groups[g]} for g in keys]


def add_custom(name: str, group_name: str, typ: str):
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "category"
    cat_id = f"custom-{slug}-{uuid.uuid4().hex[:4]}"
    db.run("INSERT INTO categories (id, group_name, name, type, custom, sort) VALUES (?,?,?,?,1,500)", (cat_id, group_name.strip(), name.strip(), typ))
    return get(cat_id)

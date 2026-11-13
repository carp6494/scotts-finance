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

GROUP_ICONS = {
    "INCOME": "💰", "TRANSFER_IN": "📥", "TRANSFER_OUT": "📤", "LOAN_PAYMENTS": "💸", "BANK_FEES": "🏦",
    "ENTERTAINMENT": "🎭", "FOOD_AND_DRINK": "🍴", "GENERAL_MERCHANDISE": "🛍️", "HOME_IMPROVEMENT": "🏡",
    "MEDICAL": "⚕️", "PERSONAL_CARE": "🧴", "GENERAL_SERVICES": "🧰", "GOVERNMENT_AND_NON_PROFIT": "🏛️",
    "TRANSPORTATION": "🚗", "TRAVEL": "🧳", "RENT_AND_UTILITIES": "🔌", "OTHER": "❓",
}
GROUP_ICON_BY_NAME = {GROUPS[p][0]: GROUP_ICONS[p] for p in GROUPS}
DEFAULT_ICON = "🏷️"
UNCAT_ICON = "❔"

# Built-in categories Plaid does not have. Same shape as the seed rows: id, group, name, type, sort, icon.
# Plaid never assigns these, so they are reached by rules or by hand.
EXTRAS = [
    ("EXTRA_CANNABIS", "Shopping", "Cannabis", "expense", 50, "🌿"),
]

ICONS = {
    "INCOME_DIVIDENDS": "💹", "INCOME_INTEREST_EARNED": "🏦", "INCOME_RETIREMENT_PENSION": "🧓", "INCOME_TAX_REFUND": "🧾",
    "INCOME_UNEMPLOYMENT": "📄", "INCOME_WAGES": "💵", "INCOME_OTHER_INCOME": "💰",
    "TRANSFER_IN_CASH_ADVANCES_AND_LOANS": "💳", "TRANSFER_IN_DEPOSIT": "📥", "TRANSFER_IN_INVESTMENT_AND_RETIREMENT_FUNDS": "📈",
    "TRANSFER_IN_SAVINGS": "🐷", "TRANSFER_IN_ACCOUNT_TRANSFER": "🔁", "TRANSFER_IN_OTHER_TRANSFER_IN": "➡️",
    "TRANSFER_OUT_INVESTMENT_AND_RETIREMENT_FUNDS": "📈", "TRANSFER_OUT_SAVINGS": "🐷", "TRANSFER_OUT_WITHDRAWAL": "🏧",
    "TRANSFER_OUT_ACCOUNT_TRANSFER": "🔁", "TRANSFER_OUT_OTHER_TRANSFER_OUT": "⬅️",
    "LOAN_PAYMENTS_CAR_PAYMENT": "🚗", "LOAN_PAYMENTS_CREDIT_CARD_PAYMENT": "💳", "LOAN_PAYMENTS_PERSONAL_LOAN_PAYMENT": "🤝",
    "LOAN_PAYMENTS_MORTGAGE_PAYMENT": "🏠", "LOAN_PAYMENTS_STUDENT_LOAN_PAYMENT": "🎓", "LOAN_PAYMENTS_OTHER_PAYMENT": "💸",
    "BANK_FEES_ATM_FEES": "🏧", "BANK_FEES_FOREIGN_TRANSACTION_FEES": "🌍", "BANK_FEES_INSUFFICIENT_FUNDS": "⚠️",
    "BANK_FEES_INTEREST_CHARGE": "📉", "BANK_FEES_OVERDRAFT_FEES": "⚠️", "BANK_FEES_OTHER_BANK_FEES": "🏦",
    "ENTERTAINMENT_CASINOS_AND_GAMBLING": "🎰", "ENTERTAINMENT_MUSIC_AND_AUDIO": "🎵",
    "ENTERTAINMENT_SPORTING_EVENTS_AMUSEMENT_PARKS_AND_MUSEUMS": "🎟️", "ENTERTAINMENT_TV_AND_MOVIES": "🎬",
    "ENTERTAINMENT_VIDEO_GAMES": "🎮", "ENTERTAINMENT_OTHER_ENTERTAINMENT": "🎭",
    "FOOD_AND_DRINK_BEER_WINE_AND_LIQUOR": "🍺", "FOOD_AND_DRINK_COFFEE": "☕", "FOOD_AND_DRINK_FAST_FOOD": "🍔",
    "FOOD_AND_DRINK_GROCERIES": "🛒", "FOOD_AND_DRINK_RESTAURANT": "🍽️", "FOOD_AND_DRINK_VENDING_MACHINES": "🥤",
    "FOOD_AND_DRINK_OTHER_FOOD_AND_DRINK": "🍴",
    "GENERAL_MERCHANDISE_BOOKSTORES_AND_NEWSSTANDS": "📚", "GENERAL_MERCHANDISE_CLOTHING_AND_ACCESSORIES": "👕",
    "GENERAL_MERCHANDISE_CONVENIENCE_STORES": "🏪", "GENERAL_MERCHANDISE_DEPARTMENT_STORES": "🏬",
    "GENERAL_MERCHANDISE_DISCOUNT_STORES": "🏷️", "GENERAL_MERCHANDISE_ELECTRONICS": "🔌",
    "GENERAL_MERCHANDISE_GIFTS_AND_NOVELTIES": "🎁", "GENERAL_MERCHANDISE_OFFICE_SUPPLIES": "📎",
    "GENERAL_MERCHANDISE_ONLINE_MARKETPLACES": "📦", "GENERAL_MERCHANDISE_PET_SUPPLIES": "🐾",
    "GENERAL_MERCHANDISE_SPORTING_GOODS": "⚽", "GENERAL_MERCHANDISE_SUPERSTORES": "🛍️",
    "GENERAL_MERCHANDISE_TOBACCO_AND_VAPE": "🚬", "GENERAL_MERCHANDISE_OTHER_GENERAL_MERCHANDISE": "🛍️",
    "HOME_IMPROVEMENT_FURNITURE": "🛋️", "HOME_IMPROVEMENT_HARDWARE": "🔧", "HOME_IMPROVEMENT_REPAIR_AND_MAINTENANCE": "🛠️",
    "HOME_IMPROVEMENT_SECURITY": "🔒", "HOME_IMPROVEMENT_OTHER_HOME_IMPROVEMENT": "🏡",
    "MEDICAL_DENTAL_CARE": "🦷", "MEDICAL_EYE_CARE": "👓", "MEDICAL_NURSING_CARE": "🩺",
    "MEDICAL_PHARMACIES_AND_SUPPLEMENTS": "💊", "MEDICAL_PRIMARY_CARE": "🏥", "MEDICAL_VETERINARY_SERVICES": "🐶",
    "MEDICAL_OTHER_MEDICAL": "⚕️",
    "PERSONAL_CARE_GYMS_AND_FITNESS_CENTERS": "🏋️", "PERSONAL_CARE_HAIR_AND_BEAUTY": "💇",
    "PERSONAL_CARE_LAUNDRY_AND_DRY_CLEANING": "🧺", "PERSONAL_CARE_OTHER_PERSONAL_CARE": "🧴",
    "GENERAL_SERVICES_ACCOUNTING_AND_FINANCIAL_PLANNING": "🧮", "GENERAL_SERVICES_AUTOMOTIVE": "🚘",
    "GENERAL_SERVICES_CHILDCARE": "🧒", "GENERAL_SERVICES_CONSULTING_AND_LEGAL": "⚖️", "GENERAL_SERVICES_EDUCATION": "🎓",
    "GENERAL_SERVICES_INSURANCE": "🛡️", "GENERAL_SERVICES_POSTAGE_AND_SHIPPING": "📮", "GENERAL_SERVICES_STORAGE": "📦",
    "GENERAL_SERVICES_OTHER_GENERAL_SERVICES": "🧰",
    "GOVERNMENT_AND_NON_PROFIT_DONATIONS": "❤️", "GOVERNMENT_AND_NON_PROFIT_GOVERNMENT_DEPARTMENTS_AND_AGENCIES": "🏛️",
    "GOVERNMENT_AND_NON_PROFIT_TAX_PAYMENT": "🧾", "GOVERNMENT_AND_NON_PROFIT_OTHER_GOVERNMENT_AND_NON_PROFIT": "🏛️",
    "TRANSPORTATION_BIKES_AND_SCOOTERS": "🚲", "TRANSPORTATION_GAS": "⛽", "TRANSPORTATION_PARKING": "🅿️",
    "TRANSPORTATION_PUBLIC_TRANSIT": "🚌", "TRANSPORTATION_TAXIS_AND_RIDE_SHARES": "🚕", "TRANSPORTATION_TOLLS": "🛣️",
    "TRANSPORTATION_OTHER_TRANSPORTATION": "🚗",
    "TRAVEL_FLIGHTS": "✈️", "TRAVEL_LODGING": "🏨", "TRAVEL_RENTAL_CARS": "🚙", "TRAVEL_OTHER_TRAVEL": "🧳",
    "RENT_AND_UTILITIES_GAS_AND_ELECTRICITY": "💡", "RENT_AND_UTILITIES_INTERNET_AND_CABLE": "📶", "RENT_AND_UTILITIES_RENT": "🏠",
    "RENT_AND_UTILITIES_SEWAGE_AND_WASTE_MANAGEMENT": "🗑️", "RENT_AND_UTILITIES_TELEPHONE": "📱", "RENT_AND_UTILITIES_WATER": "💧",
    "RENT_AND_UTILITIES_OTHER_UTILITIES": "🔌",
    "OTHER_OTHER": "❓",
    UNCAT: UNCAT_ICON,
}


def default_icon(code: str, group_name: str | None = None) -> str:
    """The icon a category gets when none was chosen: its own, else its group's, else the generic tag."""
    if code in ICONS:
        return ICONS[code]
    if code.startswith("custom-"):
        return GROUP_ICON_BY_NAME.get(group_name or "", DEFAULT_ICON)
    return GROUP_ICONS.get(primary_of(code), DEFAULT_ICON)


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
            rows.append((code, group, readable(code), typ, i, default_icon(code)))
    rows.append((UNCAT, "Uncategorized", "Uncategorized", "expense", 0, UNCAT_ICON))
    rows += EXTRAS
    db.many("INSERT OR IGNORE INTO categories (id, group_name, name, type, sort, icon) VALUES (?,?,?,?,?,?)", rows)
    # Fill icons for rows that predate the column or were inserted by ensure(); never overwrite a chosen icon.
    rows = db.q("SELECT id, group_name FROM categories WHERE icon IS NULL OR icon=''")
    if rows:
        db.many("UPDATE categories SET icon=? WHERE id=?", [(default_icon(r["id"], r["group_name"]), r["id"]) for r in rows])


def ensure(code):
    """Return the category id for a Plaid or import code, inserting a row the first time it is seen."""
    if not code:
        return None
    if db.one("SELECT 1 FROM categories WHERE id=?", (code,)):
        return code
    group, typ = GROUPS.get(primary_of(code), ("Other", "expense"))
    db.run("INSERT OR IGNORE INTO categories (id, group_name, name, type, sort, icon) VALUES (?,?,?,?,999,?)",
           (code, group, readable(code), typ, default_icon(code)))
    return code


def get(cat_id):
    return db.one("SELECT * FROM categories WHERE id=?", (cat_id,))


def grouped():
    """[{group_name, categories: [{id, name, type, hidden, custom, icon}]}] in display order."""
    order = {g: i for i, g in enumerate(v[0] for v in GROUPS.values())}
    rows = db.q("SELECT id, group_name, name, type, hidden, custom, icon FROM categories ORDER BY sort, name")
    groups = {}
    for r in rows:
        groups.setdefault(r["group_name"], []).append({k: r[k] for k in ("id", "name", "type", "hidden", "custom", "icon")})
    keys = sorted(groups, key=lambda g: (g == "Uncategorized", order.get(g, 500), g))
    return [{"group_name": g, "categories": groups[g]} for g in keys]


def add_custom(name: str, group_name: str, typ: str, icon: str | None = None):
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "category"
    cat_id = f"custom-{slug}-{uuid.uuid4().hex[:4]}"
    icon = (icon or "").strip() or default_icon(cat_id, group_name.strip())
    db.run("INSERT INTO categories (id, group_name, name, type, custom, sort, icon) VALUES (?,?,?,?,1,500,?)",
           (cat_id, group_name.strip(), name.strip(), typ, icon))
    return get(cat_id)

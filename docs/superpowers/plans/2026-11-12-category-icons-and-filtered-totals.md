# Category Icons and Filtered Totals Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every category carries an emoji icon shown wherever the category appears, and the Transactions page totals follow the account and category filters.

**Architecture:** One new column on `categories` seeded from a static dict in `backend/categories.py` and editable through the existing PATCH route. `GET /api/summary` gains two optional filters. The frontend prefixes the icon in the shared `categoryLabel`, the picker, both dropdowns, and the Categories tab, which also gets an icon input. The Transactions page fetches filtered totals itself.

**Tech Stack:** Python, FastAPI, sqlite3, pytest. React 19, Vite 7, inline styles.

**Spec:** `docs/superpowers/specs/2026-11-12-category-icons-and-filtered-totals-design.md`

**Conventions:** see the header of `docs/superpowers/plans/2026-11-12-categories-rules.md`. Tests: `.venv\Scripts\python -m pytest backend/tests -q` from the project root (57 pass today). Build: `npm run build` in `frontend\`. Commits end with `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`. Check `git diff --cached --name-only` before every commit; never stage `data/`, `backups/`, `imports/`, `.env`, `HANDOFF.md`. Never run writes against the real database outside the app. Write files as UTF-8; the icon dict contains emoji.

---

### Task 1: Icon column, seed, and API

**Files:**
- Modify: `backend/db.py` (`_ADDED_COLUMNS`)
- Modify: `backend/categories.py`
- Modify: `backend/app.py` (`CategoryReq`, `CategoryPatch`, `add_category`, `patch_category`, `summary`)
- Modify: `backend/tests/test_categories.py`, `backend/tests/test_api.py`

- [ ] **Step 1: Failing tests**

Append to `backend/tests/test_categories.py`:

```python
def test_seed_assigns_icons(fresh):
    assert db.one("SELECT icon FROM categories WHERE id='FOOD_AND_DRINK_FAST_FOOD'")["icon"] == "🍔"
    assert db.one("SELECT icon FROM categories WHERE id='UNCATEGORIZED'")["icon"] == "❔"
    assert db.one("SELECT COUNT(*) AS n FROM categories WHERE icon IS NULL OR icon=''")["n"] == 0


def test_seed_keeps_edited_icon(fresh):
    db.run("UPDATE categories SET icon='🌮' WHERE id='FOOD_AND_DRINK_FAST_FOOD'")
    categories.seed()
    assert db.one("SELECT icon FROM categories WHERE id='FOOD_AND_DRINK_FAST_FOOD'")["icon"] == "🌮"


def test_custom_inherits_group_icon(fresh):
    c = categories.add_custom("Dog stuff", "Food & drink", "expense")
    assert c["icon"] == "🍴"
    d = categories.add_custom("Mystery", "Nowhere", "expense")
    assert d["icon"] == "🏷️"
    e = categories.add_custom("Bones", "Pets", "expense", icon="🦴")
    assert e["icon"] == "🦴"


def test_ensure_gives_group_icon(fresh):
    categories.ensure("TRAVEL_SOMETHING_NEW")
    assert db.one("SELECT icon FROM categories WHERE id='TRAVEL_SOMETHING_NEW'")["icon"] == "🧳"


def test_grouped_includes_icon(fresh):
    g = categories.grouped()
    food = next(x for x in g if x["group_name"] == "Food & drink")
    assert "icon" in food["categories"][0]
```

Append to `backend/tests/test_api.py`:

```python
def test_patch_category_icon(fresh):
    assert app.patch_category("FOOD_AND_DRINK_COFFEE", app.CategoryPatch(icon=" 🫖 "))["icon"] == "🫖"
    assert app.patch_category("FOOD_AND_DRINK_COFFEE", app.CategoryPatch(icon=""))["icon"] == "☕"
    with pytest.raises(HTTPException) as e:
        app.patch_category("FOOD_AND_DRINK_COFFEE", app.CategoryPatch(icon="x" * 17))
    assert e.value.status_code == 400


def test_summary_filters(fresh):
    today = __import__("datetime").date.today().isoformat()
    add_tx("a", account="acc-1", amount=20, cat_id="FOOD_AND_DRINK_FAST_FOOD", source="plaid", date=today)
    add_tx("b", account="acc-2", amount=30, cat_id="FOOD_AND_DRINK_COFFEE", source="plaid", date=today)
    assert app.summary()["spent_month"] == 50.0
    assert app.summary(cat_id="FOOD_AND_DRINK_COFFEE")["spent_month"] == 30.0
    assert app.summary(account_id="acc-1")["spent_month"] == 20.0
    assert app.summary(account_id="acc-1", cat_id="FOOD_AND_DRINK_COFFEE")["spent_month"] == 0.0
```

Run `.venv\Scripts\python -m pytest backend/tests -q`. Expected: these new tests fail.

- [ ] **Step 2: Column**

In `backend/db.py` add to `_ADDED_COLUMNS`, after the `display_name TEXT` entry: `("categories", "icon TEXT"),`.

- [ ] **Step 3: Icons in `backend/categories.py`**

After `NAME_OVERRIDES = {...}` add:

```python
GROUP_ICONS = {
    "INCOME": "💰", "TRANSFER_IN": "📥", "TRANSFER_OUT": "📤", "LOAN_PAYMENTS": "💸", "BANK_FEES": "🏦",
    "ENTERTAINMENT": "🎭", "FOOD_AND_DRINK": "🍴", "GENERAL_MERCHANDISE": "🛍️", "HOME_IMPROVEMENT": "🏡",
    "MEDICAL": "⚕️", "PERSONAL_CARE": "🧴", "GENERAL_SERVICES": "🧰", "GOVERNMENT_AND_NON_PROFIT": "🏛️",
    "TRANSPORTATION": "🚗", "TRAVEL": "🧳", "RENT_AND_UTILITIES": "🔌", "OTHER": "❓",
}
GROUP_ICON_BY_NAME = {GROUPS[p][0]: GROUP_ICONS[p] for p in GROUPS}
DEFAULT_ICON = "🏷️"
UNCAT_ICON = "❔"

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
```

Replace `seed()` with:

```python
def seed():
    rows = []
    for p, suffixes in DETAILED.items():
        group, typ = GROUPS[p]
        for i, s in enumerate(suffixes):
            code = f"{p}_{s}"
            rows.append((code, group, readable(code), typ, i, default_icon(code)))
    rows.append((UNCAT, "Uncategorized", "Uncategorized", "expense", 0, UNCAT_ICON))
    db.many("INSERT OR IGNORE INTO categories (id, group_name, name, type, sort, icon) VALUES (?,?,?,?,?,?)", rows)
    # Fill icons for rows that predate the column or were inserted by ensure(); never overwrite a chosen icon.
    for r in db.q("SELECT id, group_name FROM categories WHERE icon IS NULL OR icon=''"):
        db.run("UPDATE categories SET icon=? WHERE id=?", (default_icon(r["id"], r["group_name"]), r["id"]))
```

In `ensure()`, change the INSERT to include the icon:

```python
    db.run("INSERT OR IGNORE INTO categories (id, group_name, name, type, sort, icon) VALUES (?,?,?,?,999,?)",
           (code, group, readable(code), typ, default_icon(code)))
```

In `grouped()`, select `icon` too and include it in the per-category dict: `("id", "name", "type", "hidden", "custom", "icon")`. Update the docstring.

Replace `add_custom` with:

```python
def add_custom(name: str, group_name: str, typ: str, icon: str | None = None):
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "category"
    cat_id = f"custom-{slug}-{uuid.uuid4().hex[:4]}"
    icon = (icon or "").strip() or default_icon(cat_id, group_name.strip())
    db.run("INSERT INTO categories (id, group_name, name, type, custom, sort, icon) VALUES (?,?,?,?,1,500,?)",
           (cat_id, group_name.strip(), name.strip(), typ, icon))
    return get(cat_id)
```

Note: `test_grouped_structure` in `test_categories.py` asserts the exact key set; update it to include `"icon"`.

- [ ] **Step 4: API in `backend/app.py`**

`CategoryReq` gains `icon: str | None = None`; `add_category` passes `req.icon` as the fourth argument to `categories.add_custom`. `CategoryPatch` gains `icon: str | None = None`. In `patch_category`, before `if sets:` add:

```python
    if req.icon is not None:
        icon = req.icon.strip()
        if len(icon) > 16:
            raise HTTPException(400, "Icon is too long")
        if not icon:
            row = categories.get(cat_id)
            icon = categories.default_icon(cat_id, row["group_name"])
        sets.append("icon=?"); args.append(icon)
```

Replace the `summary` signature and the monthly query:

```python
@app.get("/api/summary")
def summary(account_id: str | None = None, cat_id: str | None = None):
    ...
    month = date.today().strftime("%Y-%m")
    where, args = ["substr(t.date,1,7)=?", "t.pending=0", "COALESCE(t.excluded,0)=0", "COALESCE(t.is_transfer,0)=0"], [month]
    if account_id:
        where.append("t.account_id=?"); args.append(account_id)
    if cat_id:
        where.append("t.cat_id=?"); args.append(cat_id)
    m = db.one(f"""SELECT COALESCE(SUM(CASE WHEN t.amount>0 AND COALESCE(c.type,'expense')='expense' THEN t.amount END),0) AS spent,
                          COALESCE(SUM(CASE WHEN t.amount<0 AND c.type='income' THEN -t.amount END),0) AS income
                   FROM transactions t LEFT JOIN categories c ON c.id=t.cat_id WHERE {' AND '.join(where)}""", args)
```
Keep the rest of the function as it is.

- [ ] **Step 5: Run tests, import check, commit**

`.venv\Scripts\python -m pytest backend/tests -q` → all pass (64). Import check as in earlier plans. Commit `backend/db.py backend/categories.py backend/app.py backend/tests/test_categories.py backend/tests/test_api.py` with message `Categories: emoji icons; summary accepts account and category filters`.

---

### Task 2: Icons everywhere in the UI, filtered totals on the Transactions page

**Files:**
- Modify: `frontend/src/api.js` (summary wrapper)
- Modify: `frontend/src/categories.js`
- Modify: `frontend/src/components/CategoryPicker.jsx`
- Modify: `frontend/src/pages/Transactions.jsx`
- Modify: `frontend/src/pages/Rules.jsx`

- [ ] **Step 1: api.js**

Replace `  summary: () => req('GET', '/api/summary'),` with
`  summary: (p = {}) => req('GET', '/api/summary?' + new URLSearchParams(Object.entries(p).filter(([, v]) => v !== undefined && v !== ''))),`.

- [ ] **Step 2: categories.js**

Replace `categoryLabel` with:

```js
export const withIcon = (c) => (c?.icon ? `${c.icon} ` : '')

export const categoryLabel = (groups, id) => {
  const c = flatCategories(groups).find((x) => x.id === id)
  return c ? `${withIcon(c)}${c.group_name} · ${c.name}` : '❔ Uncategorized'
}
```

- [ ] **Step 3: CategoryPicker.jsx**

Import `withIcon` from `../categories`. Badge text becomes `{current ? `${withIcon(current)}${current.group_name} · ${current.name}` : '❔ Uncategorized'}`. Each list item becomes `{withIcon(c)}{c.name}{c.custom ? ... : null}`.

- [ ] **Step 4: Transactions.jsx**

Import `useEffect` and `api`, and `withIcon` from `../categories`. Add filtered totals:

```js
  const [totals, setTotals] = useState(null)
  const filtered = Boolean(acct || cat)
  useEffect(() => {
    if (!filtered) { setTotals(null); return }
    let alive = true
    api.summary({ account_id: acct || undefined, cat_id: cat || undefined }).then((r) => { if (alive) setTotals(r) }).catch(() => {})
    return () => { alive = false }
  }, [acct, cat, summary]) // eslint-disable-line
  const t = totals || s
```
Use `t.spent_month` and `t.income_month` in the two cards. Replace the caption line with `{filtered && <div style={{ marginTop: 4, fontSize: 11, color: 'var(--muted)' }}>This month, filtered</div>}`. Category options become `{withIcon(c)}{c.name}`.

- [ ] **Step 5: Rules.jsx**

Import `withIcon`. Rule editor category options: `{withIcon(x)}{x.name}`. In `CategoriesTab`:
- Add state `const [iconEdit, setIconEdit] = useState(null) // { id, icon }`.
- In each row, before the name, render an icon cell:
```jsx
                  {iconEdit && iconEdit.id === c.id ? (
                    <input autoFocus value={iconEdit.icon} onChange={(e) => setIconEdit({ ...iconEdit, icon: e.target.value })}
                      onBlur={() => { const cur = iconEdit; setIconEdit(null); patch(cur.id, { icon: cur.icon }) }}
                      onKeyDown={(e) => { if (e.key === 'Enter') e.currentTarget.blur(); if (e.key === 'Escape') setIconEdit(null) }}
                      aria-label={`Icon for ${c.name}`} style={{ ...inp, width: 48, height: 30, textAlign: 'center', padding: 0 }} />
                  ) : (
                    <button type="button" title="Change icon" onClick={() => c.id !== 'UNCATEGORIZED' && setIconEdit({ id: c.id, icon: c.icon || '' })}
                      style={{ width: 32, height: 30, border: 0, background: 'transparent', fontSize: 18, padding: 0 }}>{c.icon || '🏷️'}</button>
                  )}
```
- The add form gets `icon` in `draft` (default `''`) and an input `placeholder="Icon"` 56 px wide before the Name input; `api.addCategory(draft)` already sends it. Reset includes `icon: ''`.
- `describe` already uses `categoryLabel`, which now includes the icon.

- [ ] **Step 6: Build, commit**

`npm run build` in `frontend\` → `✓ built`. Commit the five files with message `Frontend: category icons everywhere; filtered totals on the Transactions page`.

---

### Task 3: Verify live and hand off

- [ ] The server must be restarted by the user for the backend half (new column, icon seed, summary params). The frontend is served from disk at once. After restart: badges show icons, the filter dropdown shows icons, Categories tab icon edit works, selecting a category changes "Spent this month".
- [ ] Update `HANDOFF.md` locally. Do not commit it.

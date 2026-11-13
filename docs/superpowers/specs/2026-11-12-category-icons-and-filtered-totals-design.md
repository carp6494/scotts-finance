# Category icons and filtered totals

Date: 2026-11-12. Status: approved.

## Goal

Every category carries an icon that shows wherever the category shows. The totals on the Transactions page follow the active filters.

## Icons

Icons are emoji stored as text. No image assets, so they work inside native dropdowns, badges, and plain text.

- `categories.icon TEXT`, added with the existing additive migration pattern.
- Every seeded Plaid code gets an icon from a static `ICONS` dict in `backend/categories.py`. Codes not in the dict fall back to their group's icon in `GROUP_ICONS`. `UNCATEGORIZED` is `❔`.
- A custom category gets its group's icon when the group is known, else `🏷️`, unless the add form gives one.
- `seed()` fills `icon` only where it is null, so a user edit survives restarts.
- `PATCH /api/categories/{id}` accepts `icon`. Stripped, at most 16 characters, empty resets to the default for that row.
- `POST /api/categories` accepts optional `icon`.
- `grouped()` and `get()` return `icon`.

Everywhere a category is shown, the icon leads: the badge in transaction lists, the picker list, the category filter dropdown, the rule editor dropdown, the rule summary line, and the Categories tab. `categoryLabel` returns `"🍔 Food & drink · Fast food"`.

The Categories tab gets an icon field per row: a 48 px wide text input showing the icon, committing on blur or Enter, Escape cancels. The add form gets an optional icon input.

## Filtered totals

`GET /api/summary` accepts optional `account_id` and `cat_id`. When either is given, `spent_month` and `income_month` are restricted to matching rows. Net worth and balances are unaffected.

The Transactions page fetches `api.summary({ account_id, cat_id })` whenever the account filter, the category filter, or the summary prop changes, and shows those two numbers. With a filter set, the caption under each card reads "This month, filtered". With no filter the caption is hidden. The "Whole month, all categories" caption goes away.

## Testing

- `test_categories.py`: seed assigns icons; seed does not overwrite an edited icon; custom category inherits the group icon; unknown code gets its group icon.
- `test_api.py`: PATCH icon validation; summary with `cat_id` and `account_id`.

## Out of scope

Icon pickers, image icons, per-group icon editing.

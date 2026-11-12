# Categories and rules engine

Date: 2026-11-12. Status: approved.

## Goal

Every transaction gets a category the user can trust and change. Rules do the repetitive work. Nothing the user sets by hand is ever overwritten by automation.

## Scope

In: categories table seeded from Plaid's full taxonomy, custom categories, categorization order, rules engine, category editing in transaction lists, "make this a rule" prompt with a preview, category filter, Rules page with a Categories tab, spending totals that ignore transfers and excluded items, first pytest setup.

Out, for later rounds: review queue, tags, splits, transfer pairing, duplicate detection, places and addresses, the 3D map.

## Data model

Additive changes only, using the existing `ALTER TABLE ... ADD COLUMN` pattern in `backend/db.py`.

### categories

| Column | Notes |
|---|---|
| id TEXT PK | Plaid detailed code for seeded rows, for example `FOOD_AND_DRINK_FAST_FOOD`. `custom-<slug>` for user rows. `UNCATEGORIZED` is a seeded row. |
| group_name TEXT | Readable group, for example "Food & Drink" |
| name TEXT | Readable name, for example "Fast Food" |
| type TEXT | `income`, `expense`, or `transfer` |
| hidden INTEGER | 1 hides it from pickers. Existing transactions keep it. |
| custom INTEGER | 1 for user-created rows |
| sort INTEGER | Order within the group |

Seed: all Plaid personal finance categories, 16 groups and about 104 detailed codes, from a static list in `backend/categories.py`. Groups `INCOME` map to type income. `TRANSFER_IN`, `TRANSFER_OUT`, and `LOAN_PAYMENTS` map to type transfer. Everything else is expense. Names derive from the code with title case and lowercase "and", with hand overrides where that reads badly. Any Plaid or import value not in the seed is inserted on first sight with a derived name, so no transaction is ever left without a matching row.

### transactions, new columns

| Column | Notes |
|---|---|
| cat_id TEXT | Effective category. Always set after the engine runs. |
| cat_source TEXT | `user`, `rule:<id>`, `merchant`, `plaid`, or `none` |
| excluded INTEGER | 1 removes it from spending and income totals |
| is_transfer INTEGER | 1 treats it as a transfer regardless of category |
| display_name TEXT | Merchant name set by a rule or the user. Shown instead of `merchant_name` when present. |

The existing `user_category` column stays but is no longer read.

### rules

| Column | Notes |
|---|---|
| id INTEGER PK | |
| name TEXT | Shown in the list |
| priority INTEGER | Lower runs first. Ties break by id. |
| enabled INTEGER | Disabled rules are skipped. On the next run, transactions they had set fall back to the next source. |
| conditions TEXT | JSON, see below |
| actions TEXT | JSON, see below |
| created_from TEXT | transaction_id when made from an edit, else null |
| hits INTEGER | Count of transactions this rule has set |
| last_applied TEXT | Timestamp |
| created_at TEXT | |

### merchant_memory

| Column | Notes |
|---|---|
| merchant_key TEXT PK | `lower(trim(coalesce(merchant_name, name)))` |
| cat_id TEXT | The category the user last chose for this merchant |
| updated_at TEXT | |

## Conditions and actions

Conditions are a JSON object. Every key present must match. Missing keys are ignored.

| Key | Match |
|---|---|
| merchant | Case-insensitive substring of `display_name`, `merchant_name`, or `name` |
| text | Case-insensitive substring of `name` |
| amount_min, amount_max | Inclusive bounds on the stored amount. Positive is money out, matching Plaid. |
| account_id | Exact |
| day_min, day_max | Inclusive bounds on day of month from `date` |

Actions are a JSON object. Any subset may be present.

| Key | Effect |
|---|---|
| cat_id | Sets the category |
| display_name | Sets the merchant name shown, only when the row has none yet, so a name the user typed is kept |
| exclude | true sets `excluded` to 1 |
| transfer | true sets `is_transfer` to 1 |

A rule with no `cat_id` applies its other actions and lets the category fall through to the next source.

## Categorization order

`backend/rules.py` exposes `categorize(transaction_ids=None)`. With no ids it processes every transaction. For each transaction:

1. If `cat_source` is `user`, skip it entirely.
2. Walk enabled rules by priority. The first rule whose conditions all match applies its actions, sets `cat_source` to `rule:<id>`, and increments `hits`. If that rule set a category, stop.
3. If `merchant_memory` has the merchant key, use its category with source `merchant`.
4. If `category_detail` from Plaid is set, use it with source `plaid`, inserting the category row if it is new.
5. Else `UNCATEGORIZED` with source `none`.

Flags set by a rule in step 2 persist even when the category comes from a later step. Flags and display names are only ever set by the engine, never cleared, so a manual exclude or rename survives the next sync. A rule row whose JSON is missing, invalid, or not an object is skipped and logged. Re-running the engine recomputes steps 2 to 5 for every non-user transaction, so a transaction set by a rule that no longer matches falls back correctly.

The engine runs after each Plaid sync on the added and modified ids, after each CSV import on the imported ids, once at startup for rows where `cat_id` is null, and on demand from the API.

## API

All under `/api`, behind the existing sign-in middleware.

| Method | Path | Body or params | Returns |
|---|---|---|---|
| GET | /categories | | groups, each with its categories, hidden included with the flag |
| POST | /categories | name, group_name, type | the new category |
| PATCH | /categories/{id} | name, group_name, hidden | the category |
| GET | /transactions | existing params plus cat_id, spending_only | rows gain cat_id, cat_name, cat_group, cat_type, cat_source, excluded, is_transfer, display_name |
| PATCH | /transactions/{id} | cat_id, notes, excluded, is_transfer, display_name, any subset | the row plus `similar`, the count of other non-user transactions with the same merchant key whose category differs |
| GET | /rules | | rules ordered by priority |
| POST | /rules | name, priority, conditions, actions, created_from, apply_past | the rule plus `changed` when apply_past is true |
| PUT | /rules/{id} | same fields plus enabled | the rule |
| DELETE | /rules/{id} | | ok |
| POST | /rules/preview | conditions, actions | count of non-user transactions that match, plus up to 10 sample rows |
| POST | /rules/apply | | runs the engine over every non-user transaction, returns changed count |

Setting `cat_id` through PATCH sets `cat_source` to `user` and writes `merchant_memory`. Setting other fields alone does not lock the category.

`spending_only=1` on the transactions list hides rows where `excluded` is 1, `is_transfer` is 1, or the category type is transfer.

`/summary` counts spending as rows with amount above zero, category type expense, `excluded` 0, `is_transfer` 0. Income is the same with amount below zero and type income.

## Frontend

**CategoryPicker component.** A badge showing group and name. Click opens a popover with a search box and the grouped list, hidden categories left out. Typing filters. Enter picks the first match. Escape closes. A "New category" row at the bottom opens a small form with name, group, and type. Used in `TxList` and the account drawer's transaction list, which already share `TxList`.

**TxList changes.** The category text becomes the picker. The merchant shows `display_name` when set. Rows with `excluded` or `is_transfer` render muted. After a category change, if `similar` is above zero, a one-line bar appears under the row: "Always file [merchant] as [category]? [N] past transactions would change." with buttons Make rule and Not now. Make rule creates a rule with a merchant condition and a category action, applies it to the past, and shows a toast with the count.

**Transactions page.** A category filter dropdown using the same grouped list, and a checkbox "Hide transfers and excluded". Totals at the top respect both.

**Rules page.** New nav item. Two tabs.

- Rules tab: list with name, a plain-language summary of conditions and actions, hits, an enable switch, edit, and delete. New rule opens the editor: name, priority, the six condition fields, the four action fields, and a live line "Matches N transactions" that updates as fields change, debounced. Buttons Save and Save and apply to past.
- Categories tab: groups with their categories. Inline rename, hide switch, and an add form. Custom categories are marked.

**Dashboard.** No layout change. "Spent this month" and "Income this month" now come from the corrected summary.

## Error handling

- Unknown `cat_id` in any request returns 400.
- Rule conditions with `amount_min` above `amount_max`, or day bounds outside 1 to 31, return 400.
- The engine never raises on a bad rule row. A rule whose JSON fails to parse is skipped and logged once per run.
- Rename or hide of `UNCATEGORIZED` returns 400.

## Testing

Add `pytest` in a `requirements-dev.txt`. `backend/db.py` reads an optional `FINANCE_DB` environment variable for the database path so tests use a temporary file. Tests in `backend/tests/test_rules.py` cover:

- Each condition type matches and fails correctly.
- Priority order and tie break.
- A user-set transaction is never changed by the engine.
- Merchant memory applies when no rule matches.
- Plaid fallback inserts an unseen category.
- Disabled rules are skipped.
- Re-running after a rule stops matching falls back to the next source.
- Flags from a rule without a category persist with the fallback category.
- `similar` count from the PATCH endpoint.

Frontend is verified by hand in the running app.

## Migration and backfill

On startup `db.py` adds the columns and tables, `categories.py` seeds rows with `INSERT OR IGNORE`, and `rules.categorize()` runs for rows with null `cat_id`. On the current database that is about 2,300 rows and completes in well under a second.

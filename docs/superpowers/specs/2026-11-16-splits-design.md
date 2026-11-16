# Splits and money owed back: design

Date: 2026-11-16

## Goal

Divide one bank charge across several categories, and mark part of a charge as owed back by a person. Track what is owed until a payback arrives.

## Decisions made with the owner

- Both uses: one store trip across categories, and a cost shared with someone.
- Owed parts name a person. A payback is linked to the deposit that paid it, so that deposit does not count as income.
- The "Owed to you" list is a box on the Transactions page. It is always there, even when nothing is owed.
- Receipt scanning is a later, separate project. Pantry Pal has only a design for it, in its `PLAN.md` section 11, and no code.

## Storage

Split lines live in their own table. The bank row is untouched. `SPEC.md` sketched child transactions with a split parent id; that idea is dropped because every query and the Plaid sync would need to tell parents from children.

- `splits`: id, transaction_id, seq, amount, cat_id, owed_by, note. `amount` uses the bank's sign, positive is money out. A line has a `cat_id` or an `owed_by`, never both.
- `paybacks`: id, split_id, payment_id, amount, cash, created_at. `payment_id` is the deposit's transaction id, or null when `cash` is 1.
- `payback_dismissed`: split_id, payment_id. A suggestion the owner turned down with "Not this".
- A deposit is a posted transaction with a negative amount, money in.
- The owed amount still open on a line is its amount less the sum of its `paybacks.amount`.
- People are the `owed_by` text. Names are trimmed and compared without case. "sam" and "Sam" are one person, shown as first written.

## Splitting

- The category picker gains "Split" at the bottom, next to "New category". It opens an editor under the row.
- A line is a category and an amount, or "Owed by" a name and an amount. Owed lines take no category.
- "Add line" adds a line. "Split evenly" divides the charge across the current lines, with any leftover cent on the first line.
- The editor shows the amount left. "Save" works only when the lines add up exactly to the charge and there are at least two lines.
- A split row's category pill reads "Split · N lines". Its lines show small under the row: category or "Owed by Name", then amount.
- Clicking the pill reopens the editor. "Unsplit" removes the lines. When any line has a payback, "Unsplit" first asks, and then removes those paybacks too.
- Pending charges cannot be split. "Split" is not offered on them.
- Splitting does not change `reviewed`.

## Totals

- A view, `tx_lines`, gives one row per line: a transaction with no splits is one line with its own category and amount; a split transaction gives one line per split.
- "Spent this month", "Income this month" and the Category filter totals read `tx_lines`.
- Owed lines are never spending.
- A deposit with any payback linked is not income.
- The Category filter on the transaction list shows a split transaction when any of its lines has that category.

## Owed to you box

- On Transactions, below the new-transactions box, above the "Spent this month" cards. Always shown.
- Header: "$64.00 owed to you", or "Nothing owed to you" with the line "Split a charge and mark a line Owed by someone to track it here."
- One row per person with open items: their name, their open total, then each open item with date, merchant, and amount left.
- Each open item has "Link payment" and "Paid in cash".
- "Link payment" lists deposits from the item's date on, newest first, that are not already linked in full. Picking one links it. One payment can pay several items. A payment applies to the chosen item up to that item's open amount. Whatever is left of the payment can be linked to further items.
- "Paid in cash" closes the item with a cash payback and no deposit.
- Suggestion: a deposit dated on or after an item, with an amount equal to the item's open amount, not yet linked, shows as "Venmo $40.00 on Nov 14 matches Sam's $40.00." with "Link" and "Not this". "Not this" hides that pair for good.
- A linked payment shows the person's name on its row in the transaction list: "Payback from Sam".
- Each payback shows as a small pill on its item, with an x that unlinks it and reopens that amount.
- "Paid back lately" lists items fully paid back in the last 30 days, with their payback pills, so a wrong link or a wrong "Paid in cash" can be undone.

## When the bank changes things

- Plaid changes the amount on a split transaction: the lines stay as they are. The transaction is set to `reviewed`=0 so it returns to the new box, and its row shows "Split is off by $X". Totals use the lines until the owner fixes them.
- Plaid deletes a split transaction: its lines and their paybacks are deleted.
- Plaid deletes a linked payment: its paybacks are deleted and those items reopen.
- Category rules skip split transactions. Tags stay on the whole transaction and tag rules work as before.

## Routes

- `PUT /api/transactions/{id}/splits` with `lines`: replaces all lines. Validates the sum, two or more lines, one of category or name per line, not pending. Keeps paybacks on owed lines whose person and amount are unchanged; refuses with a message if a change would drop a line that has paybacks.
- `DELETE /api/transactions/{id}/splits`: unsplit. With `force=1` it also removes paybacks.
- `GET /api/owed`: people with open items, the total, suggestions, items paid back lately, and every name used so far for the editor's suggestions.
- `GET /api/owed/{split_id}/payments`: deposits that can be linked.
- `POST /api/owed/{split_id}/payback` with `payment_id` or `cash`: link.
- `DELETE /api/paybacks/{id}`: unlink.
- `POST /api/owed/{split_id}/dismiss` with `payment_id`: "Not this".
- `GET /api/transactions` returns `splits` on each row, `split_off` when the lines do not add up, and `payback_from` on linked deposits.

All sit under `/api/` behind the sign-in. Nothing new leaves the PC.

## Tests

- `test_splits.py`: save, sum check, pending refused, totals by line, owed lines out of spending, category filter, unsplit, rules skip split rows, Plaid amount change, Plaid delete.
- `test_owed.py`: open items per person, name matching, link, partial, one payment across two items, cash, unlink, suggestion and dismiss, linked deposit out of income, payment deleted by Plaid.
- Browser pass on a database copy, light and dark.

## Out of scope

Rules that split automatically, receipt scanning, percentages, tags on single lines, splitting pending charges.

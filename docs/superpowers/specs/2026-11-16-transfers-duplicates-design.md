# Transfers and duplicates: design

Date: 2026-11-16

## Goal

Find money that moves between the owner's own accounts, such as checking paying a credit card, and link the two sides so neither counts as spending or income. Stop a CSV import from adding rows the account already has.

## Decisions made with the owner

- Transfers link on their own when the match is clear. Each row says where the money went. A link can be undone, and an undone pair stays undone.
- When a row could match more than one partner, the app asks on the row instead of guessing.
- No separate duplicate finder. Real duplicates are rare and obvious. The CSV import gets a wider "already here" check, and that is all.
- Lookalike rows from the bank feed each carry their own bank id. They are almost always real repeat purchases, so the app leaves them alone.
- A card payment the app filed under a store's spending category is the main thing this fixes. Once linked, it stops counting as spending.

## Storage

- `transfers`: out_id, in_id, source, created_at. `out_id` is the row where money left, a positive amount. `in_id` is the row where it arrived, a negative amount. Each id appears in at most one pair. `source` is `auto` or `user`.
- `transfer_dismissed`: out_id, in_id. A pair the owner unlinked or turned down. It is never linked again.
- The existing `is_transfer` flag is set to 1 on both rows of a pair. Totals, the map, and the "Hide transfers and excluded" box already leave flagged rows out.

## Matching

A pair is two rows that meet all of these:

- Both are posted, not pending.
- They are on two different accounts.
- One amount is the other's negative, to the cent.
- Their dates are at most 3 days apart.
- Neither row is split, excluded, or already in a pair.
- Neither row is a deposit linked as a payback in the Owed box.
- The pair is not in `transfer_dismissed`.

Rows from Plaid and rows from CSV imports both count. Hidden accounts count too.

`transfers.detect()` builds the candidates for every unpaired row. It links a pair only when each row has exactly one candidate, and that candidate is the other. It makes one pass and does not guess by elimination. A row left with candidates is a question for the owner.

`detect()` never links a row that appears in `transfer_dismissed`. The owner has already weighed in on that row, so its other candidates show as options instead. Without this, unlinking A from B would let the next pass link A to its only other candidate without asking. The owner can still link such a row by hand.

`detect()` runs:

- At startup, over all history.
- After each Plaid sync, after that sync's categorize step.
- After each CSV import, after its categorize step.

## What a link does

- Sets `is_transfer` to 1 on both rows.
- Fixes a category the app picked. If a row's category is not a transfer type and its `cat_source` is not `user`, the category changes and `cat_source` becomes `transfer`. When the money goes to a credit account, both rows get `LOAN_PAYMENTS_CREDIT_CARD_PAYMENT`. Otherwise the out row gets `TRANSFER_OUT_ACCOUNT_TRANSFER` and the in row gets `TRANSFER_IN_ACCOUNT_TRANSFER`. Missing categories are made with `categories.ensure`.
- A category the owner set by hand is kept.
- `rules.categorize` skips rows in a pair, the same way it skips split rows. A later sync cannot undo the fix.
- `reviewed` does not change.

## Unlink

- Deletes the pair and adds it to `transfer_dismissed`.
- Sets `is_transfer` to 0 on both rows. A rule that marks a row as a transfer sets it again on the next categorize.
- For a row whose `cat_source` is `transfer`, clears `cat_source` and runs `rules.categorize` on it, so it is filed the way it would be without the link.

## On the page

- A linked row shows a pill instead of the plain "Transfer" label: "Transfer to Travel Card" on the out row, "Transfer from Checking" on the in row. The name is the other account's name. The pill has an x that unlinks the pair.
- A row with a rule's transfer flag and no pair keeps the plain "Transfer" label.
- A row with candidates shows a line under it, like the rule suggestion line. For each candidate: "Possible transfer: $50.00 into Travel Card on Nov 3" and a "Link" button. One "Not a transfer" button at the end turns down every candidate for that row.
- "Split" is not offered on a linked row.
- Every change sends `txChanged({reload: true})` so all lists and the Owed box stay in step.

## Splits and the Owed box

- `splits.save` on a linked row fails with "This is a transfer. Unlink it before splitting."
- A linked deposit is not offered as a payback, and a payback deposit is never matched as a transfer.

## When the bank changes things

- `transfers.prune()` drops a pair when either row is gone, or when the amounts or dates no longer match. A dropped pair is not dismissed. Its rows go back to the categorizer, and the next `detect()` may link them again.
- `prune()` also drops dismissed pairs whose rows are gone.
- `prune()` runs at startup, after each sync's removals, and after an item is removed.

## Duplicates at CSV import

- Rows whose hash id already exists are skipped, as today.
- Each remaining row looks for an existing row on the same account with the same amount, to the cent, dated at most 2 days away. Any source counts, pending rows too. A same-date match is preferred, then the nearest date.
- A match is skipped. Each existing row can match only one imported row, so two real identical purchases in the file still land if only one is already there.
- Skipped rows add to `duplicates` in the result. The account drawer already says "skipped N already here".

## Routes

| Method | Path | Does |
|---|---|---|
| POST | /api/transfers | Body `{a, b}`: link two rows by hand. The server works out which is out. Same rules as matching. 400 when they do not qualify. |
| DELETE | /api/transfers/{transaction_id} | Unlink the pair holding this row. 404 when it is not in a pair. |
| POST | /api/transfers/{transaction_id}/dismiss | "Not a transfer": dismiss every current candidate for this row. |

`GET /api/transactions` adds two fields to each row:

- `transfer`: null, or `{id, account, dir}` where `dir` is `to` or `from`.
- `transfer_options`: a list of `{id, account, date, display_amount}`. Empty when the row is linked or has no candidates.

## Tests

`backend/tests/test_transfers.py`:

- A clear pair links, both rows get the flag, and a picked category becomes a transfer one.
- A category set by hand is kept.
- A pair 4 days apart, on one account, or off by a cent does not link.
- A row with two candidates is not linked and shows both as options.
- Link by hand, unlink, and dismiss. A dismissed pair does not come back on the next `detect()`.
- Unlink sends the rows back through the categorizer.
- `rules.categorize` leaves linked rows alone.
- Split rows, excluded rows, pending rows, and payback deposits are skipped. `splits.save` refuses a linked row.
- `prune()` drops a pair when a row is removed or its amount changes.
- The month's spending total leaves out both rows of a pair.

`backend/tests/test_import.py`, new. The CSV import has no tests today.

- A CSV row matching an existing row 1 day away is skipped and counted.
- Two identical CSV rows against one existing row: one is skipped, one is added.
- A match 3 days away is added.

## Out of scope

- A finder for duplicates inside the bank feed.
- Plaid rows that arrive after a CSV import already covered the same account.
- Transfers to accounts with no transaction history, such as investment accounts. Those stay one-sided, filed by their category.
- Bulk linking, and a rule action that links pairs.

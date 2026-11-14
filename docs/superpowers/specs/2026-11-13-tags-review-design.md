# Tags and review queue: design

Date: 2026-11-13

## Goal

Let the owner label transactions with tags, and give new transactions one place to be checked.

## Decisions made with the owner

- A transaction keeps its one category and can carry any number of tags.
- Tag colors are picked automatically and can be changed.
- When the queue first exists, every stored transaction counts as reviewed, except the newest five. Those stay so the queue has something to show.

## Tags

- Tables: `tags` (id, name, color), `transaction_tags` (transaction, tag, source), `removed_tags` (transaction, tag).
- Names ignore case, are trimmed, and hold at most 32 characters.
- A new tag takes the next color from a fixed list of ten.
- Each transaction row shows its tags as pills, then a "+ tag" button. The button turns into a text box that suggests existing tags. Enter adds. The x on a pill removes.
- Removing a tag by hand writes a row in `removed_tags`. Rules skip that pair from then on. Adding the tag by hand again clears it.
- Rules gain an "Add tags" field. The form sends names. The rule stores tag ids, so a rename keeps the rule working and a delete stops it.
- Tag rules differ from category rules in two ways. They also apply to transactions the owner categorized by hand. Every matching rule adds its tags, not only the first.
- The "Transactions" page gains a "Tag" filter. The totals follow it. Search also matches tag names.
- The "Rules" page gains a "Tags" tab: rename, recolor, delete, and a count per tag. Deleting a tag takes it off every transaction.

## Review queue

- A transaction waits in the queue when `reviewed` is 0 and it is not pending.
- New rows from a sync or a CSV import arrive unreviewed.
- A bank's first sync brings up to two years of history. Those rows are marked reviewed.
- New sidebar entry "Review" with a count. The page lists waiting rows with a "Reviewed" button on each, and "Mark all reviewed" with a confirm step.
- Keys on the page: up and down move, Enter marks reviewed, C opens the category picker, T opens the tag box.

## Routes

- `GET /api/tags`, `POST /api/tags`, `PATCH /api/tags/{id}`, `DELETE /api/tags/{id}`
- `POST /api/transactions/{id}/tags`, `DELETE /api/transactions/{id}/tags/{tag_id}`
- `POST /api/review/all`
- `GET /api/transactions` gains `tag_id` and `unreviewed`, and returns `tags` on each row.
- `PATCH /api/transactions/{id}` gains `reviewed`.
- `GET /api/summary` gains `tag_id` and returns `unreviewed`.

All sit under `/api/` behind the sign-in. Nothing new leaves the PC.

## Tests

- `test_tags.py`: add and remove, name rules, colors, rule tagging, removed tags staying removed, rename and delete, filter, search, totals, pruning.
- `test_review.py`: what waits, marking one, marking all, the one-time start, a bank's first sync.

## Out of scope

Bulk edit, reports and tax summary by tag, a dashboard count, streaks.

# Review inside Transactions: design

Date: 2026-11-16

Replaces the "Review" sidebar entry and page from `2026-11-13-tags-review-design.md`. Tags, the queue rules, routes, and tests from that spec stay as they are.

## Goal

New transactions get checked on the Transactions page. There is no separate Review page.

## Decisions made with the owner

- A row leaves the new box only when the owner clicks "Reviewed" or presses Enter. Editing the category or tags does not clear it.
- New rows also show in the full list below the box, with a "New" label.

## Sidebar

- The "Review" entry is removed. `frontend/src/pages/Review.jsx` is deleted.
- The "Transactions" entry shows the count pill the Review entry had. It reads `summary.unreviewed` and hides at zero.

## The new box

- It sits at the top of the Transactions page, above the "Spent this month" cards.
- It shows only when at least one transaction waits for review.
- Look: a blue border in `var(--accent)` and a light blue tint, so it stands apart from the cards below.
- Header: "1 new transaction" or "N new transactions" on the left. "Mark all reviewed" on the right, with the same confirm step the Review page had.
- Rows: the shared transaction list in review mode. Each row has the category picker, tags, and a "Reviewed" button. No search box and no account filter inside the box.
- The Account, Category, and Tag filters do not apply to the box. Its count always matches the sidebar.
- The row area has a fixed maximum height of about eight rows and scrolls inside itself past that.
- When the last row is reviewed, the box goes away and a toast says "All caught up." It comes back when a sync brings new rows.

## Keys

- Up and down move, Enter marks reviewed, C opens the category picker, T opens the tag box. Same keys as before.
- The keys work only after the owner clicks a row in the box. Esc, or a click outside the box, turns them off. Until then the arrow keys scroll the page as usual.
- Keys are ignored while typing in a text box or select, same as before.

## The full list

- A row with `reviewed` 0 that is not pending shows a small "New" label after its name, in `var(--info)`, in the same spot as "Pending". `var(--accent)` is too dark for small text on the dark theme.
- A change made in the box reaches the full list at once: category, tags, and Reviewed. A change made in the full list reaches the box the same way.
- The full list keeps the rows already loaded with "Load more" when it refreshes for these changes. A change of filter still starts from the first page.

## Not changing

Backend, routes, `backend/review.py`, the one-time start, a bank's first sync, and the backend tests.

## Checking

On a copy of the database, using the test method in the handoff, in Chrome:

- The pill on "Transactions" shows the right count and there is no "Review" entry.
- The box shows the new rows. "Reviewed", Enter, and "Mark all reviewed" each clear rows, and the pill follows.
- The keys do nothing until a row in the box is clicked. Esc turns them off.
- The "New" label shows in the full list and goes away on review.
- A category or tag change in the box shows in the full list.
- The box disappears after the last row, with the toast.
- Dark and light themes both look right.

`npm run build` must pass. The backend tests must still pass.

## Out of scope

Clearing a row by editing it, a "New" filter on the full list, a dashboard count.

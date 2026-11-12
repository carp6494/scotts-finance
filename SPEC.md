# Scott's Finance App: Build Spec v1

Local personal finance app (Monarch-style, but better). Runs only on Scott's PC. No Claude API usage anywhere in the app. Claude access is through Claude Desktop (subscription) via a heavy markdown report and a local MCP server.

## 1. Stack

> As built, the stack differs from this list (venv, plain sqlite3, JSX, custom Tailwind components, no tests yet). See `docs/STATUS.md` "Known gaps vs SPEC" and `docs/ARCHITECTURE.md` for what's actually in use.

- Python 3.12, managed with `uv`
- Backend: FastAPI, served on `http://127.0.0.1:8765` (localhost only)
- Database: SQLite (`data/finance.db`), SQLAlchemy + Alembic migrations
- Frontend: React + TypeScript (Vite), Tailwind CSS, Tremor components and Tremor Blocks (free, open source), TanStack Query for API calls, TanStack Table for transaction grids. Built files served by FastAPI so it is one local app
- Node.js LTS needed for the frontend build only
- Bank data: Plaid (`plaid-python`), Production environment
- Secrets: Plaid client ID/secret in `.env` (gitignored); Plaid access tokens encrypted in the DB with a key stored in Windows Credential Manager (`keyring`)
- Scheduler: APScheduler inside the app (sync every 6 hours plus a manual "Sync now" button)
- Tests: pytest, with Plaid Sandbox fixtures
- Project folder: wherever the repo is cloned

## 1b. UI design system (set up first, before any screens)

- Base: Tremor Insights template (transactions and reports) and Dashboard template layouts, assembled from Tremor Blocks
- Dark mode default, light mode toggle
- Design tokens: colors, typography, spacing defined once in Tailwind config
- Status color language used everywhere: green positive / under budget, red negative / over budget, amber warning / close to limit, grey inactive
- Reusable components: KPI cards, budget progress bars, category badges, merchant logos, account cards, data tables, filter bars, date range picker
- Skeleton loaders instead of spinners
- Toast notifications (sync done, rule applied, report generated)
- Subtle transitions on panels, drawers, and modals
- Responsive grid that works on a big monitor and a laptop
- Keyboard shortcuts for the review queue (categorize, mark reviewed, next)

## 1c. Motion (lots of it, it is a core feature)

- Libraries: Motion (formerly Framer Motion) for page and component animation, NumberFlow (`@number-flow/react`) for rolling / flipping numbers. Both free, MIT
- **Odometer scroll** for the main money figures only, on every page (dashboard KPIs and net worth, transactions spent and income totals, runway cash today and cash in 12 months): each digit is a vertical 0 to 9 strip that scrolls slowly (about 2.4 s, slight left-to-right stagger) into place in the normal number style. Replays every time a page opens, the app refreshes, Scott switches screens, or the browser tab becomes visible again; also scrolls to new values when a what-if changes them
- Page transitions: animated route changes (slide and fade between screens), shared-element transitions where a card expands into its detail page
- Number flip on load: every dollar amount, percentage, and count rolls up from zero (or from its old value) when a page loads or data refreshes. KPI cards, budget totals, net worth, runway months, table totals
- Charts animate in: lines draw left to right, bars grow up, donuts sweep around, area charts fill. Tremor charts with animation turned on, plus custom Motion wrappers where needed. Charts also animate between values when filters or date ranges change
- Staggered entrance: dashboard cards and table rows cascade in one after another
- Budget progress bars fill to their value on load and pulse amber or red when near or over limit
- Micro-interactions: hover lift on cards, button press feedback, smooth drawer and modal open, row highlight when a rule updates a transaction
- Sync animation: live progress while Plaid sync runs, then new transactions slide into the list
- Theme: Light, Dark, and System (follows Windows), switch in the header, choice remembered
- Settings toggle to tone motion down, and respect the Windows "reduce animations" setting

## 2. Data model (core tables)

- `institutions`, `items` (one per Plaid login, encrypted access token, sync cursor, status)
- `accounts` (type, subtype, mask, current/available balance, hidden flag, include-in-net-worth flag)
- `balances_history` (daily snapshot per account)
- `transactions` (Plaid ID, account, date, authorized date, amount, raw name, clean merchant, Plaid category, user category, notes, tags, pending flag, excluded flag, split parent ID, reviewed flag)
- `categories` (group, name, icon, type: income / expense / transfer, budget behavior: fixed / flex / non-monthly)
- `rules` (priority, match conditions, actions, created from, last applied, hit count)
- `merchants` (raw name patterns to clean display name)
- `budgets` (month, category, amount, rollover on/off, rollover balance)
- `recurring_streams` (merchant, category, frequency, expected amount, next date, status, price history)
- `goals` (target, date, linked accounts, monthly contribution)
- `holdings`, `securities` (from Plaid Investments)
- `liabilities` (credit cards, loans: APR, minimum payment, due date)
- `attachments` (receipt images linked to transactions)
- `sync_log`, `audit_log` (every change to a transaction, with old and new values)

## 3. Phase 1: Accounts, transactions, categories, rules

- Plaid Link flow in the browser, add / reconnect / remove institutions
- `/transactions/sync` with stored cursor (handles added, modified, removed)
- Balances, Investments (holdings), Liabilities products pulled per item
- Merchant cleanup ("SQ *JOES BBQ 1234 SPRINGFIELD" to "Joe's BBQ")
- Categorization order: user rule, then merchant memory (last category used), then Plaid category mapped to Scott's categories, else Uncategorized
- Rules engine: match on merchant, raw text, amount range, account, day of month; actions set category, rename merchant, add tag, exclude, mark as transfer, split
- "Create rule from this edit" prompt whenever a category is changed manually, with "apply to past transactions" preview
- Transaction list: search, filters (date, account, category, tag, amount, reviewed), bulk edit, split, notes, tags
- Transfer detection: matching opposite amounts between own accounts within 3 days
- Duplicate detection
- Review queue: new transactions marked unreviewed until confirmed
- CSV / OFX / QFX import for anything Plaid cannot reach
- Manual accounts (cash, vehicles, home value)
- Accounts to connect: checking, savings, credit cards, investments, mortgage, plus the home as a manual asset (estimated value, linked mortgage, equity shown)
- **Account detail drawer:** click any account to slide in everything Plaid provides for it. Cards: balance owed, credit used bar, limit, available credit, last statement balance and date, minimum payment, due date, last payment, APRs, overdue flag, interest paid, spend this month, card ending, last synced. Bank accounts: available vs current, pending, money in/out, masked account and routing numbers, recent transactions. Investments: sub-accounts, holdings, cost basis, gains. Home: value, mortgage balance, equity, LTV, rate, payment, due date, escrow, PMI, interest paid, maturity
- Discover logo: Discover no longer has its own ticker, so it is not in the Stock Bot set; use the Discover card artwork from the open-source datatrans/payment-logos repo on GitHub, saved into `data/logos/`

## 4. Phase 2: Budget, recurring, runway

- Monthly budget per category, rollover on/off, Flex Budgeting (fixed, flex pool, non-monthly)
- Budget vs actual with progress bars and pace indicator (on track / ahead / behind for day of month)
- Recurring detection from history (frequency, typical amount, next expected date); manual add; status active / cancelled
- Price change alerts on recurring charges
- Upcoming bills calendar (next 30 days)
- Cash flow forecast: balances projected 90 days out from recurring income and bills
- **Runway mode:** liquid cash divided by monthly burn, shown three ways: current spending, budget spending, essentials only. Shows the date cash runs out and how much each cut extends it
- **Spending audit:** subscriptions not used or recently increased, categories trending up 3 months in a row, largest discretionary merchants

## 5. Phase 3: Dashboard, reports, net worth

- Dashboard: net worth, cash, this month spend vs budget, upcoming bills, runway, unreviewed count
- Reports: spending by category / merchant / tag, income vs expense, month over month, year over year, Sankey cash flow chart
- Net worth history from daily snapshots, assets vs liabilities
- Investments view: holdings, allocation, value history
- Goals with progress and projected completion date
- Receipt upload: attach image to a transaction, split into line items manually
- Export any report to CSV

## 6. Phase 4: Claude integration (no API)

### 6a. Claude Report (heavy markdown export)

Button: "Generate Claude Report" with period picker (default last full month). Writes `reports/finance_report_YYYY-MM.md`. Sections:

1. Prompt header: who Scott is financially (situation set in Settings), what to analyze, what questions to answer
2. Summary: income, spending, net cash flow, savings rate
3. Balances by account and net worth with 12 month history
4. Runway: all three scenarios with run-out dates
5. Budget vs actual for every category, rollover balances
6. Category and merchant trend tables, 6 to 12 months
7. Recurring charges: full list, frequency, amount, price history, next date
8. Anomalies: unusual amounts, new merchants, duplicates, fees, interest charges
9. Uncategorized and unreviewed transactions
10. Debts: balances, APRs, minimums, due dates
11. Goals progress
12. Full transaction ledger for the period (date, account, merchant, amount, category, tags, notes)
13. Rules list (so Claude can suggest new or better rules)

### 6b. Local MCP server (Claude Desktop)

- Python `mcp` SDK (FastMCP), stdio transport, separate entry point `finance-mcp`
- Read-only database connection
- Tools: `get_summary(period)`, `search_transactions(filters)`, `spending_by_category(period)`, `spending_by_merchant(period)`, `get_budget_status(month)`, `list_recurring()`, `get_runway()`, `get_net_worth_history()`, `get_accounts()`, `list_rules()`, `generate_report(period)`
- Optional write tools (off by default, toggle in Settings): `set_category(transaction_id, category)`, `create_rule(...)`; every write logged to `audit_log`
- Setup docs include the exact `claude_desktop_config.json` block

## 6c. Extra features

- **What-if simulator:** sliders and toggles (cancel subscriptions, cut a category, new income starting on a date) that move the runway date and forecast chart live
- **Debt payoff planner:** avalanche vs snowball, interest saved, payoff dates per debt
- **Free trial and refund tracker:** log trials with end dates and alert before they convert; track expected refunds and flag ones that never posted
- **Tax mode (personal):** tag tax-relevant transactions all year (medical, charity, education, etc.), year-end summary export
- **Personal inflation rate:** price change over time at the merchants and categories Scott actually uses
- **Card optimizer:** best card per category based on rewards, plus interest and fees paid per card
- **Spending patterns:** time of day, weekday vs weekend, small impulse purchases under $20

## 6d. Extra UI

- **Command palette (Ctrl+K):** search and jump to any transaction, merchant, category, account, or screen; run actions (sync, generate report)
- **Spending heatmap calendar:** GitHub-style daily grid, click a day to see its transactions
- **Animated Sankey and treemap:** income flowing into categories, category size by spend
- **Year in Review:** animated full-screen story recap (top merchants, biggest month, wins), Spotify Wrapped style
- **Wall screen mode:** read-only kiosk view sized for a wall display (balances, budget bars, upcoming bills), auto-rotating panels
- **Wins:** confetti on goal hit or month under budget; streak counter for clearing the review queue

## Future (not in v1)

- Business bookkeeping module (own QuickBooks): separate company ledgers, invoicing, P&L, Schedule C export

## 6e. Logo cache (download once, never call again)

- Seed from the bundled set in `assets/ticker-logos/` (2,081 PNGs named by ticker, from Finnhub, plus `_symbols.json`; originally from Stock Bot, now a standalone copy). Copy them into `data/logos/tickers/` and keep a merchant-to-ticker map (Walmart to WMT, Costco to COST, Netflix to NFLX, etc.)
- New merchant seen for the first time: download its logo once from Plaid's merchant `logo_url`, else Finnhub company profile logo (public companies), else the merchant website's icon
- Save to `data/logos/<merchant_id>.png` and record the path in the `merchants` table; the app only ever loads logos from disk
- Never re-download unless Scott clicks "Refresh logo" or uploads his own
- Fallback: colored initial tile (as in the mockup)

## 7. Security

- Localhost binding only, no remote access
- Plaid tokens encrypted at rest, key in Windows Credential Manager
- `.env`, `data/`, `reports/`, `attachments/` all gitignored
- Nightly DB backup to `backups/` (keep 30); optional copy to Synology NAS path

## 8. Acceptance checks per phase

- Phase 1: Sandbox item links, syncs 2 years of history, rules apply, re-sync creates no duplicates
- Phase 2: budget math matches manual check for one month; runway matches hand calculation
- Phase 3: net worth equals sum of account balances; charts render with real data
- Phase 4: report opens cleanly in a Claude project; Claude Desktop lists MCP tools and answers "what did I spend on groceries last month" correctly

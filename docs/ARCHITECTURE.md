# Architecture (as built)

## Layout

```
Scott's Finance App\
  start.bat              setup + run (venv, pip, build frontend if missing, run backend)
  requirements.txt       fastapi, uvicorn, plaid-python, python-dotenv, cryptography, keyring, httpx, pyotp, qrcode
  .env / .env.example    PLAID_CLIENT_ID, PLAID_SECRET, PLAID_ENV, PLAID_REDIRECT_URI, TICKER_LOGOS, OPEN_BROWSER
  backend\
    app.py               FastAPI app, auth middleware, all endpoints, static serving, timers
    db.py                SQLite schema, migrations (ALTER ADD COLUMN), helpers q/one/run/many/dumps
    secure.py            Fernet encrypt/decrypt; key in Windows Credential Manager via keyring
    plaid_sync.py        Plaid client: link token, exchange, transactions_sync, accounts, liabilities, holdings, item_remove
    logos.py             logo cache (tickers, merchants, institutions)
    auth.py              TOTP sign-in (pyotp), sessions, settings table
    maintenance.py       daily backup + 7-year purge
  frontend\              React 19 + Vite 7 + Tailwind 4 + motion + react-plaid-link
    src\api.js           fetch wrappers for every endpoint, money/date/title helpers, 401 -> 'auth-required' event
    src\App.jsx          sign-in gate, header (theme, sync, connect), page switcher, reconnect banners, toasts
    src\components\      Odometer, Logo, ConnectButton, TxList, AccountDrawer, Lock
    src\pages\           Dashboard, Transactions, Debt
    public\brand\        app-icon.png, discover-card.png
  assets\ticker-logos\   2,081 ticker PNGs + _symbols.json (bundled source, gitignored)
  brand\                 app icon source (1024 px, used on the Plaid profile)
  data\                  finance.db (+ wal/shm), logos\ cache        (gitignored)
  backups\               finance-YYYY-MM-DD.db, keep 30              (gitignored)
  imports\               CSV statements for manual accounts           (gitignored)
```

## Database (`data/finance.db`)

| Table | Purpose |
|---|---|
| `items` | One per Plaid login: encrypted access token, institution, color, sync cursor, status/error, last_sync |
| `accounts` | Plaid and manual accounts: balances, limit, type/subtype, mask, hidden, manual, linked_account_id, institution, apr_override, limit_override, min_payment_override |
| `transactions` | Plaid id or CSV hash id, account, dates, amount (positive = out), name, merchant, pending, Plaid category, logo/website, user_category, notes, reviewed, raw JSON |
| `liabilities` | Per account: kind (credit, mortgage, student) + raw Plaid JSON |
| `holdings` | Investment positions per account/security |
| `sync_log` | Added/modified/removed counts and errors per sync |
| `settings` | Key/value (created in auth.py): `totp_secret` (encrypted), `totp_confirmed` |

The DB runs in WAL mode. Migrations are additive `ALTER TABLE ... ADD COLUMN` statements guarded in `db.py`.

## API (all under `/api`, all require the session cookie except `/api/auth/*`)

| Method | Path | Notes |
|---|---|---|
| GET | /auth/state | enrolled? signed in? |
| POST | /auth/setup | new TOTP secret, returns QR SVG (only before enrollment is confirmed) |
| POST | /auth/verify | 6-digit code, sets httponly `sf_session` cookie (12 h) |
| POST | /auth/logout | |
| GET | /status | Plaid configured, env, items + status |
| POST | /link/token | Link token (transactions, optional liabilities/investments, 730 days); pass item_id for update mode |
| POST | /link/exchange | public token -> encrypted access token, first sync |
| POST | /sync | sync all items |
| POST | /items/{id}/sync | sync one item |
| DELETE | /items/{id} | Plaid item_remove + local delete |
| GET | /accounts | list with computed apr, apr_source, min_payment, limit, logo |
| GET | /accounts/{id} | full detail: account, liability, holdings, transactions |
| POST / PUT / DELETE | /manual, /manual/{id} | home asset |
| POST | /manual/account | manual account (e.g. Lowe's / Synchrony) |
| PATCH | /manual/{id}/balance | manual balance/limit |
| POST | /accounts/{id}/import | CSV import, dedupe by sha1(account,date,amount,desc,occurrence) |
| PATCH | /accounts/{id}/terms | {apr, limit_amt, min_payment} overrides |
| GET | /debts | debts for the payoff planner |
| GET | /transactions | q, account_id, paging; adds display_amount |
| GET | /summary | KPI totals for the dashboard |

`/logos/*` is served from `data/logos`; everything else serves the SPA from `frontend/dist`.

## Flows

- **Sign-in:** First run shows a QR code, and Scott scans it into Microsoft Authenticator. Sessions are held in memory, so restarting the app means signing in again.
- **Plaid:** Link opens in the browser and the public token is exchanged. The access token is encrypted and stored. `transactions_sync` runs with a cursor and retries on `TRANSACTIONS_SYNC_MUTATION_DURING_PAGINATION`. After that, accounts, liabilities and holdings are pulled and the institution logo is saved once. When Plaid reports `ITEM_LOGIN_REQUIRED`, a reconnect banner opens Link in update mode.
- **Timers:** Auto sync runs every 6 hours (started at startup). Daily maintenance backs up to `backups/` (keeping 30) and purges transactions older than 7 years.
- **Logos:** For tickers, `assets/ticker-logos/<T>.png` is copied once into `data/logos/tickers/`, using the merchant-to-ticker map in `logos.py`. For merchants, the Plaid `logo_url` is downloaded once in the background. Institutions use the Plaid logo saved once. Special cases are Discover (`/brand/discover-card.png`) and the Lowe's, Best Buy and Capital One tickers. If none of these exist, the UI shows a letter tile.
- **Debt payoff:** A constant total payment (sum of minimums plus an extra amount from a slider) is applied, and freed minimums roll over to the next debt. Snowball orders debts by smallest balance and avalanche by highest APR. The page draws an SVG chart.

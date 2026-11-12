# Scott's Finance

A personal finance app that runs on your own PC. It pulls your bank, card, loan, and investment accounts through Plaid, keeps everything in one local database file, and shows it in your browser at a localhost address. No cloud account, no server, no AI calls. Your bank data goes from Plaid to your PC and nowhere else.

I built it for myself. You can run it too, but you need your own Plaid developer account. Plaid does not offer accounts to consumers, so there is some setup. The steps are below.

## What it does

- Connects banks through Plaid Link, with reconnect when a bank asks you to log in again
- Pulls up to two years of transactions, then syncs every six hours or when you click Sync now
- Shows balances, credit card and mortgage details, and investment holdings
- Opens a drawer for any account with everything Plaid returns for it and all of its transactions
- Transactions page with search and account filter
- Debt payoff page
- Manual accounts, home value with linked mortgage, and CSV import for anything Plaid cannot reach
- Sign-in with an authenticator app code
- Daily backups, keeps the last 30
- Light, dark, and system themes

## What you need

- Windows. The app keeps its encryption key in Windows Credential Manager.
- Python 3.10 or newer
- Node.js LTS, to build the web pages once
- A Plaid developer account

## Get Plaid keys

1. Sign up at dashboard.plaid.com.
2. Open Developers, then Keys. Copy the client ID and the production secret.
3. Request production access from the dashboard. Plaid asks what the app does and reviews the request. Until it is approved you can use sandbox mode, described below.
4. Open Settings, Compliance, US OAuth institutions. Some banks, Capital One and Chase among them, only appear in Plaid Link after you finish the registration listed there.

## Install and run

1. Clone or download this repo.
2. Double-click `start.bat`. On the first run it creates `.env` and opens it in Notepad.
3. Paste your client ID and secret into `.env`. Save and close.
4. Double-click `start.bat` again. It builds the web pages, starts the app, and opens your browser.
5. Scan the QR code with an authenticator app and enter the six-digit code. You will enter a code each time you open the app.
6. Click Connect account and sign in to each bank.
7. Click Add home to enter your home value and link your mortgage.

Keep the black window open while you use the app. Close it to stop.

## Try it without production access

Set `PLAID_ENV=sandbox` in `.env`. Plaid Link then shows test banks. Sign in to any of them with the username user_good and the password pass_good. The accounts and transactions are fake.

## Where your data lives

- `data\finance.db` holds accounts, transactions, and holdings. The bank access tokens inside it are encrypted. The key is in Windows Credential Manager.
- `.env` holds your Plaid keys. Never share it.
- `backups\` gets a copy of the database each day.
- `data\logos\` caches bank and merchant logos after the first download.

None of these are tracked by git. Transactions older than seven years are deleted during daily maintenance.

## If a bank is missing from Plaid Link

Check the OAuth page in the Plaid dashboard under Settings, Compliance, US OAuth institutions. If Plaid says a bank needs a redirect URI, add one under Developers, API, and put the same value in `PLAID_REDIRECT_URI` in `.env`.

## Import a CSV

Open an account, click Import CSV from bank, and pick the file your bank exported. The importer looks for date, description, and amount columns, or separate debit and credit columns. Tick the box if the file shows purchases as negative numbers.

## Working on the code

The backend is FastAPI in `backend\`. The frontend is React with Vite in `frontend\`. `SPEC.md` is the full plan and `docsARCHITECTURE.md` describes what is built. After changing frontend files, run `npm run build` inside `frontend\`. The app serves the built files.

## License

MIT, copyright Scott Carpenter. Use it, change it, share it. Keep the copyright line in the license file, and a link back to this repo is appreciated.

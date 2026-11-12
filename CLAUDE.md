# Scott's Finance App

Local personal finance app. Runs only on this PC. Plaid for bank data, FastAPI backend, React frontend, SQLite. Full build plan in `SPEC.md`. Layout and endpoints in `docs/ARCHITECTURE.md`. Security controls that must stay true in `docs/SECURITY.md`.

## Session handoff

**First action every session:** read `HANDOFF.md` at the project root. It holds
current state: what shipped, what is in progress, what is blocked. Do not ask
what happened last time. Read the file.

**Last action every session:** rewrite `HANDOFF.md` with current state. Replace
it, never append. Keep it under one page.

`HANDOFF.md` is gitignored and never committed. It may mention Scott's accounts
and next steps, and the repo is public. Do not force-add it.

## Public repository

This project is published at https://github.com/carp6494/scotts-finance under
the MIT license. Every committed file is public. Never put credentials, account
names, card endings, balances, rates, limits, transaction details, or sign-in
codes in any tracked file. Keep `.env`, `data\`, `backups\`, `imports\`, and
`HANDOFF.md` untracked. Before each commit, check the staged list.

## Writing

Plain, direct language. Short sentences. No em dashes, no parentheticals. Do
not write like a marketing page. Instructions name the exact button or menu.

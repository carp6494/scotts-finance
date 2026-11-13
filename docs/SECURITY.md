# Security controls (must stay true)

These controls back the security attestations Scott gave Plaid. The full policy is the Claude Doc "Scott's Finance App: Security Practices and Privacy Policy" (https://claude.ai/artifact/H2SpokD2pRz6ab1YZFuLw2). If a change would break any item below, stop and ask Scott first.

| Control | Where |
|---|---|
| App reachable only from this PC (127.0.0.1) | `app.py` uvicorn host |
| Sign-in required (TOTP, Microsoft Authenticator); httponly, same-site session cookie | `auth.py`, middleware in `app.py` |
| Sessions last 12 hours by default and 30 days at most; only a SHA-256 hash of the token is stored | `auth.py`, `PUT /api/settings/session` |
| Plaid access tokens encrypted at rest (Fernet); key in Windows Credential Manager | `secure.py` |
| Plaid keys only in `.env`, gitignored, never logged | `.env`, `.gitignore` |
| TLS for all Plaid traffic (plaid-python over HTTPS) | `plaid_sync.py` |
| Least data: only the transactions, liabilities and investments products | `create_link_token` |
| Retention: transactions older than 7 years purged daily | `maintenance.py` |
| Daily DB backups, 30 kept, local only | `maintenance.py` |
| Scott can remove a bank (Plaid item_remove + local delete) | `DELETE /api/items/{id}` |
| No data shared with third parties; no Claude API or other AI API calls | whole app |
| Dependencies from PyPI/npm only; keep them updated | `requirements.txt`, `package.json` |

Before a release-sized change, check:
- `git status` shows no `.env`, `data/` or `backups/` files staged
- No access token, secret or TOTP value appears in logs or API responses
- New endpoints are under `/api/` and covered by the auth middleware

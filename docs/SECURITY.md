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
| Shop icon fetch sends no owner or purchase data. HTTPS only, public hosts only, 3 redirects, 300 KB cap, one try per domain per 30 days. Off switch on the Settings page | `site_icons.py`, `PUT /api/settings/site-icons` |
| The Outline map and the World view load nothing from the network | `UsMap.jsx`, `GlobeMap.jsx` |
| The browser never contacts a map service. Satellite, terrain and building squares come through this app, from a fixed list of three free public services, and are saved in `data\tiles`. A request carries only the square's zoom and position. Each service has its own switch on the Settings page. Satellite photos are on. Terrain elevation and 3D buildings stay off until the owner turns them on | `tiles.py`, `GET /api/tiles/...`, `PUT /api/settings/map` |
| The local business extract names the owner's region, so it stays in `data\` and is never committed | `scripts/fetch_places.py`, `.gitignore` |
| Dependencies from PyPI/npm only; keep them updated | `requirements.txt`, `package.json` |

Before a release-sized change, check:
- `git status` shows no `.env`, `data/` or `backups/` files staged
- No access token, secret or TOTP value appears in logs or API responses
- New endpoints are under `/api/` and covered by the auth middleware

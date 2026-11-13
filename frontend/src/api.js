async function req(method, url, body) {
  const r = await fetch(url, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  })
  const data = await r.json().catch(() => ({}))
  if (r.status === 401 && !url.startsWith('/api/auth/')) window.dispatchEvent(new Event('auth-required'))
  if (!r.ok) throw new Error(data.detail || `Request failed (${r.status})`)
  return data
}

export const api = {
  authState: () => req('GET', '/api/auth/state'),
  authSetup: () => req('POST', '/api/auth/setup'),
  authVerify: (code) => req('POST', '/api/auth/verify', { code }),
  logout: () => req('POST', '/api/auth/logout'),
  status: () => req('GET', '/api/status'),
  summary: (p = {}) => { const qs = new URLSearchParams(Object.entries(p).filter(([, v]) => v !== undefined && v !== '')).toString(); return req('GET', '/api/summary' + (qs ? '?' + qs : '')) },
  accounts: () => req('GET', '/api/accounts'),
  account: (id) => req('GET', `/api/accounts/${encodeURIComponent(id)}`),
  transactions: (p = {}) => req('GET', '/api/transactions?' + new URLSearchParams(Object.entries(p).filter(([, v]) => v !== undefined && v !== ''))),
  linkToken: (item_id) => req('POST', '/api/link/token', { item_id: item_id || null }),
  exchange: (body) => req('POST', '/api/link/exchange', body),
  sync: () => req('POST', '/api/sync'),
  removeItem: (id) => req('DELETE', `/api/items/${id}`),
  addManual: (body) => req('POST', '/api/manual', body),
  updateManual: (id, body) => req('PUT', `/api/manual/${id}`, body),
  deleteManual: (id) => req('DELETE', `/api/manual/${id}`),
  addManualAccount: (body) => req('POST', '/api/manual/account', body),
  setBalance: (id, body) => req('PATCH', `/api/manual/${id}/balance`, body),
  setTerms: (id, body) => req('PATCH', `/api/accounts/${encodeURIComponent(id)}/terms`, body),
  debts: () => req('GET', '/api/debts'),
  importCsv: (id, body) => req('POST', `/api/accounts/${encodeURIComponent(id)}/import`, body),
  categories: () => req('GET', '/api/categories'),
  addCategory: (body) => req('POST', '/api/categories', body),
  patchCategory: (id, body) => req('PATCH', `/api/categories/${encodeURIComponent(id)}`, body),
  patchTransaction: (id, body) => req('PATCH', `/api/transactions/${encodeURIComponent(id)}`, body),
  rules: () => req('GET', '/api/rules'),
  addRule: (body) => req('POST', '/api/rules', body),
  updateRule: (id, body) => req('PUT', `/api/rules/${id}`, body),
  deleteRule: (id) => req('DELETE', `/api/rules/${id}`),
  previewRule: (body) => req('POST', '/api/rules/preview', body),
  applyRules: () => req('POST', '/api/rules/apply'),
  placesCoverage: () => req('GET', '/api/places/coverage'),
}

const usd = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' })
const usd0 = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 })
export const money = (n, cents = true) => (n === null || n === undefined || isNaN(n) ? '' : (cents ? usd : usd0).format(n))
export const shortDate = (s) => {
  if (!s) return ''
  const d = new Date(s + 'T12:00:00')
  return isNaN(d) ? s : d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}
export const titleCase = (s) => (s || '').toLowerCase().replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()).replace(/\bApr\b/g, 'APR')
export const toast = (msg) => window.dispatchEvent(new CustomEvent('toast', { detail: msg }))

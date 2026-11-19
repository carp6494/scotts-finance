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
  sessionSetting: () => req('GET', '/api/settings/session'),
  setSessionSetting: (hours) => req('PUT', '/api/settings/session', { hours }),
  mapSettings: () => req('GET', '/api/settings/map'),
  setMapSettings: (body) => req('PUT', '/api/settings/map', body),
  clearSavedMap: () => req('DELETE', '/api/settings/map/saved'),
  siteIcons: () => req('GET', '/api/settings/site-icons'),
  setSiteIcons: (enabled) => req('PUT', '/api/settings/site-icons', { enabled }),
  map: (p = {}) => req('GET', '/api/map?' + new URLSearchParams(Object.entries(p).filter(([, v]) => v !== undefined && v !== ''))),
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
  orderRules: (ids) => req('POST', '/api/rules/order', { ids }),
  deleteRule: (id) => req('DELETE', `/api/rules/${id}`),
  previewRule: (body) => req('POST', '/api/rules/preview', body),
  ruleDraft: (id) => req('GET', `/api/transactions/${encodeURIComponent(id)}/rule-draft`),
  applyRules: () => req('POST', '/api/rules/apply'),
  placesCoverage: () => req('GET', '/api/places/coverage'),
  tags: () => req('GET', '/api/tags'),
  patchTag: (id, body) => req('PATCH', `/api/tags/${id}`, body),
  deleteTag: (id) => req('DELETE', `/api/tags/${id}`),
  tagTransaction: (id, name) => req('POST', `/api/transactions/${encodeURIComponent(id)}/tags`, { name }),
  untagTransaction: (id, tagId) => req('DELETE', `/api/transactions/${encodeURIComponent(id)}/tags/${tagId}`),
  reviewAll: () => req('POST', '/api/review/all'),
  saveSplits: (id, lines) => req('PUT', `/api/transactions/${encodeURIComponent(id)}/splits`, { lines }),
  unsplit: (id, force) => req('DELETE', `/api/transactions/${encodeURIComponent(id)}/splits${force ? '?force=1' : ''}`),
  owed: () => req('GET', '/api/owed'),
  owedPayments: (splitId) => req('GET', `/api/owed/${splitId}/payments`),
  linkPayback: (splitId, body) => req('POST', `/api/owed/${splitId}/payback`, body),
  unlinkPayback: (id) => req('DELETE', `/api/paybacks/${id}`),
  dismissPayback: (splitId, paymentId) => req('POST', `/api/owed/${splitId}/dismiss`, { payment_id: paymentId }),
  linkTransfer: (a, b) => req('POST', '/api/transfers', { a, b }),
  unlinkTransfer: (id) => req('DELETE', `/api/transfers/${encodeURIComponent(id)}`),
  dismissTransfer: (id) => req('POST', `/api/transfers/${encodeURIComponent(id)}/dismiss`),
}

const usd = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' })
const usd0 = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 })
export const money = (n, cents = true) => (n === null || n === undefined || isNaN(n) ? '' : (cents ? usd : usd0).format(n))
export const shortDate = (s) => {
  if (!s) return ''
  const d = new Date(s + 'T12:00:00')
  return isNaN(d) ? s : d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}
// With the year, for lists that reach back more than one year.
export const fullDate = (s) => {
  if (!s) return ''
  const d = new Date(s + 'T12:00:00')
  return isNaN(d) ? s : d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}
export const titleCase = (s) => (s || '').toLowerCase().replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()).replace(/\bApr\b/g, 'APR')
// Fetch a file from the server and hand it to the browser to save. Errors come back as messages, not as a saved file.
export async function download(url) {
  const r = await fetch(url)
  if (r.status === 401) window.dispatchEvent(new Event('auth-required'))
  if (!r.ok) {
    const data = await r.json().catch(() => ({}))
    throw new Error(data.detail || `Download failed (${r.status})`)
  }
  const name = (r.headers.get('Content-Disposition') || '').match(/filename="([^"]+)"/)?.[1] || 'export'
  const href = URL.createObjectURL(await r.blob())
  const a = Object.assign(document.createElement('a'), { href, download: name })
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(href), 1000)
  return name
}

export const toast = (msg) => window.dispatchEvent(new CustomEvent('toast', { detail: msg }))
// One transaction row changed. detail is { id, fields }, { all: true, fields }, or { reload: true }.
// Every TxList on the page listens, so the new box and the full list stay in step.
export const txChanged = (detail) => window.dispatchEvent(new CustomEvent('tx-changed', { detail }))

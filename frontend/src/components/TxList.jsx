import { useEffect, useRef, useState } from 'react'
import { api, money, shortDate, toast } from '../api'
import { useCategories, categoryLabel } from '../categories'
import CategoryPicker from './CategoryPicker'
import Logo from './Logo'

const PAGE = 100

export default function TxList({ accountId, catId, spendingOnly = false, showAccount = true, compact = false, refreshKey = 0, onChanged }) {
  const [q, setQ] = useState('')
  const [rows, setRows] = useState([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [prompt, setPrompt] = useState(null) // { id, merchant, catId, similar }
  const [busy, setBusy] = useState(false)
  const timer = useRef(null)
  const groups = useCategories()

  const load = async (offset = 0, query = q) => {
    setLoading(true)
    try {
      const r = await api.transactions({ account_id: accountId, cat_id: catId, spending_only: spendingOnly ? 1 : undefined, q: query, limit: PAGE, offset })
      setTotal(r.total)
      setRows((prev) => (offset ? [...prev, ...r.rows] : r.rows))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load(0, q) }, [accountId, catId, spendingOnly, refreshKey]) // eslint-disable-line

  const onSearch = (v) => {
    setQ(v)
    clearTimeout(timer.current)
    timer.current = setTimeout(() => load(0, v), 250)
  }

  const setCategory = async (t, newCatId) => {
    try {
      const r = await api.patchTransaction(t.transaction_id, { cat_id: newCatId })
      setRows((prev) => prev.map((x) => (x.transaction_id === t.transaction_id ? { ...x, ...r } : x)))
      const merchant = t.display_name || t.merchant_name || t.name
      setPrompt(r.similar > 0 ? { id: t.transaction_id, merchant, catId: newCatId, similar: r.similar } : null)
      onChanged && onChanged()
    } catch (e) { toast(e.message) }
  }

  const makeRule = async () => {
    if (!prompt) return
    setBusy(true)
    try {
      const r = await api.addRule({
        name: `${prompt.merchant} → ${categoryLabel(groups, prompt.catId)}`,
        conditions: { merchant: prompt.merchant },
        actions: { cat_id: prompt.catId },
        created_from: prompt.id,
        apply_past: true,
      })
      toast(`Rule saved. ${r.changed} past transaction${r.changed === 1 ? '' : 's'} updated.`)
      setPrompt(null)
      load(0, q)
      onChanged && onChanged()
    } catch (e) { toast(e.message) } finally { setBusy(false) }
  }

  return (
    <div>
      <label style={{ display: 'flex', alignItems: 'center', gap: 8, background: 'var(--bg)', border: '1px solid var(--line)', borderRadius: 8, padding: '0 12px', height: 40, marginBottom: 10 }}>
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true" style={{ color: 'var(--muted)' }}><circle cx="11" cy="11" r="7" /><path d="M20 20l-3.5-3.5" /></svg>
        <span className="sr-only">Search transactions</span>
        <input value={q} onChange={(e) => onSearch(e.target.value)} placeholder="Search merchant, category"
          style={{ flex: 1, background: 'transparent', border: 0, outline: 'none', color: 'var(--text)', fontSize: 14 }} />
        <span style={{ fontSize: 12, color: 'var(--muted)' }}>{total.toLocaleString()} total</span>
      </label>
      <div style={{ border: '1px solid var(--line)', borderRadius: 12 }}>
        {rows.map((t, i) => {
          const quiet = t.excluded || t.is_transfer || t.cat_type === 'transfer'
          return (
            <div key={t.transaction_id}>
              <div className="rise" style={{
                display: 'flex', alignItems: 'center', gap: 12, padding: compact ? '9px 14px' : '11px 16px',
                borderTop: i ? '1px solid var(--line2)' : 0, animationDelay: `${Math.min(i, 20) * 0.025}s`, opacity: quiet ? 0.6 : 1,
              }}>
                <span style={{ width: 50, fontSize: 12, color: 'var(--muted)', flexShrink: 0 }}>{shortDate(t.date)}</span>
                <Logo src={t.logo} name={t.merchant_name || t.name} size={compact ? 28 : 32} />
                <span style={{ flex: 1, minWidth: 0 }}>
                  <span style={{ display: 'block', fontSize: 14, fontWeight: 500, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                    {t.display_name || t.merchant_name || t.name}
                    {t.pending ? <span style={{ marginLeft: 8, fontSize: 11, color: 'var(--warn)' }}>Pending</span> : null}
                    {t.excluded ? <span style={{ marginLeft: 8, fontSize: 11, color: 'var(--muted)' }}>Excluded</span> : null}
                    {t.is_transfer ? <span style={{ marginLeft: 8, fontSize: 11, color: 'var(--muted)' }}>Transfer</span> : null}
                  </span>
                  <span style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 2, fontSize: 12, color: 'var(--muted)', flexWrap: 'wrap' }}>
                    <CategoryPicker value={t.cat_id} compact={compact} onChange={(id) => setCategory(t, id)} />
                    {showAccount && t.account_name ? <span>{t.account_name}{t.mask ? ' ' + t.mask : ''}</span> : null}
                  </span>
                </span>
                <span className="num" style={{ fontSize: 14, fontWeight: 600, color: t.display_amount > 0 ? 'var(--pos)' : 'var(--text)' }}>
                  {t.display_amount > 0 ? '+' : ''}{money(t.display_amount)}
                </span>
              </div>
              {prompt && prompt.id === t.transaction_id && (
                <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 10, padding: '8px 16px 10px', fontSize: 13, color: 'var(--text2)', background: 'var(--hover)' }}>
                  <span style={{ flex: 1 }}>
                    Always file <b>{prompt.merchant}</b> as <b>{categoryLabel(groups, prompt.catId)}</b>? {prompt.similar} past transaction{prompt.similar === 1 ? '' : 's'} would change.
                  </span>
                  <button type="button" onClick={makeRule} disabled={busy} className="press"
                    style={{ height: 30, padding: '0 12px', borderRadius: 8, border: 0, background: 'var(--accent)', color: '#fff', fontWeight: 600, fontSize: 12 }}>
                    {busy ? 'Saving...' : 'Make rule'}
                  </button>
                  <button type="button" onClick={() => setPrompt(null)} style={{ height: 30, padding: '0 10px', borderRadius: 8, border: '1px solid var(--line)', background: 'transparent', color: 'var(--text2)', fontSize: 12 }}>Not now</button>
                </div>
              )}
            </div>
          )
        })}
        {!rows.length && !loading && <div style={{ padding: 16, fontSize: 14, color: 'var(--muted)' }}>No transactions yet.</div>}
      </div>
      {rows.length < total && (
        <button type="button" onClick={() => load(rows.length)} disabled={loading} className="press"
          style={{ marginTop: 10, width: '100%', height: 40, borderRadius: 8, border: '1px solid var(--line)', background: 'var(--card)', color: 'var(--text)', fontSize: 13 }}>
          {loading ? 'Loading...' : `Load more (${(total - rows.length).toLocaleString()} left)`}
        </button>
      )}
    </div>
  )
}

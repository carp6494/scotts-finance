import { useEffect, useRef, useState } from 'react'
import { api, money, shortDate, titleCase } from '../api'
import Logo from './Logo'

const PAGE = 100

export default function TxList({ accountId, showAccount = true, compact = false, refreshKey = 0 }) {
  const [q, setQ] = useState('')
  const [rows, setRows] = useState([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const timer = useRef(null)

  const load = async (offset = 0, query = q) => {
    setLoading(true)
    try {
      const r = await api.transactions({ account_id: accountId, q: query, limit: PAGE, offset })
      setTotal(r.total)
      setRows((prev) => (offset ? [...prev, ...r.rows] : r.rows))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load(0, q) }, [accountId, refreshKey]) // eslint-disable-line

  const onSearch = (v) => {
    setQ(v)
    clearTimeout(timer.current)
    timer.current = setTimeout(() => load(0, v), 250)
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
      <div style={{ border: '1px solid var(--line)', borderRadius: 12, overflow: 'hidden' }}>
        {rows.map((t, i) => (
          <div key={t.transaction_id} className="rise" style={{
            display: 'flex', alignItems: 'center', gap: 12, padding: compact ? '9px 14px' : '11px 16px',
            borderTop: i ? '1px solid var(--line2)' : 0, animationDelay: `${Math.min(i, 20) * 0.025}s`,
          }}>
            <span style={{ width: 50, fontSize: 12, color: 'var(--muted)', flexShrink: 0 }}>{shortDate(t.date)}</span>
            <Logo src={t.logo} name={t.merchant_name || t.name} size={compact ? 28 : 32} />
            <span style={{ flex: 1, minWidth: 0 }}>
              <span style={{ display: 'block', fontSize: 14, fontWeight: 500, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                {t.merchant_name || t.name}{t.pending ? <span style={{ marginLeft: 8, fontSize: 11, color: 'var(--warn)' }}>Pending</span> : null}
              </span>
              <span style={{ display: 'block', fontSize: 12, color: 'var(--muted)' }}>
                {titleCase(t.user_category || t.category) || 'Uncategorized'}
                {showAccount && t.account_name ? `, ${t.account_name}${t.mask ? ' ' + t.mask : ''}` : ''}
              </span>
            </span>
            <span className="num" style={{ fontSize: 14, fontWeight: 600, color: t.display_amount > 0 ? 'var(--pos)' : 'var(--text)' }}>
              {t.display_amount > 0 ? '+' : ''}{money(t.display_amount)}
            </span>
          </div>
        ))}
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

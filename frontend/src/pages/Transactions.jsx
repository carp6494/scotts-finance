import { useEffect, useState } from 'react'
import { api, money } from '../api'
import { useCategories, withIcon } from '../categories'
import Odometer from '../components/Odometer'
import TxList from '../components/TxList'

const sel = { height: 36, borderRadius: 8, border: '1px solid var(--line)', background: 'var(--card)', color: 'var(--text)', padding: '0 8px' }

export default function Transactions({ summary, accounts, refreshKey, onChanged }) {
  const [acct, setAcct] = useState('')
  const [cat, setCat] = useState('')
  const [spendingOnly, setSpendingOnly] = useState(false)
  const groups = useCategories()
  const s = summary || {}
  const linked = accounts.filter((a) => !a.manual)
  const [totals, setTotals] = useState(null)
  const filtered = Boolean(acct || cat)
  useEffect(() => {
    if (!filtered) { setTotals(null); return }
    let alive = true
    setTotals(null)
    api.summary({ account_id: acct || undefined, cat_id: cat || undefined }).then((r) => { if (alive) setTotals(r) }).catch(() => { if (alive) setTotals(null) })
    return () => { alive = false }
  }, [acct, cat, summary]) // eslint-disable-line
  const t = totals || s
  const [cov, setCov] = useState(null)
  useEffect(() => { api.placesCoverage().then(setCov).catch(() => {}) }, [refreshKey, summary]) // eslint-disable-line
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 14 }}>
        {[['Spent this month', t.spent_month], ['Income this month', t.income_month]].map(([l, v], i) => (
          <div key={l} className="card rise" style={{ padding: '14px 18px', animationDelay: `${i * 0.06}s` }}>
            <div style={{ fontSize: 12, color: 'var(--muted)' }}>{l}</div>
            <div style={{ marginTop: 4, fontSize: 22, fontWeight: 700, color: i ? 'var(--pos)' : 'var(--text)' }}><Odometer value={money(v || 0)} delay={i * 0.15} /></div>
            {filtered && <div style={{ marginTop: 4, fontSize: 11, color: 'var(--muted)' }}>This month, filtered</div>}
          </div>
        ))}
        <div className="card rise" style={{ padding: '14px 18px', animationDelay: '.12s' }}>
          <div style={{ fontSize: 12, color: 'var(--muted)' }}>Transactions stored</div>
          <div className="num" style={{ marginTop: 4, fontSize: 22, fontWeight: 700 }}>{(s.tx_count || 0).toLocaleString()}</div>
        </div>
      </div>
      <div className="card rise" style={{ padding: 18, animationDelay: '.18s' }}>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
          <h2 style={{ margin: 0, fontSize: 15, fontWeight: 600 }}>All transactions</h2>
          {cov && <span style={{ fontSize: 12, color: 'var(--muted)' }}>Places: {(cov.plaid + cov.user + (cov.overture || 0) + (cov.history || 0)).toLocaleString()} with a place, {cov.hq.toLocaleString()} headquarters, {cov.none.toLocaleString()} unknown</span>}
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, alignItems: 'center', fontSize: 13, color: 'var(--muted)' }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: 8 }}>Account
              <select value={acct} onChange={(e) => setAcct(e.target.value)} style={sel}>
                <option value="">All accounts</option>
                {linked.map((a) => <option key={a.account_id} value={a.account_id}>{a.official_name || a.name}{a.mask ? ` ${a.mask}` : ''}</option>)}
              </select>
            </label>
            <label style={{ display: 'flex', alignItems: 'center', gap: 8 }}>Category
              <select value={cat} onChange={(e) => setCat(e.target.value)} style={sel}>
                <option value="">All categories</option>
                {groups.map((g) => (
                  <optgroup key={g.group_name} label={g.group_name}>
                    {g.categories.filter((c) => !c.hidden).map((c) => <option key={c.id} value={c.id}>{withIcon(c)}{c.name}</option>)}
                  </optgroup>
                ))}
              </select>
            </label>
            <label style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <input type="checkbox" checked={spendingOnly} onChange={(e) => setSpendingOnly(e.target.checked)} /> Hide transfers and excluded
            </label>
          </div>
        </div>
        <TxList accountId={acct || undefined} catId={cat || undefined} spendingOnly={spendingOnly} refreshKey={refreshKey} onChanged={onChanged} />
      </div>
    </div>
  )
}

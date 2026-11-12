import { useState } from 'react'
import { money } from '../api'
import Odometer from '../components/Odometer'
import TxList from '../components/TxList'

export default function Transactions({ summary, accounts, refreshKey }) {
  const [acct, setAcct] = useState('')
  const s = summary || {}
  const linked = accounts.filter((a) => !a.manual)
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 14 }}>
        {[['Spent this month', s.spent_month], ['Income this month', s.income_month]].map(([l, v], i) => (
          <div key={l} className="card rise" style={{ padding: '14px 18px', animationDelay: `${i * 0.06}s` }}>
            <div style={{ fontSize: 12, color: 'var(--muted)' }}>{l}</div>
            <div style={{ marginTop: 4, fontSize: 22, fontWeight: 700, color: i ? 'var(--pos)' : 'var(--text)' }}><Odometer value={money(v || 0)} delay={i * 0.15} /></div>
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
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, color: 'var(--muted)' }}>Account
            <select value={acct} onChange={(e) => setAcct(e.target.value)} style={{ height: 36, borderRadius: 8, border: '1px solid var(--line)', background: 'var(--card)', color: 'var(--text)', padding: '0 8px' }}>
              <option value="">All accounts</option>
              {linked.map((a) => <option key={a.account_id} value={a.account_id}>{a.official_name || a.name}{a.mask ? ` ${a.mask}` : ''}</option>)}
            </select>
          </label>
        </div>
        <TxList accountId={acct || undefined} refreshKey={refreshKey} />
      </div>
    </div>
  )
}

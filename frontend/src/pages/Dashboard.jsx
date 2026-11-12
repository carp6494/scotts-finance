import { useState } from 'react'
import { api, money } from '../api'
import Odometer from '../components/Odometer'
import Logo from '../components/Logo'

const GROUPS = [
  ['Cash', (a) => a.type === 'depository'],
  ['Credit cards', (a) => a.type === 'credit'],
  ['Investments', (a) => a.type === 'investment'],
  ['Loans', (a) => a.type === 'loan'],
  ['Property', (a) => a.type === 'property'],
  ['Other', (a) => !['depository', 'credit', 'investment', 'loan', 'property'].includes(a.type)],
]

function Kpi({ label, value, sub, subColor, i }) {
  return (
    <div className="card lift rise" style={{ padding: '18px 20px', animationDelay: `${i * 0.08}s` }}>
      <div style={{ fontSize: 13, color: 'var(--muted)' }}>{label}</div>
      <div style={{ marginTop: 8, fontSize: 30, fontWeight: 700, letterSpacing: '-0.02em' }}>
        <Odometer value={money(value, false)} delay={i * 0.15} />
      </div>
      {sub && <div style={{ marginTop: 6, fontSize: 12, fontWeight: 600, color: subColor || 'var(--muted)' }}>{sub}</div>}
    </div>
  )
}

function AddHome({ accounts, onDone }) {
  const [open, setOpen] = useState(false)
  const [value, setValue] = useState('')
  const [loan, setLoan] = useState('')
  const loans = accounts.filter((a) => a.type === 'loan')
  if (!open) {
    return <button type="button" className="press" onClick={() => setOpen(true)} style={{ height: 36, padding: '0 14px', borderRadius: 8, border: '1px solid var(--line)', background: 'var(--card)', color: 'var(--text)', fontSize: 13 }}>Add home</button>
  }
  const save = async () => {
    await api.addManual({ name: 'Home', value: Number(value) || 0, linked_account_id: loan || null })
    setOpen(false); setValue(''); setLoan(''); onDone()
  }
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center' }}>
      <label style={{ display: 'flex', alignItems: 'center', gap: 6, border: '1px solid var(--line)', borderRadius: 8, padding: '0 10px', height: 36, background: 'var(--card)' }}>
        <span style={{ fontSize: 12, color: 'var(--muted)' }}>Home value $</span>
        <input type="number" value={value} onChange={(e) => setValue(e.target.value)} style={{ width: 110, background: 'transparent', border: 0, outline: 'none', color: 'var(--text)' }} />
      </label>
      <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: 'var(--muted)' }}>Mortgage
        <select value={loan} onChange={(e) => setLoan(e.target.value)} style={{ height: 36, borderRadius: 8, border: '1px solid var(--line)', background: 'var(--card)', color: 'var(--text)' }}>
          <option value="">Not connected yet</option>
          {loans.map((l) => <option key={l.account_id} value={l.account_id}>{l.name} {l.mask || ''}</option>)}
        </select>
      </label>
      <button type="button" className="press" onClick={save} style={{ height: 36, padding: '0 14px', borderRadius: 8, border: 0, background: 'var(--accent)', color: '#fff', fontWeight: 600, fontSize: 13 }}>Save</button>
    </div>
  )
}

const field = { display: 'flex', alignItems: 'center', gap: 6, border: '1px solid var(--line)', borderRadius: 8, padding: '0 10px', height: 36, background: 'var(--card)', fontSize: 12, color: 'var(--muted)' }
const input = { background: 'transparent', border: 0, outline: 'none', color: 'var(--text)', fontSize: 13 }

function AddAccount({ onDone }) {
  const [open, setOpen] = useState(false)
  const [f, setF] = useState({ name: '', institution: '', type: 'credit', mask: '', current: '', limit_amt: '' })
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })
  if (!open) {
    return <button type="button" className="press" onClick={() => setOpen(true)} style={{ height: 36, padding: '0 14px', borderRadius: 8, border: '1px solid var(--line)', background: 'var(--card)', color: 'var(--text)', fontSize: 13 }}>Add account manually</button>
  }
  const save = async () => {
    if (!f.name) return
    await api.addManualAccount({ ...f, current: Number(f.current) || 0, limit_amt: f.limit_amt ? Number(f.limit_amt) : null })
    setOpen(false); setF({ name: '', institution: '', type: 'credit', mask: '', current: '', limit_amt: '' }); onDone()
  }
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center', width: '100%' }}>
      <label style={field}>Name<input style={{ ...input, width: 180 }} value={f.name} onChange={set('name')} placeholder="MyLowe's Rewards Card" /></label>
      <label style={field}>Bank<input style={{ ...input, width: 120 }} value={f.institution} onChange={set('institution')} placeholder="Synchrony Bank" /></label>
      <label style={field}>Type
        <select value={f.type} onChange={set('type')} style={{ ...input, background: 'var(--card)' }}>
          <option value="credit">Credit card</option><option value="depository">Bank account</option><option value="loan">Loan</option><option value="investment">Investment</option>
        </select>
      </label>
      <label style={field}>Last 4<input style={{ ...input, width: 50 }} value={f.mask} onChange={set('mask')} /></label>
      <label style={field}>{f.type === 'credit' || f.type === 'loan' ? 'Owed $' : 'Balance $'}<input type="number" style={{ ...input, width: 90 }} value={f.current} onChange={set('current')} /></label>
      {f.type === 'credit' && <label style={field}>Limit $<input type="number" style={{ ...input, width: 90 }} value={f.limit_amt} onChange={set('limit_amt')} /></label>}
      <button type="button" className="press" onClick={save} style={{ height: 36, padding: '0 14px', borderRadius: 8, border: 0, background: 'var(--accent)', color: '#fff', fontWeight: 600, fontSize: 13 }}>Save</button>
      <button type="button" onClick={() => setOpen(false)} style={{ height: 36, padding: '0 10px', borderRadius: 8, border: 0, background: 'transparent', color: 'var(--muted)', fontSize: 13 }}>Cancel</button>
    </div>
  )
}

export default function Dashboard({ summary, accounts, onOpen, onChanged }) {
  const s = summary || {}
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <section aria-label="Key numbers" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 16 }}>
        <Kpi i={0} label="Net worth" value={s.net_worth || 0} sub="Cash + investments + property - debt" />
        <Kpi i={1} label="Cash on hand" value={s.cash || 0} />
        <Kpi i={2} label="Credit card and loan debt" value={s.debt || 0} subColor="var(--orange)" />
        <Kpi i={3} label="Spent this month" value={s.spent_month || 0} sub={`Income this month ${money(s.income_month || 0, false)}`} subColor="var(--pos)" />
      </section>

      <section className="card rise" style={{ padding: 20, animationDelay: '.3s' }}>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, justifyContent: 'space-between', alignItems: 'center' }}>
          <h2 style={{ margin: 0, fontSize: 15, fontWeight: 600 }}>Accounts</h2>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center' }}>
            <AddAccount onDone={onChanged} />
            <AddHome accounts={accounts} onDone={onChanged} />
          </div>
        </div>
        {!accounts.length && <p style={{ color: 'var(--muted)', fontSize: 14 }}>No accounts yet. Use Connect account at the top to link your first bank.</p>}
        {GROUPS.map(([title, test]) => {
          const list = accounts.filter(test)
          if (!list.length) return null
          const total = list.reduce((t, a) => t + (a.signed_balance || 0), 0)
          return (
            <div key={title} style={{ marginTop: 18 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '.06em', color: 'var(--muted)', marginBottom: 8 }}>
                <span>{title}</span><span className="num">{money(total, false)}</span>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: 12 }}>
                {list.map((a, i) => (
                  <button key={a.account_id} type="button" onClick={() => onOpen(a.account_id)} className="lift rise"
                    style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '12px 14px', border: '1px solid var(--line)', borderRadius: 12, background: 'var(--bg)', color: 'var(--text)', textAlign: 'left', width: '100%', animationDelay: `${0.35 + i * 0.05}s` }}>
                    <Logo src={a.logo} name={a.institution || a.name} home={a.type === 'property'} />
                    <span style={{ flex: 1, minWidth: 0 }}>
                      <span style={{ display: 'block', fontSize: 14, fontWeight: 500, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{a.official_name || a.name}</span>
                      <span style={{ display: 'block', fontSize: 12, color: a.item_status === 'needs_reconnect' ? 'var(--warn)' : 'var(--muted)' }}>
                        {a.item_status === 'needs_reconnect' ? 'Needs reconnect' : `${a.institution || ''}${a.mask ? ', ending ' + a.mask : ''}`}
                      </span>
                    </span>
                    <span style={{ textAlign: 'right' }}>
                      <span className="num" style={{ display: 'block', fontSize: 15, fontWeight: 600, color: a.signed_balance < 0 ? 'var(--orange)' : 'var(--text)' }}>{money(a.signed_balance, false)}</span>
                      {a.type === 'credit' && a.limit_amt ? <span style={{ display: 'block', fontSize: 11, color: 'var(--muted)' }}>{money(a.limit_amt - (a.current || 0), false)} available</span> : null}
                    </span>
                  </button>
                ))}
              </div>
            </div>
          )
        })}
      </section>
    </div>
  )
}

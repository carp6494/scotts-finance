import { useEffect, useMemo, useState } from 'react'
import { api, money } from '../api'
import Logo from '../components/Logo'
import Odometer from '../components/Odometer'

// Month-by-month payoff simulation. Total monthly payment stays constant, so as each debt is
// paid off its minimum rolls into the next target (that is what makes snowball/avalanche work).
function simulate(debts, extra, method) {
  const ds = debts.map((d) => ({ ...d, bal: d.balance, paidMonth: null }))
  const order = [...ds].sort(method === 'snowball' ? (a, b) => a.bal - b.bal : (a, b) => b.apr - a.apr || a.bal - b.bal)
  const budget = ds.reduce((t, d) => t + d.min, 0) + extra
  let month = 0, interest = 0
  const series = [ds.reduce((t, d) => t + d.bal, 0)]
  while (ds.some((d) => d.bal > 0.005) && month < 600) {
    month++
    for (const d of ds) if (d.bal > 0) { const i = (d.bal * d.apr) / 1200; d.bal += i; interest += i }
    let left = budget
    for (const d of ds) if (d.bal > 0) { const p = Math.min(d.min, d.bal); d.bal -= p; left -= p }
    for (const d of order) { if (left <= 0) break; if (d.bal > 0) { const p = Math.min(left, d.bal); d.bal -= p; left -= p } }
    for (const d of ds) if (d.bal <= 0.005 && d.paidMonth === null) { d.bal = 0; d.paidMonth = month }
    series.push(ds.reduce((t, d) => t + Math.max(d.bal, 0), 0))
  }
  const done = !ds.some((d) => d.bal > 0.005)
  return { months: done ? month : null, interest, series, order: order.map((d) => ({ name: d.name, month: d.paidMonth })) }
}

const monthLabel = (n) => {
  if (n === null) return 'Never at this payment'
  const d = new Date(); d.setMonth(d.getMonth() + n)
  return d.toLocaleDateString('en-US', { month: 'short', year: 'numeric' })
}

function Chart({ a, b }) {
  const W = 640, H = 220, P = 8
  const n = Math.max(a.series.length, b.series.length)
  const max = Math.max(...a.series, ...b.series, 1)
  const pts = (s) => s.map((v, i) => `${(P + (i / Math.max(n - 1, 1)) * (W - 2 * P)).toFixed(1)},${(H - P - (v / max) * (H - 2 * P)).toFixed(1)}`).join(' ')
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" height={H} preserveAspectRatio="none" role="img" aria-label="Total debt over time, snowball versus avalanche">
      <line x1={P} y1={H - P} x2={W - P} y2={H - P} stroke="var(--line)" vectorEffect="non-scaling-stroke" />
      <polyline key={'s' + a.series.length} points={pts(a.series)} fill="none" stroke="#3b82f6" strokeWidth="3" pathLength="1"
        style={{ strokeDasharray: 1, animation: 'drawLine 1.6s cubic-bezier(.4,0,.2,1) both' }} />
      <polyline key={'a' + b.series.length} points={pts(b.series)} fill="none" stroke="#f97316" strokeWidth="3" pathLength="1"
        style={{ strokeDasharray: 1, animation: 'drawLine 1.6s cubic-bezier(.4,0,.2,1) .2s both' }} />
    </svg>
  )
}

function DebtRow({ d, onSaved }) {
  const [f, setF] = useState({ apr: d.apr_override ?? '', min: d.min_payment_override ?? '', limit: d.limit_override ?? '' })
  const save = async () => {
    await api.setTerms(d.account_id, {
      apr: f.apr === '' ? null : Number(f.apr), min_payment: f.min === '' ? null : Number(f.min), limit_amt: f.limit === '' ? null : Number(f.limit),
    })
    onSaved()
  }
  const box = { display: 'flex', alignItems: 'center', gap: 4, border: '1px solid var(--line)', borderRadius: 8, padding: '0 8px', height: 36, background: 'var(--bg)', fontSize: 12, color: 'var(--muted)' }
  const inp = { width: 64, background: 'transparent', border: 0, outline: 'none', color: 'var(--text)', fontSize: 14 }
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 12, padding: '12px 0', borderTop: '1px solid var(--line2)' }}>
      <Logo src={d.logo} name={d.institution || d.name} />
      <div style={{ flex: '1 1 180px', minWidth: 0 }}>
        <div style={{ fontWeight: 500 }}>{d.official_name || d.name}</div>
        <div style={{ fontSize: 12, color: 'var(--muted)' }}>{d.institution}{d.mask ? `, ending ${d.mask}` : ''}</div>
      </div>
      <div className="num" style={{ width: 110, textAlign: 'right', fontWeight: 600, color: 'var(--orange)' }}>{money(-(d.current || 0))}</div>
      <label style={box}>APR
        <input type="number" step="0.01" value={f.apr} placeholder={d.apr_source === 'bank' ? String(d.apr) : 'needed'} onChange={(e) => setF({ ...f, apr: e.target.value })} onBlur={save} style={inp} />%</label>
      <label style={box}>Min $
        <input type="number" step="1" value={f.min} placeholder={d.min_payment != null && d.min_payment_override == null ? String(d.min_payment) : 'auto'} onChange={(e) => setF({ ...f, min: e.target.value })} onBlur={save} style={inp} /></label>
      {d.type === 'credit' && <label style={box}>Limit $
        <input type="number" step="1" value={f.limit} placeholder={d.limit_amt != null && d.limit_override == null ? String(d.limit_amt) : 'optional'} onChange={(e) => setF({ ...f, limit: e.target.value })} onBlur={save} style={{ ...inp, width: 72 }} /></label>}
    </div>
  )
}

export default function Debt() {
  const [rows, setRows] = useState([])
  const [extra, setExtra] = useState(() => { try { return Number(localStorage.getItem('debt-extra')) || 200 } catch { return 200 } })
  const [showMortgage, setShowMortgage] = useState(false)
  const load = () => api.debts().then(setRows)
  useEffect(() => { load() }, [])
  useEffect(() => { try { localStorage.setItem('debt-extra', String(extra)) } catch { /* ignore */ } }, [extra])

  const owed = rows.filter((d) => (d.current || 0) > 0.005 && (showMortgage || d.subtype !== 'mortgage'))
  const missingApr = owed.filter((d) => d.apr == null)
  const usable = owed.filter((d) => d.apr != null).map((d) => ({
    name: d.official_name || d.name, balance: d.current, apr: Number(d.apr),
    min: d.min_payment != null && d.min_payment > 0 ? Number(d.min_payment) : Math.max(25, d.current * 0.02 + (d.current * d.apr) / 1200),
  }))
  const snow = useMemo(() => simulate(usable, extra, 'snowball'), [JSON.stringify(usable), extra]) // eslint-disable-line
  const aval = useMemo(() => simulate(usable, extra, 'avalanche'), [JSON.stringify(usable), extra]) // eslint-disable-line
  const total = usable.reduce((t, d) => t + d.balance, 0)
  const minTotal = usable.reduce((t, d) => t + d.min, 0)
  const saved = snow.interest - aval.interest

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
      <style>{'@keyframes drawLine{from{stroke-dashoffset:1}to{stroke-dashoffset:0}}'}</style>
      <section className="card rise" style={{ padding: 20 }}>
        <div style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'space-between', alignItems: 'baseline', gap: 8 }}>
          <h2 style={{ margin: 0, fontSize: 15, fontWeight: 600 }}>Your debts</h2>
          <label style={{ fontSize: 12, color: 'var(--muted)', display: 'flex', gap: 6, alignItems: 'center' }}>
            <input type="checkbox" checked={showMortgage} onChange={(e) => setShowMortgage(e.target.checked)} /> Include mortgage
          </label>
        </div>
        <p style={{ margin: '6px 0 0', fontSize: 13, color: 'var(--muted)' }}>Your banks don't send interest rates for these cards. Enter each card's purchase APR from its statement or website. Leave Min blank to use the bank's minimum payment.</p>
        {rows.filter((d) => showMortgage || d.subtype !== 'mortgage').map((d) => <DebtRow key={d.account_id} d={d} onSaved={load} />)}
        {!rows.length && <p style={{ color: 'var(--muted)' }}>No credit cards or loans connected yet.</p>}
      </section>

      <section className="card rise" style={{ padding: 20, animationDelay: '.1s' }}>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 16, alignItems: 'center', justifyContent: 'space-between' }}>
          <div>
            <div style={{ fontSize: 13, color: 'var(--muted)' }}>Total debt with an APR entered</div>
            <div style={{ fontSize: 28, fontWeight: 700 }}><Odometer value={money(total, false)} /></div>
            <div style={{ fontSize: 12, color: 'var(--muted)' }}>Minimums {money(minTotal, false)} per month</div>
          </div>
          <label style={{ flex: '1 1 260px', fontSize: 13, color: 'var(--text2)' }}>
            Extra each month on top of minimums: <strong className="num">{money(extra, false)}</strong>
            <input type="range" min="0" max="2000" step="25" value={extra} onChange={(e) => setExtra(Number(e.target.value))} style={{ width: '100%', accentColor: '#3b82f6' }} />
          </label>
        </div>
        {missingApr.length > 0 && (
          <div style={{ marginTop: 12, fontSize: 13, color: 'var(--warn)' }}>Enter an APR for {missingApr.map((d) => d.official_name || d.name).join(', ')} to include it.</div>
        )}
      </section>

      {usable.length > 0 && (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 16 }}>
            {[['Snowball', 'Smallest balance first. Quick wins keep you going.', snow, '#3b82f6'], ['Avalanche', 'Highest APR first. Pays the least interest.', aval, '#f97316']].map(([t, sub, r, c], i) => (
              <section key={t} className="card rise" style={{ padding: 20, borderTop: `3px solid ${c}`, animationDelay: `${0.15 + i * 0.08}s` }}>
                <h3 style={{ margin: 0, fontSize: 16 }}>{t}</h3>
                <div style={{ fontSize: 12, color: 'var(--muted)' }}>{sub}</div>
                <div style={{ marginTop: 12, fontSize: 13, color: 'var(--muted)' }}>Debt-free</div>
                <div style={{ fontSize: 24, fontWeight: 700 }}>{monthLabel(r.months)}</div>
                <div style={{ fontSize: 13, color: 'var(--muted)', marginTop: 8 }}>Total interest</div>
                <div style={{ fontSize: 22, fontWeight: 700, color: 'var(--orange)' }}><Odometer value={money(r.interest, false)} delay={i * 0.15} /></div>
                <ol style={{ margin: '12px 0 0', paddingLeft: 18, fontSize: 13, color: 'var(--text2)' }}>
                  {r.order.map((o) => <li key={o.name}>{o.name}: paid off {o.month ? monthLabel(o.month) : 'not within 50 years'}</li>)}
                </ol>
              </section>
            ))}
          </div>
          <section className="card rise" style={{ padding: 20, animationDelay: '.3s' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
              <h2 style={{ margin: 0, fontSize: 15, fontWeight: 600 }}>Total debt over time</h2>
              <div style={{ fontSize: 12, color: 'var(--muted)', display: 'flex', gap: 14 }}>
                <span><span style={{ display: 'inline-block', width: 10, height: 3, background: '#3b82f6', marginRight: 6, verticalAlign: 'middle' }} />Snowball</span>
                <span><span style={{ display: 'inline-block', width: 10, height: 3, background: '#f97316', marginRight: 6, verticalAlign: 'middle' }} />Avalanche</span>
              </div>
            </div>
            <Chart a={snow} b={aval} />
            <p style={{ margin: '8px 0 0', fontSize: 14 }}>
              {Math.abs(saved) < 1 ? 'Both methods cost about the same here.' : `Avalanche saves ${money(saved, false)} in interest compared to snowball.`}
            </p>
          </section>
        </>
      )}
    </div>
  )
}

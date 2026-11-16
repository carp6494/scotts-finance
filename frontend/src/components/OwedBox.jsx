import { useEffect, useState } from 'react'
import { api, money, fullDate, toast, txChanged } from '../api'

const btn = { height: 28, padding: '0 10px', borderRadius: 8, border: 0, background: 'var(--accent)', color: '#fff', fontWeight: 600, fontSize: 12 }
const ghost = { ...btn, background: 'transparent', border: '1px solid var(--line)', color: 'var(--text2)', fontWeight: 500 }

function Item({ it, paid, busy, act, picking, payments, openPayments }) {
  return (
    <div style={{ padding: '6px 0', borderTop: '1px solid var(--line2)', fontSize: 13 }}>
      <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 8 }}>
        <span style={{ width: 86, color: 'var(--muted)', fontSize: 12 }}>{fullDate(it.date)}</span>
        <span style={{ flex: 1, minWidth: 120 }}>{it.merchant}{paid ? ` · ${it.owed_by}` : ''}</span>
        <span className="num">
          {money(paid ? it.amount : it.open)}
          {!paid && it.paid > 0 ? <span style={{ color: 'var(--muted)', fontSize: 12 }}> of {money(it.amount)}</span> : null}
        </span>
        {!paid && (
          <>
            <button type="button" disabled={busy} onClick={() => openPayments(it.split_id)} style={ghost}>Link payment</button>
            <button type="button" disabled={busy} onClick={() => act(() => api.linkPayback(it.split_id, { cash: true }))} style={ghost}>Paid in cash</button>
          </>
        )}
      </div>
      {it.paybacks.length > 0 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, margin: '4px 0 0 94px' }}>
          {it.paybacks.map((b) => (
            <span key={b.id} style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: 11, padding: '1px 4px 1px 8px', borderRadius: 999, border: '1px solid var(--line)', color: 'var(--text2)' }}>
              {b.cash ? 'Cash' : `${b.name} ${fullDate(b.date)}`} {money(b.amount)}
              <button type="button" disabled={busy} onClick={() => act(() => api.unlinkPayback(b.id))} aria-label="Unlink payback" title="Unlink"
                style={{ border: 0, background: 'transparent', color: 'var(--muted)', fontSize: 13, lineHeight: 1, padding: '0 2px' }}>×</button>
            </span>
          ))}
        </div>
      )}
      {picking === it.split_id && (
        <div style={{ margin: '6px 0 0 94px', border: '1px solid var(--line)', borderRadius: 8, maxHeight: 220, overflowY: 'auto' }}>
          {payments === null && <div style={{ padding: 10, color: 'var(--muted)' }}>Loading...</div>}
          {payments && !payments.length && <div style={{ padding: 10, color: 'var(--muted)' }}>No deposits on or after this charge.</div>}
          {payments && payments.map((d, i) => (
            <button key={d.transaction_id} type="button" disabled={busy} onClick={() => act(() => api.linkPayback(it.split_id, { payment_id: d.transaction_id }))}
              style={{ display: 'flex', width: '100%', gap: 8, padding: '6px 10px', border: 0, borderTop: i ? '1px solid var(--line2)' : 0, background: 'transparent', color: 'var(--text)', fontSize: 13, textAlign: 'left' }}>
              <span style={{ width: 86, color: 'var(--muted)', fontSize: 12 }}>{fullDate(d.date)}</span>
              <span style={{ flex: 1 }}>{d.name}</span>
              <span className="num">{money(d.left)}{d.left < d.amount ? <span style={{ color: 'var(--muted)', fontSize: 12 }}> left of {money(d.amount)}</span> : null}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

// Money owed back to the owner. Always on Transactions, even when nothing is owed.
export default function OwedBox({ refreshKey, onChanged }) {
  const [data, setData] = useState(null)
  const [picking, setPicking] = useState(null)
  const [payments, setPayments] = useState(null)
  const [busy, setBusy] = useState(false)
  const load = () => api.owed().then(setData).catch((e) => toast(e.message))
  useEffect(() => { load() }, [refreshKey]) // eslint-disable-line
  useEffect(() => {
    const on = () => load()
    window.addEventListener('tx-changed', on)
    return () => window.removeEventListener('tx-changed', on)
  }, []) // eslint-disable-line

  const act = async (fn) => {
    setBusy(true)
    try {
      await fn()
      setPicking(null)
      txChanged({ reload: true })
      onChanged && onChanged()
    } catch (e) { toast(e.message) } finally { setBusy(false) }
  }
  const openPayments = async (id) => {
    if (picking === id) { setPicking(null); return }
    setPicking(id); setPayments(null)
    try { setPayments((await api.owedPayments(id)).payments) } catch (e) { toast(e.message); setPayments([]) }
  }
  if (!data || !Array.isArray(data.people)) return null // a server without these routes yet answers with the page instead
  const shared = { busy, act, picking, payments, openPayments }

  return (
    <div className="card rise" style={{ padding: 18 }}>
      <h2 style={{ margin: 0, fontSize: 15, fontWeight: 600 }}>{data.total > 0 ? `${money(data.total)} owed to you` : 'Nothing owed to you'}</h2>
      {data.total <= 0 && <p style={{ margin: '6px 0 0', fontSize: 13, color: 'var(--muted)' }}>Split a charge and mark a line Owed by someone to track it here.</p>}
      {data.suggestions.map((s) => (
        <div key={`${s.split_id}-${s.payment_id}`} style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 8, marginTop: 10, padding: '8px 12px', borderRadius: 8, background: 'var(--hover)', fontSize: 13 }}>
          <span style={{ flex: 1 }}>{s.payment_name} {money(s.amount)} on {fullDate(s.payment_date)} matches {s.owed_by}'s {money(s.amount)}.</span>
          <button type="button" disabled={busy} onClick={() => act(() => api.linkPayback(s.split_id, { payment_id: s.payment_id }))} style={btn}>Link</button>
          <button type="button" disabled={busy} onClick={() => act(() => api.dismissPayback(s.split_id, s.payment_id))} style={ghost}>Not this</button>
        </div>
      ))}
      {data.people.map((p) => (
        <div key={p.name} style={{ marginTop: 12 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 14, fontWeight: 600, marginBottom: 2 }}>
            <span>{p.name}</span><span className="num">{money(p.total)}</span>
          </div>
          {p.items.map((it) => <Item key={it.split_id} it={it} {...shared} />)}
        </div>
      ))}
      {data.recent.length > 0 && (
        <div style={{ marginTop: 12 }}>
          <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--muted)', marginBottom: 2 }}>Paid back lately</div>
          {data.recent.map((it) => <Item key={it.split_id} it={it} paid {...shared} />)}
        </div>
      )}
    </div>
  )
}

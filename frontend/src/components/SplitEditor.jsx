import { useEffect, useRef, useState } from 'react'
import { api, money, txChanged } from '../api'
import { CatLabel } from './CatIcon'
import CategoryPicker from './CategoryPicker'

const inp = { height: 32, borderRadius: 8, border: '1px solid var(--line)', background: 'var(--bg)', color: 'var(--text)', padding: '0 8px', fontSize: 13 }
const btn = { height: 32, padding: '0 14px', borderRadius: 8, border: 0, background: 'var(--accent)', color: '#fff', fontWeight: 600, fontSize: 13 }
const ghost = { ...btn, background: 'transparent', border: '1px solid var(--line)', color: 'var(--text2)', fontWeight: 500 }
const cents = (v) => Math.round(Math.abs(Number(v) || 0) * 100)

// The lines of a split transaction, shown small under its row.
export function SplitLines({ t, groups }) {
  return (
    <div style={{ padding: '0 16px 10px 146px', display: 'flex', flexDirection: 'column', gap: 3, fontSize: 12, color: 'var(--muted)' }}>
      {t.split_off ? <div style={{ color: 'var(--warn)', fontWeight: 600 }}>Split is off by {money(t.split_off)}. Click the Split badge to fix it.</div> : null}
      {t.splits.map((l) => (
        <div key={l.id} style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <span style={{ flex: 1, minWidth: 0 }}>
            {l.owed_by
              ? <span style={{ color: 'var(--info)' }}>Owed by {l.owed_by}{l.paid >= l.amount - 0.005 ? ' · paid back' : ''}</span>
              : <CatLabel groups={groups} id={l.cat_id} />}
          </span>
          <span className="num">{money(l.display_amount)}</span>
        </div>
      ))}
    </div>
  )
}

// Divide one bank charge into lines. A line is a category and an amount, or a person who owes that part.
export default function SplitEditor({ t, onClose, onChanged }) {
  const sign = (t.amount || 0) < 0 ? -1 : 1 // bank sign: positive is money out
  const total = cents(t.amount)
  const [lines, setLines] = useState(() => (t.splits?.length
    ? t.splits.map((l) => ({ kind: l.owed_by ? 'owed' : 'cat', cat_id: l.cat_id || '', owed_by: l.owed_by || '', amount: Math.abs(l.amount).toFixed(2) }))
    : [{ kind: 'cat', cat_id: t.cat_id || '', owed_by: '', amount: (total / 100).toFixed(2) }, { kind: 'cat', cat_id: '', owed_by: '', amount: '' }]))
  const [names, setNames] = useState([])
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [warnUnsplit, setWarnUnsplit] = useState('')
  const root = useRef(null)
  useEffect(() => { api.owed().then((o) => setNames(o.names || [])).catch(() => {}) }, [])
  // The editor can open at the bottom of a scrolling box. Bring all of it into view.
  useEffect(() => { root.current?.scrollIntoView({ block: 'nearest' }) }, [])

  const canOwe = sign > 0
  const left = total - lines.reduce((s, l) => s + cents(l.amount), 0)
  const valid = lines.length >= 2 && left === 0 && lines.every((l) => cents(l.amount) > 0 && (l.kind === 'cat' ? l.cat_id : l.owed_by.trim()))
  const set = (i, patch) => setLines((ls) => ls.map((l, j) => (j === i ? { ...l, ...patch } : l)))
  const evenly = () => {
    const n = lines.length
    const base = Math.floor(total / n)
    const extra = total - base * n
    setLines((ls) => ls.map((l, i) => ({ ...l, amount: ((base + (i === 0 ? extra : 0)) / 100).toFixed(2) })))
  }
  const save = async () => {
    setBusy(true); setErr('')
    try {
      const r = await api.saveSplits(t.transaction_id, lines.map((l) => ({
        amount: (sign * cents(l.amount)) / 100,
        cat_id: l.kind === 'cat' ? l.cat_id : null,
        owed_by: l.kind === 'owed' ? l.owed_by.trim() : null,
      })))
      txChanged({ id: t.transaction_id, fields: { splits: r.splits, split_off: r.split_off } })
      onChanged && onChanged()
      onClose()
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }
  const unsplit = async (force) => {
    setBusy(true); setErr('')
    try {
      await api.unsplit(t.transaction_id, force)
      txChanged({ reload: true })
      onChanged && onChanged()
      onClose()
    } catch (e) { if (force) setErr(e.message); else setWarnUnsplit(e.message) } finally { setBusy(false) }
  }
  const listId = `owed-names-${t.transaction_id}`

  return (
    <div ref={root} onClick={(e) => e.stopPropagation()} style={{ padding: '10px 16px 12px', background: 'var(--hover)', borderTop: '1px solid var(--line2)', display: 'flex', flexDirection: 'column', gap: 8, fontSize: 13 }}>
      <div style={{ fontWeight: 600 }}>Split {money(Math.abs(t.amount))}</div>
      {lines.map((l, i) => (
        <div key={i} style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 8 }}>
          {canOwe && (
            <select value={l.kind} onChange={(e) => set(i, { kind: e.target.value })} aria-label="Line type" style={{ ...inp, width: 120 }}>
              <option value="cat">Category</option>
              <option value="owed">Owed by</option>
            </select>
          )}
          {l.kind === 'cat'
            ? <CategoryPicker value={l.cat_id || null} onChange={(id) => set(i, { cat_id: id })} />
            : <input value={l.owed_by} onChange={(e) => set(i, { owed_by: e.target.value })} list={listId} placeholder="Name" aria-label="Who owes this part" style={{ ...inp, width: 160 }} />}
          <span style={{ flex: 1 }} />
          <label style={{ display: 'flex', alignItems: 'center', gap: 4 }}>$
            <input inputMode="decimal" value={l.amount} onChange={(e) => set(i, { amount: e.target.value })} aria-label="Amount" style={{ ...inp, width: 96, textAlign: 'right' }} />
          </label>
          {lines.length > 2 && (
            <button type="button" onClick={() => setLines((ls) => ls.filter((_, j) => j !== i))} aria-label="Remove line"
              style={{ border: 0, background: 'transparent', color: 'var(--muted)', fontSize: 16, padding: '0 4px' }}>×</button>
          )}
        </div>
      ))}
      <datalist id={listId}>{names.map((n) => <option key={n} value={n} />)}</datalist>
      <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 8 }}>
        <button type="button" onClick={() => setLines((ls) => [...ls, { kind: 'cat', cat_id: '', owed_by: '', amount: left > 0 ? (left / 100).toFixed(2) : '' }])} style={ghost}>Add line</button>
        <button type="button" onClick={evenly} style={ghost}>Split evenly</button>
        <span style={{ flex: 1, color: valid ? 'var(--pos)' : 'var(--warn)' }}>
          {left > 0 ? `${money(left / 100)} left` : left < 0 ? `${money(-left / 100)} over` : valid ? 'Adds up' : 'Fill in each line'}
        </span>
        {t.splits?.length > 0 && (warnUnsplit
          ? <><span style={{ color: 'var(--warn)' }}>{warnUnsplit}</span><button type="button" disabled={busy} onClick={() => unsplit(true)} style={ghost}>Unsplit anyway</button></>
          : <button type="button" disabled={busy} onClick={() => unsplit(false)} style={ghost}>Unsplit</button>)}
        <button type="button" onClick={onClose} style={ghost}>Cancel</button>
        <button type="button" className="press" disabled={!valid || busy} onClick={save} style={{ ...btn, opacity: valid ? 1 : 0.5 }}>{busy ? 'Saving...' : 'Save'}</button>
      </div>
      {err && <div style={{ color: 'var(--neg)' }}>{err}</div>}
    </div>
  )
}

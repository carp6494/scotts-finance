import { useEffect, useRef, useState } from 'react'
import { api, toast, txChanged } from '../api'
import TxList from './TxList'

const btn = { height: 36, padding: '0 14px', borderRadius: 8, border: 0, background: 'var(--accent)', color: '#fff', fontWeight: 600, fontSize: 13 }
const ghost = { ...btn, background: 'transparent', border: '1px solid var(--line)', color: 'var(--text2)', fontWeight: 500 }
const key = { display: 'inline-block', minWidth: 18, textAlign: 'center', padding: '0 5px', border: '1px solid var(--line3)', borderRadius: 5, fontSize: 11, color: 'var(--text2)', background: 'var(--bg)' }

// New transactions wait here, at the top of Transactions, until the owner clicks "Reviewed". Gone when none wait.
export default function NewTransactions({ waiting, refreshKey, onChanged }) {
  const [confirm, setConfirm] = useState(false)
  const [busy, setBusy] = useState(false)
  const before = useRef(waiting)
  useEffect(() => {
    if (before.current > 0 && waiting === 0) toast('All caught up.')
    before.current = waiting
  }, [waiting])
  if (!waiting) return null

  const markAll = async () => {
    setBusy(true)
    try {
      await api.reviewAll()
      setConfirm(false)
      txChanged({ all: true, fields: { reviewed: 1 } })
      onChanged && onChanged()
    } catch (e) { toast(e.message) } finally { setBusy(false) }
  }

  return (
    <div className="card rise" style={{ padding: 18, borderColor: 'var(--accent)', background: 'color-mix(in srgb, var(--accent) 7%, var(--card))' }}>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
        <h2 style={{ margin: 0, fontSize: 15, fontWeight: 600 }}>{waiting.toLocaleString()} new transaction{waiting === 1 ? '' : 's'}</h2>
        {confirm ? (
          <span style={{ display: 'flex', gap: 8 }}>
            <button type="button" className="press" disabled={busy} onClick={markAll} style={btn}>{busy ? 'Marking...' : `Mark all ${waiting.toLocaleString()} reviewed`}</button>
            <button type="button" onClick={() => setConfirm(false)} style={ghost}>Keep</button>
          </span>
        ) : (
          <button type="button" onClick={() => setConfirm(true)} style={ghost}>Mark all reviewed</button>
        )}
      </div>
      <p style={{ margin: '0 0 14px', fontSize: 13, color: 'var(--muted)' }}>
        Fix the category or add tags, then click "Reviewed". Click a row to use keys:
        {' '}<span style={key}>↑</span> <span style={key}>↓</span> move, <span style={key}>Enter</span> reviewed, <span style={key}>C</span> category, <span style={key}>T</span> tag, <span style={key}>Esc</span> stop.
      </p>
      <TxList review unreviewed search={false} maxHeight={640} refreshKey={refreshKey} onChanged={onChanged} empty="Nothing waiting." />
    </div>
  )
}

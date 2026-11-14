import { useState } from 'react'
import { api, toast } from '../api'
import TxList from '../components/TxList'

const btn = { height: 36, padding: '0 14px', borderRadius: 8, border: 0, background: 'var(--accent)', color: '#fff', fontWeight: 600, fontSize: 13 }
const ghost = { ...btn, background: 'transparent', border: '1px solid var(--line)', color: 'var(--text2)', fontWeight: 500 }
const key = { display: 'inline-block', minWidth: 18, textAlign: 'center', padding: '0 5px', border: '1px solid var(--line3)', borderRadius: 5, fontSize: 11, color: 'var(--text2)', background: 'var(--bg)' }

export default function Review({ summary, refreshKey, onChanged }) {
  const [confirm, setConfirm] = useState(false)
  const [busy, setBusy] = useState(false)
  const [bump, setBump] = useState(0)
  const waiting = summary?.unreviewed || 0

  const markAll = async () => {
    setBusy(true)
    try {
      const r = await api.reviewAll()
      toast(`${r.marked} transaction${r.marked === 1 ? '' : 's'} marked reviewed.`)
      setConfirm(false); setBump((n) => n + 1)
      onChanged && onChanged()
    } catch (e) { toast(e.message) } finally { setBusy(false) }
  }

  return (
    <div className="card rise" style={{ padding: 18 }}>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
        <h2 style={{ margin: 0, fontSize: 15, fontWeight: 600 }}>
          {waiting ? `${waiting.toLocaleString()} transaction${waiting === 1 ? '' : 's'} to review` : 'Nothing to review'}
        </h2>
        {waiting > 0 && (confirm ? (
          <span style={{ display: 'flex', gap: 8 }}>
            <button type="button" className="press" disabled={busy} onClick={markAll} style={btn}>{busy ? 'Marking...' : `Mark all ${waiting.toLocaleString()} reviewed`}</button>
            <button type="button" onClick={() => setConfirm(false)} style={ghost}>Keep</button>
          </span>
        ) : (
          <button type="button" onClick={() => setConfirm(true)} style={ghost}>Mark all reviewed</button>
        ))}
      </div>
      <p style={{ margin: '0 0 14px', fontSize: 13, color: 'var(--muted)' }}>
        New transactions wait here until you check them. Fix the category or add tags, then click "Reviewed". Pending charges show up after they post.
        {' '}Keys: <span style={key}>↑</span> <span style={key}>↓</span> move, <span style={key}>Enter</span> reviewed, <span style={key}>C</span> category, <span style={key}>T</span> tag.
      </p>
      <TxList review unreviewed refreshKey={refreshKey + bump} onChanged={onChanged} empty="You are caught up. New transactions appear here after the next sync." />
    </div>
  )
}

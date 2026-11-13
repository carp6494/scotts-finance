import { useState } from 'react'
import { api, toast } from '../api'

const inp = { height: 30, borderRadius: 8, border: '1px solid var(--line)', background: 'var(--bg)', color: 'var(--text)', padding: '0 8px', fontSize: 12 }
const btn = { height: 30, padding: '0 10px', borderRadius: 8, border: 0, background: 'var(--accent)', color: '#fff', fontWeight: 600, fontSize: 12 }

// The address line under a transaction. Click to set or clear a place for this merchant.
export default function PlaceLine({ t, onSaved }) {
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [d, setD] = useState({ address: '', city: '', region: '', postal: '' })
  const icon = t.place_source === 'hq' ? '🏢' : t.place_source === 'user' ? '📌' : '📍'
  const text = t.place_line || 'Add a place'

  const start = (e) => {
    e.stopPropagation()
    setD({ address: t.place_address || '', city: t.place_city || '', region: t.place_region || '', postal: t.place_postal || '' })
    setOpen(true)
  }
  const save = async (e) => {
    e.preventDefault(); setBusy(true)
    try { const r = await api.patchTransaction(t.transaction_id, { place: d }); setOpen(false); onSaved(r) } catch (x) { toast(x.message) } finally { setBusy(false) }
  }
  const clear = async () => {
    setBusy(true)
    try { const r = await api.patchTransaction(t.transaction_id, { clear_place: true }); setOpen(false); onSaved(r) } catch (x) { toast(x.message) } finally { setBusy(false) }
  }

  if (!open) {
    return (
      <button type="button" onClick={start} title="Set the place for this merchant"
        style={{ border: 0, background: 'transparent', padding: 0, font: 'inherit', fontSize: 12, color: t.place_line ? 'var(--muted)' : 'var(--muted2)', cursor: 'pointer', textAlign: 'left' }}>
        {icon} {text}
      </button>
    )
  }
  return (
    <form onSubmit={save} onClick={(e) => e.stopPropagation()} style={{ display: 'flex', flexWrap: 'wrap', gap: 6, alignItems: 'center', marginTop: 4 }}>
      <input value={d.address} onChange={(e) => setD({ ...d, address: e.target.value })} placeholder="Street" style={{ ...inp, flex: '2 1 160px' }} />
      <input value={d.city} onChange={(e) => setD({ ...d, city: e.target.value })} placeholder="City" style={{ ...inp, flex: '1 1 110px' }} />
      <input value={d.region} onChange={(e) => setD({ ...d, region: e.target.value })} placeholder="State" style={{ ...inp, width: 64 }} />
      <input value={d.postal} onChange={(e) => setD({ ...d, postal: e.target.value })} placeholder="Zip" style={{ ...inp, width: 80 }} />
      <button type="submit" disabled={busy} className="press" style={btn}>Save for this merchant</button>
      {t.place_source === 'user' && <button type="button" disabled={busy} onClick={clear} style={{ ...btn, background: 'transparent', border: '1px solid var(--line)', color: 'var(--text2)', fontWeight: 500 }}>Clear</button>}
      <button type="button" onClick={() => setOpen(false)} style={{ ...btn, background: 'transparent', border: '1px solid var(--line)', color: 'var(--text2)', fontWeight: 500 }}>Cancel</button>
    </form>
  )
}

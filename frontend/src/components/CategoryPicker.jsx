import { useEffect, useId, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { api } from '../api'
import { useCategories, flatCategories, loadCategories, withIcon } from '../categories'

const inp = { height: 32, borderRadius: 8, border: '1px solid var(--line)', background: 'var(--bg)', color: 'var(--text)', padding: '0 8px', fontSize: 13 }

// A category badge. Click to search and pick another category, or add a new one.
export default function CategoryPicker({ value, onChange, compact = false }) {
  const groups = useCategories()
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState('')
  const [adding, setAdding] = useState(false)
  const [draft, setDraft] = useState({ name: '', group_name: '', type: 'expense' })
  const [err, setErr] = useState('')
  const box = useRef(null)
  const pop = useRef(null)
  const [pos, setPos] = useState({ top: 0, left: 0 })
  const groupsId = useId()

  const all = flatCategories(groups)
  const current = all.find((c) => c.id === value)

  useEffect(() => {
    if (!open) return
    const onDoc = (e) => {
      if (box.current?.contains(e.target) || pop.current?.contains(e.target)) return
      close()
    }
    const onScroll = (e) => { if (!pop.current?.contains(e.target)) close() }
    document.addEventListener('mousedown', onDoc)
    window.addEventListener('scroll', onScroll, true)
    window.addEventListener('resize', close)
    return () => {
      document.removeEventListener('mousedown', onDoc)
      window.removeEventListener('scroll', onScroll, true)
      window.removeEventListener('resize', close)
    }
  }, [open]) // eslint-disable-line

  const needle = q.trim().toLowerCase()
  const visible = all
    .filter((c) => !c.hidden || c.id === value)
    .filter((c) => !needle || `${c.group_name} ${c.name}`.toLowerCase().includes(needle))
  const byGroup = []
  for (const c of visible) {
    const g = byGroup.find((x) => x.name === c.group_name)
    if (g) g.items.push(c); else byGroup.push({ name: c.group_name, items: [c] })
  }

  const close = () => { setOpen(false); setQ(''); setAdding(false); setErr('') }
  const pick = (id) => { close(); if (id !== value) onChange(id) }
  const onKey = (e) => {
    if (e.key === 'Enter' && visible.length) { e.preventDefault(); pick(visible[0].id) }
  }
  const toggle = (e) => {
    e.stopPropagation()
    if (open) { close(); return }
    const r = e.currentTarget.getBoundingClientRect()
    const width = 300
    const left = Math.min(r.left, window.innerWidth - width - 8)
    const top = r.bottom + 4
    setPos({ top, left, maxHeight: Math.max(160, Math.min(380, window.innerHeight - top - 8)) })
    setOpen(true)
  }
  const add = async (e) => {
    e.preventDefault()
    try {
      const c = await api.addCategory(draft)
      await loadCategories(true)
      pick(c.id)
    } catch (x) { setErr(x.message) }
  }

  return (
    <>
      <span ref={box} style={{ position: 'relative', display: 'inline-block' }}>
        <button type="button" onClick={toggle} className="press" title="Change category"
          aria-haspopup="listbox" aria-expanded={open}
          style={{ font: 'inherit', fontSize: compact ? 11 : 12, lineHeight: 1.4, color: 'var(--text2)', background: 'var(--hover)', border: '1px solid var(--line)', borderRadius: 999, padding: '1px 9px', whiteSpace: 'nowrap' }}>
          {current ? `${withIcon(current)}${current.group_name} · ${current.name}` : '❔ Uncategorized'}
        </button>
      </span>
      {open && createPortal(
        <div ref={pop} onKeyDown={(e) => { if (e.key === 'Escape') { e.stopPropagation(); close() } }}
          style={{ position: 'fixed', top: pos.top, left: pos.left, zIndex: 1000, width: 300, maxHeight: pos.maxHeight, overflowY: 'auto', background: 'var(--card)', border: '1px solid var(--line3)', borderRadius: 10, boxShadow: '0 12px 40px rgba(0,0,0,.35)', padding: 8 }}>
          <input autoFocus value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={onKey} placeholder="Search categories" aria-label="Search categories"
            style={{ ...inp, width: '100%', height: 34, marginBottom: 6 }} />
          {byGroup.map((g) => (
            <div key={g.name}>
              <div style={{ fontSize: 10, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '.06em', color: 'var(--muted)', padding: '6px 6px 2px' }}>{g.name}</div>
              {g.items.map((c) => (
                <button key={c.id} type="button" onClick={() => pick(c.id)}
                  style={{ display: 'block', width: '100%', textAlign: 'left', padding: '6px 8px', borderRadius: 6, border: 0, background: c.id === value ? 'var(--active)' : 'transparent', color: 'var(--text)', fontSize: 13 }}>
                  {withIcon(c)}{c.name}{c.custom ? <span style={{ marginLeft: 6, fontSize: 10, color: 'var(--muted)' }}>custom</span> : null}
                </button>
              ))}
            </div>
          ))}
          {!visible.length && <div style={{ padding: 8, fontSize: 13, color: 'var(--muted)' }}>No match.</div>}
          <div style={{ borderTop: '1px solid var(--line2)', marginTop: 6, paddingTop: 6 }}>
            {!adding ? (
              <button type="button" onClick={() => { setAdding(true); setDraft({ name: q.trim(), group_name: '', type: 'expense' }) }}
                style={{ border: 0, background: 'transparent', color: 'var(--info)', fontSize: 13, padding: '4px 8px' }}>New category</button>
            ) : (
              <form onSubmit={add} style={{ display: 'flex', flexDirection: 'column', gap: 6, padding: 4 }}>
                <input required value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} placeholder="Name" style={inp} />
                <input required list={groupsId} value={draft.group_name} onChange={(e) => setDraft({ ...draft, group_name: e.target.value })} placeholder="Group" style={inp} />
                <datalist id={groupsId}>{groups.map((g) => <option key={g.group_name} value={g.group_name} />)}</datalist>
                <select value={draft.type} onChange={(e) => setDraft({ ...draft, type: e.target.value })} style={inp}>
                  <option value="expense">Expense</option>
                  <option value="income">Income</option>
                  <option value="transfer">Transfer</option>
                </select>
                {err && <div style={{ fontSize: 12, color: 'var(--neg)' }}>{err}</div>}
                <button type="submit" className="press" style={{ height: 32, borderRadius: 8, border: 0, background: 'var(--accent)', color: '#fff', fontWeight: 600, fontSize: 13 }}>Add</button>
              </form>
            )}
          </div>
        </div>,
        document.body
      )}
    </>
  )
}

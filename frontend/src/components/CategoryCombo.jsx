import { useEffect, useId, useRef, useState } from 'react'
import { useCategories, flatCategories } from '../categories'
import CatIcon from './CatIcon'

// A category box you type into. The matches open in a list right under the box, inside the page flow,
// so the list scrolls with the window it sits in and is never cut off. '' means no category.
// noneLabel names the '' choice. Arrow keys move, Enter picks, Escape closes the list.
export default function CategoryCombo({ value, onChange, noneLabel = 'No category', inputStyle, id }) {
  const groups = useCategories()
  const all = flatCategories(groups)
  const current = all.find((c) => c.id === value)
  const label = current ? `${current.group_name} · ${current.name}` : noneLabel
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState('')
  const [hi, setHi] = useState(0)
  const list = useRef(null)
  const listId = useId()

  const needle = q.trim().toLowerCase()
  const matches = all
    .filter((c) => !c.hidden || c.id === value)
    .filter((c) => !needle || `${c.group_name} ${c.name}`.toLowerCase().includes(needle))
  const opts = needle ? matches : [{ id: '', name: noneLabel }, ...matches]

  useEffect(() => { setHi(0) }, [needle])
  useEffect(() => {
    if (!open) return
    list.current?.scrollIntoView({ block: 'nearest' })
  }, [open])
  useEffect(() => {
    if (open) list.current?.querySelector(`[data-i="${hi}"]`)?.scrollIntoView({ block: 'nearest' })
  }, [hi, open])

  const show = () => {
    setQ('')
    const at = opts.findIndex((o) => o.id === value)
    setHi(at < 0 ? 0 : at)
    setOpen(true)
  }
  const pick = (o) => { setOpen(false); setQ(''); if (o && o.id !== value) onChange(o.id) }
  const onKey = (e) => {
    if (e.key === 'ArrowDown') { e.preventDefault(); if (!open) show(); else setHi((h) => Math.min(h + 1, opts.length - 1)) }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setHi((h) => Math.max(h - 1, 0)) }
    else if (e.key === 'Enter' && open) { e.preventDefault(); pick(opts[hi]) }
    else if (e.key === 'Escape' && open) { e.stopPropagation(); e.preventDefault(); setOpen(false); setQ('') }
  }

  let lastGroup = null
  return (
    <div style={{ flex: 1, minWidth: 200, display: 'flex', flexDirection: 'column', gap: 4 }}>
      <input id={id} role="combobox" aria-expanded={open} aria-controls={listId} aria-autocomplete="list"
        aria-activedescendant={open && opts[hi] ? `${listId}-${hi}` : undefined}
        value={open ? q : label} placeholder={open ? 'Type to search categories' : undefined}
        onFocus={show} onClick={() => { if (!open) show() }} onBlur={() => { setOpen(false); setQ('') }}
        onChange={(e) => { setQ(e.target.value); if (!open) setOpen(true) }} onKeyDown={onKey}
        style={{ ...inputStyle, width: '100%' }} />
      {open && (
        <div ref={list} id={listId} role="listbox" onMouseDown={(e) => e.preventDefault()}
          style={{ maxHeight: 240, overflowY: 'auto', border: '1px solid var(--line3)', borderRadius: 8, background: 'var(--bg)', padding: 4 }}>
          {opts.map((o, i) => {
            const groupHead = o.id && o.group_name !== lastGroup ? o.group_name : null
            if (o.id) lastGroup = o.group_name
            return (
              <div key={o.id || 'none'}>
                {groupHead && <div style={{ fontSize: 10, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '.06em', color: 'var(--muted)', padding: '6px 6px 2px' }}>{groupHead}</div>}
                <div id={`${listId}-${i}`} data-i={i} role="option" aria-selected={o.id === value}
                  onMouseEnter={() => setHi(i)} onClick={() => pick(o)}
                  style={{ padding: '6px 8px', borderRadius: 6, fontSize: 13, cursor: 'pointer', color: o.id ? 'var(--text)' : 'var(--text2)',
                    background: i === hi ? 'var(--active)' : 'transparent', fontWeight: o.id === value ? 600 : 400 }}>
                  {o.icon ? <><CatIcon icon={o.icon} /> </> : null}{o.name}
                </div>
              </div>
            )
          })}
          {!opts.length && <div style={{ padding: 8, fontSize: 13, color: 'var(--muted)' }}>No match.</div>}
        </div>
      )}
    </div>
  )
}

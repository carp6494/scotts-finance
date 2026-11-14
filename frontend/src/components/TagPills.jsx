import { useId, useState } from 'react'
import { api, toast } from '../api'
import { useTags, loadTags, pillStyle } from '../tags'

// The tags on one transaction, each with a remove button, then a "+ tag" button that turns into a text box.
export default function TagPills({ t, compact = false, onChange }) {
  const [adding, setAdding] = useState(false)
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const listId = useId()
  const { tags: all } = useTags()
  const mine = t.tags || []
  const size = compact ? 11 : 12

  const add = async () => {
    const name = text.trim()
    if (!name) { setAdding(false); return }
    setBusy(true)
    try {
      const r = await api.tagTransaction(t.transaction_id, name)
      onChange(r.tags)
      setText(''); setAdding(false)
      loadTags(true).catch(() => {})
    } catch (e) { toast(e.message) } finally { setBusy(false) }
  }
  const remove = async (tag) => {
    try {
      const r = await api.untagTransaction(t.transaction_id, tag.id)
      onChange(r.tags)
      loadTags(true).catch(() => {})
    } catch (e) { toast(e.message) }
  }

  return (
    <>
      {mine.map((g) => (
        <span key={g.id} style={{ ...pillStyle(g.color), fontSize: size, padding: '1px 3px 1px 8px' }}>
          <span aria-hidden="true" style={{ width: 6, height: 6, borderRadius: 3, background: g.color }} />
          {g.name}
          <button type="button" onClick={() => remove(g)} title={`Remove tag ${g.name}`} aria-label={`Remove tag ${g.name}`}
            style={{ border: 0, background: 'transparent', color: 'var(--muted)', padding: '0 4px', fontSize: size + 2, lineHeight: 1 }}>×</button>
        </span>
      ))}
      {adding ? (
        <>
          <input autoFocus list={listId} value={text} disabled={busy} maxLength={32} onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); add() } if (e.key === 'Escape') { e.stopPropagation(); setText(''); setAdding(false) } }}
            onBlur={() => { if (!busy) add() }}
            placeholder="Tag name" aria-label="Tag name"
            style={{ height: 22, width: 120, borderRadius: 999, border: '1px solid var(--line3)', background: 'var(--bg)', color: 'var(--text)', padding: '0 9px', fontSize: size }} />
          <datalist id={listId}>
            {all.filter((g) => !mine.some((m) => m.id === g.id)).map((g) => <option key={g.id} value={g.name} />)}
          </datalist>
        </>
      ) : (
        <button type="button" data-tag-add onClick={() => setAdding(true)} title="Add a tag"
          style={{ font: 'inherit', fontSize: size, lineHeight: 1.4, color: 'var(--muted)', background: 'transparent', border: '1px dashed var(--line3)', borderRadius: 999, padding: '1px 8px', whiteSpace: 'nowrap' }}>
          + tag
        </button>
      )}
    </>
  )
}

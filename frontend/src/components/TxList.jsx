import { useEffect, useMemo, useRef, useState } from 'react'
import { api, money, fullDate, toast } from '../api'
import { useCategories, categoryLabel, flatCategories } from '../categories'
import CategoryPicker from './CategoryPicker'
import Logo from './Logo'
import { CatLabel } from './CatIcon'
import PlaceLine from './PlaceLine'
import TagPills from './TagPills'

const PAGE = 100

// review: show a "Reviewed" button on each row and take the review keys. unreviewed: list only rows that wait for review.
export default function TxList({ accountId, catId, tagId, spot, merchant, start, end, spendingOnly = false, showAccount = true, compact = false, refreshKey = 0, onChanged, unreviewed = false, review = false, empty = 'No transactions yet.' }) {
  const [q, setQ] = useState('')
  const [rows, setRows] = useState([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [suggestion, setSuggestion] = useState(null) // { id, merchant, shown, catId, similar }
  const [busy, setBusy] = useState(false)
  const timer = useRef(null)
  const seq = useRef(0)
  const [cur, setCur] = useState(0)
  const box = useRef(null)
  const live = useRef({})
  const groups = useCategories()
  const icons = useMemo(() => Object.fromEntries(flatCategories(groups).map((c) => [c.id, c.icon || '🏷️'])), [groups])

  const load = async (offset = 0, query = q, limit = PAGE) => {
    const n = ++seq.current
    setLoading(true)
    try {
      const r = await api.transactions({ account_id: accountId, cat_id: catId, tag_id: tagId, unreviewed: unreviewed ? 1 : undefined, spot, merchant, start, end, spending_only: spendingOnly ? 1 : undefined, q: query, limit: Math.min(limit, 500), offset })
      if (seq.current !== n) return
      setTotal(r.total)
      setRows((prev) => (offset ? [...prev, ...r.rows] : r.rows))
    } finally {
      if (seq.current === n) setLoading(false)
    }
  }

  useEffect(() => {
    clearTimeout(timer.current)
    setSuggestion(null)
    load(0, q)
    return () => clearTimeout(timer.current)
  }, [accountId, catId, tagId, unreviewed, spot, merchant, start, end, spendingOnly, refreshKey]) // eslint-disable-line

  const onSearch = (v) => {
    setQ(v)
    clearTimeout(timer.current)
    timer.current = setTimeout(() => load(0, v), 250)
  }

  const setCategory = async (t, newCatId) => {
    try {
      const r = await api.patchTransaction(t.transaction_id, { cat_id: newCatId })
      setRows((prev) => prev.map((x) => (x.transaction_id === t.transaction_id ? { ...x, ...r } : x)))
      const merchant = t.merchant_name || t.name
      const shown = t.display_name || merchant
      setSuggestion(r.similar > 0 ? { id: t.transaction_id, merchant, shown, catId: newCatId, similar: r.similar } : null)
      onChanged && onChanged()
    } catch (e) { toast(e.message) }
  }

  const setTags = (t, tags) => {
    setRows((prev) => prev.map((x) => (x.transaction_id === t.transaction_id ? { ...x, tags } : x)))
    onChanged && onChanged()
  }

  const markReviewed = async (t) => {
    if (!t) return
    try {
      await api.patchTransaction(t.transaction_id, { reviewed: true })
      setRows((prev) => prev.filter((x) => x.transaction_id !== t.transaction_id))
      setTotal((n) => Math.max(0, n - 1))
      if (suggestion && suggestion.id === t.transaction_id) setSuggestion(null)
      onChanged && onChanged()
    } catch (e) { toast(e.message) }
  }

  // Review keys: arrows move, Enter marks reviewed, C opens the category picker, T opens the tag box.
  live.current = { rows, cur, markReviewed }
  useEffect(() => { if (cur > 0 && cur >= rows.length) setCur(Math.max(0, rows.length - 1)) }, [rows.length, cur])
  useEffect(() => {
    if (!review) return
    const rowEl = (i) => box.current && box.current.querySelector(`[data-row="${i}"]`)
    const onKey = (e) => {
      const el = e.target
      if (e.ctrlKey || e.metaKey || e.altKey) return
      if (el && (['INPUT', 'TEXTAREA', 'SELECT'].includes(el.tagName) || el.isContentEditable)) return
      const { rows: list, cur: at, markReviewed: mark } = live.current
      if (!list.length) return
      const k = e.key.length === 1 ? e.key.toLowerCase() : e.key
      if (k === 'ArrowDown' || k === 'ArrowUp') {
        e.preventDefault()
        const next = Math.max(0, Math.min(list.length - 1, at + (k === 'ArrowDown' ? 1 : -1)))
        setCur(next)
        const target = rowEl(next)
        if (target) target.scrollIntoView({ block: 'nearest' })
      } else if (k === 'Enter') {
        if (el && el.tagName === 'BUTTON') return // the focused button handles its own Enter
        e.preventDefault()
        mark(list[at])
      } else if (k === 'c' || k === 't') {
        const target = rowEl(at)
        const button = target && target.querySelector(k === 'c' ? 'button[title="Change category"]' : 'button[data-tag-add]')
        if (button) { e.preventDefault(); button.click() }
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [review])

  const makeRule = async () => {
    if (!suggestion) return
    setBusy(true)
    try {
      const r = await api.addRule({
        name: `${suggestion.shown} → ${categoryLabel(groups, suggestion.catId)}`,
        conditions: { merchant: suggestion.merchant },
        actions: { cat_id: suggestion.catId },
        created_from: suggestion.id,
        apply_past: true,
      })
      toast(`Rule saved. ${r.changed} past transaction${r.changed === 1 ? '' : 's'} updated.`)
      setSuggestion(null)
      load(0, q)
      onChanged && onChanged()
    } catch (e) { toast(e.message) } finally { setBusy(false) }
  }

  return (
    <div>
      <label style={{ display: 'flex', alignItems: 'center', gap: 8, background: 'var(--bg)', border: '1px solid var(--line)', borderRadius: 8, padding: '0 12px', height: 40, marginBottom: 10 }}>
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true" style={{ color: 'var(--muted)' }}><circle cx="11" cy="11" r="7" /><path d="M20 20l-3.5-3.5" /></svg>
        <span className="sr-only">Search transactions</span>
        <input value={q} onChange={(e) => onSearch(e.target.value)} placeholder="Search merchant, category"
          style={{ flex: 1, background: 'transparent', border: 0, outline: 'none', color: 'var(--text)', fontSize: 14 }} />
        <span style={{ fontSize: 12, color: 'var(--muted)' }}>{total.toLocaleString()} total</span>
      </label>
      <div ref={box} style={{ border: '1px solid var(--line)', borderRadius: 12 }}>
        {rows.map((t, i) => {
          const quiet = t.excluded || t.is_transfer || t.cat_type === 'transfer'
          return (
            <div key={t.transaction_id}>
              <div className="rise" data-row={i} onClick={review ? () => setCur(i) : undefined} style={{
                display: 'flex', alignItems: 'center', gap: 12, padding: compact ? '9px 14px' : '11px 16px',
                borderTop: i ? '1px solid var(--line2)' : 0, animationDelay: `${Math.min(i, 20) * 0.025}s`,
                ...(review && i === cur ? { background: 'var(--hover)', boxShadow: 'inset 3px 0 0 var(--accent)' } : null),
              }}>
                <span style={{ width: 86, fontSize: 12, color: 'var(--muted)', flexShrink: 0, whiteSpace: 'nowrap' }}>{fullDate(t.date)}</span>
                <Logo src={t.logo} name={t.merchant_name || t.name} size={compact ? 28 : 32} icon={icons[t.cat_id] || '❔'} />
                <span style={{ flex: 1, minWidth: 0 }}>
                  {/* Transfers and excluded rows keep full-color icons and categories. Only the name and amount go quiet. */}
                  <span style={{ display: 'block', fontSize: 14, fontWeight: 500, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', color: quiet ? 'var(--muted)' : undefined }}>
                    {t.display_name || t.merchant_name || t.name}
                    {t.pending ? <span style={{ marginLeft: 8, fontSize: 11, color: 'var(--warn)' }}>Pending</span> : null}
                    {t.excluded ? <span style={{ marginLeft: 8, fontSize: 11, color: 'var(--muted)' }}>Excluded</span> : null}
                    {t.is_transfer ? <span style={{ marginLeft: 8, fontSize: 11, color: 'var(--muted)' }}>Transfer</span> : null}
                  </span>
                  <span style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 2, fontSize: 12, color: 'var(--muted)', flexWrap: 'wrap' }}>
                    <CategoryPicker value={t.cat_id} compact={compact} onChange={(id) => setCategory(t, id)} />
                    <TagPills t={t} compact={compact} onChange={(tags) => setTags(t, tags)} />
                    {showAccount && t.account_name ? <span>{t.account_name}{t.mask ? ' ' + t.mask : ''}</span> : null}
                  </span>
                  {compact
                    ? (t.place_city ? <span style={{ display: 'block', marginTop: 2, fontSize: 11, color: 'var(--muted2)' }}>{t.place_source === 'hq' ? '🏢' : '📍'} {t.place_city}{t.place_region ? ', ' + t.place_region : ''}</span> : null)
                    : <span style={{ display: 'block', marginTop: 2 }}><PlaceLine t={t} onSaved={() => { load(0, q, Math.max(PAGE, rows.length)); onChanged && onChanged() }} /></span>}
                </span>
                <span className="num" style={{ fontSize: 14, fontWeight: 600, color: quiet ? 'var(--muted)' : t.display_amount > 0 ? 'var(--pos)' : 'var(--text)' }}>
                  {t.display_amount > 0 ? '+' : ''}{money(t.display_amount)}
                </span>
                {review && (
                  <button type="button" className="press" onClick={(e) => { e.stopPropagation(); markReviewed(t) }}
                    style={{ height: 30, padding: '0 12px', borderRadius: 8, border: '1px solid var(--line)', background: 'var(--card)', color: 'var(--text)', fontSize: 12, fontWeight: 600, flexShrink: 0 }}>
                    Reviewed
                  </button>
                )}
              </div>
              {suggestion && suggestion.id === t.transaction_id && (
                <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 10, padding: '8px 16px 10px', fontSize: 13, color: 'var(--text2)', background: 'var(--hover)' }}>
                  <span style={{ flex: 1 }}>
                    Always file <b>{suggestion.shown}</b> as <b><CatLabel groups={groups} id={suggestion.catId} /></b>? {suggestion.similar} past transaction{suggestion.similar === 1 ? '' : 's'} would change.
                  </span>
                  <button type="button" onClick={makeRule} disabled={busy} className="press"
                    style={{ height: 30, padding: '0 12px', borderRadius: 8, border: 0, background: 'var(--accent)', color: '#fff', fontWeight: 600, fontSize: 12 }}>
                    {busy ? 'Saving...' : 'Make rule'}
                  </button>
                  <button type="button" onClick={() => setSuggestion(null)} style={{ height: 30, padding: '0 10px', borderRadius: 8, border: '1px solid var(--line)', background: 'transparent', color: 'var(--text2)', fontSize: 12 }}>Not now</button>
                </div>
              )}
            </div>
          )
        })}
        {!rows.length && !loading && <div style={{ padding: 16, fontSize: 14, color: 'var(--muted)' }}>{empty}</div>}
      </div>
      {rows.length < total && (
        <button type="button" onClick={() => load(rows.length)} disabled={loading} className="press"
          style={{ marginTop: 10, width: '100%', height: 40, borderRadius: 8, border: '1px solid var(--line)', background: 'var(--card)', color: 'var(--text)', fontSize: 13 }}>
          {loading ? 'Loading...' : `Load more (${(total - rows.length).toLocaleString()} left)`}
        </button>
      )}
    </div>
  )
}

import { useEffect, useId, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { useCategories } from '../categories'
import { describeRule, openRule, useRules } from '../ruleText'

const WIDTH = 320

// Shows that a rule changed this row. Hover or focus to read the rule. Click to open it on the Rules page.
export default function RuleBadge({ ids, compact = false }) {
  const { rules, accounts } = useRules()
  const groups = useCategories()
  const [pos, setPos] = useState(null)
  const btn = useRef(null)
  const hide = useRef(null)
  const tipId = useId()
  const list = ids.map((id) => rules.find((r) => r.id === id)).filter(Boolean)

  useEffect(() => () => clearTimeout(hide.current), [])
  useEffect(() => {
    if (!pos) return
    const close = () => setPos(null)
    window.addEventListener('scroll', close, true)
    window.addEventListener('resize', close)
    return () => { window.removeEventListener('scroll', close, true); window.removeEventListener('resize', close) }
  }, [pos])

  if (!ids.length) return null
  const show = () => {
    clearTimeout(hide.current)
    const r = btn.current.getBoundingClientRect()
    const left = Math.max(8, Math.min(r.left, window.innerWidth - WIDTH - 8))
    // Below the badge, or above it when the window has more room there, so the whole box stays in view.
    const below = window.innerHeight - r.bottom - 12
    setPos(below >= 160 || below >= r.top - 12
      ? { top: r.bottom + 6, left, maxHeight: below }
      : { bottom: window.innerHeight - r.top + 6, left, maxHeight: r.top - 12 })
  }
  const later = () => { clearTimeout(hide.current); hide.current = setTimeout(() => setPos(null), 150) }
  const go = (id) => { setPos(null); openRule(id) }

  return (
    <>
      <button ref={btn} type="button" className="press" aria-describedby={pos ? tipId : undefined}
        onMouseEnter={show} onMouseLeave={later} onFocus={show} onBlur={later}
        onClick={(e) => { e.stopPropagation(); go(ids[0]) }}
        aria-label={`Changed by ${list.length === 1 ? 'rule ' + list[0].name : ids.length + ' rules'}. Open in Rules`}
        style={{ font: 'inherit', fontSize: compact ? 11 : 12, lineHeight: 1.4, display: 'inline-flex', alignItems: 'center', gap: 4, whiteSpace: 'nowrap',
          color: 'var(--info)', background: 'color-mix(in srgb, var(--info) 12%, transparent)', border: '1px solid color-mix(in srgb, var(--info) 40%, transparent)', borderRadius: 999, padding: '1px 9px' }}>
        <span aria-hidden="true">⚡</span>{ids.length > 1 ? `Rules · ${ids.length}` : 'Rule'}
      </button>
      {pos && createPortal(
        <div id={tipId} role="tooltip" onMouseEnter={() => clearTimeout(hide.current)} onMouseLeave={later}
          style={{ position: 'fixed', top: pos.top, bottom: pos.bottom, left: pos.left, width: WIDTH, maxHeight: pos.maxHeight, overflowY: 'auto', zIndex: 1000,
            background: 'var(--card)', color: 'var(--text)', border: '1px solid var(--line3)', borderRadius: 10, boxShadow: '0 12px 40px rgba(0,0,0,.35)', padding: 6, fontSize: 12 }}>
          {list.length ? list.map((r) => (
            <button key={r.id} type="button" onMouseDown={(e) => e.preventDefault()} onClick={() => go(r.id)}
              style={{ display: 'block', width: '100%', textAlign: 'left', border: 0, borderRadius: 6, background: 'transparent', color: 'inherit', padding: '6px 8px', font: 'inherit', cursor: 'pointer' }}
              onMouseEnter={(e) => { e.currentTarget.style.background = 'var(--hover)' }} onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent' }}>
              <span style={{ display: 'block', fontWeight: 600, fontSize: 13 }}>{r.name}{r.enabled ? '' : ' · turned off'}</span>
              <span style={{ display: 'block', color: 'var(--text2)', marginTop: 2, lineHeight: 1.45 }}>{describeRule(r, groups, accounts)}</span>
              <span style={{ display: 'block', color: 'var(--info)', marginTop: 4 }}>Click to open in Rules</span>
            </button>
          )) : <div style={{ padding: 8, color: 'var(--muted)' }}>Loading rule</div>}
        </div>,
        document.body
      )}
    </>
  )
}

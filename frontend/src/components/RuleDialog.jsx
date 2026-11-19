import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { api, money, fullDate, toast, txChanged } from '../api'
import { useCategories, categoryLabel } from '../categories'
import CategoryCombo from './CategoryCombo'
import { loadTags } from '../tags'
import { loadRules } from '../ruleText'

const inp = { height: 34, borderRadius: 8, border: '1px solid var(--line)', background: 'var(--bg)', color: 'var(--text)', padding: '0 10px', fontSize: 13 }
const btn = { height: 36, padding: '0 16px', borderRadius: 8, border: 0, background: 'var(--accent)', color: '#fff', fontWeight: 600, fontSize: 13 }
const ghost = { ...btn, background: 'transparent', border: '1px solid var(--line)', color: 'var(--text2)', fontWeight: 500 }
const head = { fontSize: 12, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '.06em', color: 'var(--muted)' }
const line = { display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, flexWrap: 'wrap' }

const splitTags = (s) => s.split(',').map((x) => x.trim()).filter(Boolean)
const quoteList = (xs) => xs.map((x) => `"${x}"`).join(', ')

// The review window for a rule made from one transaction. It starts from what was changed on the row,
// shows which past rows match and how many would change, and asks before saving.
export default function RuleDialog({ t, onClose, onSaved }) {
  const groups = useCategories()
  const [draft, setDraft] = useState(null)
  const [text, setText] = useState('')
  const [useDir, setUseDir] = useState(true)
  const [useBank, setUseBank] = useState(false)
  const [useAcct, setUseAcct] = useState(false)
  const [lo, setLo] = useState('')
  const [hi, setHi] = useState('')
  const [catId, setCatId] = useState('') // '' leaves the category alone
  const [showAs, setShowAs] = useState('')
  const [tagText, setTagText] = useState('')
  const [exclude, setExclude] = useState(false)
  const [preview, setPreview] = useState(null)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const first = useRef(null)

  useEffect(() => {
    api.ruleDraft(t.transaction_id).then((d) => {
      setDraft(d)
      setText(d.conditions.merchant || '')
      setUseDir(Boolean(d.conditions.direction))
      setCatId(d.actions.cat_id || t.cat_id || '')
      setShowAs(d.actions.display_name || '')
      setTagText((d.actions.tags || []).join(', '))
      setExclude(Boolean(d.actions.exclude))
    }).catch((e) => setErr(e.message))
  }, [t.transaction_id])

  useEffect(() => { if (draft) first.current?.focus() }, [draft])
  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const dir = draft?.conditions.direction
  const bank = draft?.bank_category
  // Amounts are typed as plain dollars. Inside the app money out is positive and money in is negative,
  // so a range on money coming in is flipped and swapped before it is saved.
  const num = (s) => (s === '' || Number.isNaN(Number(s)) ? undefined : Math.abs(Number(s)))
  const low = num(lo), high = num(hi)
  const isIn = dir === 'in'
  const badRange = low !== undefined && high !== undefined && low > high
  const conditions = {
    merchant: text.trim() || undefined,
    amount_min: isIn ? (high !== undefined ? -high : undefined) : low,
    amount_max: isIn ? (low !== undefined ? -low : undefined) : high,
    direction: useDir && dir ? dir : undefined,
    bank_category: useBank && bank ? bank.id : undefined,
    account_id: useAcct ? t.account_id : undefined,
  }
  const actions = {
    cat_id: catId || undefined,
    display_name: showAs.trim() || undefined,
    tags: splitTags(tagText).length ? splitTags(tagText) : undefined,
    exclude: exclude || undefined,
  }
  const hasCond = Object.values(conditions).some(Boolean)
  const hasAct = Object.values(actions).some(Boolean)
  const key = JSON.stringify([conditions, actions])

  useEffect(() => {
    if (!draft || !hasCond) { setPreview(null); return }
    const timer = setTimeout(() => {
      api.previewRule({ conditions, actions }).then(setPreview).catch((e) => setErr(e.message))
    }, 250)
    return () => clearTimeout(timer)
  }, [key, draft]) // eslint-disable-line

  // The question in plain words, built from the boxes above.
  const doing = []
  if (actions.cat_id) doing.push(`file it as ${categoryLabel(groups, actions.cat_id)}`)
  if (actions.display_name) doing.push(`show it as "${actions.display_name}"`)
  if (actions.tags) doing.push(`tag it ${quoteList(actions.tags)}`)
  if (actions.exclude) doing.push('leave it out of totals')
  const when = []
  if (conditions.merchant) when.push(`the name has "${conditions.merchant}"`)
  if (conditions.direction) when.push(conditions.direction === 'out' ? 'money goes out' : 'money comes in')
  if (low !== undefined && high !== undefined) when.push(`the amount is ${money(low)} to ${money(high)}`)
  else if (low !== undefined) when.push(`the amount is ${money(low)} or more`)
  else if (high !== undefined) when.push(`the amount is ${money(high)} or less`)
  if (conditions.bank_category) when.push(`the bank calls it ${bank.name}`)
  if (conditions.account_id) when.push(`it is on ${t.account_name || 'this account'}`)
  const question = hasCond && hasAct && !badRange ? `Are you sure you want to ${doing.join(', ')} for every transaction where ${when.join(' and ')}?` : null

  const save = async () => {
    setBusy(true); setErr('')
    try {
      const name = `${conditions.merchant || bank?.name || 'Rule'} → ${actions.cat_id ? categoryLabel(groups, actions.cat_id) : doing[0] || ''}`
      const r = await api.addRule({ name, conditions, actions, created_from: t.transaction_id, apply_past: true })
      if (actions.tags) loadTags(true)
      loadRules(true).catch(() => {})
      toast(`Rule saved. ${r.changed} past transaction${r.changed === 1 ? '' : 's'} updated.`)
      txChanged({ reload: true })
      onSaved && onSaved()
      onClose()
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  return createPortal(
    <div onClick={onClose} style={{ position: 'fixed', inset: 0, zIndex: 900, background: 'rgba(0,0,0,.45)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 16 }}>
      <div role="dialog" aria-modal="true" aria-labelledby="rule-dialog-title" onClick={(e) => e.stopPropagation()}
        style={{ width: 'min(560px, 100%)', maxHeight: 'calc(100vh - 32px)', overflowY: 'auto', background: 'var(--card)', color: 'var(--text)', border: '1px solid var(--line3)', borderRadius: 12, boxShadow: '0 20px 60px rgba(0,0,0,.4)', padding: 20, display: 'flex', flexDirection: 'column', gap: 14 }}>
        <h2 id="rule-dialog-title" style={{ margin: 0, fontSize: 17 }}>Create rule</h2>
        <div style={{ fontSize: 13, color: 'var(--text2)' }}>From {t.display_name || t.merchant_name || t.name} on {fullDate(t.date)}, {money(Math.abs(t.display_amount ?? t.amount))}</div>
        {!draft && !err && <div style={{ fontSize: 13, color: 'var(--muted)' }}>Loading</div>}
        {draft && <>
          <div style={head}>When all of these match</div>
          <label style={line}>Name has
            <input ref={first} value={text} onChange={(e) => setText(e.target.value)} style={{ ...inp, flex: 1, minWidth: 160 }} />
          </label>
          <div style={{ fontSize: 12, color: 'var(--muted)', marginTop: -8 }}>Bank text: {t.name}</div>
          {dir && <label style={line}><input type="checkbox" checked={useDir} onChange={(e) => setUseDir(e.target.checked)} /> Only money {dir === 'out' ? 'going out' : 'coming in'}</label>}
          {bank && <label style={line}><input type="checkbox" checked={useBank} onChange={(e) => setUseBank(e.target.checked)} /> Only when the bank calls it {bank.name}</label>}
          <div style={line}>
            <span>Amount</span>
            <label style={{ display: 'flex', alignItems: 'center', gap: 6 }}>at least $
              <input type="number" min="0" step="0.01" inputMode="decimal" value={lo} onChange={(e) => setLo(e.target.value)} placeholder="any" aria-label="Amount at least" style={{ ...inp, width: 96 }} />
            </label>
            <label style={{ display: 'flex', alignItems: 'center', gap: 6 }}>at most $
              <input type="number" min="0" step="0.01" inputMode="decimal" value={hi} onChange={(e) => setHi(e.target.value)} placeholder="any" aria-label="Amount at most" style={{ ...inp, width: 96 }} />
            </label>
          </div>
          {badRange && <div style={{ fontSize: 12, color: 'var(--warn)', marginTop: -8 }}>The first amount is above the second.</div>}
          <div style={{ fontSize: 12, color: 'var(--muted)', marginTop: -8 }}>This one is {money(Math.abs(t.display_amount ?? t.amount))}. For two rules on one store, like $30 or more and $29.99 or less, make one, then click Create rule again.</div>
          <label style={line}><input type="checkbox" checked={useAcct} onChange={(e) => setUseAcct(e.target.checked)} /> Only on {t.account_name || 'this account'}{t.mask ? ` ${t.mask}` : ''}</label>

          <div style={head}>Then</div>
          <div style={{ ...line, alignItems: 'flex-start' }}>
            <label htmlFor="rule-cat" style={{ lineHeight: '34px' }}>Category</label>
            <CategoryCombo id="rule-cat" value={catId} onChange={setCatId} noneLabel="Leave the category alone" inputStyle={inp} />
          </div>
          <label style={line}>Show as
            <input value={showAs} onChange={(e) => setShowAs(e.target.value)} placeholder="Leave the name alone" style={{ ...inp, flex: 1, minWidth: 160 }} />
          </label>
          <label style={line}>Add tags
            <input value={tagText} onChange={(e) => setTagText(e.target.value)} placeholder="None. Separate with commas" style={{ ...inp, flex: 1, minWidth: 160 }} />
          </label>
          <label style={line}><input type="checkbox" checked={exclude} onChange={(e) => setExclude(e.target.checked)} /> Leave out of totals</label>

          <div style={{ background: 'var(--hover)', borderRadius: 10, padding: 12, display: 'flex', flexDirection: 'column', gap: 8, fontSize: 13 }}>
            {!hasCond && <span style={{ color: 'var(--warn)' }}>Add at least one thing to match.</span>}
            {hasCond && !hasAct && <span style={{ color: 'var(--warn)' }}>Pick at least one thing for the rule to do.</span>}
            {question && <b style={{ fontWeight: 600 }}>{question}</b>}
            {preview && <span style={{ color: 'var(--text2)' }}>
              {preview.count.toLocaleString()} past transaction{preview.count === 1 ? '' : 's'} match. {preview.changes.toLocaleString()} will change. Ones you set by hand stay as they are.
            </span>}
            {preview?.sample?.length > 0 && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 2, fontSize: 12, color: 'var(--text2)' }}>
                {preview.sample.slice(0, 8).map((s) => (
                  <div key={s.transaction_id} style={{ display: 'flex', gap: 10 }}>
                    <span style={{ width: 86, color: 'var(--muted)', flexShrink: 0 }}>{fullDate(s.date)}</span>
                    <span style={{ flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{s.display_name || s.merchant_name || s.name}</span>
                    <span className="num">{money(-s.amount)}</span>
                  </div>
                ))}
                {preview.count > 8 && <span style={{ color: 'var(--muted)' }}>and {(preview.count - 8).toLocaleString()} more</span>}
              </div>
            )}
          </div>
        </>}
        {err && <div role="alert" style={{ fontSize: 13, color: 'var(--warn)' }}>{err}</div>}
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
          <button type="button" onClick={onClose} style={ghost}>Cancel</button>
          <button type="button" className="press" onClick={save} disabled={busy || !question} style={{ ...btn, opacity: busy || !question ? 0.5 : 1 }}>
            {busy ? 'Saving...' : 'Yes, create rule'}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  )
}

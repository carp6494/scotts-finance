import { useEffect, useId, useRef, useState } from 'react'
import { api, toast } from '../api'
import { useCategories, categoryLabel, loadCategories, withIcon } from '../categories'
import CatIcon from '../components/CatIcon'
import { useTags, loadTags, pillStyle } from '../tags'
import { describeRule, loadRules } from '../ruleText'

const inp = { height: 36, borderRadius: 8, border: '1px solid var(--line)', background: 'var(--bg)', color: 'var(--text)', padding: '0 10px', fontSize: 13 }
const btn = { height: 36, padding: '0 14px', borderRadius: 8, border: 0, background: 'var(--accent)', color: '#fff', fontWeight: 600, fontSize: 13 }
const ghost = { ...btn, background: 'transparent', border: '1px solid var(--line)', color: 'var(--text2)', fontWeight: 500 }
const EMPTY = { name: '', enabled: true, conditions: {}, actions: {} }

const describe = describeRule

function RuleEditor({ initial, accounts, groups, onSaved, onCancel }) {
  const [r, setR] = useState(initial)
  const [preview, setPreview] = useState(null)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const [tagText, setTagText] = useState((initial.actions.tags || []).join(', '))
  const tagsId = useId()
  const { tags: allTags } = useTags()
  const timer = useRef(null)
  const setC = (k, v) => setR((x) => ({ ...x, conditions: { ...x.conditions, [k]: v } }))
  const setA = (k, v) => setR((x) => ({ ...x, actions: { ...x.actions, [k]: v } }))

  useEffect(() => {
    clearTimeout(timer.current)
    timer.current = setTimeout(() => {
      api.previewRule({ conditions: r.conditions, actions: r.actions }).then((p) => setPreview({ ok: true, ...p })).catch((e) => setPreview({ error: e.message }))
    }, 300)
    return () => clearTimeout(timer.current)
  }, [r.conditions, r.actions])

  const save = async (applyPast) => {
    setBusy(true); setErr('')
    try {
      const body = { ...r, apply_past: applyPast }
      const out = r.id ? await api.updateRule(r.id, body) : await api.addRule(body)
      if (applyPast) toast(`${out.changed} transaction${out.changed === 1 ? '' : 's'} updated.`)
      loadTags(true).catch(() => {})
      onSaved()
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  const c = r.conditions, a = r.actions
  return (
    <div className="card" style={{ padding: 18, display: 'flex', flexDirection: 'column', gap: 14 }}>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10 }}>
        <input value={r.name} onChange={(e) => setR({ ...r, name: e.target.value })} placeholder="Rule name" style={{ ...inp, flex: '2 1 220px' }} />
        <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, color: 'var(--muted)' }}>
          <input type="checkbox" checked={r.enabled} onChange={(e) => setR({ ...r, enabled: e.target.checked })} /> Enabled
        </label>
      </div>
      <div style={{ fontSize: 12, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '.06em', color: 'var(--muted)' }}>When all of these match</div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 10 }}>
        <input value={c.merchant || ''} onChange={(e) => setC('merchant', e.target.value)} placeholder="Merchant contains" style={inp} />
        <input value={c.text || ''} onChange={(e) => setC('text', e.target.value)} placeholder="Raw text contains" style={inp} />
        <input type="number" step="0.01" value={c.amount_min ?? ''} onChange={(e) => setC('amount_min', e.target.value === '' ? null : e.target.value)} placeholder="Amount at least" style={inp} />
        <input type="number" step="0.01" value={c.amount_max ?? ''} onChange={(e) => setC('amount_max', e.target.value === '' ? null : e.target.value)} placeholder="Amount at most" style={inp} />
        <select value={c.account_id || ''} onChange={(e) => setC('account_id', e.target.value || null)} style={inp}>
          <option value="">Any account</option>
          {accounts.map((x) => <option key={x.account_id} value={x.account_id}>{x.official_name || x.name}{x.mask ? ` ${x.mask}` : ''}</option>)}
        </select>
        <select aria-label="Money in or out" value={c.direction || ''} onChange={(e) => setC('direction', e.target.value || null)} style={inp}>
          <option value="">Money in or out</option>
          <option value="out">Money out only</option>
          <option value="in">Money in only</option>
        </select>
        <select aria-label="Bank category" value={c.bank_category || ''} onChange={(e) => setC('bank_category', e.target.value || null)} style={inp}>
          <option value="">Any bank category</option>
          {groups.map((g) => {
            const plaid = g.categories.filter((x) => !x.custom && !x.id.startsWith('EXTRA_') && x.id !== 'UNCATEGORIZED')
            return plaid.length ? (
              <optgroup key={g.group_name} label={g.group_name}>
                {plaid.map((x) => <option key={x.id} value={x.id}>Bank says {x.name}</option>)}
              </optgroup>
            ) : null
          })}
        </select>
        <div style={{ display: 'flex', gap: 6 }}>
          <input type="number" min="1" max="31" value={c.day_min ?? ''} onChange={(e) => setC('day_min', e.target.value === '' ? null : e.target.value)} placeholder="Day from" style={{ ...inp, width: '50%' }} />
          <input type="number" min="1" max="31" value={c.day_max ?? ''} onChange={(e) => setC('day_max', e.target.value === '' ? null : e.target.value)} placeholder="Day to" style={{ ...inp, width: '50%' }} />
        </div>
      </div>
      <div style={{ fontSize: 12, color: 'var(--muted)' }}>Amounts follow the bank: positive is money out, negative is money in.</div>
      <div style={{ fontSize: 12, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '.06em', color: 'var(--muted)' }}>Then</div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 10, alignItems: 'center' }}>
        <select value={a.cat_id || ''} onChange={(e) => setA('cat_id', e.target.value || null)} style={inp}>
          <option value="">Leave category alone</option>
          {groups.map((g) => (
            <optgroup key={g.group_name} label={g.group_name}>
              {g.categories.filter((x) => !x.hidden).map((x) => <option key={x.id} value={x.id}>{withIcon(x)}{x.name}</option>)}
            </optgroup>
          ))}
        </select>
        <input value={a.display_name || ''} onChange={(e) => setA('display_name', e.target.value)} placeholder="Show merchant as" style={inp} />
        <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13 }}><input type="checkbox" checked={!!a.exclude} onChange={(e) => setA('exclude', e.target.checked)} /> Exclude from totals</label>
        <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13 }}><input type="checkbox" checked={!!a.transfer} onChange={(e) => setA('transfer', e.target.checked)} /> Mark as transfer</label>
        <input list={tagsId} value={tagText} placeholder="Add tags, comma between" aria-label="Add tags"
          onChange={(e) => { setTagText(e.target.value); setA('tags', e.target.value.split(',').map((x) => x.trim()).filter(Boolean)) }} style={inp} />
        <datalist id={tagsId}>{allTags.map((g) => <option key={g.id} value={g.name} />)}</datalist>
      </div>
      <div style={{ fontSize: 13, color: preview?.error ? 'var(--warn)' : 'var(--text2)' }}>
        {preview?.error
          ? preview.error
          : preview?.ok
            ? `Matches ${preview.count.toLocaleString()} transaction${preview.count === 1 ? '' : 's'} you have not set by hand`
            : 'Add a condition to see matches'}
        {preview?.ok && preview.sample.length > 0 && (
          <span style={{ color: 'var(--muted)' }}>, for example {preview.sample.slice(0, 3).map((s) => s.display_name || s.merchant_name || s.name).join(', ')}</span>
        )}
      </div>
      {err && <div style={{ fontSize: 13, color: 'var(--neg)' }}>{err}</div>}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10 }}>
        <button type="button" className="press" disabled={busy} onClick={() => save(false)} style={btn}>Save</button>
        <button type="button" className="press" disabled={busy} onClick={() => save(true)} style={btn}>Save and apply to past</button>
        <button type="button" onClick={onCancel} style={ghost}>Cancel</button>
      </div>
    </div>
  )
}

function RulesTab({ accounts, groups, focus }) {
  const [rules, setRules] = useState([])
  const [editing, setEditing] = useState(null)
  const [confirmId, setConfirmId] = useState(null)
  const [glow, setGlow] = useState(null)
  const rows = useRef({})
  const load = () => api.rules().then((r) => { setRules(r); loadRules(true).catch(() => {}) }).catch((e) => toast(e.message))
  useEffect(() => { load() }, [])
  // A Rule badge on a transaction sent us here. Scroll to that rule and let it glow for a few seconds.
  useEffect(() => {
    if (!focus || !rules.length) return
    const el = rows.current[focus.id]
    if (!el) { toast('That rule no longer exists.'); return }
    el.scrollIntoView({ behavior: 'smooth', block: 'center' })
    setGlow(focus)
    const t = setTimeout(() => setGlow(null), 4200)
    return () => clearTimeout(t)
  }, [focus, rules.length > 0]) // eslint-disable-line

  const toggle = async (r) => {
    try { await api.updateRule(r.id, { ...r, enabled: !r.enabled }); load() } catch (e) { toast(e.message) }
  }
  const remove = async (r) => {
    try { await api.deleteRule(r.id); load() } catch (e) { toast(e.message) }
  }
  // Drag a rule by its grabber, or focus the grabber and press the up and down arrow keys.
  const [drag, setDrag] = useState(null) // { id, from, over: index the rule would land at }
  const grabbers = useRef({})
  const move = async (from, to, refocus) => {
    if (to < 0 || to > rules.length - 1 || from === to) return
    const next = [...rules]
    const [r] = next.splice(from, 1)
    next.splice(to, 0, r)
    setRules(next)
    if (refocus) requestAnimationFrame(() => grabbers.current[r.id]?.focus())
    try {
      const out = await api.orderRules(next.map((x) => x.id))
      toast(`${r.name} now runs ${to === 0 ? 'first' : `number ${to + 1}`}.${out.changed ? ` ${out.changed} transaction${out.changed === 1 ? '' : 's'} updated.` : ''}`)
      load()
    } catch (e) { toast(e.message); load() }
  }
  // Where the pointer would drop: the gap before the first row whose middle is below it.
  const gapAt = (y) => {
    const i = rules.findIndex((x) => { const el = rows.current[x.id]; if (!el) return false; const b = el.getBoundingClientRect(); return y < b.top + b.height / 2 })
    return i < 0 ? rules.length : i
  }
  const grab = (e, i, r) => {
    if (e.button !== 0 || editing) return
    e.preventDefault()
    e.currentTarget.setPointerCapture(e.pointerId)
    setDrag({ id: r.id, from: i, over: i })
  }
  const drift = (e) => { if (drag) { const over = gapAt(e.clientY); if (over !== drag.over) setDrag({ ...drag, over }) } }
  const release = () => {
    if (!drag) return
    const { from, over } = drag
    setDrag(null)
    move(from, over > from ? over - 1 : over)
  }

  const applyAll = async () => {
    try { const out = await api.applyRules(); toast(`${out.changed} transaction${out.changed === 1 ? '' : 's'} updated.`); load() } catch (e) { toast(e.message) }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ fontSize: 13, color: 'var(--muted)', flex: '1 1 320px', lineHeight: 1.5 }}>
          Rules run from top to bottom on every sync. When two rules could set the category, the higher one wins. They never change a category you set by hand.
          <span style={{ display: 'block', marginTop: 2 }}>To change the order, drag a rule by its <span aria-hidden="true" style={{ color: 'var(--text2)' }}>⠿</span> grabber on the left. Or click the grabber and press the up and down arrow keys.</span>
        </div>
        <div style={{ display: 'flex', gap: 10 }}>
          <button type="button" onClick={applyAll} style={ghost}>Re-run all rules</button>
          <button type="button" className="press" onClick={() => setEditing({ ...EMPTY })} style={btn}>New rule</button>
        </div>
      </div>
      {editing && !editing.id && <RuleEditor initial={editing} accounts={accounts} groups={groups} onSaved={() => { setEditing(null); load() }} onCancel={() => setEditing(null)} />}
      <div style={{ border: '1px solid var(--line)', borderRadius: 12 }}>
        {rules.map((r, i) => (
          <div key={glow?.id === r.id ? `${r.id}-${glow.at}` : r.id} ref={(el) => { rows.current[r.id] = el }}
            className={glow?.id === r.id ? 'rule-glow' : undefined}
            style={{ borderTop: i ? '1px solid var(--line2)' : 0, position: 'relative', opacity: drag?.id === r.id ? 0.45 : 1,
              background: drag?.id === r.id ? 'var(--hover)' : undefined,
              boxShadow: drag && drag.over !== drag.from && drag.over !== drag.from + 1
                ? (drag.over === i ? 'inset 0 3px 0 var(--accent)' : drag.over === i + 1 && i === rules.length - 1 ? 'inset 0 -3px 0 var(--accent)' : undefined) : undefined }}>
            {editing && editing.id === r.id ? (
              <div style={{ padding: 10 }}><RuleEditor initial={editing} accounts={accounts} groups={groups} onSaved={() => { setEditing(null); load() }} onCancel={() => setEditing(null)} /></div>
            ) : (
              <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 12, padding: '12px 16px', opacity: r.enabled ? 1 : 0.55 }}>
                <button type="button" ref={(el) => { grabbers.current[r.id] = el }}
                  onPointerDown={(e) => grab(e, i, r)} onPointerMove={drift} onPointerUp={release} onPointerCancel={() => setDrag(null)}
                  onKeyDown={(e) => {
                    if (e.key === 'ArrowUp') { e.preventDefault(); move(i, i - 1, true) }
                    if (e.key === 'ArrowDown') { e.preventDefault(); move(i, i + 1, true) }
                  }}
                  title="Drag to move. Or press the up and down arrow keys." aria-label={`Move ${r.name}. Runs number ${i + 1} of ${rules.length}. Use the up and down arrow keys.`}
                  style={{ cursor: drag ? 'grabbing' : 'grab', border: 0, background: 'transparent', color: 'var(--muted)', fontSize: 18, lineHeight: 1, padding: '4px 2px', borderRadius: 6, touchAction: 'none' }}>
                  ⠿
                </button>
                <span style={{ flex: '1 1 260px', minWidth: 0 }}>
                  <span style={{ display: 'block', fontSize: 14, fontWeight: 600 }}>{r.name}</span>
                  <span style={{ display: 'block', fontSize: 12, color: 'var(--muted)' }}>{describe(r, groups, accounts)}</span>
                </span>
                <span className="num" style={{ fontSize: 12, color: 'var(--muted)' }}>{r.hits} hit{r.hits === 1 ? '' : 's'}</span>
                <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: 'var(--muted)' }}>
                  <input type="checkbox" checked={r.enabled} onChange={() => toggle(r)} aria-label={`Enable ${r.name}`} /> On
                </label>
                <button type="button" onClick={() => setEditing({ ...r })} style={{ ...ghost, height: 30, padding: '0 10px', fontSize: 12 }}>Edit</button>
                {confirmId === r.id ? (
                  <>
                    <button type="button" onClick={() => { remove(r); setConfirmId(null) }} style={{ ...ghost, height: 30, padding: '0 10px', fontSize: 12, color: 'var(--neg)' }}>Confirm delete</button>
                    <button type="button" onClick={() => setConfirmId(null)} style={{ ...ghost, height: 30, padding: '0 10px', fontSize: 12 }}>Keep</button>
                  </>
                ) : (
                  <button type="button" onClick={() => setConfirmId(r.id)} style={{ ...ghost, height: 30, padding: '0 10px', fontSize: 12, color: 'var(--neg)' }}>Delete</button>
                )}
              </div>
            )}
          </div>
        ))}
        {!rules.length && <div style={{ padding: 16, fontSize: 14, color: 'var(--muted)' }}>No rules yet. Change a category on any transaction and choose Make rule, or click New rule.</div>}
      </div>
    </div>
  )
}

function CategoriesTab({ groups }) {
  const [editing, setEditing] = useState(null) // { id, name }
  const [iconEdit, setIconEdit] = useState(null) // { id, icon }
  const [draft, setDraft] = useState({ name: '', group_name: '', type: 'expense', icon: '' })
  const [showHidden, setShowHidden] = useState(false)
  const groupsId = useId()

  const patch = async (id, body) => {
    try { await api.patchCategory(id, body); await loadCategories(true) } catch (e) { toast(e.message) }
  }
  const add = async (e) => {
    e.preventDefault()
    try { await api.addCategory(draft); await loadCategories(true); setDraft({ name: '', group_name: '', type: 'expense', icon: '' }); toast('Category added.') } catch (x) { toast(x.message) }
  }
  const commitRename = async () => {
    const current = editing
    setEditing(null)
    if (current && current.name.trim()) await patch(current.id, { name: current.name.trim() })
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      <form onSubmit={add} className="card" style={{ padding: 14, display: 'flex', flexWrap: 'wrap', gap: 10, alignItems: 'center' }}>
        <span style={{ fontSize: 13, color: 'var(--muted)' }}>New category</span>
        <input value={draft.icon} onChange={(e) => setDraft({ ...draft, icon: e.target.value })} placeholder="Icon" style={{ ...inp, width: 56 }} />
        <input required value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} placeholder="Name" style={{ ...inp, flex: '1 1 160px' }} />
        <input required list={groupsId} value={draft.group_name} onChange={(e) => setDraft({ ...draft, group_name: e.target.value })} placeholder="Group" style={{ ...inp, flex: '1 1 160px' }} />
        <datalist id={groupsId}>{groups.map((g) => <option key={g.group_name} value={g.group_name} />)}</datalist>
        <select value={draft.type} onChange={(e) => setDraft({ ...draft, type: e.target.value })} style={inp}>
          <option value="expense">Expense</option>
          <option value="income">Income</option>
          <option value="transfer">Transfer</option>
        </select>
        <button type="submit" className="press" style={btn}>Add</button>
        <label style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, color: 'var(--muted)' }}>
          <input type="checkbox" checked={showHidden} onChange={(e) => setShowHidden(e.target.checked)} /> Show hidden
        </label>
      </form>
      {groups.map((g) => {
        const items = g.categories.filter((c) => showHidden || !c.hidden)
        if (!items.length) return null
        return (
          <section key={g.group_name}>
            <h3 style={{ margin: '0 0 8px', fontSize: 12, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '.06em', color: 'var(--muted)' }}>{g.group_name}</h3>
            <div style={{ border: '1px solid var(--line)', borderRadius: 12 }}>
              {items.map((c, i) => (
                <div key={c.id} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '8px 14px', borderTop: i ? '1px solid var(--line2)' : 0, fontSize: 14, opacity: c.hidden ? 0.55 : 1 }}>
                  {iconEdit && iconEdit.id === c.id ? (
                    <input autoFocus value={iconEdit.icon} onChange={(e) => setIconEdit({ ...iconEdit, icon: e.target.value })}
                      onBlur={() => { const cur = iconEdit; setIconEdit(null); if (cur.icon !== (c.icon || '')) patch(cur.id, { icon: cur.icon }) }}
                      onKeyDown={(e) => { if (e.key === 'Enter') e.currentTarget.blur(); if (e.key === 'Escape') setIconEdit(null) }}
                      aria-label={`Icon for ${c.name}`} style={{ ...inp, width: 48, height: 30, textAlign: 'center', padding: 0 }} />
                  ) : c.id === 'UNCATEGORIZED' ? (
                    <span style={{ width: 32, fontSize: 18, textAlign: 'center' }}><CatIcon icon={c.icon || '🏷️'} /></span>
                  ) : (
                    <button type="button" title="Change icon" onClick={() => setIconEdit({ id: c.id, icon: c.icon || '' })}
                      style={{ width: 32, height: 30, border: 0, background: 'transparent', fontSize: 18, padding: 0 }}><CatIcon icon={c.icon || '🏷️'} /></button>
                  )}
                  {editing && editing.id === c.id ? (
                    <input autoFocus value={editing.name} onChange={(e) => setEditing({ ...editing, name: e.target.value })}
                      onBlur={commitRename} onKeyDown={(e) => { if (e.key === 'Enter') commitRename(); if (e.key === 'Escape') setEditing(null) }}
                      style={{ ...inp, height: 30, flex: 1 }} />
                  ) : c.id === 'UNCATEGORIZED' ? (
                    <span style={{ flex: 1 }}>{c.name}</span>
                  ) : (
                    <button type="button" onClick={() => setEditing({ id: c.id, name: c.name })} title="Rename"
                      style={{ flex: 1, textAlign: 'left', border: 0, background: 'transparent', color: 'var(--text)', font: 'inherit', padding: 0 }}>
                      {c.name}{c.custom ? <span style={{ marginLeft: 8, fontSize: 11, color: 'var(--muted)' }}>custom</span> : null}
                    </button>
                  )}
                  <span style={{ fontSize: 12, color: 'var(--muted)', width: 64 }}>{c.type}</span>
                  {c.id !== 'UNCATEGORIZED' && (
                    <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: 'var(--muted)' }}>
                      <input type="checkbox" checked={!c.hidden} onChange={(e) => patch(c.id, { hidden: !e.target.checked })} /> Shown
                    </label>
                  )}
                </div>
              ))}
            </div>
          </section>
        )
      })}
    </div>
  )
}

function TagsTab() {
  const { tags, colors } = useTags()
  const [editing, setEditing] = useState(null) // { id, name }
  const [confirmId, setConfirmId] = useState(null)
  useEffect(() => { loadTags(true).catch(() => {}) }, [])

  const patch = async (id, body) => {
    try { await api.patchTag(id, body); await loadTags(true) } catch (e) { toast(e.message) }
  }
  const remove = async (g) => {
    try { await api.deleteTag(g.id); await loadTags(true); setConfirmId(null) } catch (e) { toast(e.message) }
  }
  const commitRename = async () => {
    const current = editing
    setEditing(null)
    if (current && current.name.trim()) await patch(current.id, { name: current.name.trim() })
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      <div style={{ fontSize: 13, color: 'var(--muted)' }}>To make a tag, click "+ tag" on any transaction and type a name. Click a name here to rename it. Deleting a tag takes it off every transaction.</div>
      <div style={{ border: '1px solid var(--line)', borderRadius: 12 }}>
        {tags.map((g, i) => (
          <div key={g.id} style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 12, padding: '8px 14px', borderTop: i ? '1px solid var(--line2)' : 0, fontSize: 14 }}>
            {editing && editing.id === g.id ? (
              <input autoFocus value={editing.name} maxLength={32} onChange={(e) => setEditing({ ...editing, name: e.target.value })}
                onBlur={commitRename} onKeyDown={(e) => { if (e.key === 'Enter') commitRename(); if (e.key === 'Escape') setEditing(null) }}
                aria-label={`Name for tag ${g.name}`} style={{ ...inp, height: 30, flex: '1 1 160px' }} />
            ) : (
              <span style={{ flex: '1 1 160px' }}>
                <button type="button" onClick={() => setEditing({ id: g.id, name: g.name })} title="Rename"
                  style={{ ...pillStyle(g.color), font: 'inherit', fontSize: 13, padding: '2px 10px' }}>
                  <span aria-hidden="true" style={{ width: 7, height: 7, borderRadius: 4, background: g.color }} />{g.name}
                </button>
              </span>
            )}
            <span className="num" style={{ fontSize: 12, color: 'var(--muted)', width: 110 }}>{g.count.toLocaleString()} transaction{g.count === 1 ? '' : 's'}</span>
            <span style={{ display: 'flex', gap: 5 }} role="group" aria-label={`Color for ${g.name}`}>
              {colors.map((c) => (
                <button key={c} type="button" onClick={() => patch(g.id, { color: c })} title="Use this color" aria-label={`Color ${c}`} aria-pressed={c === g.color}
                  style={{ width: 18, height: 18, borderRadius: 9, padding: 0, background: c, border: c === g.color ? '2px solid var(--text)' : '2px solid transparent' }} />
              ))}
            </span>
            {confirmId === g.id ? (
              <>
                <button type="button" onClick={() => remove(g)} style={{ ...ghost, height: 30, padding: '0 10px', fontSize: 12, color: 'var(--neg)' }}>Confirm delete</button>
                <button type="button" onClick={() => setConfirmId(null)} style={{ ...ghost, height: 30, padding: '0 10px', fontSize: 12 }}>Keep</button>
              </>
            ) : (
              <button type="button" onClick={() => setConfirmId(g.id)} style={{ ...ghost, height: 30, padding: '0 10px', fontSize: 12, color: 'var(--neg)' }}>Delete</button>
            )}
          </div>
        ))}
        {!tags.length && <div style={{ padding: 16, fontSize: 14, color: 'var(--muted)' }}>No tags yet. Open "Transactions", click "+ tag" on a row, and type a name.</div>}
      </div>
    </div>
  )
}

export default function Rules({ accounts, focus }) {
  const [tab, setTab] = useState('rules')
  useEffect(() => { if (focus) setTab('rules') }, [focus])
  const groups = useCategories()
  const tabBtn = (k, l) => (
    <button key={k} type="button" onClick={() => setTab(k)} aria-current={tab === k ? 'page' : undefined}
      style={{ height: 34, padding: '0 14px', borderRadius: 8, border: 0, background: tab === k ? 'var(--active)' : 'transparent', color: tab === k ? 'var(--text)' : 'var(--text2)', fontWeight: tab === k ? 600 : 400, fontSize: 13 }}>{l}</button>
  )
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ display: 'flex', gap: 6 }}>{tabBtn('rules', 'Rules')}{tabBtn('categories', 'Categories')}{tabBtn('tags', 'Tags')}</div>
      {tab === 'rules' && <RulesTab accounts={accounts} groups={groups} focus={focus} />}
      {tab === 'categories' && <CategoriesTab groups={groups} />}
      {tab === 'tags' && <TagsTab />}
    </div>
  )
}

import { useEffect, useRef, useState } from 'react'
import { api, money, toast } from '../api'
import { useCategories, categoryLabel, loadCategories } from '../categories'

const inp = { height: 36, borderRadius: 8, border: '1px solid var(--line)', background: 'var(--bg)', color: 'var(--text)', padding: '0 10px', fontSize: 13 }
const btn = { height: 36, padding: '0 14px', borderRadius: 8, border: 0, background: 'var(--accent)', color: '#fff', fontWeight: 600, fontSize: 13 }
const ghost = { ...btn, background: 'transparent', border: '1px solid var(--line)', color: 'var(--text2)', fontWeight: 500 }
const EMPTY = { name: '', priority: 100, enabled: true, conditions: {}, actions: {} }

function describe(rule, groups) {
  const c = rule.conditions, a = rule.actions, parts = []
  if (c.merchant) parts.push(`merchant has "${c.merchant}"`)
  if (c.text) parts.push(`text has "${c.text}"`)
  if (c.amount_min != null && c.amount_max != null) parts.push(`amount ${money(c.amount_min)} to ${money(c.amount_max)}`)
  else if (c.amount_min != null) parts.push(`amount at least ${money(c.amount_min)}`)
  else if (c.amount_max != null) parts.push(`amount at most ${money(c.amount_max)}`)
  if (c.account_id) parts.push('one account')
  if (c.day_min != null || c.day_max != null) parts.push(`day ${c.day_min ?? 1} to ${c.day_max ?? 31}`)
  const acts = []
  if (a.cat_id) acts.push(`file as ${categoryLabel(groups, a.cat_id)}`)
  if (a.display_name) acts.push(`show as "${a.display_name}"`)
  if (a.exclude) acts.push('exclude from totals')
  if (a.transfer) acts.push('mark as transfer')
  return `When ${parts.join(' and ') || 'anything'}: ${acts.join(', ') || 'nothing'}`
}

function RuleEditor({ initial, accounts, groups, onSaved, onCancel }) {
  const [r, setR] = useState(initial)
  const [preview, setPreview] = useState(null)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const timer = useRef(null)
  const setC = (k, v) => setR((x) => ({ ...x, conditions: { ...x.conditions, [k]: v } }))
  const setA = (k, v) => setR((x) => ({ ...x, actions: { ...x.actions, [k]: v } }))

  useEffect(() => {
    clearTimeout(timer.current)
    timer.current = setTimeout(() => {
      api.previewRule({ conditions: r.conditions, actions: r.actions }).then(setPreview).catch(() => setPreview(null))
    }, 300)
    return () => clearTimeout(timer.current)
  }, [r.conditions, r.actions])

  const save = async (applyPast) => {
    setBusy(true); setErr('')
    try {
      const body = { ...r, apply_past: applyPast }
      const out = r.id ? await api.updateRule(r.id, body) : await api.addRule(body)
      if (applyPast) toast(`${out.changed} transaction${out.changed === 1 ? '' : 's'} updated.`)
      onSaved()
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  const c = r.conditions, a = r.actions
  return (
    <div className="card" style={{ padding: 18, display: 'flex', flexDirection: 'column', gap: 14 }}>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10 }}>
        <input value={r.name} onChange={(e) => setR({ ...r, name: e.target.value })} placeholder="Rule name" style={{ ...inp, flex: '2 1 220px' }} />
        <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, color: 'var(--muted)' }}>Priority
          <input type="number" value={r.priority} onChange={(e) => setR({ ...r, priority: Number(e.target.value) || 0 })} style={{ ...inp, width: 80 }} />
        </label>
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
              {g.categories.filter((x) => !x.hidden).map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}
            </optgroup>
          ))}
        </select>
        <input value={a.display_name || ''} onChange={(e) => setA('display_name', e.target.value)} placeholder="Show merchant as" style={inp} />
        <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13 }}><input type="checkbox" checked={!!a.exclude} onChange={(e) => setA('exclude', e.target.checked)} /> Exclude from totals</label>
        <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13 }}><input type="checkbox" checked={!!a.transfer} onChange={(e) => setA('transfer', e.target.checked)} /> Mark as transfer</label>
      </div>
      <div style={{ fontSize: 13, color: 'var(--text2)' }}>
        {preview ? `Matches ${preview.count.toLocaleString()} transaction${preview.count === 1 ? '' : 's'} you have not set by hand` : 'Add a condition to see matches'}
        {preview && preview.sample.length > 0 && (
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

function RulesTab({ accounts, groups }) {
  const [rules, setRules] = useState([])
  const [editing, setEditing] = useState(null)
  const load = () => api.rules().then(setRules).catch((e) => toast(e.message))
  useEffect(() => { load() }, [])

  const toggle = async (r) => {
    try { await api.updateRule(r.id, { ...r, enabled: !r.enabled }); load() } catch (e) { toast(e.message) }
  }
  const remove = async (r) => {
    try { await api.deleteRule(r.id); load() } catch (e) { toast(e.message) }
  }
  const applyAll = async () => {
    try { const out = await api.applyRules(); toast(`${out.changed} transaction${out.changed === 1 ? '' : 's'} updated.`); load() } catch (e) { toast(e.message) }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ fontSize: 13, color: 'var(--muted)' }}>Rules run in priority order, lowest first, on every sync. They never change a category you set by hand.</div>
        <div style={{ display: 'flex', gap: 10 }}>
          <button type="button" onClick={applyAll} style={ghost}>Re-run all rules</button>
          <button type="button" className="press" onClick={() => setEditing({ ...EMPTY })} style={btn}>New rule</button>
        </div>
      </div>
      {editing && !editing.id && <RuleEditor initial={editing} accounts={accounts} groups={groups} onSaved={() => { setEditing(null); load() }} onCancel={() => setEditing(null)} />}
      <div style={{ border: '1px solid var(--line)', borderRadius: 12 }}>
        {rules.map((r, i) => (
          <div key={r.id} style={{ borderTop: i ? '1px solid var(--line2)' : 0 }}>
            {editing && editing.id === r.id ? (
              <div style={{ padding: 10 }}><RuleEditor initial={editing} accounts={accounts} groups={groups} onSaved={() => { setEditing(null); load() }} onCancel={() => setEditing(null)} /></div>
            ) : (
              <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 12, padding: '12px 16px', opacity: r.enabled ? 1 : 0.55 }}>
                <span className="num" style={{ width: 40, fontSize: 12, color: 'var(--muted)' }}>{r.priority}</span>
                <span style={{ flex: '1 1 260px', minWidth: 0 }}>
                  <span style={{ display: 'block', fontSize: 14, fontWeight: 600 }}>{r.name}</span>
                  <span style={{ display: 'block', fontSize: 12, color: 'var(--muted)' }}>{describe(r, groups)}</span>
                </span>
                <span className="num" style={{ fontSize: 12, color: 'var(--muted)' }}>{r.hits} hit{r.hits === 1 ? '' : 's'}</span>
                <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: 'var(--muted)' }}>
                  <input type="checkbox" checked={r.enabled} onChange={() => toggle(r)} /> On
                </label>
                <button type="button" onClick={() => setEditing({ ...r })} style={{ ...ghost, height: 30, padding: '0 10px', fontSize: 12 }}>Edit</button>
                <button type="button" onClick={() => remove(r)} style={{ ...ghost, height: 30, padding: '0 10px', fontSize: 12, color: 'var(--neg)' }}>Delete</button>
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
  const [draft, setDraft] = useState({ name: '', group_name: '', type: 'expense' })
  const [showHidden, setShowHidden] = useState(false)

  const patch = async (id, body) => {
    try { await api.patchCategory(id, body); await loadCategories(true) } catch (e) { toast(e.message) }
  }
  const add = async (e) => {
    e.preventDefault()
    try { await api.addCategory(draft); await loadCategories(true); setDraft({ name: '', group_name: '', type: 'expense' }); toast('Category added.') } catch (x) { toast(x.message) }
  }
  const commitRename = async () => {
    if (editing && editing.name.trim()) await patch(editing.id, { name: editing.name.trim() })
    setEditing(null)
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      <form onSubmit={add} className="card" style={{ padding: 14, display: 'flex', flexWrap: 'wrap', gap: 10, alignItems: 'center' }}>
        <span style={{ fontSize: 13, color: 'var(--muted)' }}>New category</span>
        <input required value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} placeholder="Name" style={{ ...inp, flex: '1 1 160px' }} />
        <input required list="cat-groups-tab" value={draft.group_name} onChange={(e) => setDraft({ ...draft, group_name: e.target.value })} placeholder="Group" style={{ ...inp, flex: '1 1 160px' }} />
        <datalist id="cat-groups-tab">{groups.map((g) => <option key={g.group_name} value={g.group_name} />)}</datalist>
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
                  {editing && editing.id === c.id ? (
                    <input autoFocus value={editing.name} onChange={(e) => setEditing({ ...editing, name: e.target.value })}
                      onBlur={commitRename} onKeyDown={(e) => { if (e.key === 'Enter') commitRename(); if (e.key === 'Escape') setEditing(null) }}
                      style={{ ...inp, height: 30, flex: 1 }} />
                  ) : (
                    <button type="button" onClick={() => c.id !== 'UNCATEGORIZED' && setEditing({ id: c.id, name: c.name })} title="Rename"
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

export default function Rules({ accounts }) {
  const [tab, setTab] = useState('rules')
  const groups = useCategories()
  const tabBtn = (k, l) => (
    <button key={k} type="button" onClick={() => setTab(k)} aria-current={tab === k ? 'page' : undefined}
      style={{ height: 34, padding: '0 14px', borderRadius: 8, border: 0, background: tab === k ? 'var(--active)' : 'transparent', color: tab === k ? 'var(--text)' : 'var(--text2)', fontWeight: tab === k ? 600 : 400, fontSize: 13 }}>{l}</button>
  )
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ display: 'flex', gap: 6 }}>{tabBtn('rules', 'Rules')}{tabBtn('categories', 'Categories')}</div>
      {tab === 'rules' && <RulesTab accounts={accounts} groups={groups} />}
      {tab === 'categories' && <CategoriesTab groups={groups} />}
    </div>
  )
}

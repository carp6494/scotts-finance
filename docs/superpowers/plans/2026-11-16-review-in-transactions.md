# Review Inside Transactions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the review queue from its own page into a temporary box at the top of the Transactions page, with the count on the Transactions sidebar entry.

**Architecture:** Frontend only. `TxList` is used twice on the Transactions page: once in review mode inside a new `NewTransactions` box, once as the full list. A window event, `tx-changed`, carries every row change so both lists stay in step. Review keys turn on only after a click on a row in the box.

**Tech Stack:** React 19, Vite. No frontend test runner exists, so checks are `npm run build` plus a browser pass on a database copy. Backend tests run with pytest to confirm nothing broke.

Spec: `docs/superpowers/specs/2026-11-16-review-in-transactions-design.md`

Commits: none until Scott says so. Before that commit, check the staged list. The repo is public.

---

## File map

- Modify `frontend/src/api.js`: add `txChanged`.
- Modify `frontend/src/components/TxList.jsx`: listen for `tx-changed`, send it on every row change, keys only after a click, `search` and `maxHeight` props, "New" label.
- Create `frontend/src/components/NewTransactions.jsx`: the box.
- Delete `frontend/src/pages/Review.jsx`.
- Modify `frontend/src/pages/Transactions.jsx`: put the box at the top.
- Modify `frontend/src/App.jsx`: drop the Review page, move the count pill.
- Modify `README.md`, `docs/ARCHITECTURE.md`, `docs/superpowers/specs/2026-11-13-tags-review-design.md`.

---

### Task 1: Row change event

**Files:** Modify `frontend/src/api.js:77`

- [ ] **Step 1: Add the helper after `toast`**

```js
// One transaction row changed. detail is { id, fields }, { all: true, fields }, or { reload: true }.
// Every TxList on the page listens, so the new box and the full list stay in step.
export const txChanged = (detail) => window.dispatchEvent(new CustomEvent('tx-changed', { detail }))
```

### Task 2: TxList

**Files:** Modify `frontend/src/components/TxList.jsx`

- [ ] **Step 1: Import and props**

Change the api import to:

```js
import { api, money, fullDate, toast, txChanged } from '../api'
```

Replace the comment and signature at lines 12-13 with:

```js
// review: a "Reviewed" button on each row, and the review keys after a click on a row. unreviewed: only rows that wait for review.
// search: show the search box. maxHeight: the row area scrolls past this height.
export default function TxList({ accountId, catId, tagId, spot, merchant, start, end, spendingOnly = false, showAccount = true, compact = false, refreshKey = 0, onChanged, unreviewed = false, review = false, search = true, maxHeight, empty = 'No transactions yet.' }) {
```

- [ ] **Step 2: Armed state**

After `const [cur, setCur] = useState(0)` add:

```js
  const [armed, setArmed] = useState(false)
```

- [ ] **Step 3: Send row changes through the event**

Replace `setCategory`, `setTags` and `markReviewed` with:

```js
  const setCategory = async (t, newCatId) => {
    try {
      const r = await api.patchTransaction(t.transaction_id, { cat_id: newCatId })
      txChanged({ id: t.transaction_id, fields: r })
      const merchant = t.merchant_name || t.name
      const shown = t.display_name || merchant
      setSuggestion(r.similar > 0 ? { id: t.transaction_id, merchant, shown, catId: newCatId, similar: r.similar } : null)
      onChanged && onChanged()
    } catch (e) { toast(e.message) }
  }

  const setTags = (t, tags) => {
    txChanged({ id: t.transaction_id, fields: { tags } })
    onChanged && onChanged()
  }

  const markReviewed = async (t) => {
    if (!t) return
    try {
      await api.patchTransaction(t.transaction_id, { reviewed: true })
      if (suggestion && suggestion.id === t.transaction_id) setSuggestion(null)
      txChanged({ id: t.transaction_id, fields: { reviewed: 1 } })
      onChanged && onChanged()
    } catch (e) { toast(e.message) }
  }
```

- [ ] **Step 4: Listener, and keys that wait for a click**

Replace from `// Review keys: arrows move...` through the end of the keys `useEffect` with:

```js
  live.current = { rows, cur, armed, q, load, markReviewed }
  useEffect(() => { if (cur > 0 && cur >= rows.length) setCur(Math.max(0, rows.length - 1)) }, [rows.length, cur])

  // Every list hears every row change. A list of waiting rows drops a row once it is reviewed.
  useEffect(() => {
    const onChange = (e) => {
      const { id, all, fields, reload } = e.detail || {}
      const now = live.current
      if (reload) { now.load(0, now.q, Math.max(PAGE, now.rows.length)); return }
      const hit = (x) => all || x.transaction_id === id
      if (unreviewed && fields.reviewed) {
        const gone = now.rows.filter(hit).length
        setRows((prev) => prev.filter((x) => !hit(x)))
        setTotal((n) => Math.max(0, n - gone))
      } else {
        setRows((prev) => prev.map((x) => (hit(x) ? { ...x, ...fields } : x)))
      }
    }
    window.addEventListener('tx-changed', onChange)
    return () => window.removeEventListener('tx-changed', onChange)
  }, [unreviewed])

  // Review keys: arrows move, Enter marks reviewed, C opens the category picker, T opens the tag box, Esc stops.
  // They work only after a click on a row, so until then the arrow keys scroll the page.
  useEffect(() => {
    if (!review) return
    const rowEl = (i) => box.current && box.current.querySelector(`[data-row="${i}"]`)
    const onKey = (e) => {
      const el = e.target
      if (!live.current.armed) return
      if (e.ctrlKey || e.metaKey || e.altKey) return
      if (el && (['INPUT', 'TEXTAREA', 'SELECT'].includes(el.tagName) || el.isContentEditable)) return
      if (e.key === 'Escape') { setArmed(false); return }
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
    // A click elsewhere on the page turns the keys off. Popovers are portals outside <main>, so picking a category keeps them on.
    const onDown = (e) => {
      const el = e.target
      if (box.current && !box.current.contains(el) && el.closest && el.closest('main')) setArmed(false)
    }
    window.addEventListener('keydown', onKey)
    window.addEventListener('mousedown', onDown)
    return () => { window.removeEventListener('keydown', onKey); window.removeEventListener('mousedown', onDown) }
  }, [review])
```

- [ ] **Step 5: Reloads go through the event**

In `makeRule`, replace `load(0, q)` with `txChanged({ reload: true })`.

In the `PlaceLine` `onSaved` handler, replace `load(0, q, Math.max(PAGE, rows.length)); onChanged && onChanged()` with `txChanged({ reload: true }); onChanged && onChanged()`.

- [ ] **Step 6: Search box, scrolling, click to arm, highlight**

Wrap the search `<label>...</label>` in `{search && ( ... )}`.

Change the rows container to:

```jsx
      <div ref={box} style={{ border: '1px solid var(--line)', borderRadius: 12, maxHeight, overflowY: maxHeight ? 'auto' : undefined }}>
```

On the row div, change `onClick` and the highlight:

```jsx
              <div className="rise" data-row={i} onClick={review ? () => { setCur(i); setArmed(true) } : undefined} style={{
                ...
                ...(review && armed && i === cur ? { background: 'var(--hover)', boxShadow: 'inset 3px 0 0 var(--accent)' } : null),
```

- [ ] **Step 7: "New" label in the full list**

After the `Pending` span add:

```jsx
                    {!review && !t.reviewed && !t.pending ? <span style={{ marginLeft: 8, fontSize: 11, fontWeight: 600, color: 'var(--info)' }}>New</span> : null}
```

### Task 3: The box

**Files:** Create `frontend/src/components/NewTransactions.jsx`. Delete `frontend/src/pages/Review.jsx`.

- [ ] **Step 1: Write the component**

```jsx
import { useEffect, useRef, useState } from 'react'
import { api, toast, txChanged } from '../api'
import TxList from './TxList'

const btn = { height: 36, padding: '0 14px', borderRadius: 8, border: 0, background: 'var(--accent)', color: '#fff', fontWeight: 600, fontSize: 13 }
const ghost = { ...btn, background: 'transparent', border: '1px solid var(--line)', color: 'var(--text2)', fontWeight: 500 }
const key = { display: 'inline-block', minWidth: 18, textAlign: 'center', padding: '0 5px', border: '1px solid var(--line3)', borderRadius: 5, fontSize: 11, color: 'var(--text2)', background: 'var(--bg)' }

// New transactions wait here, at the top of Transactions, until the owner clicks "Reviewed". Gone when none wait.
export default function NewTransactions({ waiting, refreshKey, onChanged }) {
  const [confirm, setConfirm] = useState(false)
  const [busy, setBusy] = useState(false)
  const before = useRef(waiting)
  useEffect(() => {
    if (before.current > 0 && waiting === 0) toast('All caught up.')
    before.current = waiting
  }, [waiting])
  if (!waiting) return null

  const markAll = async () => {
    setBusy(true)
    try {
      await api.reviewAll()
      setConfirm(false)
      txChanged({ all: true, fields: { reviewed: 1 } })
      onChanged && onChanged()
    } catch (e) { toast(e.message) } finally { setBusy(false) }
  }

  return (
    <div className="card rise" style={{ padding: 18, borderColor: 'var(--accent)', background: 'color-mix(in srgb, var(--accent) 7%, var(--card))' }}>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
        <h2 style={{ margin: 0, fontSize: 15, fontWeight: 600 }}>{waiting.toLocaleString()} new transaction{waiting === 1 ? '' : 's'}</h2>
        {confirm ? (
          <span style={{ display: 'flex', gap: 8 }}>
            <button type="button" className="press" disabled={busy} onClick={markAll} style={btn}>{busy ? 'Marking...' : `Mark all ${waiting.toLocaleString()} reviewed`}</button>
            <button type="button" onClick={() => setConfirm(false)} style={ghost}>Keep</button>
          </span>
        ) : (
          <button type="button" onClick={() => setConfirm(true)} style={ghost}>Mark all reviewed</button>
        )}
      </div>
      <p style={{ margin: '0 0 14px', fontSize: 13, color: 'var(--muted)' }}>
        Fix the category or add tags, then click "Reviewed". Click a row to use keys:
        {' '}<span style={key}>↑</span> <span style={key}>↓</span> move, <span style={key}>Enter</span> reviewed, <span style={key}>C</span> category, <span style={key}>T</span> tag, <span style={key}>Esc</span> stop.
      </p>
      <TxList review unreviewed search={false} maxHeight={640} refreshKey={refreshKey} onChanged={onChanged} empty="Nothing waiting." />
    </div>
  )
}
```

- [ ] **Step 2: Delete the old page**

Run: `git rm frontend/src/pages/Review.jsx`

### Task 4: Transactions page

**Files:** Modify `frontend/src/pages/Transactions.jsx`

- [ ] **Step 1: Import**

```js
import NewTransactions from '../components/NewTransactions'
```

- [ ] **Step 2: Box first in the page column**

Right after `<div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>` add:

```jsx
      <NewTransactions waiting={s.unreviewed || 0} refreshKey={refreshKey} onChanged={onChanged} />
```

### Task 5: Sidebar

**Files:** Modify `frontend/src/App.jsx`

- [ ] **Step 1:** Delete `import Review from './pages/Review'`.
- [ ] **Step 2:** Change `PAGES` to `[['dashboard', 'Dashboard'], ['transactions', 'Transactions'], ['map', 'Map'], ['rules', 'Rules'], ['debt', 'Debt payoff']]`.
- [ ] **Step 3:** In the sidebar pill condition change `k === 'review'` to `k === 'transactions'`.
- [ ] **Step 4:** Delete the line `{page === 'review' && <Review ... />}`.

### Task 6: Docs

- [ ] **Step 1:** `README.md` line 15: replace `- Review page: new transactions wait there until you check them` with `- New transactions wait in a box at the top of Transactions until you check them`.
- [ ] **Step 2:** `docs/ARCHITECTURE.md` review queue bullet: replace the sentence about `pages/Review.jsx` with `` `components/NewTransactions.jsx` shows the queue at the top of the Transactions page. Its keys work after a click on a row. The sidebar count sits on Transactions. `` Then run `grep -n "Review.jsx" docs/ARCHITECTURE.md` and fix any other mention, such as the file tree.
- [ ] **Step 3:** `docs/superpowers/specs/2026-11-13-tags-review-design.md`: under `## Review queue` add the line `Changed on 2026-11-16: the queue moved into the Transactions page. See 2026-11-16-review-in-transactions-design.md.`

### Task 7: Check

- [ ] **Step 1: Build**

Run: `cd frontend && npm run build`
Expected: builds with no errors.

- [ ] **Step 2: Backend tests**

Run: `.venv\Scripts\python -m pytest backend/tests -q`
Expected: 170 passed.

- [ ] **Step 3: Leftover references**

Run: `grep -rn "pages/Review\|'review'" frontend/src`
Expected: no output.

- [ ] **Step 4: Browser pass on a copy**

Copy `data/finance.db` with its `-wal` and `-shm` files to the scratchpad. Set the copy's newest five posted rows to `reviewed=0`. Run uvicorn on port 8799 with `FINANCE_DB` set to the copy and empty Plaid keys. Open `http://127.0.0.1:8799` in Chrome. Check each item under "Checking" in the spec, in dark and light themes. Then stop the server and delete the copy.

### Task 8: Hand back

- [ ] **Step 1:** Tell Scott what changed and that `start.bat` needs no restart for frontend-only changes once `frontend/dist` is rebuilt. A browser refresh loads it.
- [ ] **Step 2:** On Scott's word, run `git status`, check the staged list holds only the files in the file map plus the spec and plan, then commit and push.

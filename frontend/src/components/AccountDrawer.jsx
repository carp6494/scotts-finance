import { useEffect, useState } from 'react'
import { motion, AnimatePresence } from 'motion/react'
import { api, money, shortDate, titleCase } from '../api'
import Logo from './Logo'
import TxList from './TxList'
import ConnectButton from './ConnectButton'

const SKIP = new Set(['account_id', 'kind', 'aprs', 'property_address', 'interest_rate', 'loan_status', 'pslf_status', 'repayment_plan', 'servicer_address'])

function fmt(k, v) {
  if (v === null || v === undefined || v === '') return null
  if (typeof v === 'boolean') return v ? 'Yes' : 'No'
  if (typeof v === 'number') {
    if (/amount|balance|payment|principal|paid|fee|limit|interest_paid|escrow/.test(k)) return money(v)
    if (/percentage|rate/.test(k)) return v + '%'
    return String(v)
  }
  if (/date/.test(k)) return String(v)
  if (typeof v === 'object') return null
  return String(v)
}

function Section({ title, rows, delay = 0 }) {
  const shown = rows.filter((r) => r && r[1] !== null && r[1] !== undefined && r[1] !== '')
  if (!shown.length) return null
  return (
    <section className="rise" style={{ animationDelay: `${delay}s` }}>
      <h3 style={{ margin: '0 0 8px', fontSize: 12, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '.06em', color: 'var(--muted)' }}>{title}</h3>
      <div style={{ border: '1px solid var(--line)', borderRadius: 12, overflow: 'hidden' }}>
        {shown.map(([k, v, c], i) => (
          <div key={k + i} style={{ display: 'flex', justifyContent: 'space-between', gap: 12, padding: '10px 14px', borderTop: i ? '1px solid var(--line2)' : 0, fontSize: 14 }}>
            <span style={{ color: 'var(--text2)' }}>{k}</span>
            <span className="num" style={{ fontWeight: 600, textAlign: 'right', color: c || 'var(--text)' }}>{v}</span>
          </div>
        ))}
      </div>
    </section>
  )
}

export default function AccountDrawer({ accountId, onClose, onChanged, onTotals }) {
  const [a, setA] = useState(null)
  const [err, setErr] = useState('')
  const [homeValue, setHomeValue] = useState('')
  const [bal, setBal] = useState({ current: '', limit_amt: '' })
  const [txKey, setTxKey] = useState(0)
  const [importMsg, setImportMsg] = useState('')
  const [flip, setFlip] = useState(false)

  useEffect(() => {
    if (!accountId) return
    setA(null)
    api.account(accountId).then((d) => { setA(d); setHomeValue(d.current ?? ''); setBal({ current: d.current ?? '', limit_amt: d.limit_amt ?? '' }); setImportMsg('') }).catch((e) => setErr(e.message))
  }, [accountId])

  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const l = a?.liability || {}
  const isCard = a?.type === 'credit'
  const isHome = a?.type === 'property'
  const util = isCard && a.limit_amt ? Math.round((a.current / a.limit_amt) * 100) : null

  const sections = []
  if (a) {
    if (isCard) {
      sections.push(['Statement', [
        ['Last statement balance', money(l.last_statement_balance)],
        ['Statement date', l.last_statement_issue_date && shortDate(l.last_statement_issue_date)],
        ['Minimum payment', money(l.minimum_payment_amount)],
        ['Payment due', l.next_payment_due_date && shortDate(l.next_payment_due_date), 'var(--warn)'],
        ['Last payment', l.last_payment_amount != null ? `${money(l.last_payment_amount)}${l.last_payment_date ? ' on ' + shortDate(l.last_payment_date) : ''}` : null],
        ['Overdue', l.is_overdue === undefined ? null : (l.is_overdue ? 'Yes' : 'No'), l.is_overdue ? 'var(--neg)' : 'var(--pos)'],
      ]])
      sections.push(['Credit', [
        ['Credit limit', money(a.limit_amt)],
        ['Available credit', money(a.available)],
        ...(l.aprs || []).map((p) => [titleCase(p.apr_type), `${p.apr_percentage}%`]),
        (l.aprs || []).length ? null : ['Purchase APR', a.apr != null ? `${a.apr}%${a.apr_source === 'you' ? ' (you entered)' : ''}` : 'Not sent by bank, add it on Debt payoff', a.apr != null ? null : 'var(--warn)'],
        ['Cash advance limit', money(l.cash_advance_limit)],
      ]])
    } else if (isHome) {
      const m = a.mortgage || {}
      const owed = m.balance || 0
      sections.push(['Equity', [
        ['Estimated value', money(a.current)],
        ['Mortgage balance', owed ? '-' + money(owed) : 'Not linked', 'var(--orange)'],
        ['Equity', money((a.current || 0) - owed), 'var(--pos)'],
        ['Loan to value', owed && a.current ? Math.round((owed / a.current) * 100) + '%' : null],
      ]])
      if (a.mortgage) {
        sections.push(['Mortgage', [
          ['Interest rate', m.interest_rate?.percentage != null ? `${m.interest_rate.percentage}% ${m.interest_rate.type || ''}` : null],
          ['Monthly payment', money(m.next_monthly_payment)],
          ['Next payment due', m.next_payment_due_date && shortDate(m.next_payment_due_date)],
          ['Escrow balance', money(m.escrow_balance)],
          ['PMI', m.has_pmi === undefined ? null : (m.has_pmi ? 'Yes' : 'No')],
          ['Interest paid this year', money(m.ytd_interest_paid)],
          ['Principal paid this year', money(m.ytd_principal_paid)],
          ['Original loan', money(m.origination_principal_amount)],
          ['Maturity date', m.maturity_date],
        ]])
      }
    } else {
      sections.push(['Balances', [
        ['Available', money(a.available)],
        ['Current', money(a.current)],
        ['Credit limit', a.limit_amt ? money(a.limit_amt) : null],
      ]])
    }
    if (a.activity && !isHome) {
      const act = a.activity
      const monthName = new Date().toLocaleString('en-US', { month: 'long' })
      const title = act.basis === 'statement' ? 'Since last statement' : `${monthName} so far`
      sections.push([title, [
        act.basis === 'statement' ? ['Statement date', shortDate(act.statement_date)] : ['No statement date from this account', 'Showing the calendar month', 'var(--muted)'],
        ['Money in', money(act.in_amt), 'var(--pos)'],
        ['Money out', money(act.out_amt ? -act.out_amt : 0)],
      ]])
    }
    if (a.holdings?.length) {
      sections.push(['Holdings', a.holdings.map((h) => [h.ticker ? `${h.ticker}, ${h.name}` : h.name, money(h.value)])])
    }
    // Everything else the bank sent for this liability, so nothing is hidden
    const extra = Object.entries(l).filter(([k]) => !SKIP.has(k) && !['last_statement_balance', 'last_statement_issue_date', 'minimum_payment_amount', 'next_payment_due_date', 'last_payment_amount', 'last_payment_date', 'is_overdue', 'cash_advance_limit'].includes(k))
      .map(([k, v]) => [titleCase(k), fmt(k, v)])
    if (extra.length) sections.push(['More from your bank', extra])
    sections.push(['Account', [
      ['Institution', a.institution],
      ['Official name', a.official_name],
      ['Account ending', a.mask],
      ['Type', [titleCase(a.type), titleCase(a.subtype)].filter(Boolean).join(', ')],
      ['Last synced', a.last_sync ? new Date(a.last_sync + 'Z').toLocaleString() : (a.manual ? 'Manual' : null)],
    ]])
  }

  const isManualAcct = Boolean(a?.manual) && !isHome
  const saveBal = async () => {
    const body = { current: Number(bal.current) || 0, limit_amt: bal.limit_amt === '' ? null : Number(bal.limit_amt) }
    await api.setBalance(a.account_id, body)
    const d = await api.account(a.account_id); setA(d)
    onChanged && onChanged()
  }
  const onFile = async (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    try {
      const r = await api.importCsv(a.account_id, { csv: await file.text(), flip })
      setImportMsg(`Imported ${r.added} new transactions${r.duplicates ? `, skipped ${r.duplicates} already here` : ''}.`)
      setTxKey((k) => k + 1)
      onChanged && onChanged()
    } catch (err) { setImportMsg(err.message) }
    e.target.value = ''
  }

  const saveHome = async () => {
    await api.updateManual(a.account_id, { name: a.name, value: Number(homeValue) || 0, linked_account_id: a.linked_account_id })
    setA({ ...a, current: Number(homeValue) || 0 })
    onChanged && onChanged()
  }

  return (
    <AnimatePresence>
      {accountId && (
        <div style={{ position: 'fixed', inset: 0, zIndex: 50 }}>
          <motion.button type="button" aria-label="Close account details" onClick={onClose}
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            style={{ position: 'absolute', inset: 0, border: 0, background: 'var(--scrim)' }} />
          <motion.aside aria-label="Account details"
            initial={{ x: 60, opacity: 0 }} animate={{ x: 0, opacity: 1 }} exit={{ x: 60, opacity: 0 }}
            transition={{ type: 'spring', stiffness: 260, damping: 30 }}
            style={{ position: 'absolute', top: 0, right: 0, bottom: 0, width: 'min(520px, 100%)', overflowY: 'auto', background: 'var(--card)', borderLeft: '1px solid var(--line)', boxShadow: '-20px 0 50px rgba(0,0,0,.35)', padding: 24, display: 'flex', flexDirection: 'column', gap: 18 }}>
            {err && <div style={{ color: 'var(--neg)' }}>{err}</div>}
            {!a && !err && <div style={{ color: 'var(--muted)' }}>Loading...</div>}
            {a && (
              <>
                <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
                  <Logo src={a.logo} name={a.name} size={48} home={isHome} />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <h2 style={{ margin: 0, fontSize: 19, fontWeight: 700 }}>{a.official_name || a.name}</h2>
                    <div style={{ fontSize: 13, color: 'var(--muted)' }}>{a.institution}{a.mask ? `, ending ${a.mask}` : ''}</div>
                  </div>
                  <button type="button" onClick={onClose} aria-label="Close" style={{ width: 40, height: 40, borderRadius: 8, border: '1px solid var(--line)', background: 'transparent', color: 'var(--text)', fontSize: 18 }}>&#215;</button>
                </div>
                {a.item_status === 'needs_reconnect' && (
                  <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: 12, borderRadius: 10, border: '1px solid var(--warn)', color: 'var(--warn)', fontSize: 13 }}>
                    <span style={{ flex: 1 }}>This bank needs you to log in again.</span>
                    <ConnectButton itemId={a.item_id} label="Reconnect" small onDone={() => onChanged && onChanged()} />
                  </div>
                )}
                <div style={{ background: 'var(--bg)', border: '1px solid var(--line)', borderRadius: 12, padding: 16 }}>
                  <div style={{ fontSize: 12, color: 'var(--muted)' }}>{isCard ? 'Current balance owed' : isHome ? 'Estimated value' : 'Balance'}</div>
                  <div className="num" style={{ fontSize: 32, fontWeight: 700, letterSpacing: '-0.02em', color: a.signed_balance < 0 ? 'var(--orange)' : 'var(--text)' }}>{money(a.signed_balance)}</div>
                  {util !== null && (
                    <>
                      <div style={{ marginTop: 10, display: 'flex', justifyContent: 'space-between', fontSize: 12, color: 'var(--muted)' }}>
                        <span>Credit used</span><span style={{ fontWeight: 600, color: util > 30 ? 'var(--warn)' : 'var(--pos)' }}>{util}% of {money(a.limit_amt, false)}</span>
                      </div>
                      <div style={{ marginTop: 6, height: 8, borderRadius: 99, background: 'var(--line)', overflow: 'hidden' }}>
                        <div style={{ height: '100%', width: `${Math.min(util, 100)}%`, background: util > 30 ? 'var(--warn)' : 'var(--pos)', borderRadius: 99, transformOrigin: 'left', animation: 'growX .9s cubic-bezier(.2,.8,.2,1) both .2s' }} />
                      </div>
                    </>
                  )}
                  {isHome && (
                    <div style={{ marginTop: 12, display: 'flex', gap: 8 }}>
                      <label style={{ flex: 1, display: 'flex', alignItems: 'center', gap: 6, border: '1px solid var(--line)', borderRadius: 8, padding: '0 10px', height: 38, background: 'var(--card)' }}>
                        <span style={{ fontSize: 12, color: 'var(--muted)' }}>Value $</span>
                        <input type="number" value={homeValue} onChange={(e) => setHomeValue(e.target.value)} style={{ flex: 1, background: 'transparent', border: 0, outline: 'none', color: 'var(--text)', fontSize: 14 }} />
                      </label>
                      <button type="button" onClick={saveHome} className="press" style={{ height: 38, padding: '0 14px', borderRadius: 8, border: 0, background: 'var(--accent)', color: '#fff', fontWeight: 600, fontSize: 13 }}>Save</button>
                    </div>
                  )}
                </div>
                {isManualAcct && (
                  <section className="rise" style={{ animationDelay: '.05s', border: '1px solid var(--line)', borderRadius: 12, padding: 14, display: 'flex', flexDirection: 'column', gap: 10 }}>
                    <div style={{ fontSize: 12, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '.06em', color: 'var(--muted)' }}>Manual account: update from the bank's site</div>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                      <label style={{ display: 'flex', alignItems: 'center', gap: 6, border: '1px solid var(--line)', borderRadius: 8, padding: '0 10px', height: 38, background: 'var(--bg)', fontSize: 12, color: 'var(--muted)' }}>{isCard ? 'Owed $' : 'Balance $'}
                        <input type="number" value={bal.current} onChange={(e) => setBal({ ...bal, current: e.target.value })} style={{ width: 90, background: 'transparent', border: 0, outline: 'none', color: 'var(--text)', fontSize: 14 }} /></label>
                      {isCard && <label style={{ display: 'flex', alignItems: 'center', gap: 6, border: '1px solid var(--line)', borderRadius: 8, padding: '0 10px', height: 38, background: 'var(--bg)', fontSize: 12, color: 'var(--muted)' }}>Limit $
                        <input type="number" value={bal.limit_amt} onChange={(e) => setBal({ ...bal, limit_amt: e.target.value })} style={{ width: 90, background: 'transparent', border: 0, outline: 'none', color: 'var(--text)', fontSize: 14 }} /></label>}
                      <button type="button" onClick={saveBal} className="press" style={{ height: 38, padding: '0 14px', borderRadius: 8, border: 0, background: 'var(--accent)', color: '#fff', fontWeight: 600, fontSize: 13 }}>Save balance</button>
                    </div>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, alignItems: 'center' }}>
                      <label className="press" style={{ height: 38, padding: '0 14px', borderRadius: 8, border: '1px solid var(--line)', background: 'var(--bg)', color: 'var(--text)', fontSize: 13, display: 'inline-flex', alignItems: 'center', cursor: 'pointer' }}>
                        Import CSV from bank<input type="file" accept=".csv,text/csv" onChange={onFile} style={{ display: 'none' }} />
                      </label>
                      <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: 'var(--muted)' }}>
                        <input type="checkbox" checked={flip} onChange={(e) => setFlip(e.target.checked)} /> File shows purchases as negative
                      </label>
                    </div>
                    {importMsg && <div style={{ fontSize: 13, color: 'var(--info)' }}>{importMsg}</div>}
                  </section>
                )}
                {sections.map(([t, rows], i) => <Section key={t} title={t} rows={rows} delay={0.08 + i * 0.06} />)}
                {!isHome && (
                  <section className="rise" style={{ animationDelay: '.3s' }}>
                    <h3 style={{ margin: '0 0 8px', fontSize: 12, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '.06em', color: 'var(--muted)' }}>All transactions</h3>
                    <TxList accountId={a.account_id} showAccount={false} compact refreshKey={txKey} onChanged={onTotals} />
                  </section>
                )}
              </>
            )}
          </motion.aside>
        </div>
      )}
    </AnimatePresence>
  )
}

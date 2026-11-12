import { useCallback, useEffect, useState } from 'react'
import { motion, AnimatePresence } from 'motion/react'
import { api } from './api'
import ConnectButton from './components/ConnectButton'
import AccountDrawer from './components/AccountDrawer'
import Dashboard from './pages/Dashboard'
import Transactions from './pages/Transactions'
import Lock from './components/Lock'
import Debt from './pages/Debt'

function useTheme() {
  const [mode, setMode] = useState(() => { try { return localStorage.getItem('theme') || 'system' } catch { return 'system' } })
  useEffect(() => {
    const mq = window.matchMedia('(prefers-color-scheme: dark)')
    const apply = () => {
      const dark = mode === 'dark' || (mode === 'system' && mq.matches)
      document.documentElement.setAttribute('data-theme', dark ? 'dark' : 'light')
    }
    apply()
    mq.addEventListener('change', apply)
    try { localStorage.setItem('theme', mode) } catch { /* ignore */ }
    return () => mq.removeEventListener('change', apply)
  }, [mode])
  return [mode, setMode]
}

const PAGES = [['dashboard', 'Dashboard'], ['transactions', 'Transactions'], ['debt', 'Debt payoff']]

export default function App() {
  const [authed, setAuthed] = useState(null)
  useEffect(() => {
    const check = () => api.authState().then(setAuthed).catch(() => setAuthed({ enrolled: true, signed_in: false }))
    check()
    window.addEventListener('auth-required', check)
    return () => window.removeEventListener('auth-required', check)
  }, [])
  if (!authed) return null
  if (!authed.signed_in) return <Lock enrolled={authed.enrolled} onUnlocked={() => setAuthed({ enrolled: true, signed_in: true })} />
  return <Main onLogout={async () => { await api.logout(); setAuthed({ enrolled: true, signed_in: false }) }} />
}

function Main({ onLogout }) {
  const [page, setPage] = useState('dashboard')
  const [theme, setTheme] = useTheme()
  const [status, setStatus] = useState(null)
  const [summary, setSummary] = useState(null)
  const [accounts, setAccounts] = useState([])
  const [openId, setOpenId] = useState(null)
  const [syncing, setSyncing] = useState(false)
  const [toast, setToast] = useState('')
  const [refreshKey, setRefreshKey] = useState(0)

  const refresh = useCallback(async () => {
    const [st, sm, ac] = await Promise.all([api.status(), api.summary(), api.accounts()])
    setStatus(st); setSummary(sm); setAccounts(ac); setRefreshKey((k) => k + 1)
  }, [])

  useEffect(() => { refresh().catch((e) => setToast(e.message)) }, [refresh])
  useEffect(() => { if (toast) { const t = setTimeout(() => setToast(''), 5000); return () => clearTimeout(t) } }, [toast])
  useEffect(() => {
    const onToast = (e) => setToast(e.detail)
    window.addEventListener('toast', onToast)
    return () => window.removeEventListener('toast', onToast)
  }, [])

  const sync = async () => {
    setSyncing(true)
    try {
      const r = await api.sync()
      const errs = r.results.filter((x) => x.error)
      const added = r.results.reduce((t, x) => t + (x.added || 0), 0)
      setToast(errs.length ? `Synced with ${errs.length} problem(s): ${errs[0].message}` : `Synced. ${added} new transactions.`)
      await refresh()
    } catch (e) { setToast(e.message) } finally { setSyncing(false) }
  }

  const needsReconnect = (status?.items || []).filter((i) => i.status === 'needs_reconnect')

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexWrap: 'wrap' }}>
      <nav aria-label="Main" style={{ flex: '1 1 220px', maxWidth: 240, padding: '24px 16px', borderRight: '1px solid var(--line)', display: 'flex', flexDirection: 'column', gap: 4 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '0 8px 24px' }}>
          <img src="/brand/app-icon.png" alt="" style={{ width: 32, height: 32, borderRadius: 9 }} />
          <span style={{ fontWeight: 700, fontSize: 17 }}>Scott's Finance</span>
        </div>
        {PAGES.map(([k, l]) => (
          <button key={k} type="button" onClick={() => setPage(k)} aria-current={page === k ? 'page' : undefined}
            style={{ textAlign: 'left', padding: '10px 12px', borderRadius: 8, border: 0, background: page === k ? 'var(--active)' : 'transparent', color: page === k ? 'var(--text)' : 'var(--text2)', fontWeight: page === k ? 600 : 400, fontSize: 14 }}>
            {l}
          </button>
        ))}
        <button type="button" onClick={onLogout} style={{ marginTop: 'auto', textAlign: 'left', padding: '10px 12px', borderRadius: 8, border: 0, background: 'transparent', color: 'var(--text2)', fontSize: 14 }}>Sign out</button>
        <div style={{ fontSize: 12, color: 'var(--muted)', padding: '0 12px' }}>
          Plaid: {status ? (status.configured ? status.env : 'not set up') : '...'}
        </div>
      </nav>

      <main style={{ flex: '999 1 560px', minWidth: 0, padding: '28px 32px 48px', display: 'flex', flexDirection: 'column', gap: 20 }}>
        <header style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
          <h1 style={{ margin: 0, fontSize: 28, fontWeight: 700, letterSpacing: '-0.02em' }}>{PAGES.find((p) => p[0] === page)[1]}</h1>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, alignItems: 'center' }}>
            <div role="group" aria-label="Theme" style={{ display: 'flex', border: '1px solid var(--line)', borderRadius: 8, overflow: 'hidden', height: 40, background: 'var(--card)' }}>
              {['light', 'dark', 'system'].map((m) => (
                <button key={m} type="button" aria-pressed={theme === m} onClick={() => setTheme(m)}
                  style={{ padding: '0 12px', border: 0, background: theme === m ? 'var(--accent)' : 'transparent', color: theme === m ? '#fff' : 'var(--text2)', fontSize: 13, fontWeight: 500 }}>
                  {m[0].toUpperCase() + m.slice(1)}
                </button>
              ))}
            </div>
            <button type="button" className="press" onClick={sync} disabled={syncing || !status?.items?.length}
              style={{ height: 40, padding: '0 14px', borderRadius: 8, border: '1px solid var(--line)', background: 'var(--card)', color: 'var(--text)', fontSize: 13, display: 'flex', alignItems: 'center', gap: 8, opacity: status?.items?.length ? 1 : 0.5 }}>
              <svg className={syncing ? 'spin' : ''} width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" aria-hidden="true"><path d="M21 12a9 9 0 1 1-3-6.7L21 8" /><path d="M21 3v5h-5" /></svg>
              {syncing ? 'Syncing' : 'Sync now'}
            </button>
            <ConnectButton onDone={() => { setToast('Account connected. Pulling up to 2 years of transactions.'); refresh() }} onError={setToast} />
          </div>
        </header>

        {status && !status.configured && (
          <div className="card" style={{ padding: 16, borderColor: 'var(--warn)', fontSize: 14 }}>
            <strong>Plaid isn't set up yet.</strong> Open the <code>.env</code> file in the app folder, paste your Plaid client ID and production secret, then restart the app.
          </div>
        )}
        {needsReconnect.map((i) => (
          <div key={i.item_id} className="card" style={{ padding: 14, borderColor: 'var(--warn)', display: 'flex', alignItems: 'center', gap: 12, fontSize: 14 }}>
            <span style={{ flex: 1 }}>{i.institution_name} needs you to log in again.</span>
            <ConnectButton itemId={i.item_id} label="Reconnect" small onDone={refresh} onError={setToast} />
          </div>
        ))}

        <AnimatePresence mode="wait">
          <motion.div key={page} initial={{ opacity: 0, x: 24 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -24 }} transition={{ duration: 0.28, ease: 'easeOut' }}>
            {page === 'dashboard' && <Dashboard summary={summary} accounts={accounts} onOpen={setOpenId} onChanged={refresh} />}
            {page === 'transactions' && <Transactions summary={summary} accounts={accounts} refreshKey={refreshKey} onChanged={refresh} />}
            {page === 'debt' && <Debt />}
          </motion.div>
        </AnimatePresence>
      </main>

      <AccountDrawer accountId={openId} onClose={() => setOpenId(null)} onChanged={refresh} />

      <AnimatePresence>
        {toast && (
          <motion.div role="status" initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 20 }}
            style={{ position: 'fixed', right: 24, bottom: 24, maxWidth: 380, background: 'var(--card)', border: '1px solid var(--accent)', borderRadius: 12, padding: '12px 16px', boxShadow: '0 12px 40px rgba(0,0,0,.35)', fontSize: 14, zIndex: 60 }}>
            {toast}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

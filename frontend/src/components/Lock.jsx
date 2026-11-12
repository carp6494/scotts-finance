import { useEffect, useState } from 'react'
import { api } from '../api'

// Sign-in screen: an authenticator code is required before anything (including Plaid Link) opens.
export default function Lock({ enrolled, onUnlocked }) {
  const [setup, setSetup] = useState(null)
  const [code, setCode] = useState('')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (!enrolled) api.authSetup().then(setSetup).catch((e) => setErr(e.message))
  }, [enrolled])

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true); setErr('')
    try { await api.authVerify(code); onUnlocked() } catch (x) { setErr(x.message); setCode('') } finally { setBusy(false) }
  }

  return (
    <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24 }}>
      <form onSubmit={submit} className="card rise" style={{ width: 'min(420px, 100%)', padding: 28, display: 'flex', flexDirection: 'column', gap: 16 }}>
        <img src="/brand/app-icon.png" alt="" style={{ width: 56, height: 56, borderRadius: 14 }} />
        <h1 style={{ margin: 0, fontSize: 22 }}>{enrolled ? "Sign in to Scott's Finance" : 'Set up your authenticator'}</h1>
        {!enrolled && (
          <>
            <p style={{ margin: 0, fontSize: 14, color: 'var(--text2)' }}>Scan this code with an authenticator app (Microsoft Authenticator, Google Authenticator or 1Password), then enter the 6-digit code it shows.</p>
            {setup && (
              <>
                <div style={{ background: '#fff', borderRadius: 12, padding: 12, width: 220, alignSelf: 'center' }} dangerouslySetInnerHTML={{ __html: setup.svg }} />
                <div style={{ fontSize: 12, color: 'var(--muted)' }}>Can't scan? Enter this key: <code style={{ color: 'var(--text)' }}>{setup.secret}</code></div>
              </>
            )}
          </>
        )}
        <label style={{ display: 'flex', flexDirection: 'column', gap: 6, fontSize: 13, color: 'var(--muted)' }}>6-digit code
          <input value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))} inputMode="numeric" autoComplete="one-time-code" autoFocus
            style={{ height: 48, borderRadius: 10, border: '1px solid var(--line3)', background: 'var(--bg)', color: 'var(--text)', fontSize: 24, letterSpacing: '.3em', textAlign: 'center' }} />
        </label>
        {err && <div style={{ fontSize: 13, color: 'var(--neg)' }}>{err}</div>}
        <button type="submit" disabled={busy || code.length !== 6} className="press"
          style={{ height: 44, borderRadius: 10, border: 0, background: 'var(--accent)', color: '#fff', fontWeight: 600, fontSize: 15, opacity: code.length === 6 ? 1 : 0.6 }}>
          {busy ? 'Checking...' : enrolled ? 'Sign in' : 'Finish setup'}
        </button>
      </form>
    </div>
  )
}

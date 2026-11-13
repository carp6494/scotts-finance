import { useEffect, useState } from 'react'
import { api, toast } from '../api'

const SESSION_LABELS = { 12: '12 hours', 24: '1 day', 168: '7 days', 720: '30 days' }
const THEMES = ['light', 'dark', 'system']

// One row per setting: name and help text on the left, the control on the right.
function Row({ title, help, children }) {
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', justifyContent: 'space-between', gap: 16, padding: '16px 20px', borderTop: '1px solid var(--line)' }}>
      <div style={{ flex: '1 1 260px', minWidth: 0 }}>
        <div style={{ fontSize: 15, fontWeight: 600 }}>{title}</div>
        <div style={{ fontSize: 13, color: 'var(--text2)', marginTop: 4 }}>{help}</div>
      </div>
      {children}
    </div>
  )
}

function Section({ title, children }) {
  return (
    <section className="card" style={{ maxWidth: 720 }}>
      <h2 style={{ margin: 0, padding: '16px 20px', fontSize: 16, fontWeight: 700 }}>{title}</h2>
      {children}
    </section>
  )
}

export default function Settings({ theme, setTheme }) {
  const [session, setSession] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => { api.sessionSetting().then(setSession).catch((e) => setError(e.message)) }, [])

  const changeSession = async (hours) => {
    try {
      setSession(await api.setSessionSetting(hours))
      toast(`You will stay signed in for ${SESSION_LABELS[hours]}, restarts included.`)
    } catch (e) { toast(e.message) }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <Section title="Appearance">
        <Row title="Theme" help="System follows the Windows light or dark setting.">
          <div role="group" aria-label="Theme" style={{ display: 'flex', border: '1px solid var(--line)', borderRadius: 8, overflow: 'hidden', height: 40, background: 'var(--card)' }}>
            {THEMES.map((m) => (
              <button key={m} type="button" aria-pressed={theme === m} onClick={() => setTheme(m)}
                style={{ padding: '0 14px', border: 0, background: theme === m ? 'var(--accent)' : 'transparent', color: theme === m ? '#fff' : 'var(--text2)', fontSize: 13, fontWeight: 500 }}>
                {m[0].toUpperCase() + m.slice(1)}
              </button>
            ))}
          </div>
        </Row>
      </Section>

      <Section title="Sign-in">
        <Row title="Stay signed in for" help="How long before the app asks for a new authenticator code. Restarting the app does not sign you out. The longest is 30 days.">
          {session ? (
            <select aria-label="Stay signed in for" value={session.hours} onChange={(e) => changeSession(Number(e.target.value))}
              style={{ height: 40, minWidth: 140, padding: '0 10px', borderRadius: 8, border: '1px solid var(--line)', background: 'var(--card)', color: 'var(--text)', fontSize: 14 }}>
              {session.choices.map((h) => <option key={h} value={h}>{SESSION_LABELS[h] || `${h} hours`}</option>)}
            </select>
          ) : (
            <span role={error ? 'alert' : undefined} style={{ fontSize: 13, color: error ? 'var(--warn)' : 'var(--muted)', maxWidth: 260 }}>
              {error ? 'This setting did not load. Close the app window that start.bat opened, then double-click start.bat again.' : 'Loading'}
            </span>
          )}
        </Row>
      </Section>
    </div>
  )
}

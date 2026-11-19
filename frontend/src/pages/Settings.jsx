import { useEffect, useState } from 'react'
import { api, toast, download } from '../api'

const SESSION_LABELS = { 12: '12 hours', 24: '1 day', 168: '7 days', 720: '30 days' }
const THEMES = ['light', 'dark', 'system']
const MAP_ROWS = [
  ['usgs', 'Satellite photos', 'For the Satellite and Hybrid styles. From the U.S. Geological Survey.'],
  ['terrain', 'Terrain elevation', 'For hills, the Terrain style and the Terrain height slider. From the Terrain Tiles open data set hosted by Amazon Web Services.'],
  ['buildings', '3D buildings', 'Building shapes when you zoom into a city. From OpenFreeMap, built on OpenStreetMap data.'],
]

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

const FIELD = { height: 36, padding: '0 10px', borderRadius: 8, border: '1px solid var(--line)', background: 'var(--card)', color: 'var(--text)', fontSize: 13 }
const BUTTON = { height: 36, padding: '0 14px', borderRadius: 8, border: 0, background: 'var(--accent)', color: '#fff', fontWeight: 600, fontSize: 13 }

function qs(p) {
  const s = new URLSearchParams(Object.entries(p).filter(([, v]) => v)).toString()
  return s ? '?' + s : ''
}

// Files to take out of the app. The dates at the top apply to the first two rows.
function ExportSection() {
  const thisYear = new Date().getFullYear()
  const [start, setStart] = useState(`${thisYear}-01-01`)
  const [end, setEnd] = useState('')
  const [accounts, setAccounts] = useState([])
  const [account, setAccount] = useState('')
  const [fmt, setFmt] = useState('qbo')
  const [year, setYear] = useState(thisYear - 1)
  useEffect(() => {
    api.accounts().then((list) => {
      const real = list.filter((a) => ['depository', 'credit', 'loan'].includes(a.type))
      setAccounts(real)
      setAccount((cur) => cur || real[0]?.account_id || '')
    }).catch(() => {})
  }, [])
  const get = async (url) => {
    try { toast(`Downloaded ${await download(url)}.`) } catch (e) { toast(e.message) }
  }
  return (
    <Section title="Export">
      <Row title="Dates" help="For the transactions file and the QuickBooks file. Leave To blank to go through today. Pending transactions are left out.">
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', fontSize: 13, color: 'var(--text2)' }}>
          <label>From <input type="date" value={start} onChange={(e) => setStart(e.target.value)} style={FIELD} /></label>
          <label>To <input type="date" value={end} onChange={(e) => setEnd(e.target.value)} style={FIELD} /></label>
        </div>
      </Row>
      <Row title="All transactions" help="Every account, with category, tags, notes, and who owes money back. A split shows one row per line. Money out is negative. Opens in Excel.">
        <button type="button" className="press" style={BUTTON} onClick={() => get('/api/export/transactions.csv' + qs({ start, end }))}>Download CSV</button>
      </Row>
      <Row title="QuickBooks file" help="One account at a time. QBO is the Web Connect file QuickBooks Desktop and Online both import. CSV is the three column upload for QuickBooks Online.">
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
          <select aria-label="Account" value={account} onChange={(e) => setAccount(e.target.value)} style={{ ...FIELD, maxWidth: 200 }}>
            {accounts.map((a) => <option key={a.account_id} value={a.account_id}>{a.name}</option>)}
          </select>
          <select aria-label="File type" value={fmt} onChange={(e) => setFmt(e.target.value)} style={FIELD}>
            <option value="qbo">QBO</option>
            <option value="csv">CSV</option>
          </select>
          <button type="button" className="press" style={BUTTON} disabled={!account}
            onClick={() => get(`/api/export/quickbooks/${encodeURIComponent(account)}` + qs({ fmt, start, end }))}>Download</button>
        </div>
      </Row>
      <Row title="Tax summary" help="Totals for the year by category and by tag. Tag tax items all year, like Medical or Charity, and each tag gets its own line. Transfers and money owed back are left out.">
        <div style={{ display: 'flex', gap: 8 }}>
          <select aria-label="Tax year" value={year} onChange={(e) => setYear(Number(e.target.value))} style={FIELD}>
            {[0, 1, 2, 3, 4].map((n) => <option key={n} value={thisYear - n}>{thisYear - n}</option>)}
          </select>
          <button type="button" className="press" style={BUTTON} onClick={() => get(`/api/export/tax-summary.csv?year=${year}`)}>Download CSV</button>
        </div>
      </Row>
    </Section>
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
  const [siteIcons, setSiteIcons] = useState(null)
  const [mapData, setMapData] = useState(null)
  useEffect(() => { api.mapSettings().then(setMapData).catch(() => {}) }, [])
  const changeMap = async (key, on) => {
    try { setMapData(await api.setMapSettings({ [key]: on })) } catch (e) { toast(e.message) }
  }
  const clearMap = async () => {
    try { const r = await api.clearSavedMap(); setMapData(r); toast(`Deleted ${r.removed.toLocaleString()} saved map squares.`) } catch (e) { toast(e.message) }
  }

  useEffect(() => { api.sessionSetting().then(setSession).catch((e) => setError(e.message)) }, [])

  useEffect(() => { api.siteIcons().then((r) => setSiteIcons(r.enabled)).catch(() => {}) }, [])
  const changeSiteIcons = async (on) => {
    try {
      setSiteIcons((await api.setSiteIcons(on)).enabled)
      toast(on ? 'The app will get shop icons from their websites.' : 'The app will not contact shop websites. Icons already saved stay.')
    } catch (e) { toast(e.message) }
  }

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

      <ExportSection />

      <Section title="Privacy">
        <Row title="Get shop icons from their websites" help="For a shop with no logo, the app asks the shop's own website for its icon, once. The request says nothing about you or the purchase. Turn this off and the app contacts no shop websites.">
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 14 }}>
            <input type="checkbox" checked={Boolean(siteIcons)} disabled={siteIcons === null} onChange={(e) => changeSiteIcons(e.target.checked)} style={{ width: 18, height: 18 }} />
            {siteIcons ? 'On' : 'Off'}
          </label>
        </Row>
      </Section>

      <Section title="Map data">
        <div style={{ padding: '0 20px 14px', fontSize: 13, color: 'var(--text2)' }}>
          The Outline map and the World view need none of these. Each service below is free and needs no account. It sees your internet address and which area of the map you look at, and nothing about you or your purchases. Squares you have viewed are saved on this PC and load from disk after that.
        </div>
        {MAP_ROWS.map(([key, title, help]) => (
          <Row key={key} title={title} help={help}>
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 14 }}>
              <input type="checkbox" checked={Boolean(mapData?.[key])} disabled={!mapData} onChange={(e) => changeMap(key, e.target.checked)} style={{ width: 18, height: 18 }} />
              {mapData?.[key] ? 'On' : 'Off'}
            </label>
          </Row>
        ))}
        <Row title="Saved map squares" help={mapData ? `${mapData.saved.count.toLocaleString()} squares, ${(mapData.saved.bytes / 1048576).toFixed(1)} MB on this PC.` : 'Loading'}>
          <button type="button" onClick={clearMap} disabled={!mapData || !mapData.saved.count}
            style={{ height: 36, padding: '0 14px', borderRadius: 8, border: '1px solid var(--line)', background: 'transparent', color: 'var(--text2)', fontSize: 13, opacity: mapData?.saved.count ? 1 : 0.5 }}>Delete saved squares</button>
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

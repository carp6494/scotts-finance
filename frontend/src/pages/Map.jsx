import { Suspense, lazy, useEffect, useMemo, useState } from 'react'
import { api, money, toast } from '../api'
import { useCategories, withIcon } from '../categories'
import TxList from '../components/TxList'
import { PRECISION, placeName } from '../components/mapStyle'

// The 3D code is large, so it loads only when this page opens.
const UsMap = lazy(() => import('../components/UsMap'))
const GlobeMap = lazy(() => import('../components/GlobeMap'))
const TileMap = lazy(() => import('../components/TileMap'))

const LOOKS = [['outline', 'Outline'], ['satellite', 'Satellite'], ['hybrid', 'Hybrid'], ['terrain', 'Terrain']]
const remember = (k, v) => { try { localStorage.setItem(k, v) } catch { /* ignore */ } }
const recall = (k, d) => { try { return localStorage.getItem(k) || d } catch { return d } }

const sel = { height: 36, borderRadius: 8, border: '1px solid var(--line)', background: 'var(--card)', color: 'var(--text)', padding: '0 8px' }
const iso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
const daysAgo = (n) => { const d = new Date(); d.setDate(d.getDate() - n); return iso(d) }
const RANGES = [
  ['all', 'All time', () => undefined],
  ['year', 'This year', () => `${new Date().getFullYear()}-01-01`],
  ['365', 'Last 12 months', () => daysAgo(365)],
  ['90', 'Last 90 days', () => daysAgo(90)],
  ['30', 'Last 30 days', () => daysAgo(30)],
]

export default function MapPage({ accounts, refreshKey, onChanged }) {
  const [view, setView] = useState('us')
  const [range, setRange] = useState('all')
  const [acct, setAcct] = useState('')
  const [cat, setCat] = useState('')
  const [hq, setHq] = useState(false)
  const [data, setData] = useState(null)
  const [picked, setPicked] = useState(null)
  const [look, setLook] = useState(() => recall('map-look', 'outline'))
  const [height, setHeight] = useState(() => Number(recall('map-height', '2')) || 2)
  const [show3d, setShow3d] = useState(() => recall('map-3d', '1') === '1')
  const [have, setHave] = useState(null)
  useEffect(() => { api.mapSettings().then(setHave).catch(() => setHave({ usgs: false, terrain: false, buildings: false })) }, [])
  useEffect(() => { remember('map-look', look); remember('map-height', String(height)); remember('map-3d', show3d ? '1' : '0') }, [look, height, show3d])
  const groups = useCategories()
  const linked = accounts.filter((a) => !a.manual)
  const start = useMemo(() => RANGES.find((r) => r[0] === range)[2](), [range])

  useEffect(() => {
    let alive = true
    api.map({ account_id: acct || undefined, cat_id: cat || undefined, start, hq: hq ? 1 : undefined })
      .then((r) => { if (alive) { setData(r); setPicked((p) => (p ? r.points.find((x) => x.id === p.id) || null : null)) } })
      .catch((e) => toast(e.message))
    return () => { alive = false }
  }, [acct, cat, start, hq, refreshKey])

  const points = data?.points || []
  const abroad = points.filter((p) => p.country && !['US', 'USA'].includes(p.country.toUpperCase())).length
  const tiled = view === 'us' && look !== 'outline'
  // What the chosen style needs that is switched off in Settings.
  const missing = !tiled || !have ? '' : (look === 'terrain' && !have.terrain) ? 'Terrain elevation' : (look !== 'terrain' && !have.usgs) ? 'Satellite photos' : ''

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
      <div className="card rise" style={{ padding: 18 }}>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, alignItems: 'center', justifyContent: 'space-between', marginBottom: 12, fontSize: 13, color: 'var(--muted)' }}>
          <div role="group" aria-label="Map view" style={{ display: 'flex', border: '1px solid var(--line)', borderRadius: 8, overflow: 'hidden', height: 36 }}>
            {[['us', 'United States'], ['world', 'World']].map(([k, l]) => (
              <button key={k} type="button" aria-pressed={view === k} onClick={() => setView(k)}
                style={{ padding: '0 14px', border: 0, background: view === k ? 'var(--accent)' : 'transparent', color: view === k ? '#fff' : 'var(--text2)', fontSize: 13, fontWeight: 500 }}>{l}</button>
            ))}
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, alignItems: 'center' }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: 8 }}>Dates
              <select value={range} onChange={(e) => setRange(e.target.value)} style={sel}>
                {RANGES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
              </select>
            </label>
            <label style={{ display: 'flex', alignItems: 'center', gap: 8 }}>Account
              <select value={acct} onChange={(e) => setAcct(e.target.value)} style={sel}>
                <option value="">All accounts</option>
                {linked.map((a) => <option key={a.account_id} value={a.account_id}>{a.official_name || a.name}{a.mask ? ` ${a.mask}` : ''}</option>)}
              </select>
            </label>
            <label style={{ display: 'flex', alignItems: 'center', gap: 8 }}>Category
              <select value={cat} onChange={(e) => setCat(e.target.value)} style={sel}>
                <option value="">All categories</option>
                {groups.map((g) => (
                  <optgroup key={g.group_name} label={g.group_name}>
                    {g.categories.filter((c) => !c.hidden).map((c) => <option key={c.id} value={c.id}>{withIcon(c)}{c.name}</option>)}
                  </optgroup>
                ))}
              </select>
            </label>
            <label style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <input type="checkbox" checked={hq} onChange={(e) => setHq(e.target.checked)} /> Show online purchases at headquarters
            </label>
          </div>
        </div>

        {view === 'us' && (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 14, alignItems: 'center', marginBottom: 12, fontSize: 13, color: 'var(--muted)' }}>
            <div role="group" aria-label="Map style" style={{ display: 'flex', border: '1px solid var(--line)', borderRadius: 8, overflow: 'hidden', height: 34 }}>
              {LOOKS.map(([k, l]) => (
                <button key={k} type="button" aria-pressed={look === k} onClick={() => setLook(k)}
                  style={{ padding: '0 12px', border: 0, background: look === k ? 'var(--accent)' : 'transparent', color: look === k ? '#fff' : 'var(--text2)', fontSize: 13, fontWeight: 500 }}>{l}</button>
              ))}
            </div>
            {tiled && have?.terrain && (
              <label style={{ display: 'flex', alignItems: 'center', gap: 8 }}>Terrain height
                <input type="range" min="0" max="10" step="0.5" value={height} onChange={(e) => setHeight(Number(e.target.value))} style={{ width: 140 }} />
                <span className="num" style={{ width: 34, color: 'var(--text2)' }}>{height === 0 ? 'Flat' : `${height}x`}</span>
              </label>
            )}
            {tiled && have?.buildings && (
              <label style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <input type="checkbox" checked={show3d} onChange={(e) => setShow3d(e.target.checked)} /> 3D buildings
              </label>
            )}
            {tiled && have && !have.terrain && look !== 'terrain' && <span>The ground is flat. For hills, turn on "Terrain elevation" in Settings.</span>}
            {tiled && have && !have.buildings && <span>For 3D buildings, turn on "3D buildings" in Settings.</span>}
          </div>
        )}

        <div style={{ height: 'min(68vh, 640px)', minHeight: 380, borderRadius: 10, overflow: 'hidden', border: '1px solid var(--line)', background: 'var(--bg)' }}>
          <Suspense fallback={<div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--muted)', fontSize: 14 }}>Loading the map</div>}>
            {view === 'world' && <GlobeMap points={points} selected={picked} onSelect={setPicked} />}
            {view === 'us' && !tiled && <UsMap points={points} selected={picked} onSelect={setPicked} />}
            {tiled && have && !missing && <TileMap points={points} selected={picked} onSelect={setPicked} look={look} height={height} show3d={show3d && have.buildings} have={have} />}
            {tiled && missing && (
              <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24, textAlign: 'center', color: 'var(--text2)', fontSize: 14 }}>
                This style needs "{missing}", which is off. Click Settings in the left sidebar and turn it on under Map data.
              </div>
            )}
          </Suspense>
        </div>

        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px 18px', alignItems: 'center', marginTop: 12, fontSize: 12, color: 'var(--muted)' }}>
          {view === 'world' && <span>Warmer color means more spending in that area.</span>}
          {view === 'us' && Object.entries(PRECISION).filter(([k]) => k !== 'hq' || hq).map(([k, v]) => (
            <span key={k} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <span style={{ width: 10, height: 10, borderRadius: 2, background: v.color }} />{v.label}
            </span>
          ))}
          <span style={{ marginLeft: 'auto' }}>{view === 'us' ? 'Each bar is one business. Its height is what you spent there. Drag to turn, scroll to zoom, click a bar for its purchases.' : 'Drag to turn, scroll to zoom. Each dot is one business. Click a dot for its purchases.'}</span>
        </div>
        {data && (
          <p style={{ margin: '10px 0 0', fontSize: 13, color: 'var(--text2)' }}>
            {money(data.total)} at {points.length.toLocaleString()} {points.length === 1 ? 'business' : 'businesses'}.
            {data.unplaced.count > 0 && ` ${data.unplaced.count.toLocaleString()} purchases totaling ${money(data.unplaced.total)} have no location.`}
            {!hq && data.hq.count > 0 && ` ${data.hq.count.toLocaleString()} online purchases totaling ${money(data.hq.total)} are hidden.`}
            {view === 'us' && abroad > 0 && ` ${abroad} ${abroad === 1 ? 'business is' : 'businesses are'} outside the United States. Click World to see ${abroad === 1 ? 'it' : 'them'}.`}
          </p>
        )}
      </div>

      {picked && (
        <div className="card rise" style={{ padding: 18 }}>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, alignItems: 'baseline', justifyContent: 'space-between' }}>
            <h2 style={{ margin: 0, fontSize: 16, fontWeight: 600 }}>{picked.name}</h2>
            <span style={{ fontSize: 13, color: 'var(--text2)' }}>{placeName(picked)}</span>
            <span style={{ fontSize: 13, color: 'var(--muted)' }}>Placed by: {(PRECISION[picked.precision] || PRECISION.city).label.toLowerCase()}</span>
            <button type="button" onClick={() => setPicked(null)} style={{ marginLeft: 'auto', height: 32, padding: '0 12px', borderRadius: 8, border: '1px solid var(--line)', background: 'transparent', color: 'var(--text2)', fontSize: 13 }}>Close</button>
          </div>
          <div className="num" style={{ marginTop: 6, fontSize: 22, fontWeight: 700 }}>{money(picked.total)}</div>
          <div style={{ margin: '0 0 14px', fontSize: 13, color: 'var(--muted)' }}>{picked.count} {picked.count === 1 ? 'purchase' : 'purchases'}</div>
          <TxList spot={`${picked.lat},${picked.lon}`} merchant={picked.name} accountId={acct || undefined} catId={cat || undefined} start={start} refreshKey={refreshKey} onChanged={onChanged} compact />
        </div>
      )}
    </div>
  )
}

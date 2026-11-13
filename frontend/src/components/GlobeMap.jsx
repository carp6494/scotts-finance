import { useEffect, useRef } from 'react'
import Globe from 'globe.gl'
import { MeshPhongMaterial } from 'three'
import { feature } from 'topojson-client'
import world from 'world-atlas/countries-110m.json'
import { money } from '../api'
import { palette, placeName } from './mapStyle'

const countries = feature(world, world.objects.countries).features
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]))
const at = (p) => [p.show_lat ?? p.lat, p.show_lon ?? p.lon]

// A plain globe with country outlines and a heatmap of spending. No image textures or
// tiles, so nothing loads from the network. Small flat dots sit under the heat so a
// business can still be hovered and clicked.
export default function GlobeMap({ points, selected, onSelect }) {
  const box = useRef(null)
  const globe = useRef(null)
  const selectRef = useRef(onSelect)
  selectRef.current = onSelect

  useEffect(() => {
    const el = box.current
    const c = palette()
    const g = new Globe(el, { animateIn: false })
      .backgroundColor('rgba(0,0,0,0)')
      .showAtmosphere(true)
      .atmosphereColor('#60a5fa')
      .globeMaterial(new MeshPhongMaterial({ color: c.water }))
      .polygonsData(countries)
      .polygonCapColor(() => c.land)
      .polygonSideColor(() => 'rgba(0,0,0,0)')
      .polygonStrokeColor(() => c.line)
      .polygonAltitude(0.004)
      .polygonsTransitionDuration(0)
      .heatmapPointLat((p) => at(p)[0])
      .heatmapPointLng((p) => at(p)[1])
      .heatmapPointWeight((p) => p.heat)
      .heatmapBandwidth(0.9)
      .heatmapColorSaturation(2.4)
      .heatmapBaseAltitude(0.006)
      .heatmapTopAltitude(0.006)
      .heatmapsTransitionDuration(0)
      .pointLat((p) => at(p)[0])
      .pointLng((p) => at(p)[1])
      .pointAltitude(0.008)
      .pointRadius(0.07)
      .pointResolution(6)
      .pointsMerge(false)
      .pointsTransitionDuration(0)
      .pointLabel((p) => `<div style="background:var(--card);border:1px solid var(--line3);border-radius:8px;padding:6px 10px;font-size:12px;color:var(--text)"><b>${esc(p.name)}</b><br>${esc(money(p.total))} in ${p.count} ${p.count === 1 ? 'purchase' : 'purchases'}<br><span style="color:var(--muted)">${esc(placeName(p))}</span></div>`)
      .onPointClick((p) => selectRef.current(p))
      .pointOfView({ lat: 38, lng: -97, altitude: 1.7 }, 0)
    g.controls().minDistance = 103
    globe.current = g
    const resize = () => { if (el.clientWidth && el.clientHeight) g.width(el.clientWidth).height(el.clientHeight) }
    const ro = new ResizeObserver(resize)
    ro.observe(el)
    resize()
    return () => { ro.disconnect(); g._destructor(); el.replaceChildren(); globe.current = null }
  }, [])

  useEffect(() => {
    const g = globe.current
    if (!g) return
    const max = Math.max(0, ...points.map((p) => p.total))
    const hi = palette().highlight
    // Square root keeps one big spender from washing out every other area.
    const heat = points.map((p) => ({ ...p, heat: max > 0 ? Math.sqrt(p.total / max) : 0 }))
    g.heatmapsData(heat.length ? [heat] : [])
      .pointColor((p) => (selected && selected.id === p.id ? hi : 'rgba(255,255,255,0.55)'))
      .pointsData(points)
  }, [points, selected])

  return <div ref={box} style={{ width: '100%', height: '100%' }} />
}

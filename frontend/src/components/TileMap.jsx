import { useEffect, useRef, useState } from 'react'
import * as maplibregl from 'maplibre-gl'
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?url'
import 'maplibre-gl/dist/maplibre-gl.css'
import { mesh } from 'topojson-client'
import states from 'us-atlas/states-10m.json'
import { money } from '../api'
import { colorOf, heightOf, palette, placeName } from './mapStyle'

// The worker file ships with the app, so the map engine loads nothing from the network.
maplibregl.setWorkerUrl(workerUrl)

const stateLines = { type: 'Feature', properties: {}, geometry: mesh(states, states.objects.states) }
// Map squares come from this app's own server, which fetches and saves them. See backend/tiles.py.
const squares = (name) => [`${window.location.origin}/api/tiles/${name}/{z}/{x}/{y}`]
const EARTH = 40075016.686
const BAR_HALF_WIDTH_PX = 4
const BAR_MAX_PX = 210

// Low ground green, hills tan and brown, peaks white. Water blue.
const ELEVATION_COLORS = ['interpolate', ['linear'], ['elevation'],
  -4000, '#123a6b', -50, '#3f7fbf', 0, '#2f7d4f', 150, '#5fa35a', 400, '#a9c56e', 800, '#e6d98a',
  1300, '#d1a95f', 1900, '#a9743f', 2600, '#7d5236', 3300, '#b9b3ad', 4200, '#ffffff']

function styleFor(have) {
  const sources = {
    states: { type: 'geojson', data: stateLines },
    bars: { type: 'geojson', data: { type: 'FeatureCollection', features: [] } },
    imagery: { type: 'raster', tiles: squares('imagery'), tileSize: 256, maxzoom: 16, attribution: 'Imagery: USGS The National Map' },
    hybrid: { type: 'raster', tiles: squares('hybrid'), tileSize: 256, maxzoom: 16, attribution: 'Imagery and labels: USGS The National Map' },
  }
  const layers = [
    { id: 'background', type: 'background', paint: { 'background-color': palette().water } },
    { id: 'imagery', type: 'raster', source: 'imagery', layout: { visibility: 'none' } },
    { id: 'hybrid', type: 'raster', source: 'hybrid', layout: { visibility: 'none' } },
  ]
  if (have.terrain) {
    const dem = { type: 'raster-dem', tiles: squares('dem'), tileSize: 256, maxzoom: 14, encoding: 'terrarium', attribution: 'Elevation: Terrain Tiles on AWS Open Data' }
    sources.dem = dem // shapes the ground
    sources.relief = { ...dem } // colors and shading; the engine wants its own copy
    layers.push({ id: 'elevation', type: 'color-relief', source: 'relief', layout: { visibility: 'none' }, paint: { 'color-relief-color': ELEVATION_COLORS } })
    layers.push({ id: 'shade', type: 'hillshade', source: 'relief', layout: { visibility: 'none' }, paint: { 'hillshade-exaggeration': 0.45, 'hillshade-shadow-color': '#1f2937' } })
  }
  layers.push({ id: 'states', type: 'line', source: 'states', paint: { 'line-color': '#ffffff', 'line-opacity': 0.55, 'line-width': ['interpolate', ['linear'], ['zoom'], 3, 0.6, 8, 1.4] } })
  if (have.buildings) {
    sources.buildings = { type: 'vector', tiles: squares('buildings'), minzoom: 13, maxzoom: 14, attribution: 'Buildings: OpenFreeMap, OpenMapTiles, OpenStreetMap contributors' }
    layers.push({
      id: 'buildings', type: 'fill-extrusion', source: 'buildings', 'source-layer': 'building', minzoom: 13, layout: { visibility: 'none' },
      paint: {
        'fill-extrusion-color': '#cbd5e1', 'fill-extrusion-opacity': 0.85,
        'fill-extrusion-height': ['coalesce', ['get', 'render_height'], 6],
        'fill-extrusion-base': ['coalesce', ['get', 'render_min_height'], 0],
      },
    })
  }
  layers.push({
    id: 'bars', type: 'fill-extrusion', source: 'bars',
    paint: { 'fill-extrusion-color': ['get', 'color'], 'fill-extrusion-height': ['get', 'h'], 'fill-extrusion-base': 0, 'fill-extrusion-opacity': 0.92 },
  })
  return { version: 8, sources, layers }
}

// One square column per business. Sized in screen pixels, so it reads the same at every zoom.
function barFeatures(points, zoom, selected) {
  const max = Math.max(0, ...points.map((p) => p.total))
  const hi = palette().highlight
  return points.map((p) => {
    const lat = p.show_lat ?? p.lat
    const lon = p.show_lon ?? p.lon
    const metersPerPx = (EARTH * Math.cos((lat * Math.PI) / 180)) / (512 * 2 ** zoom)
    const dLat = (BAR_HALF_WIDTH_PX * metersPerPx) / 111320
    const dLon = dLat / Math.max(Math.cos((lat * Math.PI) / 180), 0.2)
    return {
      type: 'Feature',
      properties: { id: p.id, color: selected && selected.id === p.id ? hi : colorOf(p), h: (6 + heightOf(p, max) * BAR_MAX_PX) * metersPerPx },
      geometry: { type: 'Polygon', coordinates: [[[lon - dLon, lat - dLat], [lon + dLon, lat - dLat], [lon + dLon, lat + dLat], [lon - dLon, lat + dLat], [lon - dLon, lat - dLat]]] },
    }
  })
}

export default function TileMap({ points, selected, onSelect, look, height = 1.5, show3d = false, have }) {
  const box = useRef(null)
  const mapRef = useRef(null)
  const ready = useRef(false)
  const live = useRef({ points, selected, onSelect, look, height, show3d })
  live.current = { points, selected, onSelect, look, height, show3d }
  const [tip, setTip] = useState(null)
  const [failed, setFailed] = useState('')

  const apply = () => {
    const map = mapRef.current
    if (!map || !ready.current) return
    const s = live.current
    const show = (id, on) => { if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', on ? 'visible' : 'none') }
    show('imagery', s.look === 'satellite')
    show('hybrid', s.look === 'hybrid')
    show('elevation', s.look === 'terrain')
    show('shade', s.look === 'terrain')
    show('buildings', s.show3d)
    if (map.getSource('dem')) map.setTerrain({ source: 'dem', exaggeration: s.height })
    map.getSource('bars')?.setData({ type: 'FeatureCollection', features: barFeatures(s.points, map.getZoom(), s.selected) })
  }

  // The map is rebuilt only when the set of allowed data changes.
  useEffect(() => {
    let map
    try {
      map = new maplibregl.Map({
        container: box.current, style: styleFor(have), bounds: [[-125, 24], [-66.5, 49.6]], fitBoundsOptions: { padding: 24 },
        pitch: 48, maxPitch: 80, maxZoom: 18, attributionControl: { compact: true },
      })
    } catch (e) {
      setFailed(e.message || 'The map could not start.')
      return undefined
    }
    mapRef.current = map
    map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), 'top-right')
    map.on('error', () => {}) // a missing square is normal at the edge of coverage
    map.on('load', () => { ready.current = true; apply() })
    let queued = 0
    map.on('zoom', () => { cancelAnimationFrame(queued); queued = requestAnimationFrame(apply) })
    const pointAt = (e) => {
      const id = e.features?.[0]?.properties?.id
      return live.current.points.find((p) => p.id === id) || null
    }
    map.on('mousemove', 'bars', (e) => { const p = pointAt(e); map.getCanvas().style.cursor = p ? 'pointer' : ''; setTip(p ? { p, x: e.point.x, y: e.point.y } : null) })
    map.on('mouseleave', 'bars', () => { map.getCanvas().style.cursor = ''; setTip(null) })
    map.on('click', 'bars', (e) => { const p = pointAt(e); if (p) live.current.onSelect(p) })
    const ro = new ResizeObserver(() => map.resize())
    ro.observe(box.current)
    return () => { ro.disconnect(); ready.current = false; mapRef.current = null; map.remove() }
  }, [have.terrain, have.buildings]) // eslint-disable-line

  useEffect(apply, [points, selected, look, height, show3d]) // eslint-disable-line

  if (failed) return <div role="alert" style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--warn)', fontSize: 14, padding: 24, textAlign: 'center' }}>This view could not start: {failed} Click Outline to use the built-in map.</div>
  return (
    <div style={{ position: 'relative', width: '100%', height: '100%' }}>
      <div ref={box} style={{ position: 'absolute', inset: 0 }} />
      {tip && (
        <div role="tooltip" style={{ position: 'absolute', left: Math.min(tip.x + 14, (box.current?.clientWidth || 0) - 200), top: Math.max(tip.y - 62, 4), pointerEvents: 'none', background: 'var(--card)', border: '1px solid var(--line3)', borderRadius: 8, padding: '6px 10px', fontSize: 12, boxShadow: '0 8px 24px rgba(0,0,0,.3)', whiteSpace: 'nowrap', zIndex: 2 }}>
          <div style={{ fontWeight: 600 }}>{tip.p.name}</div>
          <div style={{ color: 'var(--text2)' }}>{money(tip.p.total)} in {tip.p.count} {tip.p.count === 1 ? 'purchase' : 'purchases'}</div>
          <div style={{ color: 'var(--muted)' }}>{placeName(tip.p)}</div>
        </div>
      )}
    </div>
  )
}

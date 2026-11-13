import { useEffect, useRef, useState } from 'react'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { geoAlbersUsa } from 'd3-geo'
import { feature, mesh } from 'topojson-client'
import states from 'us-atlas/states-albers-10m.json'
import counties from 'us-atlas/counties-albers-10m.json'
import { money } from '../api'
import { colorOf, heightOf, palette, placeName } from './mapStyle'

// us-atlas "albers" files are already projected into a 975 by 610 box with this projection.
const W = 975
const H = 610
const project = geoAlbersUsa().scale(1300).translate([W / 2, H / 2])
const MAX_HEIGHT = 150
const HOME_DISTANCE = 835 // camera distance of the opening view

const flat = ([x, y]) => new THREE.Vector2(x - W / 2, H / 2 - y)

function landMesh(color) {
  const shapes = []
  for (const f of feature(states, states.objects.states).features) {
    const polys = f.geometry.type === 'Polygon' ? [f.geometry.coordinates] : f.geometry.coordinates
    for (const rings of polys) {
      const shape = new THREE.Shape(rings[0].map(flat))
      for (const hole of rings.slice(1)) shape.holes.push(new THREE.Path(hole.map(flat)))
      shapes.push(shape)
    }
  }
  return new THREE.Mesh(new THREE.ShapeGeometry(shapes), new THREE.MeshBasicMaterial({ color, side: THREE.DoubleSide }))
}

function borderLines(topology, object, color, z, opacity = 1) {
  const pts = []
  for (const line of mesh(topology, object).coordinates) {
    for (let i = 0; i < line.length - 1; i++) {
      const a = flat(line[i]); const b = flat(line[i + 1])
      pts.push(a.x, a.y, z, b.x, b.y, z)
    }
  }
  const g = new THREE.BufferGeometry()
  g.setAttribute('position', new THREE.Float32BufferAttribute(pts, 3))
  return new THREE.LineSegments(g, new THREE.LineBasicMaterial({ color, transparent: opacity < 1, opacity }))
}

export default function UsMap({ points, selected, onSelect }) {
  const box = useRef(null)
  const stage = useRef(null) // { scene, camera, controls, renderer, columns, draw }
  const [tip, setTip] = useState(null)
  const selectRef = useRef(onSelect)
  selectRef.current = onSelect

  // Scene, camera and base map: built once.
  useEffect(() => {
    const el = box.current
    const colors = palette()
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true })
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    el.appendChild(renderer.domElement)
    const scene = new THREE.Scene()
    const camera = new THREE.PerspectiveCamera(38, 1, 0.1, 6000)
    camera.position.set(0, 620, 560)
    const controls = new OrbitControls(camera, renderer.domElement)
    controls.enableDamping = true
    controls.zoomToCursor = true
    controls.minDistance = 5
    controls.zoomSpeed = 1.8
    controls.maxDistance = 1800
    controls.maxPolarAngle = Math.PI / 2 - 0.08
    controls.target.set(0, 0, 20)
    // Keep the camera aimed at the ground inside the map, so a hard zoom or pan cannot lose it.
    const keepOnMap = () => {
      const t = controls.target
      const dx = THREE.MathUtils.clamp(t.x, -W / 2, W / 2) - t.x
      const dz = THREE.MathUtils.clamp(t.z, -H / 2, H / 2) - t.z
      const dy = -t.y
      if (dx || dy || dz) { t.set(t.x + dx, 0, t.z + dz); camera.position.x += dx; camera.position.z += dz; camera.position.y = Math.max(camera.position.y + dy, 1) }
    }

    // The map is drawn in the XY plane, then laid flat so columns rise along world Y.
    const ground = new THREE.Group()
    ground.rotation.x = -Math.PI / 2
    ground.add(landMesh(colors.land))
    ground.add(borderLines(counties, counties.objects.counties, colors.fine, 0.05, 0.7))
    ground.add(borderLines(states, states.objects.states, colors.line, 0.1))
    const columns = new THREE.Group()
    ground.add(columns)
    scene.add(ground)
    scene.add(new THREE.AmbientLight(0xffffff, 1.5))
    const sun = new THREE.DirectionalLight(0xffffff, 1.6)
    sun.position.set(-300, 600, 400)
    scene.add(sun)

    let frame = 0
    const draw = () => {
      controls.update()
      keepOnMap()
      // Keep bars a steady size on screen. Zoomed in on a city they shrink with the map,
      // so neighbors stand apart instead of merging into one wall.
      const dist = camera.position.distanceTo(controls.target)
      const w = THREE.MathUtils.clamp(dist * 0.004, 0.01, 4)
      const k = THREE.MathUtils.clamp(dist / HOME_DISTANCE, 0.004, 1)
      for (const c of columns.children) {
        c.scale.set(w, w, k)
        c.position.z = (c.userData.h * k) / 2 + 0.02
      }
      renderer.render(scene, camera)
      frame = requestAnimationFrame(draw)
    }
    const resize = () => {
      const { clientWidth: w, clientHeight: h } = el
      if (!w || !h) return
      renderer.setSize(w, h)
      camera.aspect = w / h
      camera.updateProjectionMatrix()
    }
    const ro = new ResizeObserver(resize)
    ro.observe(el)
    resize()
    draw()

    const ray = new THREE.Raycaster()
    const hit = (e) => {
      const r = renderer.domElement.getBoundingClientRect()
      ray.setFromCamera(new THREE.Vector2(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1), camera)
      const found = ray.intersectObjects(columns.children, false)[0]
      return found ? found.object.userData.point : null
    }
    let down = null
    const onMove = (e) => {
      const p = hit(e)
      const r = el.getBoundingClientRect()
      setTip(p ? { p, x: e.clientX - r.left, y: e.clientY - r.top } : null)
      renderer.domElement.style.cursor = p ? 'pointer' : 'grab'
    }
    const onDown = (e) => { down = [e.clientX, e.clientY] }
    const onUp = (e) => {
      const moved = down && Math.hypot(e.clientX - down[0], e.clientY - down[1]) > 4
      down = null
      if (moved) return
      const p = hit(e)
      if (p) selectRef.current(p)
    }
    const dom = renderer.domElement
    dom.addEventListener('pointermove', onMove)
    dom.addEventListener('pointerdown', onDown)
    dom.addEventListener('pointerup', onUp)
    dom.addEventListener('pointerleave', () => setTip(null))

    stage.current = { columns, colors }
    return () => {
      cancelAnimationFrame(frame)
      ro.disconnect()
      controls.dispose()
      scene.traverse((o) => { o.geometry?.dispose(); o.material?.dispose() })
      renderer.dispose()
      dom.remove()
      stage.current = null
    }
  }, [])

  // Columns: rebuilt when the data or the selection changes.
  useEffect(() => {
    const s = stage.current
    if (!s) return
    for (const c of [...s.columns.children]) { c.geometry.dispose(); c.material.dispose(); s.columns.remove(c) }
    const max = Math.max(0, ...points.map((p) => p.total))
    const unit = new THREE.BoxGeometry(1, 1, 1)
    for (const p of points) {
      const xy = project([p.show_lon ?? p.lon, p.show_lat ?? p.lat])
      if (!xy) continue // outside the United States
      const h = 1.5 + heightOf(p, max) * MAX_HEIGHT
      const isSel = selected && selected.id === p.id
      const m = new THREE.Mesh(unit.clone(), new THREE.MeshLambertMaterial({ color: isSel ? s.colors.highlight : colorOf(p) }))
      const at = flat(xy)
      m.geometry.scale(1, 1, h)
      m.position.set(at.x, at.y, h / 2 + 0.12)
      m.userData.point = p
      m.userData.h = h
      s.columns.add(m)
    }
    unit.dispose()
  }, [points, selected])

  return (
    <div ref={box} style={{ position: 'relative', width: '100%', height: '100%', touchAction: 'none' }}>
      {tip && (
        <div role="tooltip" style={{ position: 'absolute', left: Math.min(tip.x + 14, (box.current?.clientWidth || 0) - 190), top: Math.max(tip.y - 62, 4), pointerEvents: 'none', background: 'var(--card)', border: '1px solid var(--line3)', borderRadius: 8, padding: '6px 10px', fontSize: 12, boxShadow: '0 8px 24px rgba(0,0,0,.3)', whiteSpace: 'nowrap', zIndex: 2 }}>
          <div style={{ fontWeight: 600 }}>{tip.p.name}</div>
          <div style={{ color: 'var(--text2)' }}>{money(tip.p.total)} in {tip.p.count} {tip.p.count === 1 ? 'purchase' : 'purchases'}</div>
          <div style={{ color: 'var(--muted)' }}>{placeName(tip.p)}</div>
        </div>
      )}
    </div>
  )
}

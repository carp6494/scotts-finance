import { DRAWN, flatCategories } from '../categories'

// "icon Group · Name" for one category id, with the drawing where there is one.
export function CatLabel({ groups, id }) {
  const c = flatCategories(groups).find((x) => x.id === id)
  if (!c) return <>❔ Uncategorized</>
  return <>{c.icon ? <><CatIcon icon={c.icon} /> </> : null}{c.group_name} · {c.name}</>
}

// One leaflet, base at 0,0 and tip straight up. The leaf is seven of these, turned and scaled.
const LEAFLET = 'M0 0C-2.7-4.2-2.2-9.6 0-13.4C2.2-9.6 2.7-4.2 0 0Z'
const FAN = [[0, 1], [38, 0.86], [-38, 0.86], [72, 0.64], [-72, 0.64], [108, 0.4], [-108, 0.4]]

function Cannabis({ size }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true" style={{ display: 'inline-block', verticalAlign: '-0.15em', flexShrink: 0 }}>
      <g transform="translate(12 16.4)" fill="#22c55e">
        {FAN.map(([turn, scale]) => <path key={turn} d={LEAFLET} transform={`rotate(${turn}) scale(${scale})`} />)}
        <path d="M0-1V5.4" stroke="#22c55e" strokeWidth="1.3" strokeLinecap="round" fill="none" />
      </g>
    </svg>
  )
}

const DRAWINGS = { ':cannabis:': Cannabis }

// A category icon: an emoji as text, or a drawing for the names in DRAWN. Size is in px or any CSS length.
export default function CatIcon({ icon, size = '1.15em' }) {
  const Drawing = DRAWN[icon] ? DRAWINGS[icon] : null
  return Drawing ? <Drawing size={size} /> : <>{icon}</>
}

const TINTS = ['#2563eb', '#7c3aed', '#0891b2', '#db2777', '#d97706', '#16a34a', '#475569', '#9333ea']

// With no logo, show the category icon when one is passed, else the first letter of the name.
export default function Logo({ src, name, size = 36, wide = false, home = false, icon = '' }) {
  const radius = Math.round(size / 4)
  if (home) {
    return (
      <span style={{ width: size, height: size, borderRadius: radius, background: '#0e7490', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
        <svg width={size * 0.55} height={size * 0.55} viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M3 11l9-7 9 7" /><path d="M5 10v10h14V10" /><path d="M10 20v-6h4v6" />
        </svg>
      </span>
    )
  }
  if (src) {
    const isCardArt = src.includes('discover-card')
    return (
      <img src={src} alt="" style={{
        width: isCardArt || wide ? size * 1.5 : size, height: size, borderRadius: isCardArt ? 5 : radius,
        background: '#fff', objectFit: isCardArt ? 'cover' : 'contain', flexShrink: 0,
      }} />
    )
  }
  if (icon) {
    return (
      <span aria-hidden="true" style={{ width: size, height: size, borderRadius: radius, background: '#1e293b', border: '1px solid #334155', boxSizing: 'border-box', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: size * 0.55, lineHeight: 1, flexShrink: 0 }}>
        {icon}
      </span>
    )
  }
  const letter = (name || '?').trim()[0]?.toUpperCase() || '?'
  const tint = TINTS[(name || '').length % TINTS.length]
  return (
    <span style={{ width: size, height: size, borderRadius: radius, background: tint, color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 700, fontSize: size * 0.4, flexShrink: 0 }}>
      {letter}
    </span>
  )
}

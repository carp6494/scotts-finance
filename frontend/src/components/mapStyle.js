// Shared by the United States map and the globe.
export const PRECISION = {
  exact: { label: 'Exact address', color: '#2563eb' },
  likely: { label: 'Likely branch of a chain', color: '#14b8a6' },
  zip: { label: 'Zip code center', color: '#38bdf8' },
  city: { label: 'City center', color: '#7dd3fc' },
  hq: { label: 'Company headquarters', color: '#a855f7' },
}

export const colorOf = (p) => (PRECISION[p.precision] || PRECISION.city).color

// Column height from 0 to 1. Square root keeps one big purchase from flattening the rest.
export const heightOf = (p, max) => (max > 0 ? Math.sqrt(p.total / max) : 0)

export const placeName = (p) => [p.precision === 'exact' || p.precision === 'likely' ? p.address : null, p.city, p.region].filter(Boolean).join(', ') || 'No address'

export function palette() {
  const dark = document.documentElement.getAttribute('data-theme') !== 'light'
  return dark
    ? { land: '#16223a', line: '#3b4a66', fine: '#223049', water: '#0a1120', highlight: '#fbbf24' }
    : { land: '#dde6f3', line: '#8496b0', fine: '#c3cfe0', water: '#b9cfea', highlight: '#d97706' }
}

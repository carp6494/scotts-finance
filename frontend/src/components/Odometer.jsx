import { useEffect, useState } from 'react'

// Slow odometer scroll for the main money figures.
// Replays on mount (page open / refresh / screen switch) and when the browser tab becomes visible again.
export default function Odometer({ value, className = '', style, delay = 0 }) {
  const [rolled, setRolled] = useState(false)

  useEffect(() => {
    const roll = () => {
      setRolled(false)
      requestAnimationFrame(() => requestAnimationFrame(() => setRolled(true)))
    }
    roll()
    const onVis = () => { if (!document.hidden) roll() }
    document.addEventListener('visibilitychange', onVis)
    return () => document.removeEventListener('visibilitychange', onVis)
  }, [])

  let d = 0
  return (
    <span className={`odo-row num ${className}`} style={style} role="img" aria-label={value}>
      {String(value).split('').map((ch, i) => {
        if (!/[0-9]/.test(ch)) return <span key={i} aria-hidden="true">{ch}</span>
        const n = Number(ch)
        const t = (delay + d++ * 0.09).toFixed(2)
        const s = rolled
          ? { transform: `translateY(-${n * 10}%)`, transition: `transform 2.4s cubic-bezier(.16,1,.3,1) ${t}s` }
          : { transform: 'translateY(0)', transition: 'none' }
        return (
          <span key={i} className="odo" aria-hidden="true">
            <span className="odo-strip" style={s}>
              {[0, 1, 2, 3, 4, 5, 6, 7, 8, 9].map((k) => <span key={k}>{k}</span>)}
            </span>
          </span>
        )
      })}
    </span>
  )
}

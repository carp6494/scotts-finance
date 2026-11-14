import { useEffect, useState } from 'react'
import { api, toast } from './api'

// One shared copy of the tag list, like categories.js. Adding or renaming a tag refreshes everyone.
const EMPTY = { tags: [], colors: [] }
let cache = null
let inflight = null
const listeners = new Set()

export function loadTags(force = false) {
  if (cache && !force) return Promise.resolve(cache)
  if (inflight && !force) return inflight
  const p = api.tags().then((r) => {
    cache = r
    listeners.forEach((l) => l(r))
    return r
  }).finally(() => { if (inflight === p) inflight = null })
  inflight = p
  return p
}

// { tags: [{ id, name, color, count }], colors: [hex] }
export function useTags() {
  const [state, setState] = useState(cache || EMPTY)
  useEffect(() => {
    listeners.add(setState)
    loadTags().then(setState).catch((e) => toast(e.message))
    return () => listeners.delete(setState)
  }, [])
  return state
}

// A tinted pill that reads on both themes: the color shows as a dot, a wash, and a border.
export const pillStyle = (color) => ({
  display: 'inline-flex', alignItems: 'center', gap: 5, borderRadius: 999, whiteSpace: 'nowrap', lineHeight: 1.4,
  color: 'var(--text2)', background: `color-mix(in srgb, ${color} 14%, transparent)`, border: `1px solid color-mix(in srgb, ${color} 45%, transparent)`,
})

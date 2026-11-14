import { useEffect, useState } from 'react'
import { api, toast } from './api'

// One shared copy of the grouped category list. Components subscribe; adding a category refreshes everyone.
let cache = null
let inflight = null
const listeners = new Set()

export function loadCategories(force = false) {
  if (cache && !force) return Promise.resolve(cache)
  if (inflight && !force) return inflight
  const p = api.categories().then((g) => {
    cache = g
    listeners.forEach((l) => l(g))
    return g
  }).finally(() => { if (inflight === p) inflight = null })
  inflight = p
  return p
}

export function useCategories() {
  const [groups, setGroups] = useState(cache || [])
  useEffect(() => {
    listeners.add(setGroups)
    loadCategories().then(setGroups).catch((e) => toast(e.message))
    return () => listeners.delete(setGroups)
  }, [])
  return groups
}

export const flatCategories = (groups) => groups.flatMap((g) => g.categories.map((c) => ({ ...c, group_name: g.group_name })))

// Icons with no emoji. The app draws them in CatIcon.jsx. Plain text places, such as a
// dropdown list, cannot hold a drawing, so each one names the emoji that stands in there.
export const DRAWN = { ':cannabis:': '🍁' }

export const iconText = (icon) => DRAWN[icon] || icon

export const withIcon = (c) => (c?.icon ? `${iconText(c.icon)} ` : '')

export const categoryLabel = (groups, id) => {
  const c = flatCategories(groups).find((x) => x.id === id)
  return c ? `${withIcon(c)}${c.group_name} · ${c.name}` : '❔ Uncategorized'
}

import { useEffect, useState } from 'react'
import { api } from './api'

// One shared copy of the grouped category list. Components subscribe; adding a category refreshes everyone.
let cache = null
let inflight = null
const listeners = new Set()

export function loadCategories(force = false) {
  if (cache && !force) return Promise.resolve(cache)
  if (!inflight || force) {
    inflight = api.categories().then((g) => { cache = g; inflight = null; listeners.forEach((l) => l(g)); return g })
  }
  return inflight
}

export function useCategories() {
  const [groups, setGroups] = useState(cache || [])
  useEffect(() => {
    listeners.add(setGroups)
    loadCategories().then(setGroups).catch(() => {})
    return () => listeners.delete(setGroups)
  }, [])
  return groups
}

export const flatCategories = (groups) => groups.flatMap((g) => g.categories.map((c) => ({ ...c, group_name: g.group_name })))

export const categoryLabel = (groups, id) => {
  const c = flatCategories(groups).find((x) => x.id === id)
  return c ? `${c.group_name} · ${c.name}` : 'Uncategorized'
}

import { useEffect, useState } from 'react'
import { api, money } from './api'
import { categoryLabel } from './categories'

// The plain sentence for a rule. Used on the Rules page and in the hover on a transaction's Rule badge.
export function describeRule(rule, groups, accounts) {
  const c = rule.conditions || {}, a = rule.actions || {}, parts = []
  if (c.merchant) parts.push(`merchant has "${c.merchant}"`)
  if (c.text) parts.push(`text has "${c.text}"`)
  if (c.direction) parts.push(c.direction === 'out' ? 'money goes out' : 'money comes in')
  if (c.bank_category) parts.push(`bank calls it ${categoryLabel(groups, c.bank_category)}`)
  if (c.amount_min != null && c.amount_max != null) parts.push(`amount ${money(c.amount_min)} to ${money(c.amount_max)}`)
  else if (c.amount_min != null) parts.push(`amount at least ${money(c.amount_min)}`)
  else if (c.amount_max != null) parts.push(`amount at most ${money(c.amount_max)}`)
  if (c.account_id) {
    const acct = (accounts || []).find((x) => x.account_id === c.account_id)
    parts.push(`account ${acct ? `${acct.official_name || acct.name}${acct.mask ? ` ${acct.mask}` : ''}` : 'one account'}`)
  }
  if (c.day_min != null || c.day_max != null) parts.push(`day ${c.day_min ?? 1} to ${c.day_max ?? 31}`)
  const acts = []
  if (a.cat_id) acts.push(`file as ${categoryLabel(groups, a.cat_id)}`)
  if (a.display_name) acts.push(`show as "${a.display_name}"`)
  if (a.exclude) acts.push('exclude from totals')
  if (a.transfer) acts.push('mark as transfer')
  if (a.tags && a.tags.length) acts.push(`tag ${a.tags.map((x) => `"${x}"`).join(', ')}`)
  return `When ${parts.join(' and ') || 'anything'}: ${acts.join(', ') || 'nothing'}`
}

// One shared copy of the rule list and accounts, like tags.js. The Rules page refreshes it after each change.
let cache = null
let inflight = null
const listeners = new Set()
const EMPTY = { rules: [], accounts: [] }

export function loadRules(force = false) {
  if (cache && !force) return Promise.resolve(cache)
  if (inflight && !force) return inflight
  const p = Promise.all([api.rules(), api.accounts()]).then(([rules, accounts]) => {
    cache = { rules, accounts }
    listeners.forEach((l) => l(cache))
    return cache
  }).finally(() => { if (inflight === p) inflight = null })
  inflight = p
  return p
}

export function useRules() {
  const [state, setState] = useState(cache || EMPTY)
  useEffect(() => {
    listeners.add(setState)
    loadRules().then(setState).catch(() => {})
    return () => listeners.delete(setState)
  }, [])
  return state
}

// Ask the app to open the Rules page with this rule lit up.
export const openRule = (id) => window.dispatchEvent(new CustomEvent('open-rule', { detail: id }))

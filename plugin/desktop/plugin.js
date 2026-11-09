/**
 * Comfy Recipe — desktop half (Hermes desktop app).
 *
 * Adds a "Comfy Recipe" sidebar entry (under Kanban) + a "New ComfyUI session" palette command. Both open a fresh chat
 * and send a one-line kickoff ("[ComfyUI session]" + optional motto from the plugin settings). The Python half's
 * pre_llm_call hook adds the real instructions model-side; the agent then opens ComfyUI in the PREVIEW PANE (the browser
 * pane it can click/type in via drive_preview) and works there by hand while the user watches or steps in.
 *
 * Why the agent opens the pane (not this plugin): only the agent-opened preview pane is controllable by the agent;
 * an iframe embedded by a plugin would be view-only for it.
 *
 * Live progress: the Python tools (comfy_setup, comfy_downloads, comfy_onboarding) return a progress JSON file
 * (install status.json, progress/downloads.json, progress/nodes.json) that the agent posts once as a MEDIA: line.
 * The host lets the plugin that OWNS the producing tool draw that attachment (transcript.toolMedia), so instead of a
 * file card the chat shows a live progress card, re-read every second until it is finished; a compact chip in the
 * status bar mirrors the most recent active one.
 *
 * Plain ESM, loaded uncompiled — only @hermes/plugin-sdk, react and react/jsx-runtime resolve.
 */
import { PALETTE_AREA, ROUTES_AREA, SIDEBAR_NAV_AREA, haptic, host } from '@hermes/plugin-sdk'
import * as SDK from '@hermes/plugin-sdk'
import { useEffect, useSyncExternalStore } from 'react'
import { jsx, jsxs } from 'react/jsx-runtime'

const ID = 'comfy-recipe'
const PAGE_PATH = '/comfy-recipe'
const MARKER = '[ComfyUI session]'
const PROGRESS_TOOLS = ['comfy_setup', 'comfy_downloads', 'comfy_onboarding']
// Namespace import: an older host without these exports must still load the rest of the plugin.
const MEDIA_AREA = SDK.TOOL_MEDIA_RENDERER_AREA || 'transcript.toolMedia'
const STATUS_AREA = (SDK.STATUSBAR_AREAS && SDK.STATUSBAR_AREAS.right) || 'statusBar.right'

const sleep = ms => new Promise(resolve => setTimeout(resolve, ms))

// Motto from the agent-side settings (Settings -> Plugins -> Comfy Recipe). Read in parallel with opening the chat,
// remembered after the first read (refreshed in the background), so it never delays the session.
let cachedMotto = null

async function fetchMotto() {
  try {
    const res = await Promise.race([host.request('plugins.manage', { action: 'list' }), sleep(2500).then(() => null)])
    const row = (res && res.plugins || []).find(p => p && (p.name === ID || p.key === ID))
    const field = (row && row.settings_schema || []).find(f => f.key === 'motto')
    const motto = field && (field.value ?? field.default)
    cachedMotto = typeof motto === 'string' ? motto.trim() : ''
    return cachedMotto
  } catch {
    return cachedMotto ?? ''
  }
}

function readMotto() {
  const fresh = fetchMotto()
  return cachedMotto === null ? fresh : Promise.resolve(cachedMotto)
}

async function startComfySession(ctx) {
  haptic('tap')
  const mottoP = readMotto() // in parallel with opening the chat
  const res = await ctx.runAction('session.new')
  if (!res || res.ok === false) {
    host.notify({ kind: 'error', message: `Comfy Recipe: could not open a new chat (${res && res.reason})` })
    return
  }
  const motto = await mottoP
  const kickoff = motto ? `${MARKER} "${motto.replace(/"/g, "'")}"` : MARKER
  // Address the FRESH draft ('new'), never the active composer: right after session.new the previous chat's composer
  // can still be the active one, and a null address would post the kickoff into that old chat. 'new' fails closed
  // (false) until the new chat's composer is mounted, so retry for a while.
  for (let i = 0; i < 100; i++) {
    if (host.composer.submit('new', kickoff)) return
    await sleep(100)
  }
  host.notify({ kind: 'warning', message: 'Comfy Recipe: chat opened, but the kickoff could not be sent — type “[ComfyUI session]”.' })
}

let starting = false

// Page behind the sidebar entry: navigating here immediately opens a new ComfyUI chat (session.new navigates away).
function StartComfyPage({ ctx }) {
  useEffect(() => {
    if (starting) return
    starting = true
    startComfySession(ctx).finally(() => {
      setTimeout(() => { starting = false }, 1500)
    })
  }, [])

  return jsx('div', {
    className: 'flex h-full items-center justify-center text-sm text-(--ui-text-tertiary)',
    children: 'Opening a ComfyUI session…'
  })
}

// ---------------------------------------------------------------- progress: pure helpers (unit-tested with node)
export function decodeDataUrl(url) {
  const comma = String(url || '').indexOf(',')
  if (comma < 0) return String(url || '')
  const meta = url.slice(0, comma)
  const body = url.slice(comma + 1)
  if (!/;base64/i.test(meta)) return decodeURIComponent(body)
  const bin = atob(body)
  const bytes = new Uint8Array(bin.length)
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i)
  return new TextDecoder('utf-8').decode(bytes)
}

const gb = n => (n / 1e9).toFixed(n >= 1e10 ? 1 : 2)

function duration(s) {
  if (s == null || !isFinite(s)) return ''
  if (s < 60) return `${Math.max(1, Math.round(s))} s`
  if (s < 3600) return `${Math.round(s / 60)} min`
  return `${Math.floor(s / 3600)} h ${Math.round((s % 3600) / 60)} min`
}

export const ACTIVE = new Set(['running', 'pending', 'downloading', 'starting'])

/** One view model for every card kind: {kind, title, state, percent, label, rows:[{label, state, percent, detail}]} */
export function summarize(data, now = Date.now() / 1000) {
  if (!data || typeof data !== 'object') return null
  const kind = data.kind || (Array.isArray(data.steps) ? 'install' : null)
  const stale = ACTIVE.has(data.state) && data.updated_at && now - data.updated_at > 120
  if (kind === 'install') {
    const steps = data.steps || []
    const weights = data.weights && data.weights.length === steps.length ? data.weights : steps.map(() => 100 / (steps.length || 1))
    const total = weights.reduce((a, b) => a + b, 0) || 1
    const step = Math.min(Number(data.step) || 0, steps.length)
    const done = data.state === 'done'
    const percent = done ? 100 : (100 * weights.slice(0, step).reduce((a, b) => a + b, 0)) / total
    const elapsed = data.started_at ? duration(now - data.started_at) : ''
    return {
      kind, title: data.title || 'Installing ComfyUI', state: stale ? 'stalled' : data.state, percent,
      label: done ? `Installed${data.duration_s ? ` in ${duration(data.duration_s)}` : ''}`
        : data.state === 'error' ? (data.error || 'Install failed')
        : `Step ${Math.min(step + 1, steps.length)}/${steps.length}: ${data.step_name || steps[step] || ''}${elapsed ? ` · ${elapsed}` : ''}`,
      rows: steps.map((name, i) => ({
        label: name, detail: '',
        state: done || i < step ? 'done' : i === step ? (data.state === 'error' ? 'error' : 'running') : 'pending'
      }))
    }
  }
  if (kind === 'downloads') {
    const total = data.total_bytes || 0
    const bits = [total ? `${gb(data.bytes || 0)} / ${gb(total)} GB` : `${data.done_files || 0}/${data.files || 0} files`]
    if (data.state === 'running' && data.speed_bps) bits.push(`${(data.speed_bps / 1e6).toFixed(0)} MB/s`)
    if (data.state === 'running' && data.eta_s) bits.push(`~${duration(data.eta_s)} left`)
    const rows = (data.groups || []).map(g => ({
      label: g.label, state: g.state,
      percent: g.total_bytes ? (100 * Math.min(g.bytes, g.total_bytes)) / g.total_bytes : (g.files ? (100 * g.done_files) / g.files : 0),
      detail: `${g.done_files}/${g.files} files${g.total_bytes ? ` · ${gb(g.total_bytes)} GB` : ''}${g.state === 'done' ? ' · ready' : ''}`
    }))
    const label = data.state === 'done' ? `All ${data.files} files downloaded`
      : data.state === 'error' ? `${(data.errors || []).length} file(s) failed: ${((data.errors || [])[0] || {}).error || ''}`
      : data.state === 'stalled' ? (data.note || 'Download worker stopped')
      : data.current ? `${data.current.name} · ${bits.join(' · ')}` : bits.join(' · ')
    return { kind, title: data.title || 'Downloading models', state: stale ? 'stalled' : data.state, percent: data.percent || 0, label, rows }
  }
  if (kind === 'nodes') {
    const label = data.state === 'done' ? (data.note || 'Node packs installed')
      : data.state === 'idle' ? (data.note || 'Waiting for the install to start')
      : `${data.done || 0}/${data.total || '?'} packs${data.error ? ` · ${data.error}` : ''}`
    return {
      kind, title: data.title || 'Installing node packs', state: stale ? 'stalled' : data.state, percent: data.percent || 0, label,
      rows: (data.packs || []).map(name => ({ label: name, state: data.state === 'done' ? 'done' : 'pending', detail: '' }))
    }
  }
  return null
}

// ---------------------------------------------------------------- progress: shared store + one poller
const store = { entries: new Map(), listeners: new Set(), version: 0 }

function emit() {
  store.version++
  for (const fn of store.listeners) fn()
}

function subscribe(fn) {
  store.listeners.add(fn)
  return () => store.listeners.delete(fn)
}

function track(path, resolveUrl) {
  const old = store.entries.get(path)
  if (old) { old.resolveUrl = resolveUrl; return }
  store.entries.set(path, { path, resolveUrl, view: null, error: null, seen: Date.now(), finishedAt: null })
  void refresh(path)
}

async function refresh(path) {
  const e = store.entries.get(path)
  if (!e || e.busy) return
  e.busy = true
  try {
    const view = summarize(JSON.parse(decodeDataUrl(await e.resolveUrl())))
    if (view) {
      e.view = view
      e.error = null
      e.seen = Date.now()
      if (!ACTIVE.has(view.state) && !e.finishedAt) e.finishedAt = Date.now()
      if (ACTIVE.has(view.state)) e.finishedAt = null
    }
  } catch (err) {
    e.error = String((err && err.message) || err)
  } finally {
    e.busy = false
    emit()
  }
}

function pollAll() {
  for (const e of store.entries.values()) {
    // Active cards every second; finished ones re-read rarely (a new download can reuse the same card file).
    const finished = e.view && !ACTIVE.has(e.view.state)
    if (!finished || Date.now() - (e.lastSlow || 0) > 15000) {
      if (finished) e.lastSlow = Date.now()
      void refresh(e.path)
    }
  }
}

const useStore = () => useSyncExternalStore(subscribe, () => store.version)

// ---------------------------------------------------------------- progress: UI
const COLORS = {
  running: 'var(--color-primary, #7c5cff)', pending: 'var(--ui-text-tertiary, #888)', done: '#2ea043',
  error: '#e5534b', stalled: '#d29922', cancelled: '#888', idle: '#888'
}
const ICON = { done: '✓', error: '✕', stalled: '!', cancelled: '–' }

function Bar({ percent, state, height = 6, width = '100%' }) {
  const p = Math.max(0, Math.min(100, percent || 0))
  return jsx('div', {
    style: { width, height, borderRadius: height, background: 'color-mix(in srgb, var(--ui-text-tertiary, #888) 22%, transparent)', overflow: 'hidden' },
    children: jsx('div', {
      style: { width: `${p}%`, height: '100%', borderRadius: height, background: COLORS[state] || COLORS.running, transition: 'width 0.6s ease' }
    })
  })
}

function Row({ row }) {
  const color = COLORS[row.state] || COLORS.pending
  return jsxs('div', {
    style: { display: 'grid', gridTemplateColumns: '1.1rem 1fr auto', alignItems: 'center', gap: '0.4rem', fontSize: '0.78rem' },
    children: [
      jsx('span', { style: { color, textAlign: 'center' }, children: ICON[row.state] || (row.state === 'running' ? '●' : '○') }),
      jsxs('div', {
        style: { minWidth: 0 },
        children: [
          jsx('div', { style: { overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', opacity: row.state === 'pending' ? 0.7 : 1 }, children: row.label }),
          row.percent != null && row.state !== 'done' ? jsx(Bar, { percent: row.percent, state: row.state, height: 3 }) : null
        ]
      }),
      jsx('span', { style: { color: 'var(--ui-text-tertiary, #888)', fontVariantNumeric: 'tabular-nums' }, children: row.detail })
    ]
  })
}

const cardStyle = {
  display: 'grid', gap: '0.45rem', padding: '0.7rem 0.85rem', margin: '0.35rem 0', maxWidth: '34rem',
  border: '1px solid color-mix(in srgb, var(--ui-text-tertiary, #888) 30%, transparent)', borderRadius: '0.6rem',
  background: 'var(--ui-bg-elevated, transparent)'
}

function ProgressCard({ file, fallback }) {
  useStore()
  useEffect(() => { track(file.path, file.resolveUrl) }, [file.path])
  const e = store.entries.get(file.path)
  if (!e || (!e.view && !e.error)) {
    return jsx('div', { style: cardStyle, children: jsx('span', { style: { fontSize: '0.8rem', opacity: 0.7 }, children: 'Reading progress…' }) })
  }
  if (!e.view) return fallback
  const v = e.view
  const pct = Math.round(v.percent || 0)
  return jsxs('div', {
    style: cardStyle,
    children: [
      jsxs('div', {
        style: { display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: '0.75rem' },
        children: [
          jsx('strong', { style: { fontSize: '0.88rem' }, children: `${ICON[v.state] ? ICON[v.state] + ' ' : ''}${v.title}` }),
          jsx('span', { style: { fontSize: '0.8rem', fontVariantNumeric: 'tabular-nums', color: COLORS[v.state] || 'inherit' }, children: `${pct}%` })
        ]
      }),
      jsx(Bar, { percent: v.percent, state: v.state, height: 7 }),
      jsx('div', { style: { fontSize: '0.78rem', color: 'var(--ui-text-tertiary, #888)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }, children: v.label }),
      v.rows.length ? jsx('div', { style: { display: 'grid', gap: '0.3rem', marginTop: '0.2rem' }, children: v.rows.map((row, i) => jsx(Row, { row }, i)) }) : null
    ]
  })
}

const SHORT = { install: 'ComfyUI', downloads: 'Models', nodes: 'Nodes' }

function StatusChip() {
  useStore()
  const now = Date.now()
  const shown = [...store.entries.values()]
    .filter(e => e.view && (ACTIVE.has(e.view.state) || (e.finishedAt && now - e.finishedAt < 10000)))
    .sort((a, b) => b.seen - a.seen)[0]
  if (!shown) return null
  const v = shown.view
  return jsxs('span', {
    title: `${v.title}: ${v.label}`,
    style: { display: 'inline-flex', alignItems: 'center', gap: '0.35rem', height: '100%', padding: '0 0.4rem', fontSize: '0.6875rem', color: 'var(--ui-text-tertiary, #888)', fontVariantNumeric: 'tabular-nums' },
    children: [
      jsx('span', { children: ICON[v.state] || '⬇' }),
      jsx('span', { children: `${SHORT[v.kind] || 'Comfy'} ${Math.round(v.percent || 0)}%` }),
      jsx(Bar, { percent: v.percent, state: v.state, height: 4, width: '3rem' })
    ]
  })
}

export function isProgressFile(path) {
  return /[\\/]\.comfy-recipe[\\/](status\.json|progress[\\/](downloads|nodes)\.json)$/i.test(String(path || ''))
}

export default {
  id: ID,
  name: 'Comfy Recipe',
  register(ctx) {
    void fetchMotto() // warm the cache at app start
    ctx.register({
      id: 'new-session',
      area: PALETTE_AREA,
      data: {
        id: `${ID}.newSession`,
        label: 'New ComfyUI session',
        keywords: ['comfy', 'comfyui', 'comfy recipe', 'image', 'video', 'generate', 'workflow'],
        run: () => startComfySession(ctx)
      }
    })
    ctx.register({
      id: 'page',
      area: ROUTES_AREA,
      data: { path: PAGE_PATH },
      render: () => jsx(StartComfyPage, { ctx })
    })
    ctx.register({
      id: 'nav',
      area: SIDEBAR_NAV_AREA,
      order: 60, // Kanban is 50 -> directly under it
      data: { codicon: 'beaker', label: 'Comfy Recipe', path: PAGE_PATH }
    })
    // Live progress card in place of the progress JSON's file card; anything else keeps the built-in player.
    ctx.register({
      id: 'progress-card',
      area: MEDIA_AREA,
      data: {
        tools: PROGRESS_TOOLS,
        render: props => (isProgressFile(props.file && props.file.path) ? jsx(ProgressCard, { file: props.file, fallback: props.fallback }) : props.fallback)
      }
    })
    ctx.register({ id: 'progress-chip', area: STATUS_AREA, order: 70, render: () => jsx(StatusChip, {}) })
    ctx.setInterval(pollAll, 1000)
  }
}

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
 * Plain ESM, loaded uncompiled — only @hermes/plugin-sdk, react and react/jsx-runtime resolve.
 */
import { PALETTE_AREA, ROUTES_AREA, SIDEBAR_NAV_AREA, haptic, host } from '@hermes/plugin-sdk'
import { useEffect } from 'react'
import { jsx } from 'react/jsx-runtime'

const ID = 'comfy-recipe'
const PAGE_PATH = '/comfy-recipe'
const MARKER = '[ComfyUI session]'

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
  // The new chat's composer mounts asynchronously; submit is fail-closed (false until a visible composer exists).
  for (let i = 0; i < 60; i++) {
    if (host.composer.submit(null, kickoff)) return
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
  }
}

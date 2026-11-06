# Comfy Live — a Hermes Agent plugin for ComfyUI

**The agent works in your ComfyUI window, next to the chat.** Click **Comfy Live** in the Hermes sidebar: a new chat
opens, ComfyUI appears in the preview pane on the right, and the agent opens workflows, types prompts and clicks Run
*by hand* while you watch — or step in yourself to show it what you mean. Any model can follow it (tested with a local
27B model), because the session runs on a literal step-by-step recipe instead of clever shortcuts.

It can also run your **saved UI workflows headless** (subgraphs included, your `.json` is never rewritten) and tell you
where the time goes.

## What you get

| | |
|---|---|
| **Comfy Live** sidebar entry (+ Ctrl/⌘+K → *New ComfyUI session*) | Opens a ComfyUI session: the agent checks which ComfyUI is running, opens it in the pane and reports instance, GPU and active workflow. The session is named after your first real request. |
| `comfy_instances` | Finds ComfyUI installs: StabilityMatrix (incl. portable), ComfyUI Desktop, servers on ports 8188–8190 / 8000 and any `extra_urls`. Switches automatically if the remembered one is down; if none is running it just asks you to start yours — it never starts anything. |
| `comfy_workflows` | Lists saved workflows, describes one (subgraph controls, Load Image nodes, prompt target), shows measured timings. |
| `comfy_run` | **Headless** run of a saved UI workflow with prompt / seed / images / widget overrides. Converted to API format in memory; jobs are identical, input by input, to what the ComfyUI frontend sends. |
| `comfy_result` | Waits for a job and returns per-stage timing (sampling, prompt enhancer, loading/patching overhead, cache hits, hints), output files, and for videos a contact sheet + audio level. `prompt_id: "latest"` also reads jobs started with Run in the window. |
| `/comfy status \| switch \| workflows \| setup \| run` | Quick control from any chat. |
| Skill `comfy-live:session` | The recipe and verified pitfalls for driving ComfyUI in the pane, layout-preserving workflow JSON edits, and a method for finding slow stages. |

## Visible vs headless

ComfyUI only streams progress and results to the browser tab that queued a job. A job sent through the API can never
show up in your open window — so in a ComfyUI session the agent works **in the window**, and `comfy_run` is kept for
batches, seed sweeps and exact timing when you ask for "headless".

## Install

```bash
hermes plugins install dotroza/hermes-comfy-live     # or clone and link <repo>/plugin into your Hermes plugins folder
hermes plugins enable comfy-live
```
Then fully restart Hermes. In the desktop app: **Ctrl/⌘+K → Reload desktop plugins**, and enable **Comfy Live** under
**Settings → Plugins** (the desktop half of a plugin is off by default).

Requirements
- A running ComfyUI (any recent version with the new frontend).
- Headless runs only: [comfy-cli](https://github.com/Comfy-Org/comfy-cli) (`pip install comfy-cli`). It is called as a
  separate process; this repo contains none of its (GPL-3.0) code. Visible sessions work without it.
- Video checks: `ffmpeg` / `ffprobe` on PATH (optional).

## Settings (Settings → Plugins → Comfy Live)

| Key | Default | Use |
|---|---|---|
| `personal_skill` | — | Your own ComfyUI skill (paths, workflow catalog, model notes), loaded in every session after the generic one. |
| `motto` | — | Text shown after `[ComfyUI session]` when a session opens. |
| `extra_urls` | `[]` | ComfyUI servers on other ports, e.g. `["http://127.0.0.1:8283"]`. |
| `stabilitymatrix_dirs` | `[]` | Portable StabilityMatrix data folders (learned automatically once seen running). |
| `converter_python` | auto | A Python with comfy-cli, if auto-detection misses it. |

`/comfy setup` shows what is detected. Runtime data (instance list, object_info cache, run and timing logs, contact
sheets) lives in `<hermes home>/plugin-data/comfy-live/`, never in the plugin folder.

## Layout

```
plugin/
  plugin.yaml           manifest + settings schema
  __init__.py           tools, /comfy, session hook (instructions + session title), bundled skill
  core.py               discovery, workflow describe/run, results, timing (Hermes-independent)
  comfy_client.py       stdlib HTTP client for the ComfyUI API
  convert_bridge.py     UI→API conversion via comfy-cli + two fixes it needs (subgraph socket values, viewer nodes)
  desktop/plugin.js     desktop half: sidebar entry + "New ComfyUI session"
  skills/session/       the bundled comfy-live:session skill
```

## Status

Developed on Windows 11 with ComfyUI 0.44 / frontend 1.57 and a portable StabilityMatrix on a 2-GPU machine. The
visible-session flow was proven in the Hermes desktop app in the predecessor plugin; this generic version's core
functions are tested standalone and the in-app session was verified (sidebar entry, session card, settings). Other platforms are coded for (paths per OS)
but not yet verified — reports welcome.

Known limitation: naming the session after the first request uses a Hermes internal (`hermes_state_registry`), which the
validator flags as a private import; if a Hermes update changes it, only the session title falls back to Hermes' default.

## License

MIT

# Comfy Recipe — a Hermes Agent plugin for ComfyUI

**The agent works in your ComfyUI window, next to the chat.** Click **Comfy Recipe** in the Hermes sidebar: a new chat
opens, ComfyUI appears in the preview pane on the right, and the agent opens workflows, types prompts and clicks Run
*by hand* while you watch — or step in yourself to show it what you mean. Any model can follow it (tested with a local
27B model), because the session runs on a literal step-by-step recipe instead of clever shortcuts.

It can also run your **saved UI workflows headless** (subgraphs included, your `.json` is never rewritten) and tell you
where the time goes.

## What you get

| | |
|---|---|
| **First run** | The first session asks one question: install a ComfyUI just for Comfy Recipe (recommended — nothing to set up, works next to any ComfyUI you already have) or use an existing one. With several GPUs it asks which one; if another ComfyUI is found it offers to reuse its models (nothing copied). It asks where to install (default `Documents\ComfyRecipeEnv`; refuses non-empty, cloud-synced or too-small locations). The install runs in the background (~6 GB, 5–20 min) with live progress in the chat: [uv](https://github.com/astral-sh/uv), Python 3.13, the latest ComfyUI release, the right PyTorch for your GPU (NVIDIA CUDA, Apple Metal, AMD ROCm on Linux, else CPU) and ComfyUI-Manager. |
| `comfy_setup` | check / install / status / start / stop / use_existing / reset / adopt for Comfy Recipe's own ComfyUI (adopt = use an existing or moved install folder again). It only ever starts or stops that install. |
| **Comfy Recipe** sidebar entry (+ Ctrl/⌘+K → *New ComfyUI session*) | Opens a ComfyUI session. The plugin itself finds the running ComfyUI and opens it in the pane at the start of the turn (no model round trips), then the agent reports instance, GPU and active workflow. The session is named after your first real request. |
| `comfy_instances` | With its own install: only that one (isolated from your other ComfyUIs). With *use existing*: finds StabilityMatrix (incl. portable), ComfyUI Desktop, servers on ports 8188–8190 / 8000 and any `extra_urls`; switches automatically if the remembered one is down; if none is running it asks you to start yours. |
| `comfy_workflows` | Lists saved workflows, describes one (subgraph controls, Load Image nodes, prompt target), shows measured timings. |
| `comfy_templates` | Searches ComfyUI's ~650 built-in templates for what you want to make and proposes the best ones with thumbnail, inputs, download size and **readiness** (installed vs missing models with download links, missing custom nodes). Ready ones rank first. Opens them in the window or saves a copy to your workflows. |
| `comfy_run` | **Headless** run of a saved UI workflow with prompt / seed / images / widget overrides. Converted to API format in memory; jobs are identical, input by input, to what the ComfyUI frontend sends. |
| `comfy_result` | Waits for a job and returns per-stage timing (sampling, prompt enhancer, loading/patching overhead, cache hits, hints), output files, and for videos a contact sheet + audio level. `prompt_id: "latest"` also reads jobs started with Run in the window. |
| `comfy_media` | Prepares inputs with ffmpeg, next to the source file: `probe`, `convert` (trim + resize cover/fit/stretch + fps in one pass), `frames` (first / last / index / time as PNG, e.g. for first-last-frame workflows), `split` (N-second segments), `join` (concatenate with audio), `sheet` (contact sheet). `to_input: true` copies results into ComfyUI `input/`, reusing identical files. |
| `/comfy status \| switch \| workflows \| templates <query> \| setup \| run` | Quick control from any chat. |
| Skill `comfy-recipe:session` | The recipe and verified pitfalls for driving ComfyUI in the pane, layout-preserving workflow JSON edits, and a method for finding slow stages. |

## Shared workflows and native skills

Ten workflow definitions ship with library 1.4.0: five in **Workflows → Local Recipe** and five in
**Workflows → Cloud Recipe**, added to the managed instance after startup. User copies are never overwritten; dependencies can be installed after setup or on demand, with consent.
Native Hermes skills stay in `plugin/skills/` and may reference zero, one or multiple shared workflow IDs. There is no
separate recipe engine or registry. See [the workflow-library guide](docs/WORKFLOW_LIBRARY.md) for exact filenames,
stable IDs, authoring and updates. Cloud workflows require ComfyUI login and credits; copying definitions never
queues a paid run. Obtain explicit approval before paid execution and never embed credentials.

Qwen image editing uses an explicit change plus keep-list composed by Hermes, `refine_prompt` OFF, 4 steps and
Lightning ON by default. Text-to-image uses light wording cleanup and built-in refinement, as described below.
Neither policy overrides explicit user settings.

Use `comfy_workflows action=library` (offline), `action=install` (copy only), or `action=check workflow=<stable ID>`
(read-only requirements). Commands: `/comfy library`, `/comfy library install`, `/comfy check <stable ID>`.

## Guided first image

After a new managed installation, choose independently whether to install missing node packs now (recommended)
and download missing models now (with verified GB) or on use. Then describe your first image in this chat:
Hermes lightly cleans the wording without imposing a pose, setting or palette; Qwen's Image Gen
`refine_prompt` is ON (25 steps, Lightning disabled at strength 0) for creative expansion, unless explicitly overridden.
The agent generates it visibly. Skip with
“skip tutorial”, or replay with `/comfy tutorial`. Returning sessions open normally; step 2 teaches image editing, and steps 3–6 are held.
See [onboarding details](docs/ONBOARDING.md). Add redistributable references under [plugin/assets](plugin/assets/README.md).

## Visible vs headless

ComfyUI only streams progress and results to the browser tab that queued a job. A job sent through the API can never
show up in your open window — so in a ComfyUI session the agent works **in the window**, and `comfy_run` is kept for
batches, seed sweeps and exact timing when you ask for "headless".

## Install

```bash
hermes plugins install dotroza/hermes-comfy-recipe     # or clone and link <repo>/plugin into your Hermes plugins folder
hermes plugins enable comfy-recipe
```
Then fully restart Hermes. In the desktop app: **Ctrl/⌘+K → Reload desktop plugins**, and enable **Comfy Recipe** under
**Settings → Plugins** (the desktop half of a plugin is off by default).

Requirements
- A running ComfyUI (any recent version with the new frontend).
- Headless runs only: [comfy-cli](https://github.com/Comfy-Org/comfy-cli) (`pip install comfy-cli`). It is called as a
  separate process; this repo contains none of its (GPL-3.0) code. Visible sessions work without it.
- Video checks: `ffmpeg` / `ffprobe` on PATH (optional).

## Settings (Settings → Plugins → Comfy Recipe)

| Key | Default | Use |
|---|---|---|
| `personal_skill` | — | Your own ComfyUI skill (paths, workflow catalog, model notes), loaded in every session after the generic one. |
| `motto` | — | Text shown after `[ComfyUI session]` when a session opens. |
| `extra_urls` | `[]` | ComfyUI servers on other ports, e.g. `["http://127.0.0.1:8283"]`. |
| `stabilitymatrix_dirs` | `[]` | Portable StabilityMatrix data folders (learned automatically once seen running). |
| `converter_python` | auto | A Python with comfy-cli, if auto-detection misses it. |
| `stop_with_hermes` | `true` | Stop Comfy Recipe's own ComfyUI when Hermes is closed (frees GPU memory). Off = keep it running in the background. |

`/comfy setup` shows what is detected. Runtime data (instance list, object_info cache, run and timing logs, contact
sheets) lives in `<hermes home>/plugin-data/comfy-recipe/`, never in the plugin folder.

## Layout

```
plugin/
  plugin.yaml           manifest + settings schema
  __init__.py           tools, /comfy, session hook (instructions + session title), bundled skill
  core.py               discovery, workflow describe/run, results, timing (Hermes-independent)
  templates.py          template search, readiness check, save as user workflow
  library.py            shared catalog + protected working-copy publication
  dependencies.py       read-only workflow requirements and Manager installation guidance
  skill_registration.py native skill discovery + optional workflow ID references
  workflows/            ten versioned UI-format JSON assets (local + cloud) + catalog.json
  comfy_client.py       stdlib HTTP client for the ComfyUI API
  convert_bridge.py     UI→API conversion via comfy-cli + two fixes it needs (subgraph socket values, viewer nodes)
  desktop/plugin.js     desktop half: sidebar entry + "New ComfyUI session"
  skills/session/       the bundled comfy-recipe:session skill
docs/DEVELOPMENT.md     how the plugin hooks into Hermes (reload rules, hook, titles, settings, endpoints)
```

## Status

Developed on Windows 11 with ComfyUI 0.44 / frontend 1.57 and a portable StabilityMatrix on a 2-GPU machine. The
visible-session flow was proven in the Hermes desktop app in the predecessor plugin; this generic version's core
functions are tested standalone and the in-app session was verified (sidebar entry, session card, settings). Other platforms are coded for (paths per OS)
but not yet verified — reports welcome.

Known limitation: naming the session after the first request uses a Hermes internal (`hermes_state_registry`), which the
validator flags as a private import; if a Hermes update changes it, only the session title falls back to Hermes' default.
Likewise the instant pane opening uses `tools.desktop_ui` / `gateway.session_context`; if they change, the agent opens
the pane itself (a few seconds slower).

## License

MIT

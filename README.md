<p align="center">
  <img src="plugin/assets/images/comfy-recipe-icon.png" alt="Comfy Recipe — chef cat icon" width="256">
</p>

# Comfy Recipe — a Hermes Agent plugin for ComfyUI

**The agent brings ComfyUI inside Hermes, next to the chat.** Click **Comfy Recipe** in the Hermes sidebar: a new chat
opens, ComfyUI appears in the preview pane on the right, and the agent opens workflows, types prompts and clicks Run
*by hand* while you watch — or step in yourself to show it what you mean. Bundled skills give the agent
a step-by-step recipe for visible work (including testing with a local 27B model).

You can also run saved ComfyUI workflows in the background, including workflows with subgraphs. Comfy Recipe converts
them in memory, leaves your original `.json` files unchanged, and reports how long each stage of a run takes.

## Screenshots

A visible Comfy Recipe session inside Hermes: generate an image, refine the framing, and create a multi-view pet sheet.

![Comfy Recipe generating a realistic cat in a visible Hermes and ComfyUI session](docs/screenshots/visible-session-cat-generation.png)

![Comfy Recipe editing the generated cat image to show its full body](docs/screenshots/visible-session-image-editing.png)

![Comfy Recipe creating a multi-view pet sheet in ComfyUI](docs/screenshots/visible-session-pet-sheet.png)

## What you get

| | |
|---|---|
| **First run** | The first session asks one question: install a ComfyUI just for Comfy Recipe (recommended — nothing to set up, works next to any ComfyUI you already have) or use an existing one. With several GPUs it asks which one; if another ComfyUI is found it offers to reuse its models (nothing copied). It asks where to install (default `Documents\ComfyRecipeEnv`; refuses non-empty, cloud-synced or too-small locations). The install runs in the background (~6 GB, 5–20 min, excluding workflow model weights) with live progress in the chat: [uv](https://github.com/astral-sh/uv), Python 3.13, the latest ComfyUI release, the right PyTorch for your GPU (NVIDIA CUDA, Apple Metal, AMD ROCm on Linux, else CPU) and ComfyUI-Manager. |
| `comfy_setup` | check / check_dir / install / status / start / stop / restart / use_existing / reset / adopt for Comfy Recipe's own ComfyUI. Reset forgets the choice without deleting files; adopt reuses an existing or moved managed install. It only starts, stops or restarts its own install. |
| `comfy_onboarding` | Managed-install setup preferences and the four-step tutorial: start, resume, replay, skip and verify a fresh run. Supplies bundled reference-sheet layouts for people, pets, objects, outdoor places and interiors. |
| `comfy_downloads` | Resumable background model downloads with live chat progress cards and a status-bar chip; start / status / wait / cancel, plus approved node-pack installation through ComfyUI-Manager's API and installed-state checks. Supports bundled workflows, saved workflows with declared model links, and explicit model lists. |
| **Comfy Recipe** sidebar entry (+ Ctrl/⌘+K → *New ComfyUI session*) | Opens a ComfyUI session. The plugin finds the running ComfyUI; the agent opens its controllable preview using `desktop_preview`, then reports instance, GPU and active workflow. The session is named after your first real request. |
| `comfy_instances` | With its own install: only that one (isolated from your other ComfyUIs). With *use existing*: finds ComfyUI Desktop, servers on ports 8188–8190 / 8000 and any `extra_urls`; switches automatically if the remembered one is down and exactly one other is running; if none is running it asks you to start yours. |
| `comfy_workflows` | Lists saved workflows, describes one (subgraph controls, Load Image nodes, prompt target), shows measured timings. |
| `comfy_templates` | Searches ComfyUI's built-in templates for what you want to make and proposes the best ones with thumbnail, inputs, download size and **readiness** (installed vs missing models with download links, missing custom nodes). Ready ones rank first. Opens them in the window or saves a copy to your workflows. |
| `comfy_run` | **Headless** run of a saved UI workflow with prompt / seed / images / widget overrides. Converted to API format in memory; jobs are identical, input by input, to what the ComfyUI frontend sends. |
| `comfy_result` | Waits for a job and returns per-stage timing (sampling, prompt enhancer, loading/patching overhead, cache hits, hints), output files, and for videos a contact sheet + audio level. `prompt_id: "latest"` also reads jobs started with Run in the window. |
| `comfy_media` | Prepares inputs with ffmpeg, next to the source file: `probe`, `convert` (trim + resize cover/fit/stretch + fps in one pass), `frames` (first / last / index / time as PNG, e.g. for first-last-frame workflows), `split` (N-second segments, optional one-frame overlap for chaining), `join` (concatenate with audio; `drop_first=1` removes repeated boundary frames), `sheet` (contact sheet), `mux` (add a soundtrack or mix music under existing sound without re-encoding the video). `to_input: true` copies results into ComfyUI `input/`, reusing identical files. |
| `/comfy status \| switch \| workflows \| templates <query> \| setup \| run` | Quick control from any chat. |
| Skill `comfy-recipe:session` | The recipe and verified pitfalls for driving ComfyUI in the pane, layout-preserving workflow JSON edits, and a method for finding slow stages. |

## Shared workflows and native skills

Ten workflow definitions ship with library 1.4.0: five in **Workflows → Local Recipe** and five in
**Workflows → Cloud Recipe**, added to the managed instance after startup. User copies are never overwritten; dependencies can be installed after setup or on demand, with consent.
Native Hermes skills stay in `plugin/skills/` and may reference zero, one or multiple shared workflow IDs. There is no
separate recipe engine or registry. See [the workflow-library guide](docs/WORKFLOW_LIBRARY.md) for exact filenames,
stable IDs, authoring and updates. Cloud workflows require ComfyUI login and credits; copying definitions never
queues a paid run. Obtain explicit approval before paid execution and never embed credentials. Prompts and supplied
media are sent to the selected provider during execution. Existing/foreign instances require explicit library
installation; updates can be published as versioned siblings rather than replacing user copies.

| Folder | Included workflows |
|---|---|
| **Local Recipe** | Qwen Image 2.1 text-to-image and image editing; MiniMax H3 reference-to-video with optional first/last-frame guides; ACE-Step 1.5 XL audio; Pixal3D / TRELLIS.2 image-to-textured-GLB. |
| **Cloud Recipe** | Seedance 2.5 reference-to-video and text-to-video; ElevenLabs v4 text-to-speech; GPT Image 2.6 text/image-to-image; Seedream 5.0 Pro text/image-to-image. |

Twelve native skills cover the session, four tutorials, Qwen prompting/editing, workflow authoring, run recovery,
refinement, quality review and consistency. Focused skills load when needed, not all at session start.

Qwen image editing uses an explicit change plus keep-list composed by Hermes, `refine_prompt` OFF, 25 steps and
Lightning OFF (strength 0) by default. Text-to-image uses light wording cleanup and built-in refinement, as described below.
Neither policy overrides explicit user settings.

Use `comfy_workflows action=library` (offline), `action=install` (copy only), or `action=check workflow=<stable ID>`
(read-only requirements). Commands: `/comfy library`, `/comfy library install`, `/comfy check <stable ID>`.

## Guided four-step tutorial

After a new managed installation, choose independently whether to install missing node packs now (recommended)
and download missing models on use (recommended) or now (with verified missing-download GB). Shared/installed
models are excluded and duplicates counted once. Frontend settings require separate consent. Approved packs are
installed through ComfyUI-Manager’s API; model downloads run in the background with live progress cards and a
status-bar chip. Bulk downloads prioritize tutorial steps 1–4 before the rest; on-use downloads are queued as
you reach each lesson. A lesson can proceed once its own group is ready and workflow warnings are checked,
without waiting for unrelated downloads. Then describe your first image in this chat:
Hermes lightly cleans the wording without imposing a pose, setting or palette; Qwen's Image Gen
`refine_prompt` is ON (25 steps, Lightning disabled at strength 0) for creative expansion, unless explicitly overridden.
The agent generates it visibly. Skip with
“skip tutorial”, or replay with `/comfy tutorial [1-4]`. Returning sessions open normally. The tutorial has 4 steps:

| Step | Result | Behaviour |
|---|---|---|
| 1 — First image | Qwen text-to-image | Describe a person, pet, object or place; generate visibly and inspect the result. |
| 2 — Edit or reference sheet | Qwen image editing | Make an edit or a reusable sheet using bundled person, pet, object, outdoor or indoor layouts. |
| 3 — First video | Local MiniMax H3 | Use an image and subject sheet, plus an optional short motion-reference clip. Make a sheet first if needed. Without a clip, bypass its inputs and set duration visibly: the video is silent. With a clip, the saved video uses that clip’s sound. |
| 4 — Add sound | ACE-Step audio + media mux | Generate music, then mix it under existing sound or use it as a silent video’s soundtrack. Trim/pad to video length, fade out and preserve the video stream. |

Lessons require a fresh matching successful run with uncached sampling and output review. Cached or failed runs
do not count; visual mismatches are disclosed and retries offered rather than launched automatically. Step 4
also checks the final video’s audio stream and duration. Resume by asking to return to the tutorial.

A fresh ComfyUI opens five tabs in that order (text-to-image, image edit, video, audio, image-to-3D) and selects the first. Later launches preserve existing tabs, drafts and selection.
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
- Hermes Agent **0.23.1 or later** (`requires_hermes: ">=0.23.1"`); validated on 0.23.1, not claimed compatible with earlier releases.
- Hermes desktop for visible side-by-side sessions.
- A recent ComfyUI frontend: installed by managed setup, or already running when using an existing instance.
- Workflow-specific models, custom nodes and suitable hardware; base installation does not include model weights.
  Availability of nodes and models alone does not prove hardware compatibility or successful execution.
- Headless runs only: [comfy-cli](https://github.com/Comfy-Org/comfy-cli) (`pip install comfy-cli`). It is called as a
  separate process; this repo contains none of its (GPL-3.0) code. Visible sessions work without it.
- Media preparation, video checks and soundtrack muxing: `ffmpeg` / `ffprobe` on PATH.

## Security, privacy and external activity

Installing the plugin does not itself authorize a ComfyUI installation, model downloads, custom-node installation
or a paid generation. Those actions need user consent. No automatic approval or Hermes guard bypass is used;
without an interactive clarification tool, first-run instructions ask in chat and stop for an answer.

- **Network:** discovery probes localhost ComfyUI ports and explicitly configured `extra_urls`. The selected ComfyUI
  receives workflows, prompts and uploaded inputs. Setup contacts official GitHub sources (`Comfy-Org/ComfyUI`,
  `astral-sh/uv`), Python distributions downloaded by uv, Python package indexes and `download.pytorch.org`.
  Model readiness/downloads contact URLs declared by workflows or supplied explicitly (bundled models use
  Hugging Face; redirects may use its CDN). Node-pack installation uses ComfyUI-Manager and its registry/upstream
  repositories. These upstream components have their own network and dependency policies.
- **Downloaded code:** if no uv is installed, bootstrap downloads **uv 0.13.7** from its official GitHub release,
  verifies the archive against SHA-256 values committed in `plugin/installer.py`, and copies only the expected
  executable. Unsupported bootstrap architectures fail instead of guessing. Existing uv installations are reused.
  uv installs Python 3.13 and resolves ComfyUI/PyTorch dependencies in a separate venv; their artifacts are handled
  by uv, not vendored in this plugin. ComfyUI uses the latest release tag (default branch only if release lookup
  fails). Approved custom nodes run third-party code with the user's local permissions; this is not a sandbox.
- **Local access outside plugin data:** discovery reads process command lines, ComfyUI Desktop / StabilityMatrix
  settings and selected installation metadata. Workflow/model inspection reads the selected ComfyUI directories,
  model inventories and optional `extra_model_paths.yaml`. Approved model sharing references those folders without
  copying weights. Media tools read user-selected source files, write derived files beside them and optionally
  copy them to ComfyUI `input/`. Library installation writes protected workflow copies and startup support into
  the managed ComfyUI; existing instances require an explicit library install. Approved frontend settings are
  written through the selected ComfyUI. Session naming reads/writes the calling session's title through the
  public `SessionDB` API in the **active Hermes profile**.
- **Commands and background processes:** setup invokes uv, Python, git when available, package installation and
  hardware/process utilities. Headless conversion invokes an external Python with comfy-cli. Media tools invoke
  ffmpeg/ffprobe. Installer, download/node workers, ComfyUI and the owner watchdog may run beyond a chat turn;
  logs and progress are stored locally. Only the managed ComfyUI is started/stopped by this plugin. By default
  the watchdog stops it when its Hermes owners exit; `stop_with_hermes=false` keeps it running.
- **Stored data:** instance choices, installation paths, tutorial state, download queues, run/timing logs and
  contact sheets are local. Headless run records include prompts and overrides, and ComfyUI outputs may include
  workflow/prompt metadata. Tutorial prompt matching stores a hash. Treat these files as potentially sensitive;
  reset forgets setup choices, **not** files, logs or generated outputs.
- **Credentials and cloud runs:** the plugin declares no secret settings, required environment credentials or
  OAuth client. It does not read credential stores or implement token refresh. Cloud workflow authentication
  belongs to ComfyUI's official API-node sign-in; use that UI, never give credentials to the agent. Paid runs send
  prompts/media to the selected provider and require explicit approval for each execution.
- **Telemetry and updates:** the plugin adds no telemetry or usage reporting and never replaces its own code.
  Catalog updates arrive only through reviewed SHA-pin updates and `hermes plugins update comfy-recipe`.
  ComfyUI, custom nodes and providers are separate upstream software with their own policies.

## Settings (Settings → Plugins → Comfy Recipe)

| Key | Default | Use |
|---|---|---|
| `personal_skill` | — | Your own ComfyUI skill (paths, workflow catalog, model notes), loaded in every session after the generic one. |
| `motto` | — | Text shown after `[ComfyUI session]` when a session opens. |
| `extra_urls` | `[]` | ComfyUI servers on other ports, e.g. `["http://127.0.0.1:8283"]`. |
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
  installer.py          managed installation, start/stop/restart and adoption
  onboarding*.py        setup preferences, tutorial routing and run verification
  download*.py          background model downloads and node-pack installation
  media.py              ffmpeg media preparation and soundtrack muxing
  templates.py          template search, readiness check, save as user workflow
  library.py            shared catalog + protected working-copy publication
  dependencies.py       read-only workflow requirements and Manager installation guidance
  skill_registration.py native skill discovery + optional workflow ID references
  workflows/            ten versioned UI-format JSON assets (local + cloud) + catalog.json
  comfy_client.py       stdlib HTTP client for the ComfyUI API
  convert_bridge.py     UI→API conversion via comfy-cli + two fixes it needs (subgraph socket values, viewer nodes)
  comfyui/startup.js    fresh-workspace tab initialization
  desktop/plugin.js     sidebar, session entry and live progress UI
  skills/               twelve native skills and their references
  assets/               reference sheets and placeholder image
docs/DEVELOPMENT.md     how the plugin hooks into Hermes (reload rules, hook, titles, settings, endpoints)
```

## Verification and status

From the repository root:

```bash
python scripts/run_tests.py
python -m compileall -q plugin tests
hermes plugins validate ./plugin
```

Tests use isolated state and controlled backend fixtures; they do not establish live generation success for every
workflow or provider. Installation, model downloads and paid runs need their own consent and live checks. Python
tools, hooks and skill registration require a full Hermes restart after updates; a new chat is not a reload.


Developed on Windows 11 with ComfyUI 0.44 / frontend 1.57 on a 2-GPU machine. The
visible-session flow was proven in the Hermes desktop app; this version's core
functions are tested standalone and the in-app session was verified (sidebar entry, session card, settings). Other platforms are coded for (paths per OS)
but not yet verified — reports welcome.

Session naming uses the public `hermes_state.SessionDB` API with an explicitly profile-scoped path and deterministic
close; cosmetic failures leave Hermes' default naming in place. Pane opening uses the agent's `desktop_preview`
tool, not a private renderer event bridge. It may take an extra model round trip compared with the former fast path.

The test runner uses a disposable Hermes profile and rejects detached workers outside its sandbox. Fixtures do not
establish fresh installation or successful generation on every OS/provider. See [catalog submission](docs/CATALOG_SUBMISSION.md)
for the release checklist, disclosure draft and exact-SHA entry generation after you commit and push.

## License

MIT

---
name: session
description: "Use when driving ComfyUI in the Hermes preview pane."
version: 0.4.0
platforms: [windows, linux, macos]
author: dotroza
license: MIT
metadata:
  comfy_recipe:
    workflow_ids: []
  hermes:
    tags: [comfyui, preview-pane, live-session, workflows, image-generation, video-generation]
    related_skills: [comfyui]
---

# Comfy Recipe — drive ComfyUI in the window next to the chat

## When to Use
- A chat that starts with `[ComfyUI session]` (opened from the **Comfy Recipe** sidebar entry): the user wants to SEE
  ComfyUI work in the preview pane on the right and steer it, not just receive files.
- Any request to run, edit, inspect or debug a ComfyUI workflow with the `comfy_*` tools of the comfy-recipe plugin.
- If the user has a personal ComfyUI skill (paths, workflow catalog, model notes), load it too — it overrides the
  generic defaults here.

## Two ways to run — pick the right one
| | Visible (default in a ComfyUI session) | Headless |
|---|---|---|
| How | By hand in the pane with `drive_preview`: type the prompt, click Run | `comfy_run` → `comfy_result` |
| User sees | prompt change, progress, result on the canvas | only the result in chat |
| Use for | interactive work, anything the user watches or steers | batches, seed sweeps, exact timing, no window wanted |

**Why:** ComfyUI streams progress/results only to the browser tab that queued the job (`client_id`). A job queued
through the API can never appear in the open window. In a ComfyUI session never call `comfy_run` unless the user
says "headless" or "API". Small models tend to pick the shortest tool — follow the recipe instead.

## Comfy Recipe's own ComfyUI (first run, start, stop)
Comfy Recipe installs and runs its OWN ComfyUI, separate from any other ComfyUI on the machine (those keep working and
can run at the same time, e.g. on another port/GPU). The kickoff tells you the phase; `comfy_setup` does the work:
| phase | what to do |
|---|---|
| first_run | Explain in 3-4 plain lines (beginner-friendly), then ONE clarify form: new install (recommended) vs existing; GPU (only if `ask_gpu`); share models of `existing_installs` (only if any); install folder (default `<Documents>/ComfyRecipeEnv`, or `alternative_dir` first when Documents is cloud-synced; a typed path → `check_dir` first). |
| installing | `comfy_setup action=status wait_s=300` in a loop; one short line per finished step (x/7); on `error` show the error + `log_tail` and offer a retry. |
| stopped | `comfy_setup action=start` (waits until it answers), then open the pane. |
| install_missing | The install was deleted or moved. One line saying so, then the first-run form with an extra choice "I moved it" → ask the folder → `comfy_setup action=adopt dir=<it>` → `start`. If the kickoff says the old ComfyUI still runs, `comfy_setup stop` first. |
| running | Normal session start (below). |
- `comfy_setup action=install` returns at once; the install runs in the background (about 6 GB, 5-20 min; uv, Python,
  ComfyUI latest release, PyTorch for the GPU, ComfyUI-Manager). It survives the chat ending: a later session resumes
  with `status`.
- Shared models: the new install READS the chosen installs' model folders via its `extra_model_paths.yaml`; nothing is
  copied and new downloads (Manager, template models) go to its own `ComfyUI/models/`. Delete that yaml to stop sharing.
- Moving workflows: drag a workflow `.json` (or a PNG/WebP made by ComfyUI) into the window - the graph opens exactly
  as saved; Ctrl+S puts it in the Workflows list. Tell new users this once, after the first start.
- `start`/`stop` only ever touch this plugin's install (pid or the process serving its port, checked against the
  install folder). `reset` forgets the choice, deletes nothing; `adopt dir=<folder>` uses that install again (also
  after the user moved it: paths are rewritten, the venv is tested; a move to another drive may break the venv → new
  install). To remove the install, the user stops it (`comfy_setup stop`, Windows locks a running install) and deletes
  its folder; the next session reports `install_missing`.
- Closing Hermes stops this ComfyUI (setting `stop_with_hermes`, default on): a small watchdog started with it watches
  the Hermes desktop app (or the Hermes process when there is no desktop app) and runs `stop` when it is gone. The next
  session starts it again (phase `stopped`). Other ComfyUI installs are never touched.

## Post-install setup and tutorial
After a fresh managed installation opens in the pane, call `comfy_onboarding action=status` BEFORE the ordinary
question. Ask ONE clarify form with independent choices for missing node packs now (recommended) vs on use,
missing models on use (recommended) vs now with verified missing-download GB, and - only when `proposal.settings` is
not empty - a separate settings question (e.g. turn on Nodes 2.0). Skip categories already available; unknown
sizes/inventory remain explicit. Then make ONE call:
`comfy_onboarding action=preferences nodes=now|on_use models=now|on_use settings=apply|skip`.
The plugin does the approved work itself and its `instruction` lists the remaining steps in order. With node packs
approved they are always:
1. Post each `progress_card` MEDIA line once (models and/or nodes).
2. `comfy_downloads action=nodes_status wait_s=300`, repeated until `state=done` (pip dependencies take minutes).
   Do NOT open the Nodes Manager, do NOT search packs there, do NOT click `Install All` - the packs are already queued.
3. `comfy_setup action=restart` (one call). Never the Manager's `Apply Changes` button.
4. `desktop_preview action=close`, then `action=open` with the same url (loads the new nodes and Nodes 2.0), then
   select `Comfy Recipe/RCP_qwen_image_2_1_t2i.json` again.
5. `comfy_onboarding action=status refresh=true` -> `proposal.node_packs` must be empty.
6. `comfy_onboarding action=tutorial`, then load `comfy-recipe:first-image-tutorial`.
`state=error` on the node card names the packs that failed: show it and offer one retry with
`comfy_downloads action=install_nodes`. Settings only (no packs): step 4 is enough, no restart.
Do not ask what the user wants to do until tutorial success, explicit skip, or the next distinct Recipe session.
`/comfy tutorial` replays the first-image lesson at any time; “tutorial” and “skip tutorial” also work in Recipe chats.
Only the first-image lesson exists. The reusable `comfy-recipe:qwen-image-2-1-prompting` skill writes prompts in
Hermes, leaving the graph's extra model-based enhancer off. Returning/legacy installs are not forced into onboarding.

## Procedure: open a ComfyUI session
In the desktop app the plugin does steps 1–2 itself at the kickoff (it checks ComfyUI, opens the pane and hands you the
instance facts), so the opening turn is just step 3 + the card. Load this skill on the first real request. Without the
plugin's kickoff facts, do all steps:
1. `comfy_instances`.
   - `action_required` in the result → do exactly that (for the plugin's own install it says `comfy_setup action=start`).
     A user-chosen existing ComfyUI that is not running → reply only:
     "No ComfyUI backend is running. Please start your ComfyUI backend, then tell me when it is up."
     No tips on how to start it, never start it yourself, don't open the pane. When the user says it's up, redo step 1.
   - `switched` in the result → the remembered instance was down; mention the switch in one line.
2. `desktop_preview {"action":"open","url":"<active url>","label":"ComfyUI"}`.
3. ONE `drive_preview {"action":"elements","max":5}` to confirm control; its result carries the page title
   `<workflow name> - ComfyUI` (leading `*` = unsaved edits). If refused ("only takes actions in the session the user
   is looking at"): ask the user to click into this chat, retry once.
4. Report instance, GPU and active workflow. With `--cuda-device N` ComfyUI sees only that GPU as `cuda:0`: take
   `cuda:N` from `argv`/`configured_gpu` and the VRAM from `devices[0]`. If the first `elements` call returns 0
   elements while the title is just `ComfyUI` (still loading), use `desktop_preview read` for the active workflow. For fresh managed installs follow onboarding next_step above; for returning sessions use the normal ready card and wait.

## Procedure: work in the window
Act as a graph-editing assistant: modify the user's current workflow in place by default.
Adding/removing a node, reconnecting a link, or adding a reference image is a small in-place edit, not a new workflow.
For example, if `RCP_qwen_image_2_1_i2i` has only one Load Image and the user supplies two images, add a Load Image
node and connect its IMAGE output to the Image Edit subgraph's `image_2` input in that same graph.
Duplicate only for substantial restructuring (many coordinated edits, including edits inside group/subgraph nodes),
or when the user explicitly asks for a copy. Explain a substantial fork before creating it. Missing inputs, a dirty
`*` tab, and tooling friction do not justify duplication. Preserve the current unsaved state; if tools cannot do the
requested in-place change safely, explain the limitation instead of silently substituting a saved/bundled graph.
Follow `references/pane-recipe.md` step by step (open workflow → prompt → numbers/dropdowns → images → Run → result).
- The user may work in the window too (open workflows, select or edit nodes) to show what they want or ask about the
  graph: re-read the part of the window concerned before acting or answering — never assume its earlier state.
- Keep `drive_preview elements` calls rare: every call flashes a box over each reachable element (the app's watch
  overlay). Read the `delta` each click/type returns instead of re-scanning.
- Prompt, numbers, seeds and Load Image files are ALWAYS changed in the window, never through the JSON. A widget that
  vanished after a view change is hidden by the zoom: `Nodes` tab → `Locate node on canvas` (pane-recipe step 2).
- **Match the loaders to the media.** When the user supplies images/videos/audio, the graph must end up with exactly
  one connected Load Image / Load Video / Load Audio per item: add the missing ones next to the existing loaders (same
  column, free space), delete extras (select -> `Delete Selected Items`), connect each to the right socket
  (`image_N`, `ref_image_N`, `ref_video_N` + `ref_video_audio_N`...). Never silently drop an attached file or leave a
  stale loader wired. Procedure: `references/pane-recipe.md` §1b.
- Adding/deleting nodes and setting values happen visibly in the window. `drive_preview` cannot drag, so a wire can
  only be made through the API-mode wiring fallback (`references/workflow-json-editing.md`, "API-mode wiring"):
  backup, save the tab from the window, edit only nodes/links on disk, close + reopen the tab, verify the sockets.
  The user gave standing consent for this when it is used to add/delete/connect loaders; any other structural JSON
  edit still needs their OK. It keeps the same workflow identity and is never permission to fork the graph. Never
  claim a wire was dragged when it was not.

## Procedure: use the shared workflow library
- Native skills stay in the plugin; a skill may use zero, one, or several shared workflow IDs. There is no separate
  recipe engine. Do not copy workflows into skill folders.
- `comfy_workflows action=library` lists bundled IDs offline. Managed startup adds all five definitions to the
  `Comfy Recipe/` folder; dependencies are not installed by copying JSON.
- Before using one, follow `references/workflow-library.md`: `comfy_workflows action=check`, then propose its
  `setup_proposal` — ALL missing node packs, models and settings (e.g. Nodes 2.0) — in ONE clarify form; on OK run
  its `window_steps` in order (`comfy_downloads action=install_nodes`, `action=start`, `comfy_workflows
  action=apply_settings`, `comfy_setup action=restart` if packs were added, reopen the pane), re-check. Preserve
  working copies and open/run visibly. A modified working copy is not certified by a preflight report about the
  bundled revision.

## Procedure: propose a template as a starting point
When the user describes something new ("I want to turn a photo into a 3D model", "a video with sound"), or none of
their workflows fits:
1. `comfy_templates action=search query="<task in a few words>"` (add `media` if obvious). Results come with a
   thumbnail, inputs, download size and readiness (`ready`, `missing_models`, `missing_node_types`).
2. Propose 2–4 options: one line each — title, what it does, ready or what's missing (model names + size), and show
   the thumbnails with `MEDIA:<thumbnail_path>`. Prefer ready ones; say clearly what the others would need.
3. On the user's choice, open it in the window (`references/pane-recipe.md`, step 7). It opens as a new unsaved tab with
   the template's example inputs; then adapt it with them (prompt, images) as usual.
4. Missing models or custom nodes: give the folder + download link; never download or install without the user's OK.
5. To keep it: `comfy_templates action=save name=<template>` (copy in the `templates` workflows folder — also makes it
   usable with `comfy_run`), or let the user save the tab.

## Procedure: headless run (user asked for it, or no window wanted)
1. `comfy_workflows action=describe workflow=<name>` → subgraph controls, LoadImage nodes, prompt target.
   Only `connected: true` LoadImage nodes feed the graph (for a subgraph: the first is `image_1`, usually the edit
   target, then `image_2`… in listed order). `connected: false` ones are loose and never run, even if they already hold
   the right file. Key `images` on the connected node ids. When the user names an input by description ("the
   footballer"), match it against these nodes and confirm with vision_analyze before wiring it.
2. `comfy_run workflow=<name> prompt="…" [seed] [images {node: path}] [overrides [{node, widget, value}]]`
   (`dry_run=true` first for a new workflow). Runs the SAVED file — unsaved tab edits are not included.
3. `comfy_result prompt_id=<id>` (call again while running) → per-stage timing, outputs, video contact sheet + audio level.
   `cached_nodes` with no sampling = ComfyUI reused a previous result: change seed/prompt.
   `warning: Partial run` from comfy_run = some output nodes failed validation, the others still ran.
4. Vision-check every output before reporting it. `comfy_workflows action=timings` before proposing speed changes.

## Procedure: prepare input media
`comfy_media` does trims, resizes, fps changes, first/last/Nth frame stills, N-second segments, joins and contact
sheets with ffmpeg - outputs next to the source, probed back, `to_input=true` to place them in ComfyUI `input/`.
Then reopen the pane once and pick the files visibly (pane-recipe §5). Long clips on 24 GB: `split seconds=3
chained=true` (each segment starts on the previous one's last frame), run each segment in the MiniMax mix graph with the
previous OUTPUT's `frames which=["last"]` as its first frame, then `join drop_first=1`. Full recipe, toggles and
measured pitfalls: `references/minimax-h3-mix.md`.

## Procedure: diagnose a slow workflow
See `references/performance-method.md`: per-stage breakdown from the ComfyUI log, VRAM vs model sizes, prompt
enhancers running to their token cap, reference-image count, LoRA re-patching, model swapping. Check the graph's own
speed switches (Lightning LoRA, duration) first; video length is a hard cliff on 24 GB. Stuck job / stop-restart /
free VRAM: `references/pane-pitfalls.md` ("Queue and stuck jobs").

## Rules
- For an approved disk wiring edit, back up first, then modify the same workflow identity/path and report exactly
  which fields changed. A backup is recovery data, not a duplicate working tab. Routine edits stay in the current graph;
  separate working copies are reserved for substantial restructuring or an explicit user request.
- Never start, restart or stop a ComfyUI yourself - except Comfy Recipe's own install, through `comfy_setup
  start/stop/restart`. Never click the Nodes Manager's `Apply Changes`: it restarts outside the plugin's tracking.
- Node packs and frontend settings are installed/applied by the plugin tools, never by hand in the Nodes Manager
  or the Settings dialog (weak models get lost there: search needs bare words, refs renumber after each install).
- Never save a tab (Ctrl+S) or close a tab with unsaved edits unless the user asks.
- Verify results with real tool output (vision check, ffprobe) — never just "done".

## References
- `references/workflow-library.md` — shared workflow copies, readiness and consented Manager installation.
- `references/pane-recipe.md` — literal tool-call recipe for the visible session (any model can follow it).
- `references/pane-pitfalls.md` — verified drive_preview behaviour on the ComfyUI frontend.
- `references/workflow-json-editing.md` — layout-preserving UI-JSON edits (links, subgraph inputs, inserting nodes).
- `references/performance-method.md` — how to find where the time goes and what to try first.
- `references/minimax-h3-mix.md` — MiniMax H3 mix graph: first/last-frame toggles, placeholder, chained 3 s segments.

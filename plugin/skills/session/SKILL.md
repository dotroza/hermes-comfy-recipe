---
name: session
description: "Use when driving ComfyUI live in the Hermes preview pane (Comfy Live)."
version: 0.2.0
author: dotroza
license: MIT
metadata:
  hermes:
    tags: [comfyui, preview-pane, live-session, workflows, image-generation, video-generation]
    related_skills: [comfyui]
---

# Comfy Live — drive ComfyUI in the window next to the chat

## When to Use
- A chat that starts with `[ComfyUI session]` (opened from the **Comfy Live** sidebar entry): the user wants to SEE
  ComfyUI work in the preview pane on the right and steer it, not just receive files.
- Any request to run, edit, inspect or debug a ComfyUI workflow with the `comfy_*` tools of the comfy-live plugin.
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

## Procedure: open a ComfyUI session
In the desktop app the plugin does steps 1–2 itself at the kickoff (it checks ComfyUI, opens the pane and hands you the
instance facts), so the opening turn is just step 3 + the card. Load this skill on the first real request. Without the
plugin's kickoff facts, do all steps:
1. `comfy_instances`.
   - `action_required` in the result → do exactly that and stop. None running → reply only:
     "No ComfyUI backend is running. Please start your ComfyUI backend, then tell me when it is up."
     No tips on how to start it, never start it yourself, don't open the pane. When the user says it's up, redo step 1.
   - `switched` in the result → the remembered instance was down; mention the switch in one line.
2. `desktop_preview {"action":"open","url":"<active url>","label":"ComfyUI"}`.
3. ONE `drive_preview {"action":"elements","max":5}` to confirm control; its result carries the page title
   `<workflow name> - ComfyUI` (leading `*` = unsaved edits). If refused ("only takes actions in the session the user
   is looking at"): ask the user to click into this chat, retry once.
4. Report instance, GPU and the active workflow's name only — do not inspect the workflow yet. Then wait.

## Procedure: work in the window
Follow `references/pane-recipe.md` step by step (open workflow → prompt → numbers/dropdowns → images → Run → result).
- The user may work in the window too (open workflows, select or edit nodes) to show what they want or ask about the
  graph: re-read the part of the window concerned before acting or answering — never assume its earlier state.
- Keep `drive_preview elements` calls rare: every call flashes a box over each reachable element (the app's watch
  overlay). Read the `delta` each click/type returns instead of re-scanning.
- Wiring changes (drag a link, add a node) cannot be done in the pane: edit the workflow JSON on disk
  (`references/workflow-json-editing.md`, back up first), then close + reopen the pane.

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

## Procedure: diagnose a slow workflow
See `references/performance-method.md`: per-stage breakdown from the ComfyUI log, VRAM vs model sizes, prompt
enhancers running to their token cap, reference-image count, LoRA re-patching, model swapping.

## Rules
- Never overwrite the user's workflow file: write a sibling copy or a `.bak-<purpose>.json` backup first, then
  report exactly which fields changed.
- Never start, restart or stop ComfyUI yourself.
- Never save a tab (Ctrl+S) or close a tab with unsaved edits unless the user asks.
- Verify results with real tool output (vision check, ffprobe) — never just "done".

## References
- `references/pane-recipe.md` — literal tool-call recipe for the visible session (any model can follow it).
- `references/pane-pitfalls.md` — verified drive_preview behaviour on the ComfyUI frontend.
- `references/workflow-json-editing.md` — layout-preserving UI-JSON edits (links, subgraph inputs, inserting nodes).
- `references/performance-method.md` — how to find where the time goes and what to try first.

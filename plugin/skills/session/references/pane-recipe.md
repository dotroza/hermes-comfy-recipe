# Visible session — literal recipe

Use in every `[ComfyUI session]`. The user must SEE each change happen in the ComfyUI window on the right.
Run every step with the exact tool calls below; read each result before the next call.
`<root>` = the instance's ComfyUI folder (`root` in `comfy_instances`); `<url>` = its URL.

## 0. (Re)open the window
1. `comfy_instances` → active `url`. `action_required` → do exactly that and stop. `switched` → say so in one line.
2. `desktop_preview {"action":"open","url":"<url>","label":"ComfyUI"}`
3. `drive_preview {"action":"elements","max":5}` — confirms control and gives the page title.
   0 elements → `terminal sleep 4`, retry. Refused → ask the user to click into this chat, retry once.

## 1. Open the right workflow
- The title `<name> - ComfyUI` names the active tab (`*` prefix = unsaved edits).
- Another workflow: `drive_preview {"action":"click","ref":"<Workflows sidebar button ref>"}` →
  `drive_preview {"action":"click","selector":"[title='<folder name>']"}` (only if it sits in a folder) →
  `drive_preview {"action":"click","selector":"[title='<workflow name without .json>']"}`.
  Sidebar tree items have no refs — the `[title='…']` selector is the reliable way. Check the returned title.

## 2. Find what you need on the canvas
- `drive_preview {"action":"elements","max":150}` once, when you actually need refs. Use every ref it already gives you
  (prompt textarea, Run) BEFORE moving the view.
- Do NOT use `Fit View` to find a node: on a big graph it zooms out below ~20 % and ComfyUI stops drawing node widgets —
  the prompt textareas and file buttons vanish (the delta lists them under `removed`). That is the zoom, not a broken
  window; never switch to editing the JSON because of it.
- Reach any node at a readable zoom:
  1. With nothing selected, the right panel has a `Nodes` tab: `click` it → each node is listed by title with a
     `Locate node on canvas` button right after it (refs follow the list order).
  2. `click` that node's `Locate node on canvas` → the canvas zooms to ~150 % with the node in the centre.
  3. `click` with selector `#graph-canvas` (centre = that node) → it is selected; its widgets appear in the delta /
     right panel (`INPUTS`; a Load Image node shows its file button, labelled with the current file name).
- Hidden widgets of a node: `click` the node div → `Node Info` → `Parameters` tab; the delta lists them, plus the node
  label with its `#<node id>` badge (text, not a DOM id — never build selectors from it).

## 3. Set the prompt (do this first — it is visible right after the page opens)
1. Find the prompt **textarea** (role `textarea`, e.g. `txt-positive-prompt`) inside the node that holds the main
   prompt. Not in the list → step 2 (Locate the node), never the JSON.
2. To READ the current text: `elements` truncates textarea values and `desktop_preview read` omits them. If the tab has
   no `*`, read the saved workflow JSON (`<root>/user/default/workflows/…/<name>.json`) and take that node's
   `widgets_values` (match by the `#<id>` badge). Never call a field empty from a truncated value.
3. `drive_preview {"action":"type","ref":"<textarea ref>","text":"<full new prompt>"}` — `type` REPLACES the whole field.
4. Never `press` key combinations (Ctrl+A, Ctrl+End…): they insert literal characters into the prompt.

## 4. Numbers and dropdowns
- Number widgets: `Decrement` / `Increment` buttons around the value; for a seed prefer `Randomize Value`.
- Dropdowns (role `combobox`): click the combobox ref, then the `opt-…` ref. Confirm from the delta.

## 5. Change an input image (Load Image)
1. The file must be in `<root>/input/`. Before copying an attachment there, compare its md5 with existing input files —
   if the same image is already there under another name, use that name.
2. Expose the node first (step 2 "Hidden widgets"): a label like "IMAGEMASKLoad Image" may already hold a file.
3. Check in the JSON wiring that this node really feeds the socket you mean (`workflow-json-editing.md`, "Read the wiring").
4. `click` the file button (label = current file name) → in the picker
   `drive_preview {"action":"type","ref":"<Search … input ref>","text":"<exact file name>","submit":true}` (Enter = top result).
   No file button in the list → step 2 (Locate the node, then select it).
5. Verify from the delta: the file button label and the node label (file + dimensions) changed.
   The picker only sees newly copied files after a fresh page (close + open, not in-page reload) — so copy ALL needed
   images first, reopen the pane once, then set the prompt and the images in the window.
6. Last resort only (picker tried at a readable zoom and failed twice): tell the user, back up the JSON, set that
   LoadImage's `widgets_values[0]`, close + reopen the pane. Never edit the JSON for the prompt, a number or a seed.

## 6. Run and report
1. `drive_preview {"action":"click","ref":"<Run button ref>"}` — the page title shows `[N%]` while it runs.
2. Error refs in the delta (`View details`, `Error`) → read the message, fix the widget in the window, Run again.
3. Wait: `terminal sleep 10` between checks (videos: longer); `GET <url>/queue` is empty when done.
4. Result: `comfy_result {"prompt_id":"latest"}` (read-only; works for jobs queued from the window) → timing + output
   paths. Vision-check images; videos: contact sheet from `comfy_result`. Reply with one timing line + `MEDIA:<path>`.

## 7. Open a template
1. `drive_preview {"action":"click","ref":"<Templates button ref>"}` (left bar, label "Templates").
2. `drive_preview {"action":"type","ref":"<Search ... input ref of the Templates dialog>","text":"<template title>"}`.
3. `drive_preview {"action":"click","selector":"[data-testid=\"template-workflow-<template name>\"]"}` — the selector is
   `window_card_selector` from `comfy_templates`. The cards are not in the `elements` list; the selector is the way.
4. The template opens as a new tab named after it (check the page title). A "Warning … is missing" banner = a model
   file is missing: report it with the download link from `comfy_templates`, don't download without the user's OK.

## Do not
- Do not call `comfy_run` in a ComfyUI session unless the user says "headless"/"API".
- Do not change prompts, numbers, seeds or images by editing the workflow JSON: they are always reachable in the window
  (step 2). JSON edits are for wiring only (`workflow-json-editing.md`).
- Do not use `browser_*` / `browser_exec` tools: they drive a separate, invisible browser, not the user's window.
- "No Hermes Desktop window answered" / "only takes actions in the session the user is looking at" = the user is in
  another chat or tile. Ask them to click into this chat, wait for their reply, retry. Do not work around it.
- Do not click with broad CSS selectors (`[data-testid] button` hits the first button on the page). Use refs.
- Do not save tabs or close tabs with unsaved edits unless asked.

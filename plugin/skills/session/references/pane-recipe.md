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
- Edit the current workflow in place. Treat the user's selected graph as the workspace, including its unsaved edits.
  A missing Load Image input means add the node and connect it to the next appropriate `image_N` socket in this graph.
  Duplicate only for substantial restructuring (many coordinated changes including group/subgraph internals), or when
  the user explicitly asks. Do not fork merely because an input is missing or the current tab is dirty.
- Node/link manipulation uses visible controls first. Wires cannot be dragged with `drive_preview`; make them with the
  API-mode wiring fallback (§1b + `workflow-json-editing.md`), never by duplicating a saved workflow. It preserves live
  state and keeps the same workflow identity.
- The title `<name> - ComfyUI` names the active tab (`*` prefix = unsaved edits).
- Another workflow: `drive_preview {"action":"click","ref":"<Workflows sidebar button ref>"}` →
  `drive_preview {"action":"click","selector":"[title='<folder name>']"}` (only if it sits in a folder) →
  `drive_preview {"action":"click","selector":"[title='<workflow name without .json>']"}`.
  Prefer tree refs when returned. On newer frontends a folder has no title: click
  `[role='treeitem'][aria-label='<folder name>']`, then ArrowRight on its returned ref if still collapsed.
  A file can be targeted by `[data-testid$='/<folder name>/<workflow name>.json']`; scope the folder so a same-named
  source at the root is not opened instead. This fallback was verified with frontend 1.57.6. Check the returned
  title AND URL UUID to distinguish original files from distributed copies.

## 1b. Match the Load nodes to the user's media (add / delete / connect)
Verified on the MiniMax r2v graph, now `RCP_video_minimax_h3_r2v` (cat sheet + photo + 3 s video): every attached item gets its own connected
loader; extras are removed. Count what the request needs, then what the LIVE graph has:
1. Read the live wiring, not the bundled file: a dirty tab may differ (it had 3 Load Images where the file had 2, and
   no Load Video the agent thought it had added). Either save the tab (step 5 below) and read the links, or in the
   window hover `[data-node-id="<id>"] .lg-slot:nth-of-type(N)` (the delta names the socket) and test
   `...:nth-of-type(N)[class*='connected']` (match = wired). Autogrow sockets shift the index by one after a reload:
   re-hover to read the label before trusting N.
2. Add a missing loader visibly: Node Library -> `type` its name in `Search Nodes...` -> click the category tree to
   expand it -> click the node treeitem (the click may report "pointer never reached the page" yet still add the node;
   check the canvas before clicking again - a second click adds a duplicate). Close the sidebar before touching the
   canvas. Delete an extra: select it -> `Delete Selected Items`.
3. Try the wire in the window only if the frontend offers a click gesture; click output then input does NOT connect
   (verified, Nodes 2.0, frontend 1.57.6). Move on to API-mode wiring instead of retrying.
4. API-mode wiring (standing user consent for loader add/delete/connect; `workflow-json-editing.md`):
   back up the disk file -> `Menu` -> hover `File` -> `Save` (visible; the title loses its `*`) -> back up the saved live
   state -> in the file delete the extra loader + its links, add the new loader at the removed one's `pos` or in the
   loaders' column, add the links, set every touched `link`/`links`, bump `last_node_id`/`last_link_id` -> close the
   (clean) tab -> Workflows sidebar -> folder treeitem -> file -> verify every socket as in 1.
5. Then set the files, prompt and numbers in the window as usual (§3-§5). Prompt tags follow connection order:
   `<Picture 1>` = `ref_image_0`, `<Video 1>` = `ref_video_0` (MiniMax H3). Wire the video's `audio` to
   `ref_video_audio_0` when the clip's sound should carry over.

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
- Nodes 2.0 often lists a number only as `Decrement`/`Increment` with no value. Reveal it: `click` selector
  `[data-node-id="<id>"] input` (one-widget primitives: click the node div) -> the delta adds a `spinbutton` ref ->
  `type` the number with `submit=true` -> click the input again to confirm. Prefer this over blind Increment clicks.
- A widget that is "off-screen" even after scrolling (switches, far nodes): click empty `#graph-canvas` to deselect ->
  `Nodes` tab -> `type` the node title in its `Search ...` -> hover `#graph-canvas`; the delta lists that node's
  widgets in the panel (e.g. `sw-value` for a Boolean) -> act on that ref.
- Dropdowns (role `combobox`): click the combobox ref, then the `opt-…` ref. Confirm from the delta.

## 5. Change an input image (Load Image)
1. The file must be in `<root>/input/`. Before copying an attachment there, compare its md5 with existing input files —
   if the same image is already there under another name, use that name.
2. Expose the node first (step 2 "Hidden widgets"): a label like "IMAGEMASKLoad Image" may already hold a file.
3. Check in the JSON wiring that this node really feeds the socket you mean (`workflow-json-editing.md`, "Read the wiring").
4. `click` the file button (label = current file name) → in the picker
   `drive_preview {"action":"type","ref":"<Search … input ref>","text":"<exact file name>","submit":true}` (Enter = top result).
   No file button in the list → step 2 (Locate the node, then select it).
   Newer frontends open an asset browser instead of a list: `type` into its `Search ...` input, then click
   `img[alt='<exact file name>']` (verified, frontend 1.57.6). Reach the file button through the right panel's
   `Nodes` tab search ("Load Image") when the node is off-screen.
5. Verify from the delta: the file button label and the node label (file + dimensions) changed.
   The picker only sees newly copied files after a fresh page (close + open, not in-page reload) — so copy ALL needed
   images AND videos first, reopen the pane once, then set the prompt and the media in the window. Same for the Load
   Video `video` combobox: click it -> `opt-<file>` ref (verified: a clip copied after page load was absent until the
   pane was reopened; the unsaved tab survived the reopen).
   Prepare media with `comfy_media` (never hand-written ffmpeg): `action=convert` (trim `start`/`duration` + resize
   `width`/`height` `mode=cover|fit|stretch` + `fps`, one pass; e.g. `duration=3.042 width=544 height=960 fps=24` = 73
   frames for a 3 s MiniMax run), `action=frames which=["first","last"]` for first/last-frame graphs, `action=split
   seconds=3 chained=true` for segment runs and `action=join drop_first=1` to stitch the results, `action=sheet` + vision to check. Outputs land
   next to the source; `to_input=true` copies them into `input/` (identical files reused) and returns `input_name`.
6. Picker failed twice at a readable zoom: tell the user and stop. Never set a LoadImage value in the JSON.
7. Switching from single-image to reference editing: re-read the current Nodes list first - a dirty working tab may
   no longer have the saved template's second Load Image. Never infer it from the bundled JSON or a previous run.
   If it is gone, keep the dirty tab and add a Load Image node visibly (session skill), or ask before opening a
   separate copy of the saved two-image template.
8. Before Node Info / Parameters, confirm the right panel's selected-node heading: clicking a DOM node wrapper can
   leave the old node selected. Use Nodes -> `Locate node on canvas` -> click `#graph-canvas` instead of re-clicking.

## 6. Run and report
1. `drive_preview {"action":"click","ref":"<Run button ref>"}` — the page title shows `[N%]` while it runs.
2. Error refs in the delta (`View details`, `Error`) → read the message, fix the widget in the window, Run again.
   `View details` opens Issues with a `Locate <node> - <widget>` button: click it, then fix the combobox there
   (verified: `Create Video - chroma_subsampling` = `none` is rejected by current ComfyUI -> `auto`).
   Before Run on a video graph, read the speed switches (`Boolean (Enable Lightning LoRA)`, `Float (Duration)`) and the
   values that will run (`GET <url>/queue` -> `queue_running[0][2]` right after Run).
3. Wait: `terminal sleep 10` between checks (videos: longer); `GET <url>/queue` is empty when done.
4. Result: `comfy_result {"prompt_id":"latest"}` (read-only; works for jobs queued from the window) → timing + output
   paths. Vision-check images; videos: contact sheet from `comfy_result`. Reply with one timing line + `MEDIA:<path>`.
   Long video runs outlast one `comfy_result` call (it may time out after ~7 min): read the step progress from
   `GET <url>/internal/logs/raw`, then call `comfy_result` again.
   Audio results: ffprobe duration + `volumedetect` + `silencedetect=n=-45dB:d=0.5`; report trailing silence
   (ACE-Step 1.5 XL, 15 s, seed 1: music ended at ~13 s).

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

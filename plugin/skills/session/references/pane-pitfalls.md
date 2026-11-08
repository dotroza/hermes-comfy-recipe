# drive_preview on the ComfyUI frontend — verified behaviour

- `drive_preview` acts only while this chat is the active, non-tiled session in the app. Refused → ask the user to
  focus this chat, retry once.
- `desktop_preview read` always works (page text, title). It omits textarea contents.
- Zoom hides widgets: below ~20 % (e.g. after `Fit View` on a big graph) ComfyUI stops drawing node widgets; textareas
  and file buttons leave the inventory (verified: present at 24 %, gone at 12 %). `Nodes` tab → `Locate node on canvas`
  zooms to ~150 % and brings them back; then `click` `#graph-canvas` selects the centred node.
- The zoom popover (`Zoom Controls`) traps the inventory (`same: N` with only its own refs) and `Escape` does not close
  it: `click` selector `#graph-canvas`.
- "No Hermes Desktop window answered" also appears briefly when this chat is not the focused one; it recovers once the
  user is back in this chat.
- `elements` returns refs that survive re-renders. With `full=true` it still answers with a delta (`same: N`).
  The list is viewport-culled: off-screen canvas nodes are missing until `Fit View`.
- Every `elements` call makes the app strobe a box over each reachable element (watch overlay); every action boxes its
  target. This is visual feedback, not the agent searching randomly. Keep `elements` calls rare.
- `type` replaces the whole field. `press` with key combos inserts literal characters into textareas.
- Textarea values in `elements` show only ~60 characters; verify full text from the saved JSON or the run result.
- Legacy sidebar tree items support title selectors. Frontend 1.57.6 folders instead support
  `[role='treeitem'][aria-label='<folder>']`; files expose `[data-testid$='/<folder>/<name>.json']`.
  Use a returned ref when available. Prefer a folder-scoped file selector when original and copied basenames match.
- After API file provisioning, click the sidebar's Refresh button (`[data-testid='workflows-refresh-button']`).
  Reopening the sidebar exposes this button if initially absent; a full pane reload is unnecessary and risks dirty tabs.
- Dropdowns: click the combobox ref, then the `opt-…` ref.
- Node hidden widgets: click node div → `Node Info` → `Parameters`. The `#<id>` badge in node labels is text, not a DOM id.
- Load Image picker: confirms as `changed` deltas (file button label, node label with dimensions).
- In-page reload keeps stale workflow and input-file lists: use `desktop_preview close` + `open` (check for `*` tabs first).
- Closing a tab with edits: hover the tab → `Close` → `Close anyway` discards them — only with the user's OK.
- Running: the page title shows `[N%]`.
- Right after the pane opens, `elements` can return 0 elements or no page while ComfyUI loads (a few seconds): wait ~3 s, retry once.
- Properties-panel prompt textareas appear in `elements` only in some selection states: one call lists them, the next
  may not. Treat their absence as a view state, not a missing widget (Locate the node, pane-recipe step 2).

## Settings, Nodes 2.0 and the Issues tab
- Settings dialog (`Settings (Ctrl + ,)`): each setting is a switch/combobox with selector `#<setting id>` (dots
  escaped, e.g. `#Comfy\.VueNodes\.Enabled` = "Modern Node Design (Nodes 2.0)") and its `value` in the delta; no search
  needed, close with `Close dialog`. To only READ a setting use `GET <url>/settings` (an omitted key = frontend
  default) - never toggle a setting just to inspect it.
- Some widgets draw only in Nodes 2.0 (e.g. `ImageCompare`'s slider): a node that looks empty on the classic canvas is a
  setting problem, not a broken node. `Comfy.VueNodes.Enabled` is off on a fresh frontend. With it on, nodes are DOM
  cards and `elements` lists each node's widgets directly, so Locate-node detours are rarely needed.
- Right panel `Issues` tab (nothing selected): Missing Node Packs (`Install All`, per-row `Install` /
  `View in Manager`), missing models and missing media for the open tab. `desktop_preview read` returns it as text -
  cheaper than an `elements` call.

## Node packs and restarts
- `Install All` flips every row to `Installing...`: confirm completion from `<root>/custom_nodes/` and the tail of the
  ComfyUI log (`After restarting ComfyUI, please refresh the browser.`) instead of re-scanning the page.
- The first start after new packs installs their pip dependencies and ComfyUI-Manager re-launches ComfyUI once
  (`[ComfyUI-Manager] Restarting to reapply dependency installation.`). A start that reports "exited while starting"
  with that line is not a crash: poll `GET <url>/system_stats` (up within ~30-60 s), then search the log for
  `IMPORT FAILED` / `Cannot import`. Optional-feature errors inside a pack (no triton, no pip in a uv venv) are not
  import failures while the pack still logs its import time.

## Before the first run of a workflow
- Each input file answers `GET <url>/view?filename=<name>&type=input` with HTTP 200.
- Each model is listed by `GET <url>/models/<folder>` (diffusion_models, vae, loras, text_encoders, ...). The bare
  `GET <url>/models` returns folder names, not model files.
- `comfy_workflows list/describe` can report 0 matches for a workflow that exists: look in
  `<root>/user/default/workflows/` before calling it unsaved. A brand-new ComfyUI has no `workflows` folder at all
  until the first file is saved (the listing answers 404 "Directory not found").

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
  target. This is visual feedback, not the agent searching randomly. Keep `elements` calls rare. Never call `strobe`;
  do not poll `elements` while waiting or after handing control back to the user. Use `desktop_preview read` for
  read-only status, download/result tools for background progress, and reuse the refs/deltas already returned.
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

- Nodes 2.0 sockets are DOM elements: `[data-node-id="<id>"] .lg-slot` (inputs in order, `.lg-slot--output` for
  outputs); hovering one names it in the action text, `[class*='connected']` on it means wired. They never appear in
  `elements`. Clicking output then input does not create a link; `drive_preview` has no drag.
- The newest node is `[data-node-id]:last-child`; its id is not shown, read it from the saved file when needed.
- `press` needs a ref or selector; to close a menu press `Escape` on `body` with `allow_shortcut=true`, or on the
  open listbox's selector.
- Free VRAM visibly: `Menu` -> hover `Edit` -> `Unload Models and Execution Cache` (or `Unload Models`). Verify with
  `GET /system_stats`: `torch_vram_total` 0 = ComfyUI holds nothing; the rest belongs to other processes/display.
  The jobs panel `More options` menu only has `Clear job history`.

- `Menu -> File -> Save As` names the file relative to the CURRENT workflow's folder: typing
  `Local Recipe/<name>` from a tab in `Local Recipe/` creates `Local Recipe/Local Recipe/<name>.json` (the same folder-relative rule applies to `Cloud Recipe/`). Type only the
  name. To fix a misplaced file: close its clean tab, move the file on disk, Workflows sidebar `Refresh`, reopen.
- Off-screen widgets ("still off-screen after scrolling"): right panel `Nodes` tab -> type the node title in
  `Search ...` -> the panel shows that node's widgets (switches, file buttons, textareas) directly; act on them there.
- Number widgets with a value popup: click `[aria-label='<widget name>']` -> an input + `OK` appear -> `type
  clear=true` -> `OK`. A scroll over a canvas number widget silently changes it (seen: Load Video
  `select_every_nth` 1 -> 34): re-read numbers from `/queue` after Run when an error is unexpected.

## Queue and stuck jobs
- `comfy_setup restart` refuses while a job runs. `Cancel current run` in the window (toast "Execution has been
  interrupted") only lands at the next model-call boundary - minutes when one step is huge. Wait on `GET /queue` in a
  bounded loop. A job queued by an earlier page leaves Cancel disabled: with the user's OK `POST <url>/interrupt`.
- `0/N [... Model Initializing ...]` with the GPU at ~99 % = step 1 is computing (tqdm writes to the log only when a
  step ends), not a load hang. Give an ETA from measured s/step before stopping.
- First sampling step suddenly 10x slower than the previous run of the same graph (655 s/step vs 33 s/step) after
  several runs: cancel, `Menu -> Edit -> Unload Models`, Run again - it went back to 26-30 s/step. Model staging can
  also take 5-8 min before step 1 on a cold run; that is not a stall.
- `comfy_result` can time out (420 s) on long runs: read `GET /internal/logs/raw` for the `Prompt executed` line, then
  call `comfy_result` again.
- User asked to stop/restart and the queue still shows 1 running after ~5 min: `comfy_setup stop` -> `start` (~12 s)
  -> `desktop_preview close` + `open` -> `elements max=5`; the unsaved `*` tab is restored (verified twice). Do not
  re-run the same settings; propose the speed fix and ask.

## Settings, Nodes 2.0 and the Issues tab
- Change settings with `comfy_workflows action=apply_settings workflow=<ID>` (or `settings=apply` in setup
  preferences), never in the Settings dialog: the API write is verified, the dialog path is where models get lost.
  The open window keeps the old value until `desktop_preview close` + `open`. To only READ a setting use
  `GET <url>/settings` (an omitted key = frontend default).
- Some widgets draw only in Nodes 2.0 (e.g. `ImageCompare`'s slider): a node that looks empty on the classic canvas is a
  setting problem, not a broken node. `Comfy.VueNodes.Enabled` is off on a fresh frontend. With it on, nodes are DOM
  cards and `elements` lists each node's widgets directly, so Locate-node detours are rarely needed.
- Right panel `Issues` tab (nothing selected): Missing Node Packs (`Install All`, per-row `Install` /
  `View in Manager`), missing models and missing media for the OPEN tab only. `desktop_preview read` returns it as
  text - cheaper than an `elements` call. When the panel is not visible, the error overlay's `View details` opens it.
  Pack rows may first show raw registry ids without buttons: the registry lookup fills them in asynchronously, read
  again before deciding. Bundled workflows never need these buttons (`comfy_downloads action=install_nodes`).
- `[data-testid='missing-model-header-refresh']` exists only while the Issues panel is open: click the node's or the
  right panel's `Issues` first, then `Refresh`. Never click the panel's Download buttons (downloads go through tools).
- Models added on disk do not automatically clear the visible warnings. As soon as the current workflow's model
  downloads finish, click the Missing Models header Refresh (`[data-testid='missing-model-header-refresh']`), then
  use `desktop_preview read` to verify the warnings cleared. Do this before asking for a prompt, not only before
  Run. If warnings are already clear and the control is absent, no click is needed. Preserve dirty tabs/prompts;
  refreshing this list does not need a full page reload.

## Node packs and restarts
- Never install packs one by one in the Nodes Manager: its search only matches bare words (`Video`, not
  `ComfyUI-VideoHelperSuite`), Install-button refs renumber after every install, and a queued install never runs
  until the queue is started - packs silently stay uninstalled. `comfy_downloads action=install_nodes` avoids all of it.
- Completion = `comfy_downloads action=nodes_status` `state=done` (per-pack `pack_states` come from Manager's
  installed list). A Manager queue that went idle is not proof: check `pack_states`, then
  `comfy_workflows action=check ... refresh=true` after the restart.
- Restart = `comfy_setup action=restart`, never `Apply Changes`.
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

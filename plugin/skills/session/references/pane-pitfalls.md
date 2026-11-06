# drive_preview on the ComfyUI frontend — verified behaviour

- `drive_preview` acts only while this chat is the active, non-tiled session in the app. Refused → ask the user to
  focus this chat, retry once.
- `desktop_preview read` always works (page text, title). It omits textarea contents.
- `elements` returns refs that survive re-renders. With `full=true` it still answers with a delta (`same: N`).
  The list is viewport-culled: off-screen canvas nodes are missing until `Fit View`.
- Every `elements` call makes the app strobe a box over each reachable element (watch overlay); every action boxes its
  target. This is visual feedback, not the agent searching randomly. Keep `elements` calls rare.
- `type` replaces the whole field. `press` with key combos inserts literal characters into textareas.
- Textarea values in `elements` show only ~60 characters; verify full text from the saved JSON or the run result.
- Sidebar workflow tree items have no refs: click via `[title='<folder>']` then `[title='<workflow name>']`.
- Dropdowns: click the combobox ref, then the `opt-…` ref.
- Node hidden widgets: click node div → `Node Info` → `Parameters`. The `#<id>` badge in node labels is text, not a DOM id.
- Load Image picker: confirms as `changed` deltas (file button label, node label with dimensions).
- In-page reload keeps stale workflow and input-file lists: use `desktop_preview close` + `open` (check for `*` tabs first).
- Closing a tab with edits: hover the tab → `Close` → `Close anyway` discards them — only with the user's OK.
- Running: the page title shows `[N%]`.

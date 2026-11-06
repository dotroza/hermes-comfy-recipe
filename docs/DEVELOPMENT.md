# Developing Comfy Live — Hermes mechanisms that matter

Verified while building the plugin (Hermes desktop, Nov 2026). Read before changing the Python half, desktop half or packaging.

## Reload rules
- Python half (tools, hooks, skills): the Hermes backend imports plugins ONCE per process — new chat sessions keep the
  old code. Tell the user to fully quit (tray → Quit) and reopen Hermes. Never claim "applies in the next session".
- Desktop half (`desktop/plugin.js`): Ctrl+K → *Reload desktop plugins*; the desktop half of a combined plugin is OFF by
  default → Settings → Plugins → enable it.
- `hermes plugins validate <plugin dir>` must pass: every registered hook must be listed in `provides_hooks`, tools in
  `provides_tools`. Validation regenerates `__pycache__` — keep it gitignored.

## Hidden instructions (pre_llm_call)
- `ctx.register_hook("pre_llm_call", fn)`; fn gets `user_message, conversation_history, is_first_turn, session_id, ...`
  and returns `{"context": str}`. The context is appended to what the MODEL receives for that turn only, never shown in
  chat — that is how a one-line visible kickoff carries a long instruction block.
- Inject the start instructions only on the kickoff turn and a short rules block on every later turn of a session whose
  FIRST user message starts with the marker (checking only the current message misses later turns).
- Tell the model the text after the marker is decoration, otherwise it answers it.

## Session title after the first real request
- Hooks run BEFORE Hermes' turn-start titling. Kickoff turn: `set_auto_title(sid, "ComfyUI session <date>", source="llm")`
  (equal/lower ranks can't overwrite it; titles must be unique → fall back to a suffixed variant on ValueError).
  First real request: `set_session_title(sid, "")` (user-rank clear) if the title still starts with the placeholder →
  Hermes titles that request immediately.
- Uses `hermes_state_registry.acquire()/release()` — a private import the validator warns about; keep it best-effort.

## Settings
- `config_schema:` in plugin.yaml renders a form under Settings → Plugins; read with `ctx.get_config(key)`
  (stored in config.yaml `plugins.entries.<id>.settings`). Push values into the Hermes-independent core per call.
- Desktop half reads them via `host.request('plugins.manage', {action:'list'})` → `plugins[].settings_schema[]`
  (`{key, value, default}`); race it with a short timeout so the kickoff never hangs.
- Bundle a skill with `ctx.register_skill("<name>", path_to_SKILL.md)` → available as `<plugin>:<name>`.

## Desktop half
- Sidebar entry = `ROUTES_AREA` page + `SIDEBAR_NAV_AREA` item with `order` (Kanban = 50 → 60 sits under it); the page's
  effect calls `ctx.runAction('session.new')` then retries `host.composer.submit(null, text)` (false until the new
  composer mounts). The SDK submit cannot send hidden turns — keep the visible kickoff short instead.
- Only the agent-opened preview pane is drivable by `drive_preview`; a plugin iframe would be view-only.

## ComfyUI endpoints worth using
- `GET /system_stats` → `system.argv[0]` is the full path of `main.py` (= ComfyUI root; a `<Data>/Packages/<pkg>` root
  reveals a portable StabilityMatrix data dir), plus devices and launch args.
- `GET /history?max_items=1` → last finished job from ANY client (window runs too); `/queue` for the running one.
- `GET /internal/logs/raw` → `{entries:[{t: local ISO time, m: chunk}]}` — log without disk access (tqdm bars arrive
  as `\r`-separated chunks; concatenate then split).
- Jobs queued via API are never shown in a browser tab (events go only to the queuing `client_id`).

## Repo hygiene
- Two plugins registering the same tool names cannot both be enabled — disable the old one before enabling a rename.
- Scan new public repos for personal refs (`grep -rniE "<username>|<project>|<port>"`) before publishing.

## Fast session start
- Port probing: on Windows a refused localhost connect takes ~2 s, so a sequential HTTP probe of 4 closed ports cost
  8 s. `comfy_client.port_open` (0.3 s TCP check) + `alive_many` (parallel) brought `comfy_instances` to ~0.3 s.
- The kickoff hook resolves the instance and opens the pane itself: `tools.desktop_ui.emit("preview.open",
  {"url", "label"})` routes to the window running the turn (needs `HERMES_UI_SESSION_ID` in the session env; check
  `desktop_ui.available()`). The model then gets the facts and only does one `drive_preview elements` before the card.
  Skills load on the first real request, not at kickoff. Private imports again - keep it best-effort with a fallback.
- Desktop half: read the motto in parallel with `session.new`, cache it, warm the cache at register.

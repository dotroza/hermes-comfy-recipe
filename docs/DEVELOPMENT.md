# Developing Comfy Recipe — Hermes mechanisms that matter

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

## Shared workflow library (0.4.0)
- `library.py` validates package paths/hashes and publishes only missing working copies under `Comfy Recipe/`, with
  overwrite disabled and exact target read-back. Different user JSON is protected; updates are explicit siblings.
- `core.setup_start` and the running-session fast path provision only the managed instance. Foreign instances require
  explicit `comfy_workflows action=install`. Runtime records live in `core.DATA/library/`, not the plugin package.
- Native `skills/*/SKILL.md` files register through `ctx.register_skill`. Optional
  `metadata.comfy_recipe.workflow_ids` references the shared catalog; no separate skill/recipe index exists.
- `dependencies.py` checks evidence without installing anything. Refresh schema after consented Manager installation.
- Batch readiness checks share `model_inventory` only for the lifetime of one report. Keys include backend URL,
  root and model folder; failures remain unknown and are retried on the next report. Do not introduce a long-lived
  inventory cache without download/restart invalidation. Both onboarding and bundled download proposals use this path.
- Proposals retain positive integer catalog `size_bytes` before doing HEAD lookups; unknown sizes still use the
  existing bounded metadata cache. Shared targets can inherit a known size from a later requirement with the same URL.
  The offline six-workflow fixture reduces folder requests from 25 to 6 and size lookups from 21 to 16; these are
  request budgets, not measured end-to-end startup timings. Regression tests live in `tests/test_setup_optimizations.py`
  and `tests/test_onboarding_dependencies.py`.
- Standard-library tests: `python -m unittest discover -s tests -v`; authoring details in `docs/WORKFLOW_LIBRARY.md`.

## Onboarding
- See `docs/ONBOARDING.md` for state, migration, replay and consent contracts.
- `onboarding.py` holds transactional records and backend image evidence; `onboarding_flow.py` adapts reports/instructions.
- `comfy_onboarding` receives calling-session identity through tool context. Do not accept session ids from model args.
- `/comfy tutorial` uses public command context and persists next-turn hook routing; no gateway injection grant is needed.
- New-install provenance is written by the installer; an absent onboarding record alone does not imply a fresh install.
- Test with `python -m unittest discover -s tests -p 'test_onboarding*.py' -v` and `test_tutorial_evidence.py`.

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

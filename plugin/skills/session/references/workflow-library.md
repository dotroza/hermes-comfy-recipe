# Shared workflows and on-demand dependencies

## Find and open a bundled workflow

1. `comfy_workflows action=library` lists stable workflow IDs and metadata without requiring a backend.
2. Managed ComfyUI startup adds five local JSON definitions under **Workflows → Local Recipe** and
   five cloud definitions under **Workflows → Cloud Recipe**. No models,
   custom nodes, media uploads, generation or paid requests happen as part of copying definitions.
3. On a foreign/existing instance, explain the destination and obtain consent before
   `comfy_workflows action=install`. Optional `workflow_ids` selects a subset; `[]` selects none.
4. Open the working copy by hand in the ComfyUI Workflows sidebar. Use the treeitem ref when present; otherwise the
   observed title selector. Keep all prompt/seed/number/media changes and every Run in the visible window.
5. The startup/install result reports each copy. `installed` means the exact target was read back and verified;
   `unchanged` means it already matches. An error is not a successful copy, even if other copies succeeded.

Cloud workflows require ComfyUI login and credits. Never embed credentials or infer login/credit readiness from
publication or node availability. Obtain explicit approval before a paid run. Exact filenames and stable IDs are
listed in the shipped catalog; preserve literal names, including `RCPcloud_t2s__elevenlabs_v4.json` and
`RCPcloud_ti2i_seedream-5-0-pro.app.json`. Existing working copies, tabs and drafts remain untouched.

## Check requirements before installing anything

Use `comfy_workflows action=check workflow=<stable ID>` (fresh backend schema by default; `refresh=false` explicitly
uses the cache). Read each dimension: core nodes, missing registered packs, unresolved providers, frontend helpers,
frontend `settings` (e.g. Nodes 2.0), selected model files, required input media, external programs, services,
compatibility and portability warnings. `execution_ready=not_tested` is deliberate: passing availability checks does
not prove a graph can run.

The report's `definition.scope=bundled_asset` identifies its basis. If `definition.working_copy=modified`, inspect the
actual open graph before relying on that report: user changes may introduce different requirements. `missing` means
the working copy has not been installed; `unknown` means it could not be inspected. Neither means the catalog is absent.
Do not treat missing core nodes as arbitrary custom packs; a compatible ComfyUI update needs separate consent
(`setup_proposal.blockers`).

## Fresh managed install: independent setup choices

Before the ordinary question, call `comfy_onboarding action=status`. Its proposal covers all ten graphs,
deduplicates files/packs and shows verified missing-download GB. Use one form with independent choices for nodes
now (recommended) vs on use, and models on use (recommended) vs now. Unknown sizes/manual files must remain explicit;
settings require separate consent in the same form. Record only submitted answers. Base installation is not consent.
Select `Local Recipe/RCPlocal_t2i_qwen_image_2-1.json` visibly before the form, even if browser storage from a previous
installation restored another graph. Keep other tabs/drafts. Use one short setup introduction, no inventory or generic
untested-execution disclaimer; put actionable blockers and security disclosures briefly in the relevant question.
The bulk-download option ends at `Download everything now (<verified GB>)` with no commentary after the size.
Submit the answers in ONE call: `comfy_onboarding action=preferences nodes=.. models=.. settings=apply|skip`. The
plugin installs approved packs through ComfyUI-Manager's API (every pack of all ten graphs, no graph switching, no
window clicks), queues approved models and writes approved settings. Follow its numbered `instruction`:
`comfy_downloads action=nodes_status wait_s=300` until `done` -> `comfy_setup action=restart` -> pane close + open ->
select text-to-image again -> `comfy_onboarding action=status refresh=true` (`proposal.node_packs` must be empty;
approved settings must leave `proposal.settings`; deferred models and user media may stay missing - do not require
aggregate `needed=false`) -> start the tutorial. When its models finish downloading, refresh
the Missing Models list immediately and verify that this workflow's warnings clear before asking for a prompt;
do not defer refresh until the user's next message. Preserve dirty tabs; no full page reload is needed.
If installation fails, offer retry/skip without claiming readiness or completion. Existing-user ordinary workflow use
still follows the per-workflow proposal below. Shared models are never copied and new downloads stay in our install.

## Set up a workflow: ONE proposal for packs, models and settings

`setup_proposal` in the check result is the whole to-do list. Propose it in ONE go, never pack-by-pack or
models-then-packs:

1. ONE `clarify` form (a single question, recommended choice first: "Install everything"; then "Only the node packs",
   "Not now"). In the question text list, grouped:
   - **Node packs** (`node_packs`): registry name + id, the node types they provide. Tested version when known;
     declared source versions are not proof of compatibility. Say once: custom nodes run third-party Python, a venv is
     not a sandbox, and a ComfyUI restart follows.
   - **Models** (`models`): file name, destination folder, size (`size_gb`), total `download_gb`. `models_without_url`:
     first search the existing installs for the EXACT filename (`existing_installs[].root/models`, the launcher's
     shared `Data/Models`). Found -> ask once: hard-link (recommended: same NTFS volume, no extra disk, `os.link`),
     copy, or leave out - even if the user chose not to share whole model folders. Never a similarly named variant
     (fp8 vs nvfp4...). Not found -> the user must supply it.
   - **Settings** (`settings`): label + `reason` (e.g. Nodes 2.0 because ImageCompare only draws in it).
   Mention blockers and needed input media in the same message, but they are not installable items.
2. On OK, run `window_steps` in this order (tools do the work; the window only shows the result):
   - **Packs:** `comfy_downloads action=install_nodes packs=[<node_packs ids>]` queues them in ComfyUI-Manager (same
     request as the Issues tab's `Install All`) and returns a live card; post it once. Then
     `comfy_downloads action=nodes_status wait_s=300` until `state=done`. Do not open the Nodes Manager, search packs
     or click `Install All` meanwhile. `state=error` lists the failed packs (`pack_states`): offer one retry.
     A pack outside the bundled catalog (the user's own workflow): `comfy_downloads action=watch_nodes`, then the
     Issues tab's `Install All` once, then the same `nodes_status` wait.
   - **Models:** `comfy_downloads action=start workflow_ids=[<ID>]` (background, resumable, live card).
   - **Settings:** `comfy_workflows action=apply_settings workflow=<ID>` writes them through ComfyUI's settings API
     and verifies the stored value (`failed` must be empty). Never toggle them by hand in the Settings dialog.
   - **Restart** (only if packs were installed): managed instance = `comfy_setup action=restart` (one call: refuses
     while a job runs, stops, starts, waits through the Manager's dependency re-launch). Never the Manager's
     `Apply Changes` (restarts outside the plugin's process tracking). Another launcher's instance: ask the user.
   - **Reopen:** `desktop_preview close` + `open` (also after settings only): an in-page `reload` keeps stale node
     lists and settings; unsaved tabs are restored by the frontend.
3. Verify: `comfy_workflows action=check workflow=<ID> refresh=true` -> `setup_proposal.needed` must be `false`
   (or only `models_without_url` left). If a pack's classes are still absent, say unavailable - not proven import
   failure - and check the ComfyUI log.

Unregistered/unresolved providers cannot go through `Install All` (registry-only Manager): stop and offer a reviewed
pinned Git/manual route requiring separate approval. Do not weaken Manager security or copy a foreign `custom_nodes`
directory. Any approved manual Python dependencies belong in this ComfyUI's environment, not Hermes.
Input media are user-provided unless explicitly bundled with redistribution permission. Source example filenames and
cached previews are not supplied images/videos. Review portability warnings before use or public release.

## Protect user copies

Publication never overwrites existing different JSON, including on first install. `conflict` preserves the user's file;
`update_available` preserves an earlier revision. Ask before `comfy_workflows action=install versioned=true` to create
separate versioned siblings. Siblings have independent tab identities. Never overwrite, delete or silently reload an
edited tab to force an update. Repeated installation must not duplicate identical files.

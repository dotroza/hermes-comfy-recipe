# Shared workflows and on-demand dependencies

## Find and open a bundled workflow

1. `comfy_workflows action=library` lists stable workflow IDs and metadata without requiring a backend.
2. Managed ComfyUI startup adds the six bundled JSON definitions under **Workflows → Comfy Recipe**. No models,
   custom nodes, media uploads, generation or paid requests happen as part of copying definitions.
3. On a foreign/existing instance, explain the destination and obtain consent before
   `comfy_workflows action=install`. Optional `workflow_ids` selects a subset; `[]` selects none.
4. Open the working copy by hand in the ComfyUI Workflows sidebar. Use the treeitem ref when present; otherwise the
   observed title selector. Keep all prompt/seed/number/media changes and every Run in the visible window.
5. The startup/install result reports each copy. `installed` means the exact target was read back and verified;
   `unchanged` means it already matches. An error is not a successful copy, even if other copies succeeded.

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

Before the ordinary question, call `comfy_onboarding action=status`. Its proposal covers all six graphs,
deduplicates files/packs and shows verified missing-download GB. Use one form with independent choices for nodes
now (recommended) vs on use, and models on use (recommended) vs now. Unknown sizes/manual files must remain explicit;
settings require separate consent in the same form. Record only submitted answers. Base installation is not consent.
Open each affected graph visibly to access its Issues panel; one graph does not list every pack in the library.
Perform only approved categories. Recheck via `comfy_onboarding action=status refresh=true`, then start the tutorial.
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
     the user must supply them - never substitute similarly named weights.
   - **Settings** (`settings`): label + `reason` (e.g. Nodes 2.0 because ImageCompare only draws in it).
   Mention blockers and needed input media in the same message, but they are not installable items.
2. On OK, do every step visibly in the window (`window_steps`, in this order):
   - **Packs:** right panel `Issues` tab -> `Missing Node Packs` -> `Install All` (one click installs every listed
     pack through ComfyUI-Manager). The frontend may show an extra row for frontend helpers whose workflow metadata
     only has an `aux_id` (e.g. `kijai/ComfyUI-KJNodes` with a `Search` button for SetNode/GetNode): it is the same
     pack as the registered row and needs no extra install. Watch the delta until the rows report installed.
   - **Models:** download each `models` entry to `<root>/models/<folder>/<name>` from its `url` (use the Issues tab's
     download control when it lists the file). Report progress per file; verify the size on disk afterwards.
   - **Settings:** `Settings (Ctrl + ,)` -> click the switch `window_selector` (e.g. `#Comfy\.VueNodes\.Enabled`,
     "Modern Node Design (Nodes 2.0)") -> confirm `value: checked` in the delta -> `Close dialog`. Takes effect at once.
   - **Restart** (only if packs were installed): queue must be idle. Do NOT click Manager's `Apply Changes` (it
     restarts outside the plugin's process tracking). Managed instance: `comfy_setup stop` then `start` — the first
     start after new packs may install their pip dependencies and let ComfyUI-Manager re-launch ComfyUI once; `start`
     waits through that and records the new process. Another launcher's instance: ask the user to restart it.
     Then `desktop_preview close` + `open` the pane (an in-page `reload` only reconnects and keeps the stale Issues
     panel); unsaved tabs are restored by the frontend.
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

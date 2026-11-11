# Skills and the shared workflow library

**Comfy Recipe** is the product. **Skills** are ordinary Hermes instruction files. **Workflows** are shared ComfyUI
UI-format graphs. A skill can use zero, one, or multiple workflow IDs; multiple skills can share the same workflow.
There is no separate recipe registry, execution engine, or recipe tool.

## Shipped workflows

Library 1.4.0 ships five local and five cloud workflows. Local stable IDs are unchanged.

| Stable ID | Working-copy path | Workflow |
| --- | --- | --- |
| `qwen-image-2-1-t2i` | `Local Recipe/RCPlocal_t2i_qwen_image_2-1.json` | Qwen Image 2.1 text to image |
| `qwen-image-2-1-i2i` | `Local Recipe/RCPlocal_ti2i_qwen_image_2-1.json` | Qwen Image 2.1 image editing |
| `ace-step1-5-xl-base` | `Local Recipe/RCPlocal_audio_ace_step1-5_xl_base.json` | ACE Step audio generation |
| `pixal3d-img-to-3d` | `Local Recipe/RCPlocal_i23d_pixal3d.json` | Pixal3D / TRELLIS.2 image to textured 3D mesh (GLB) |
| `minimax-h3-r2v-mix` | `Local Recipe/RCPlocal_r2v_video_minimax_h3.json` | Local MiniMax H3 reference to video with optional first/last-frame guides |
| `cloud-seedance-2-5-r2v` | `Cloud Recipe/RCPcloud_r2v_seedance2-5.json` | Seedance 2.5 reference to video |
| `cloud-seedance-2-5-t2v` | `Cloud Recipe/RCPcloud_t2v_seedance-2-5.json` | Seedance 2.5 text to video |
| `cloud-elevenlabs-v4-t2s` | `Cloud Recipe/RCPcloud_t2s__elevenlabs_v4.json` | ElevenLabs v4 text to speech |
| `cloud-gpt-image-2-6-ti2i` | `Cloud Recipe/RCPcloud_ti2i_gpt_image_2-6_sunburst.json` | GPT Image 2.6 text/image to image |
| `cloud-seedream-5-0-pro-ti2i` | `Cloud Recipe/RCPcloud_ti2i_seedream-5-0-pro.app.json` | Seedream 5.0 Pro text/image to image |

Cloud workflows require ComfyUI login and credits. Copying definitions or passing preflight does not verify login,
credit balance or provider execution and does not authorize paid runs. Obtain explicit approval before a paid run;
never embed credentials in the graphs or documentation.

Qwen text-to-image: Hermes lightly cleans the user's wording without imposing a pose, setting or palette;
Image Gen `refine_prompt` ON, 25 steps, Lightning disabled (strength 0). Qwen image editing: Hermes writes an
explicit change plus keep-list; `refine_prompt` OFF, 4 steps, Lightning ON. Preserve explicit user settings.

The MiniMax graph in this release uses local model loaders, not a paid API (w6a8 diffusion model + Qwen3-VL 8B
encoder through ComfyUI-ClipProj, Load Video from VideoHelperSuite). It replaces `minimax-h3-r2v` and
`minimax-h3-r2v-f2lf` (retired in library 1.3.0): two toggles give pure r2v, first-frame only, last-frame only or both. Availability of nodes/models does not
certify runtime compatibility or adequate hardware. The simplified Pixal3D graph needs two registered third-party packs:
KJNodes for frontend Set/Get wiring and ComfyUI-Easy-Use for `easy cleanGpuUsed`. Background removal uses
BiRefNet; SAM segmentation and Qwen image-to-text captioning have been removed. Inspect its preflight report
instead of assuming its dependencies are installed. (The Wan/SCAIL loop graph was retired in library 1.2.0.)
The canonical video filename is `Local Recipe/RCPlocal_r2v_video_minimax_h3.json`; the stable catalog ID remains
`minimax-h3-r2v-mix` for installed-revision tracking.

## Handoff to ComfyUI

The package owns `plugin/workflows/catalog.json` and one JSON per shared workflow. After the plugin-managed ComfyUI
answers, startup provisions working copies into **Workflows → Local Recipe** and **Workflows → Cloud Recipe** using ComfyUI's userdata API. This is
new-file provisioning, not hidden graph editing. It never downloads weights, installs custom code, uploads personal
media, queues a job, or restarts a backend. Existing/foreign installations require an explicit install action.

Before starting its own ComfyUI, Comfy Recipe deploys a dependency-free frontend helper under
`custom_nodes/hermes_comfy_recipe_startup/`. In a fresh browser workspace it seeds ComfyUI's native tab restore
pointers with all ten bundled workflows, **`Local Recipe/RCPlocal_t2i_qwen_image_2-1.json` first and selected**. Existing tab pointers,
drafts and legacy sessions are left untouched; later launches retain the user's selected workflow and tab order.
The helper does not edit workflow JSON, run a graph, or download models. An empty draft index created by ComfyUI
itself is not treated as prior user work. This startup helper is only deployed to the managed installation.

Agent tools:

- `comfy_workflows action=library`: offline catalog, IDs and dependency metadata.
- `comfy_workflows action=install`: provision missing working copies, never overwrite different user content.
- `workflow_ids=[...]`: install a subset. Omit for all ten; an empty list selects none.
- `versioned=true`: explicitly request separate versioned siblings with distinct internal identities.
- `comfy_workflows action=check workflow=<stable ID> refresh=true`: read-only requirements for the bundled revision.

Commands: `/comfy library`, `/comfy library install`, `/comfy check <stable ID>`.

Every created file is read back before success is reported. Per-copy statuses include `installed`, `unchanged`,
`conflict`, `update_available`, and `error`; partial progress remains retryable. A filename collision is never permission
to overwrite. New bundled versions are offered as siblings, not forced updates, even for an unmodified old copy.
Installation records use the existing profile-safe plugin data directory, keyed by instance/destination rather than
only a display name. Startup checks are cached within the process after full success; explicit install reconciles again.

Checks distinguish missing core types, missing registered packs, unknown providers, frontend-only helpers, selected
models, input media, executables and services. They do not invent import-failure or credential success. If the working
copy is modified, the report warns that bundled metadata may not describe the user's actual graph.

## Add a native skill

Create `plugin/skills/<stable-name>/SKILL.md`; its name must match the directory and its description must be nonempty.
It is registered with Hermes under `comfy-recipe:<stable-name>` after a full backend restart. Do not duplicate workflow
JSON inside skills. Optional plugin-specific metadata references existing shared IDs:

```yaml
---
name: image-editing
description: Use when editing an image with references.
metadata:
  comfy_recipe:
    workflow_ids:
      - qwen-image-2-1-i2i
---

# Image editing
Use the shared workflow's working copy. Set the target and reference images in the visible window.
```

A second skill such as `person-replacement` can reference the same `qwen-image-2-1-i2i` ID. A multi-stage skill can list
both `qwen-image-2-1-t2i` and `minimax-h3-r2v-mix`. A workflow-free troubleshooting skill omits `metadata.comfy_recipe`
completely or sets `workflow_ids: []`. No running ComfyUI is needed merely to load these instructions. Registration
checks names, package-contained paths and references; unknown IDs and malformed metadata are errors, not silent skips.
Only requested skills are loaded in full; discovery does not inject all skill bodies into each session.

## Capture and version workflows

1. Reconcile open tabs with saved files. Preserve unsaved edits and ask before saving/exporting them.
2. Freeze the selected source files before generating assets. The initial capture explicitly uses last-saved files;
   all six open unsaved tabs were left untouched.
3. Preserve UI format, node layout, groups, subgraphs, widget values, model choices and input filenames. Never convert
   to API format or silently repair graph wiring during capture.
4. Distributed top-level IDs use UUID5 URL namespace with
   `https://github.com/dotroza/hermes-comfy-recipe/workflows/<stable-id>` to isolate source/bundled tabs and the two
   MiniMax variants. Versioned sibling publication uses its own ID derived from stable ID and version.
5. Update the entry version and SHA-256. The catalog has `schema_version: 1`, `library_version: 1.4.0`, and explicit
   per-workflow requirements. `docs/workflow-capture.json` records source/distributed hashes and allowed identity changes.
6. Use verified metadata for exact node providers, selected weight filenames and source links. Keep uncertain pack
   providers/versions unknown; a source-declared version is not an execution-tested version. Observed ComfyUI/frontend
   versions are evidence, not an invented minimum version.
7. Scan for secrets, absolute author paths, stale previews and unredistributable media. Current Wan warnings refer to
   an author-machine cached video preview; that GIF is not bundled. Review/clear those preview fields in ComfyUI before
   a public release if desired. No personal media or model binaries are shipped.

## Installing requirements

`comfy_workflows action=check` returns a `setup_proposal`: every missing registered node pack, every missing model
(folder, link, size from a HEAD request) and every frontend setting the workflow needs (catalog
`requirements.frontend_settings`, e.g. `Comfy.VueNodes.Enabled=true` for the ImageCompare node of
`qwen-image-2-1-i2i`). The agent proposes all of it in ONE consent form, then works visibly in the window: Issues tab →
`Install All` (ComfyUI-Manager, registry packs only), model downloads, the Settings switch, a restart if packs were
added, and a refreshed check. The new Manager UI cannot install arbitrary Git sources; unknown/unregistered providers
need a separately approved, reviewed pinned fallback — do not infer repositories from display names. Requirements
belong in the target ComfyUI environment, never system/Hermes Python. A venv is not a sandbox.

Restarts require an idle queue; use `comfy_setup stop/start` only for the managed instance, and ask the owner to
restart foreign instances. No hidden installer or blanket update mechanism is added: nothing is installed, downloaded
or switched without the user's one OK.

## Verification and activation

Run from the repository root:

```bash
python -m unittest discover -s tests -v
python -m compileall -q plugin tests
hermes plugins validate ./plugin
```

Tests use temporary data and controlled HTTP servers, never the author's live workflows. Visible integration checks
must preserve source entries and unsaved tabs; no expensive/paid generation is implied by a successful publication test.
The Python plugin is imported once per Hermes process: fully quit and restart Hermes to activate code changes. A new
chat alone is insufficient. This feature does not change the desktop JavaScript half, so no separate UI reload is needed.
The initial host verification is Windows; cross-platform code is not a claim of cross-platform runtime certification.

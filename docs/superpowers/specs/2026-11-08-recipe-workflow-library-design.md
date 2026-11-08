# Comfy Recipe v1: plugin-side skills and a shared workflow library

Date: 2026-11-08
Repository: `C:/Users/pablo/Documents/GitHub/hermes-comfy-recipe`
Status: approved by the user, including the terminology simplification to native skills; implementation planning authorized.

## 1. Intent and approved decisions

Comfy Recipe should give a fresh managed ComfyUI installation a useful workflow library without requiring users to reconstruct the author's environment. Skills are native Hermes instructions that stay in the plugin. They are not synonymous with workflows. Comfy Recipe remains the product name; there is no separate recipe abstraction or registry.

The user approved:

| Decision | Required behavior |
| --- | --- |
| Separate skills from workflows | A skill references zero, one, or multiple shared workflow IDs. Multiple skills may reference the same workflow. |
| Reuse native Hermes skills | Register instructions with the plugin skill API rather than build a second execution engine or skill catalog. |
| Ship six initial workflows | Capture the six currently open RCP workflows, subject to saved/open-tab reconciliation and release checks. |
| Automatic managed-install handoff | After the plugin's own ComfyUI starts and answers, add all six bundled workflow definitions to its workflow browser. |
| Dependencies on demand | Copying workflows does not install node packs, download models, run jobs, or trigger paid API calls. |
| Protect working copies | Never overwrite a user-modified workflow or an unrelated same-name file. |
| Existing installations | Require an explicit library-install action; do not auto-populate a user-selected foreign ComfyUI. |

Work is local and uncommitted. The user controls commits and publication. Plugin implementation does not require changing the existing six source workflows or another Hermes profile.

## 2. Scope and non-goals

### In scope

- A versioned, shared catalog of UI-format workflows bundled with the plugin.
- Registration and validation of plugin-side native skills with optional workflow references.
- An idempotent, non-destructive workflow handoff to the selected ComfyUI.
- Per-workflow dependency/readiness reports, extending the existing readiness approach.
- A documented, consent-gated Manager-first installation procedure.
- Tests, plugin validation, authoring documentation, and a release checklist.

### Not in scope

- A new recipe browser, custom skill engine, or general-purpose package manager.
- Bundling models, Python environments, entire `custom_nodes` folders, or personal input media.
- Automatically generating, running paid API workflows, installing all dependencies at startup, or updating all packages.
- Inventing a large skill collection from the six workflows. Preserve the current session skill; provide the authoring contract for future skills and exercise zero/shared/multiple references in tests.
- Claiming a workflow is execution-ready just because its JSON was copied or its node names were found.
- Automatically modifying prompts, seeds, numeric settings, input filenames, or source graph wiring while packaging.

## 3. Verified starting point

The repository is clean at the start of this design. Its current version is 0.3.0. It contains a generic session skill and tools for setup, discovery, saved workflows, official templates, headless runs, and read-only results.

`installer.py` creates a separate Python environment and installs ComfyUI plus Manager dependencies. `templates.py` already reads nodes in subgraph definitions and compares node types with the backend. There are no bundled workflow assets yet.

The six workflows were read from the visible ComfyUI tab list. Saved files for all six exist under `ComfyUI/user/default/workflows/`:

| Stable catalog ID | Source filename |
| --- | --- |
| `qwen-image-2-1-t2i` | `RCP_qwen_image_2_1_t2i.json` |
| `qwen-image-2-1-i2i` | `RCP_qwen_image_2_1_i2i.json` |
| `minimax-h3-r2v` | `RCP_video_minimax_h3_r2v.json` |
| `minimax-h3-r2v-f2lf` | `RCP_video_minimax_h3_r2v_f2lf.json` |
| `wan21-scail-2-loop-cr-mt` | `RCP_wan21_scail-2_loop_cr_mt.json` |
| `ace-step1-5-xl-base` | `RCP_audio_ace_step1_5_xl_base.json` |

The two MiniMax source files currently share a top-level workflow UUID. Distributed copies must have distinct stable identities. The source files themselves must not be rewritten to solve this.

The six-file inventory in scratch is discovery evidence, not the canonical release export: the user may still edit the open tabs. Recheck before capture.

## 4. Content model

### 4.1 Shared workflow library

Proposed files:

```text
plugin/
  workflows/
    catalog.json
    RCP_qwen_image_2_1_t2i.json
    RCP_qwen_image_2_1_i2i.json
    RCP_video_minimax_h3_r2v.json
    RCP_video_minimax_h3_r2v_f2lf.json
    RCP_wan21_scail-2_loop_cr_mt.json
    RCP_audio_ace_step1_5_xl_base.json
  skills/
    session/SKILL.md
    image-editing/SKILL.md (future skill, not required for the initial asset handoff)
    troubleshooting/SKILL.md (future skill, not required for the initial asset handoff)
```

Use the existing UI/editor format; do not convert assets to API format. Preserve layout, groups, subgraphs, widget values, notes, model selections, and input filenames. Normalize only distributed top-level identity where needed, with deterministic distinct UUIDs. Record the normalization in capture evidence. Do not carry absolute author-machine paths or secrets into a release unnoticed: scan and report them for author review rather than silently rewriting content.

The catalog has a schema version and library version. Every entry has a unique stable ID, title, relative asset path, asset version, content hash, media/task description, and dependency metadata. Paths are package-relative and validated against traversal. Filenames are presentation; stable IDs resolve references.

Dependency metadata distinguishes:

- Core backend node types and their tested/minimum ComfyUI compatibility information when known.
- Registered custom packs: registry ID, expected node types, tested version when verified, and source information.
- Unregistered packs: explicitly reviewed source and revision when verified; never guess a URL from a display name.
- Frontend-only helpers, embedded subgraph UUIDs, and UI-only nodes, which must not be blindly treated as missing backend packs.
- Exact model filenames, model folders, source URLs, optional size/checksum/license information when known.
- Required input media, external executables, credentials, online services, and paid API requirements.

Unknown metadata is reported as unresolved, not fabricated or considered ready. Dependencies may be deduplicated across workflows when presenting an installation plan.

### 4.2 Native skills

Discover `plugin/skills/*/SKILL.md` and register them with `ctx.register_skill`, retaining the existing `comfy-recipe:session` behavior and public name. Use each skill directory's stable name and its ordinary frontmatter description. There is no `recipes/index.json`, separate skill catalog, or custom skill engine.

Optional workflow references live in the SKILL.md frontmatter at `metadata.comfy_recipe.workflow_ids`. A missing field or an empty array is valid. Validate referenced stable workflow IDs against the shared workflow catalog. This plugin-specific metadata does not replace or change the Hermes skill format. PyYAML is already available in the Hermes runtime; isolated tests must not install packages into that environment.

Do not duplicate workflow JSON inside skill folders. Validate skill names, package-contained paths, frontmatter, and workflow references at load/test time. A shared workflow is installed once regardless of how many skills reference it. A workflow-free skill must be discoverable/loadable without requiring a running ComfyUI just to read its instructions.

The current session skill remains workflow-free. The contract and tests support future task skills without a registration-code change for every skill. Only load the requested skill's full instructions; do not inject every skill into every session.

## 5. Workflow handoff and update policy

### 5.1 Destination and API

Publish working copies into `workflows/Comfy Recipe/` through ComfyUI's existing userdata API, using the selected instance rather than a hardcoded author path. The normal ComfyUI Workflows browser remains the user's interface.

Publication is an explicit file-provisioning operation, not a generation run or hidden graph edit. Never rewrite an already-open source workflow. In this development session, any manual workflow editing and all generation tests remain visible through `drive_preview`; do not use `comfy_run`.

Extend `comfy_workflows` with clear actions to list the bundled library, check dependencies, and install/synchronize bundled working copies. Preserve existing list/describe/timings behavior. Names and payloads must be unambiguous about bundled assets versus saved working copies.

### 5.2 Automatic managed-install handoff

After `comfy_setup start` establishes that the managed ComfyUI answers, provision all bundled workflows. Also cover the session-start fast path if it bypasses that tool, without starting or stopping an instance just to synchronize files.

- First publication: create each missing destination using overwrite-disabled semantics.
- Repeat publication: leave an identical copy alone.
- Same-name file with different content and no trusted publication record: preserve it and report a conflict, even on a first run. A semantically identical file can be reported unchanged without overwriting it.
- User-modified copy: preserve it and report that a newer bundled revision is available.
- Bundled update: preserve the existing working copy; offer an explicit versioned sibling copy. Do not auto-overwrite even if an older copy appears unmodified.
- Partial failure: retain successful verified copies, report per-entry results, and allow retry without duplicates.
- Failure does not misreport a working ComfyUI server as failed to start; return server health and library-provisioning status separately.

Read back every created target and compare its identity/content before reporting publication success. Keep installation records and hashes in the existing profile-safe plugin data directory, scoped to the actual instance/destination. State must not live inside the installed plugin package.

For a user-selected existing installation, library installation is explicit. Repeated calls must follow the same conflict policy.

### 5.3 Scope of copying

Only workflow JSON is automatically copied. Do not install models or code, upload personal media, queue a workflow, save an unrelated tab, or restart ComfyUI as a side effect. Reuse linked model directories as the existing installer already supports.

## 6. Readiness and dependency installation

### 6.1 Read-only preflight

A workflow check returns separate dimensions rather than one misleading boolean:

- Workflow definition installed and readable.
- Core node compatibility.
- Missing or unresolved custom packs/node providers.
- Installed-but-unavailable/import-failed possibilities where evidence supports that distinction.
- Missing exact model files, with links/folders from verified metadata.
- Required input slots needing user media.
- External programs, credentials, paid API/service requirements, and hardware guidance.

Walk nested subgraphs and avoid false positives for embedded definitions or known UI helpers. Refresh cached backend information after installation/restart. Do not say an arbitrary model alternative is compatible merely because a similarly named file exists.

### 6.2 Installation workflow

Use the bundled session skill and workflow reports to drive the existing ComfyUI-Manager in the visible window:

1. Present only the missing requirements for the selected workflow(s), grouped by pack.
2. Show package identity, tested version/source when verified, and the fact that custom nodes execute third-party code.
3. Obtain user consent.
4. Install registered packs using Manager's version selection and dependency handling.
5. For unknown/unregistered providers, stop automatic installation and present a reviewed, pinned manual/Git fallback requiring separate explicit approval. Do not weaken Manager security or infer arbitrary repositories.
6. Check the queue, obtain restart consent, and use `comfy_setup stop/start` only for the plugin-managed installation. For a foreign instance, ask its owner to restart it.
7. Refresh node information, read import errors where available, and recheck readiness.

Large model downloads have separate consent and progress expectations. No model downloads are added to first-run workflow publication. This implementation reuses Manager and existing download guidance; it does not introduce an independent general-purpose binary/package downloader.

A separate ComfyUI environment isolates dependencies, not malicious code. Never use system/Hermes Python to install node requirements, share a foreign executable custom_nodes folder, or silently change PyTorch/Python to resolve a conflict.

## 7. Author capture procedure

Before adding the six assets:

1. Re-read the visible six-tab list and inspect each target tab's dirty status. Do not assume the saved inventory is current.
2. Preserve unsaved edits; ask before saving them or using a different saved snapshot. Export/save actions, if needed, are performed in the window.
3. Copy the agreed saved/exported UI JSON into the plugin package. Packaging is file capture, not prompt/image/seed editing.
4. Compare against the source, allowing only the explicitly documented distributed identity normalization.
5. Validate graph/link structure, unique top-level identities, embedded subgraph references, and catalog hashes.
6. Scan inputs, paths, credentials, paid-service nodes, model metadata, and custom-provider metadata; mark unknown/missing requirements honestly.
7. If a source graph is invalid, report the exact issue for author review. Do not silently repair graph content while calling the capture unchanged.

Do not bundle the user's current photo/audio/video input files merely because a workflow references them. User-provided assets remain an explicit readiness requirement unless the author separately approves redistributable examples.

## 8. Compatibility and integration

- Keep existing setup, discovery, template, run, result, personal_skill, and visible-session behavior.
- Runtime library code stays Hermes-independent where practical; plugin registration remains in `__init__.py`.
- Use profile-safe data paths and current public Hermes plugin APIs.
- Keep skill metadata and the workflow schema small and explicit; no database, separate recipe registry, or new background service.
- Preserve the session skill's UI-driving, consent, unsaved-tab, and managed-instance lifecycle rules.
- Update README, developer guidance, skill instructions, tool schemas, and plugin version consistently. Version bump must reflect feature addition without pretending all operating systems or GPU combinations were tested.
- Python plugin changes require a full Hermes restart to activate. A new chat alone is insufficient. Do not claim the already-running plugin was reloaded by editing the repository.

## 9. Verification and acceptance

### Automated tests

- Exactly the six intended workflows are bundled, with unique stable IDs, valid content hashes, and distinct distributed workflow identities.
- Every asset is valid UI-format JSON; source capture differences are accounted for.
- Skill references support zero, one, multiple, and shared workflow IDs. Invalid references and path traversal are rejected.
- Native skill registration preserves the existing session skill and works without invoking ComfyUI for skill-only reading.
- First publication, identical repeat, conflicting preexisting file, edited user copy, explicit versioned update, unavailable server, partial failure, and read-back mismatch are covered.
- Managed-only automatic publication; foreign instances require an explicit action.
- No publication action installs packages/models, queues prompts, or restarts a server.
- Dependency reports handle core nodes, embedded subgraphs, UI helpers, custom packs, unresolved providers, missing models, and external requirements.
- Existing tools and commands retain their contracts.
- Tests use isolated temporary data directories and controlled servers/fixtures; no tests mutate the author's actual workflow files or another profile.
- Run Hermes plugin validation and syntax/test checks with real output. Record warning categories separately from failures.

### Visible integration check

After implementation and with approval for a real managed-instance handoff test, verify the six working copies appear under `Comfy Recipe/` in the actual workflow browser. Open representative copies by hand; verify the correct variants and preserved layout. Read back published targets. Preserve all existing source entries and unsaved tabs.

Full image/video/audio generation is not a prerequisite for claiming library publication works. In particular, do not trigger MiniMax generation, any paid-service calls, or expensive model downloads as an implicit test. The two bundled MiniMax graphs use local models, not a paid API. Any generation test must be separately authorized, queued via the visible Run button, and inspected using `comfy_result` and the output media.

If the live Python plugin cannot be reloaded without the user's full Hermes restart, distinguish verified repository behavior from pending activation. Do not claim a live hot reload.

## 10. Written-spec review gate

The user approved the design and then approved simplifying its terminology and implementation to native skills plus a shared workflow catalog. Write and self-review the implementation plan, obtain the user's plan review and execution-method selection, then implement and verify. No second design review is required for this agreed simplification. Leave design, plan, code changes, and bundled assets uncommitted.

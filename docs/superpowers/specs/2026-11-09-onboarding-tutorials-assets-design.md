# Comfy Recipe: post-install setup, first-image tutorial, and reference assets

Date: 2026-11-09
Status: written spec approved by the user; implementation plan awaiting user review and execution-method selection.
Repository: `C:/Users/pablo/Documents/GitHub/hermes-comfy-recipe`

## 1. Intent and agreed decisions

Give a beginner a guided path from installing Comfy Recipe to creating their first image, instead of ending installation with an open-ended question. Keep installation consent explicit, explain download size before downloading, and preserve the ordinary experience on later sessions.

| Decision | Required behaviour |
| --- | --- |
| Order | ComfyUI installation/startup → dependency/model choices → approved setup work → first-image tutorial → ordinary conversation. |
| Node dependencies | Offer installation of missing node packs across the bundled workflows now (recommended), or defer until a workflow needs them. |
| Models | Independently offer downloading missing models now, with their verified aggregate download size, or defer until needed. Default recommendation: defer these potentially large downloads. |
| First workflow | Keep the earlier text-to-image-first startup change; do not overwrite existing tabs or workflow copies. |
| First tutorial | Ask the user to describe their first image in this chat. Enhance the description using a bundled Hermes Qwen Image 2.1 prompt-writing skill, visibly enter it in ComfyUI, and generate an image. |
| Prompt enhancement | The Hermes agent does the writing. Leave the graph's extra model-based prompt enhancer disabled; no extra enhancement-model download or GPU allocation for this tutorial. |
| Other tutorials | Hold the other five tutorials. Do not write invented lessons, run them, or automatically advance to them. |
| Exit | Ask the ordinary “What would you like to do?” question after tutorial success, an explicit skip, or opening a second Comfy Recipe session. |
| Meaning of second run | A second Comfy Recipe chat/session, NOT the second generated image, a polling call, a backend restart, or a pane reload. |
| Replay | `/comfy tutorial` is available at any time; natural-language “tutorial” and “skip tutorial” also work in a Comfy Recipe chat. |
| Assets | Add `plugin/assets/` for author-supplied reference images, character sheets and motion videos; no invented or downloaded media in this change. |

Changes remain local and uncommitted. Preserve the existing uncommitted first-tab change. Do not commit, push, restart Hermes, install third-party node packs, download models or run a live generation as a side effect of implementing this feature without the appropriate user approval.

## 2. Verified starting point

- `plugin/__init__.py` owns the kickoff text, ready card, pre-LLM hook and `/comfy` command. Its ready card currently always asks what the user wants to do; first-run and returning-session instructions must be separated.
- `plugin/core.py` provides setup/start/status and profile-safe plugin data paths. Runtime state is outside the source tree.
- `plugin/dependencies.py` already reports missing node packs, selected catalog models, frontend settings and blockers. Its `remote_size` is best-effort HEAD metadata. Its current per-workflow total sums rounded GB values; the new library-wide proposal must aggregate raw byte sizes and deduplicate before rounding.
- `plugin/library.py` publishes six bundled workflow definitions without overwriting user files. The in-progress startup helper makes text-to-image first/selected only in a fresh workspace.
- `plugin/skill_registration.py` registers ordinary bundled Hermes skills and validates referenced workflow IDs. Only the session skill currently exists; the Qwen writing skill must be added, not assumed to exist.
- Several bundled workflows reference author-specific media. Creating an assets directory does not make these portable or execution-ready.

## 3. Scope and boundaries

### In scope

Post-install setup preferences; one deduplicated library-wide dependency report; persisted first-session/tutorial progress; the first-image tutorial and reusable Qwen text-to-image prompt-writing skill; namespaced replay command; author-facing assets structure and metadata; tests and documentation.

### Out of scope

The other five tutorials; a general tutorial editor or execution engine; automatic workflow upgrades; changing user prompts/values through JSON; automatic headless runs; bundling weights or third-party Python environments; importing the author's personal images/videos; changing a foreign ComfyUI without consent; licensing claims based solely on a download URL.

Use native skills, the existing Manager-first installation procedure, and existing read-only result tools. Do not add a second workflow-running subsystem.

## 4. Beginner-facing flow

### 4.1 Finish the base installation

Retain the existing installation/GPU/folder/shared-model questions. Start the managed ComfyUI, publish the six definitions, open the visible preview and verify it responds. Show a compact ready summary, but do not yet append the ordinary open-ended question.

Base installation consent does not imply consent to custom nodes or model downloads.

### 4.2 Inspect and ask once

Inspect all six bundled default workflow configurations. Build one proposal covering the union of missing node packs, missing model files, required frontend settings, unresolved providers/core nodes, and missing media.

Use one clarify form with two independent questions:

1. “Install the missing workflow building blocks now?” Choices: “Install now (recommended)” and “Install when I use a workflow”. Show pack names and explain once that these are third-party code and may require a ComfyUI restart.
2. “When should we download the missing models?” Choices: “Download when I use a workflow (recommended)” and “Download now — approximately X GB”. Show the verified aggregate size before consent; if some sizes are unknown, use “at least X GB; N file sizes unknown” rather than an exact-looking total.

Skip an installation question when nothing in that category is missing; say that category is already available. If inventory fails, report unknown rather than classifying files or nodes as missing. A zero-file download is 0 GB, not unknown.

Frontend settings are not silently changed by permission to install packs/models. List any required setting changes in the same proposal with a separate approval question when needed. Explain unresolved blockers and missing example media; do not offer to install unknown node providers as if they were verified packs.

### 4.3 Carry out the chosen setup

Install only the approved categories through the visible ComfyUI window. Deduplicate packs by verified registry identity and install them once. Download models only from verified URLs to the managed installation's own model folders. Never copy shared model files or overwrite unrelated files.

If packs need a restart, disclose that in the consent form, wait for an idle queue, use the managed `comfy_setup stop/start` path, reopen the pane and recheck. Never restart a foreign installation yourself. Verify model files and node availability after installation; a successful request alone is not proof of readiness.

Failures remain retryable and are not marked installed. If a dependency choice is deferred, store the preference, not fabricated readiness. If setup cannot finish, explain the blocker and offer retry or skipping the tutorial; do not claim tutorial success.

### 4.4 First-image tutorial

Load the native first-image tutorial skill. Introduce only the essentials: the user describes an image in chat; the agent turns that into a useful prompt and operates ComfyUI visibly.

Suggested opening:

> Let’s create your first image. Describe what you’d like to see here in the chat—a subject, a place, a style, or just an idea. I’ll turn it into a prompt and make it in the ComfyUI window. You can say “skip tutorial” at any time.

When the user supplies an image description:

1. Load the bundled Qwen Image 2.1 text-to-image prompt-writing skill.
2. Check readiness for `qwen-image-2-1-t2i`. If downloads/packs were deferred, ask for the actual missing requirements of this workflow only, with its own verified download size. A prior “later” choice is not authorization to download now.
3. Open the bundled working copy visibly. Protect dirty tabs and user-modified working copies; do not silently save, replace or discard them. If the copy no longer matches the tutorial assumptions, explain and offer a separate working copy or use the user's current configuration with explicit agreement.
4. Rewrite the user's description into a faithful, clear prompt. The skill must not invent requested subjects, identities, text, or constraints. Ask a focused question only when ambiguity materially affects the image. Briefly show the enhanced prompt without a long lesson.
5. Type the prompt with `drive_preview`; keep the graph's model-based enhancement off. Preserve the current configured resolution, seed and other values unless an adjustment is necessary and disclosed. Never edit these values through JSON.
6. Tell the user the described image will now be generated, then click Run visibly. Do not call `comfy_run`.
7. Use `comfy_result prompt_id=latest` read-only, associate the result with the actual queued tutorial run, and inspect the output image. Cached results, unrelated jobs and failed runs must not count as a new successful tutorial image.
8. Present the image and timing, record completion only after a verified successful image output, then invite another request or modification with the ordinary “What would you like to do?” question.

The tutorial teaches one complete loop. It does not require a second image or all six workflows. “Skip tutorial” exits without generation and records skipped, not completed.

## 5. Persisted state and integration

### 5.1 State location and identity

Add a small versioned onboarding state document under the existing profile-safe plugin data directory, not inside the repository. Scope records to a stable managed-install identity persisted in its marker/manifest. Preserve that identity when adopting/moving an installation; give a genuinely new installation a new identity. Existing manifest compatibility is required.

Use atomic writes. Store only small state and result identifiers—not the user's full image description, credentials or generated media.

Suggested record fields:

- `schema_version`, `install_id`, `first_session_id`;
- `setup_choices`: nodes = now/on_use/unanswered, models = now/on_use/unanswered;
- `setup_status`: pending/in_progress/ready/partial/deferred, plus verified installation evidence;
- `tutorial`: id `first-image`, state not_offered/awaiting_description/in_progress/completed/skipped, owner session id, last verified prompt id;
- timestamps for transitions.

Session identity must be the actual Hermes chat/session id, not an incrementing count of tool or hook calls. Repeated kickoff hooks, polling, restarts and preview reloads in the same chat are idempotent. Concurrent sessions must not overwrite another session's active tutorial or replay approval.

### 5.2 Routing and transitions

New install: pending setup → preference form → chosen work/recheck → tutorial awaiting description → in progress → completed or skipped.

Second distinct session: suppress automatic setup/tutorial prompting and show the ordinary returning-session card. Do not mark an unfinished tutorial completed or erase its saved choices. Deferred requirements remain consent-gated at actual use.

Explicit `/comfy tutorial`: select the available first-image lesson and return the tutorial instructions even if previously completed, skipped or suppressed. Do not rerun installation or reset node/model preferences. Restarting the lesson changes tutorial progress only after an explicit replay request.

Use an explicit, small plugin tool surface for reading/recording onboarding transitions so the agent does not edit state files directly. Proposed tool `comfy_onboarding` actions: `status`, `preferences`, `tutorial`, `complete`, `skip`. Validate enums and installation/session identity. `complete` must verify a successful corresponding image result read-only against ComfyUI; the agent's assertion alone is insufficient. Tool replies return the next clear step and concise evidence.

The `/comfy tutorial` command must work through Hermes' supported command/hook handoff, not merely print text that no agent consumes. Cover that handoff in an integration test. Natural-language triggers only apply within a Comfy Recipe session; do not intercept unrelated uses of the word “tutorial” in ordinary chats or quoted prompts. Keep the command namespaced; do not claim a global `/tutorial` command.

### 5.3 Existing users and migration

Do not surprise an existing managed installation with a first-install wizard after a plugin update. Absence of the new state alone is not proof of a new install. Existing installations get conservative returning-user behaviour and may explicitly invoke the tutorial. New-install provenance is set when a fresh setup finishes; install continuation after process restart must retain that provenance.

Corrupt/unsupported state must not trigger downloads, reset a workspace or claim completion. Surface the issue and offer an explicit recovery/replay path. Never reuse consent from another installation or session.

## 6. Library-wide missing-download calculation

Extend existing dependency reporting; do not add a separate installer.

- Read all six catalog entries and the active backend's registered nodes/model inventory. Shared model paths count as already available if the backend resolves the exact model.
- Deduplicate node packs by registry id.
- Deduplicate model targets by validated folder plus relative filename. Preserve source URL provenance; conflicting URLs for the same target are a blocker, not permission to choose arbitrarily.
- Resolve file sizes from trusted metadata/HEAD with bounded concurrency, caching and timeouts. Sum integer byte sizes; round only once for display in decimal GB. Unknown sizes remain explicit, and files lacking verified URLs remain manual requirements.
- Report exact missing files and download totals, not installed weight totals or VRAM estimates. Do not label node-pack environment downloads as covered by a models-only total; their additional size may be unknown.
- Resolve executable default branches where possible. For the first-image tutorial, exclude the disabled model-based prompt enhancer from required downloads. Mark optional branch models separately rather than implying they are needed for the tutorial. If a default branch cannot be resolved reliably, label that uncertainty rather than silently guessing.
- Recheck before execution. If the missing set grows or the approved scope changes, ask for the added scope before downloading it. A smaller set because files became available is safe to use.

Keep the existing per-workflow checks for ordinary on-demand use. Update skill guidance so post-install independent category choices do not conflict with the existing single combined per-workflow consent recipe.

## 7. Native skills

Add two ordinary registered skills:

1. `first-image-tutorial`: references `qwen-image-2-1-t2i`; teaches the short visible first-image loop, deferred requirement checks, result verification, completion and skip/replay behaviour.
2. `qwen-image-2-1-prompting`: references `qwen-image-2-1-t2i`; reusable outside the tutorial when the user requests Qwen text-to-image. Preserve user intent, explicit text and constraints; describe subject, action, composition, setting, lighting and requested style without a bloated template or unsupported guarantees. Avoid inserting negative-prompt instructions into a CFG-1 negative field. Do not enable the graph's extra enhancement model.

Update the session skill, opening instructions and library reference. Do not implement the five postponed lessons or pretend they are selectable. A request for an unavailable tutorial should say it is not available yet and offer the first-image lesson or normal workflow assistance.

## 8. Reference assets

Planned package layout:

```text
plugin/assets/
  README.md
  images/
  character-sheets/
  motion-videos/
```

Track empty category directories with `.gitkeep` files. The README documents supported formats, sensible filenames, attribution/redistribution requirements and the future media contract. The initial folder contains no sample images, videos or character sheets; do not reuse personal media without separate approval.

When real assets are added later, require metadata mapping each asset to a stable workflow id and input role, with a package-relative path, content hash and licence/attribution. Validate against traversal and missing files. Copy only needed approved assets into ComfyUI's input folder, without overwriting user files, and select them through the visible Load Image/Load Video controls. This change establishes the authoring contract, not an empty asset-installation engine or automatic rewiring. The text-to-image tutorial needs no input asset.

## 9. Implementation areas

- `plugin/onboarding.py`: compact state/transition logic and next-step selection.
- `plugin/dependencies.py`: deduplicated library proposal and byte-accurate totals, retaining per-workflow checks.
- `plugin/core.py`, `plugin/installer.py`: new-install provenance/identity and setup lifecycle integration.
- `plugin/__init__.py`: onboarding tool, explicit command/hook routing, first/returning card separation.
- `plugin/skills/`: two native skills and updates to current session/library instructions.
- `plugin/assets/`: README and tracked empty category folders.
- Existing and new tests; README/development/library documentation.

Reuse the present state/path and skill registration conventions. No desktop UI changes are required unless supported command handoff discovery demonstrates a small necessary SDK change; any such change must remain within the plugin SDK.

## 10. Verification and acceptance

Use tests first for each behaviour slice. Tests use temporary profile/installation directories and controlled backend/metadata fixtures; never alter the user's current onboarding history or download real model files during unit tests.

Required automated coverage:

1. Fresh installation completes into setup choices, not the ordinary question.
2. Both categories can be selected independently; all four combinations produce only the approved work.
3. Already available/shared files are excluded; shared requirements across six workflows are counted once.
4. Byte-level summation, zero missing models, unknown sizes, unreachable inventory, conflicting URLs, missing URLs and changing inventories are handled honestly.
5. A disabled tutorial enhancement model is not required or downloaded.
6. Repeated hooks/status calls, same-session restart and pane reload do not count as a second session.
7. A second distinct session uses the ordinary opening while retaining unfinished tutorial state.
8. Completed, skipped and failed tutorial states differ; only a matching verified image result permits completion.
9. Replay via `/comfy tutorial` and natural-language triggers reaches the agent's lesson, including from completed/skipped states; unrelated chats/quoted words are untouched.
10. Existing installation migration does not force onboarding; a moved/adopted installation keeps identity; genuinely new installs do not inherit old consent.
11. State writes are atomic, invalid state is safe and concurrent sessions do not steal tutorial ownership.
12. New skills register correctly and reference valid workflow IDs; only the first lesson is offered.
13. Assets directories/README exist, contain no private media, and document the authoring contract.
14. No onboarding path queues through the API or silently mutates workflow prompt/seed/image/number values through JSON.

Run the full suite and plugin validation; distinguish new failures from reproduced baseline failures. The repository already has a reproduced watchdog timing-test failure; do not silently change watchdog behaviour as part of onboarding.

Live verification, after explicit activation permission: reload the appropriate plugin half/full backend, use an isolated test installation/profile so the current user's saved tabs and history stay intact, and inspect the visible first-run flow. Installation/download/generation tests require explicit real-world consent and reported scope. Verify deferred choices do not install anything; verify skip, replay and second-session routing. Clearly distinguish source tests from activated live behaviour.

## 11. Spec self-review

- Only one tutorial is specified; the other five remain explicitly out of scope.
- The extra graph enhancement model stays disabled; Hermes prompt-writing is the approved implementation.
- Download sizes are machine-specific missing-byte estimates, not a fixed number invented in this spec.
- All setup/download/restart/generation side effects have explicit scope and consent; the normal open-ended prompt is deferred only in the first onboarding session.
- Second session is defined by session identity, not polling count; failed work never becomes completion.
- Existing users, moves, repeat sessions, dirty graphs and private reference media are protected.
- No implementation files or runtime state were changed while writing this spec.

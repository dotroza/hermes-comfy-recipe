# Post-install Onboarding and First-image Tutorial Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `subagent-driven-development` or `executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. No commits without the user's explicit request.

**Goal:** Replace the fresh-install open-ended greeting with independent setup choices and a replayable first-image tutorial, while preserving normal returning sessions and providing a reference-assets authoring folder.

**Architecture:** Add a small persisted onboarding state module and reuse the current dependency checker, native Hermes skills, `/comfy` command and pre-LLM hook. All installs and generations remain visible, consent-gated agent actions. The command displays a real beginner-facing lesson opening and stores its session routing; the next description reaches the agent through the existing hook, without privileged gateway message injection.

**Tech Stack:** Existing Python plugin, stdlib persistence/networking, `unittest`, existing ComfyUI client and Manager, native Hermes SKILL.md registration. No new runtime package dependencies.

**Spec:** `docs/superpowers/specs/2026-11-09-onboarding-tutorials-assets-design.md` (user approved).

**Plan status:** Awaiting user review and execution-method selection. No implementation code below is labelled tested. Only the public command-dispatch probe described below was executed.

## Global Constraints

- Only `first-image` / `qwen-image-2-1-t2i` is a tutorial in this release; the other five are postponed.
- Keep the graph's extra model-based prompt enhancer off. Hermes writes the enhanced prompt.
- Second run means a second distinct Comfy Recipe chat/session, NOT a second image, polling call, restart or reload.
- Never queue through `comfy_run` during onboarding/tutorials; use `drive_preview` and `comfy_result prompt_id=latest`.
- Never modify workflow prompts, seeds, numbers or selected media through JSON.
- All node/model/setting/restart changes require category-appropriate consent; no live downloads, third-party installs or runs during unit tests.
- Preserve user-modified workflows, dirty tabs, existing installations and the earlier uncommitted first-tab implementation.
- Use profile-safe runtime paths; no personal hardcoded paths in shipped code/skills.
- No commits, pushes, Hermes restarts or private-media imports without explicit approval.

## Review Focus

1. Installation finishes in one chat but status/start is polled repeatedly: only a genuinely different session counts as session two. Task 2 pins this.
2. A catalog file names an optional disabled prompt-enhancer model: do not include that model in the first-image download consent. Task 1 pins this.
3. A session has no kickoff marker because the user invoked `/comfy tutorial` directly: the next ordinary description must still route to the lesson. Task 5 pins this.
4. Another browser queues a different or cached image while the tutorial waits: never accept `latest` blindly as tutorial completion. Tasks 3 and 5 pin this.
5. An existing install lacks onboarding state after an upgrade, or state is corrupt: do not infer fresh-install provenance or grant download consent. Task 2 pins this.

---

## Verified repository and SDK anchors

Read the spec and these current files before editing:

| Existing symbol | Location / role |
| --- | --- |
| `core.DATA`, `_managed_dir`, `_managed_instance`, `_inst` | `plugin/core.py`; profile-safe storage and instance lookup |
| `core.setup_install`, `setup_status`, `setup_start`, `_finish_setup` | Managed setup lifecycle; discover exact call sites before wiring provenance |
| `installer.manifest`, `_meta`, `_write`, `install`, `adopt` | `plugin/installer.py`; manifest creation and rebasing |
| `library.load_catalog`, `load_asset`, `canonical_hash` | `plugin/library.py`; catalog, UI graphs and identity |
| `dependencies.check`, `setup_proposal`, `remote_size` | `plugin/dependencies.py`; per-workflow evidence and best-effort size lookup |
| `cc.history`, `cc.queue_state`, `cc.get_json` | `plugin/comfy_client.py`; read-only backend evidence |
| `_workflows`, `_setup`, `_wrap`, `SCHEMAS`, `HANDLERS` | `plugin/__init__.py`; tool wiring |
| `_command`, `_pre_llm_call`, `_session_start`, `CARD`, `FIRST_RUN`, `STOPPED` | Existing command, hook and opening instructions |
| `skill_registration.skills_for_registration` | Native skill discovery/metadata validation |

The actual installed public `hermes_cli.plugin_command_dispatch.invoke_plugin_command` was exercised with a throwaway handler. It forwards `session_id`, `session_key`, and `platform` to declared keyword arguments and returns the handler's beginner-facing text. The probe did NOT prove follow-up tutorial routing; Task 5 must implement and test that routing. Do not use gateway injection or private session mutation to launch the lesson.

Commands from repository root:

```bash
python -m unittest discover -s tests -v
hermes plugins validate plugin
node --version
git diff --check
```

The full pre-feature suite ran 58 tests with one reproduced baseline watchdog failure (`test_keep_running_and_idle_and_missing_install_exit_without_stopping`). Do not hide it, edit watchdog production logic, or describe the full suite as all passing unless it really does.

## File ownership and task order

| Task | Files / responsibility |
| --- | --- |
| 1 | `plugin/dependencies.py`, `plugin/workflows/catalog.json`, new `tests/test_onboarding_dependencies.py`: accurate library proposal and optional-model metadata |
| 2 | new `plugin/onboarding.py`, `plugin/installer.py`, `plugin/core.py`, new `tests/test_onboarding.py`, existing lifecycle tests: installation provenance and transactional state |
| 3 | `plugin/onboarding.py`, new `tests/test_tutorial_evidence.py`: proof of a corresponding fresh image run |
| 4 | new native tutorial/prompt skills, `plugin/assets/`, `tests/test_skills.py`, new content tests: lesson/prompt contracts and assets folders |
| 5 | `plugin/__init__.py`, `plugin/plugin.yaml` if declarations require it, hook/command/tool integration tests: first-run and replay routing |
| 6 | session/library docs and README, all tests, isolated SDK test, plugin validation: consistency and handoff |

Dependency order: 1 → 2 → 3 → 4 → 5 → 6 for native execution. Tasks 1 and 4 can be independently prepared by subagents after their contracts below are fixed, but only one worker edits a shared file at a time. Integrate and verify each task before starting its dependent task.

## Task 1: Byte-accurate library proposal

**Files:** Modify `plugin/dependencies.py` and catalog requirement metadata. Create `tests/test_onboarding_dependencies.py`.

**Interfaces:**
- Existing `check(...) -> dict` remains supported.
- Add `library_proposal(reports: list[dict], size_of=remote_size) -> dict` to combine already-collected per-workflow reports; it performs no installs.
- Add `size_bytes` to downloadable model rows; retain current `size_gb` for compatibility.
- Proposal output: `node_packs`, `models`, `optional_models`, `settings`, `blockers`, `models_without_url`, `unknown_inventory`, `download_bytes`, `download_gb`, `unknown_size_count`, `size_complete`.
- `download_bytes` is the sum of KNOWN missing bytes; `size_complete` is false when any required missing file lacks a size or verified URL. Empty required missing set has 0 bytes and complete size.

- [ ] **Step 1: Add and run a failing deduplication test.** Build two reports referencing the same `(folder, name, url)` with `size_bytes=1_234_567_890`. Assert one model row and `download_bytes == 1_234_567_890`, not a sum of rounded GB. Run `python -m unittest discover -s tests -p test_onboarding_dependencies.py -v`; confirm failure for missing behaviour.

```python
reports = [report_with_missing_model('shared.safetensors', 1_234_567_890),
           report_with_missing_model('shared.safetensors', 1_234_567_890)]
proposal = dependencies.library_proposal(reports, size_of=lambda url: 1_234_567_890)
self.assertEqual(len(proposal['models']), 1)
self.assertEqual(proposal['download_bytes'], 1_234_567_890)
```

Define `report_with_missing_model` inside the new test file with the minimum actual `check` report structure: `workflow_id`, `models`, `nodes`, `settings`, `setup_proposal`. It is fixture data, not an API result presented to the user.

- [ ] **Step 2: Implement only the failing dedup/summing case, then rerun it.** Deduplicate packs by registry id; models by `(folder, normalized relative name)`. Reject traversal/absolute targets using the current checker rules. Conflicting source URLs are explicit blockers.
- [ ] **Step 3: Add one failing edge-case test at a time, then implement it.** Available/shared models excluded; unknown inventory not missing; one missing file size unknown; missing URL; conflicting URLs; duplicate settings with conflicting requested values; no missing files = 0 GB. Keep every failure/readiness distinction in the report.
- [ ] **Step 4: Add a failing optional-enhancer test.** Add requirement metadata on both Qwen entries marking the PE model optional when `refine_prompt` is false. Current bundled widget defaults must be verified against the UI graph. `library_proposal` must keep optional rows separate and exclude them from the required-now total; tutorial checks must use the same distinction. Do not change graph widget values or hashes merely to add requirement metadata.
- [ ] **Step 5: Bound and cache size lookups.** Query each unique verified URL once per proposal, at most four parallel lookups, existing 8-second timeout. Persist a bounded short-lived size cache under `core.DATA` only when integrating the caller; metadata failures must remain unknown. Use integer bytes until final display rounding. Add a deterministic fake-clock cache-expiry test.
- [ ] **Step 6: Run new dependency tests plus existing dependency/library tests.** Review no catalog graph, model choice or user file was silently changed. Leave changes uncommitted.

## Task 2: Installation identity and onboarding transitions

**Files:** Create `plugin/onboarding.py`, `tests/test_onboarding.py`; modify managed manifest creation in `plugin/installer.py` and setup glue in `plugin/core.py`; extend lifecycle tests.

**Interfaces (new module):**
- `status(data_dir: Path, manifest: dict, session_id: str) -> dict`
- `preferences(data_dir: Path, install_id: str, session_id: str, *, nodes: str, models: str) -> dict`
- `tutorial(data_dir: Path, manifest: dict, session_id: str, *, replay: bool = False) -> dict`
- `skip(data_dir: Path, install_id: str, session_id: str) -> dict`
- `complete(data_dir: Path, install_id: str, session_id: str, evidence: dict) -> dict` (Task 3 defines the proof)
- Every result includes `install_id`, state, and `next_step`; enums are validated. No function installs packages, downloads weights, queues jobs, or edits workflow data.

**Persistence choice:** Store small versioned JSON record documents inside stdlib SQLite at `core.DATA / 'onboarding.sqlite3'`, keyed by `install_id`. Use transactions for cross-process atomic updates and concurrency, plus a table of session membership/routing. This satisfies the spec's versioned state-document and atomic-write requirements without a hand-rolled cross-platform lock service. Do not store user prompts or image bytes.

- [ ] **Step 1: Add a failing fresh-provenance test.** A manifest explicitly created by the new installer contains `install_id` and `onboarding_version=1`. `status(..., 'chat-A')` returns `next_step='setup_choices'` and retains `first_session_id='chat-A'` after repeated calls.
- [ ] **Step 2: Implement the minimal transactional store.** Create tables on demand in a transaction. Validate UUID installation keys, bounded nonempty session ids, schema version and enums. Each mutating operation reads current state and validates ownership inside the SAME transaction before writing. Use SQLite busy timeout and return a clear retryable error if locked.
- [ ] **Step 3: Add tests for first/second chat identity.** Multiple calls from chat A, a fresh Python process using chat A, backend stop/start and pane reopen remain first-session. Chat B gets `next_step='ordinary'` without completing/skipping chat A. A concurrent chat B must not overwrite chat A's active tutorial. An explicit replay in B establishes B's separate lesson ownership without stealing A's unfinished record.
- [ ] **Step 4: Add migration/recovery tests.** Legacy manifests without fresh provenance return ordinary mode; unknown/corrupt JSON record or unsupported schema returns recovery instructions and no consent. Legacy installations may explicitly start a lesson without running the post-install wizard. Empty/missing session identity must not claim ownership or create fresh-session progress.
- [ ] **Step 5: Wire installation identity at creation.** Add new UUID/provenance fields only when a genuinely new install is created in `installer.install`; preserve them on retry and adopt/move. A setup reset must not delete the install manifest identity; a new folder/new install must not inherit old choices. Extend `tests/test_install_lifecycle.py` for move preservation and reinstall separation.
- [ ] **Step 6: Store preferences only after the submitted form.** Accept `now` or `on_use` for each category, not arbitrary strings. Do not persist cancelled/unanswered questions as consent. Keep verification state distinct from preference: `now` does not mean installed. Mark deferred choices and partial verification without blocking tutorial skip or ordinary later sessions.
- [ ] **Step 7: Run onboarding/lifecycle tests, then current integration tests.** Leave current user runtime state untouched.

## Task 3: Verify tutorial completion against backend history

**Files:** Extend `plugin/onboarding.py`; create `tests/test_tutorial_evidence.py` using controlled backend history fixtures.

**Interfaces:**
- Add `verify_image_run(inst: dict, prompt_id: str, *, expected_workflow_id: str, started_after_ms: int, baseline_prompt_ids: set[str]) -> dict`.
- Task 2 `tutorial` records a baseline of known history prompt ids and a start timestamp when entering `in_progress`, supplied by the integration layer after description/readiness. `verify_image_run` reads `cc.history`; it never resolves `latest` by itself or queues a job.
- Proof contains explicit prompt id, expected workflow id, successful execution timestamp, image output metadata, and evidence of uncached sampling. `complete` accepts only proof produced by backend verification, not unvalidated model-supplied success fields.

- [ ] **Step 1: Failing test: matching successful fresh image.** Build a realistic history row using ComfyUI's current `prompt`, `extra_data.extra_pnginfo.workflow`, `status.messages` and `outputs` structure; inspect the existing `core.result`/client fixture format before constructing it. Assert the correct explicit prompt id is accepted.
- [ ] **Step 2: Add failing rejection cases one at a time.** Unknown prompt; unfinished/error/interrupted prompt; successful audio/video with no image; previous baseline prompt; execution before lesson start; wrong workflow UUID; headless client; cached sampler/no new sampling; malformed/absent timestamps. Fail closed with a human-readable reason.
- [ ] **Step 3: Tie to the window's queued run.** Record actual returned prompt id from `comfy_result latest` only after checking it corresponds to the visible run; unrelated concurrent jobs are rejected. A modified working copy may use its verified UUID, but the integration must confirm the tutorial graph before starting; never accept a matching filename alone.
- [ ] **Step 4: Implement `complete` as one guarded transition.** Read backend proof, verify lesson/session ownership and then persist completion. Repeated completion with the same proved prompt id is idempotent. A failed verification leaves the tutorial in progress, not completed. Visual image inspection remains an agent responsibility in the skill.
- [ ] **Step 5: Run evidence/state tests.** No live GPU or model is needed.

## Task 4: Native skills and reference-assets structure

**Files:** Create `plugin/skills/first-image-tutorial/SKILL.md`, `plugin/skills/qwen-image-2-1-prompting/SKILL.md`, `plugin/assets/README.md`, three `.gitkeep` files; extend registration/content tests.

**Interfaces:** Both skills reference `metadata.comfy_recipe.workflow_ids: [qwen-image-2-1-t2i]`. Use native skill registration unchanged. State/tool names match Tasks 2/5.

- [ ] **Step 1: Write a failing registration/content test.** Assert the two names register, their metadata resolves to the text-to-image catalog id, and no postponed tutorial is registered. Assert the tutorial contains visible Run/result/vision verification, skip/replay routing and no headless generation instruction.
- [ ] **Step 2: Write the first-image tutorial skill.** Include the actual beginner opening from the spec; wait for a description; invoke the Qwen writing skill; check this workflow's missing requirements; request consent for deferred items; open/select the graph by pane controls; type prompt; click Run; read `latest`; verify corresponding prompt/output; vision-check; record completion; present output and ask the ordinary question. Never overwrite dirty work. Any unavailable requirement produces a retry/skip choice.
- [ ] **Step 3: Write the Qwen prompt-writing skill.** Keep subject/action/composition/environment/lighting/style only when useful and faithful to the request. Preserve exact requested text, counts and exclusions. Do not manufacture identity/reference images. Rewrite rather than expand into a fixed bloated template. Briefly show the enhanced prompt, keep the graph PE off, and do not insert CFG-1 negative prompts as a fake control. The skill must also be usable for ordinary non-tutorial Qwen text-to-image requests.
- [ ] **Step 4: Write failing assets-content tests, then create the folders.** Required tracked paths:

```text
plugin/assets/README.md
plugin/assets/images/.gitkeep
plugin/assets/character-sheets/.gitkeep
plugin/assets/motion-videos/.gitkeep
```

The README must state: no bundled media yet; exact relative paths; no traversal; future stable workflow id/input-role mapping; hashes; licence/attribution/redistribution checks; non-overwriting copy into `input/`; visible Load Image/Load Video selection. Do not build a media installer or fake catalog before real assets exist.

- [ ] **Step 5: Run skill/content tests and plugin validation.** Read `hermes-agent-skill-authoring` and `writing-skills` before authoring the new skills; follow their frontmatter rules. Do not put personal machine paths in published skills.

## Task 5: Tools, kickoff routing and `/comfy tutorial`

**Files:** Modify `plugin/__init__.py` and manifest declarations if needed. Add `tests/test_onboarding_integration.py`; extend current plugin integration tests.

**Interfaces:**
- Add `comfy_onboarding` schema with `action=status|preferences|tutorial|complete|skip`; `nodes`/`models` enums `now|on_use`; optional explicit `prompt_id` only for `complete`.
- The runtime provides session identity to its handler through declared `session_id` / `task_id` context. Do NOT expose session identity as a model-writable schema field. `_wrap` currently discards kwargs; provide a context-aware wrapper just for this tool, or carefully extend `_wrap` while preserving all existing handlers.
- Extend `_command(raw_args: str, *, session_id: str='', session_key: str='', platform: str='', source=None)` without breaking its current positional usage.
- Store command tutorial routing before returning the concrete beginner opening. `_pre_llm_call` must consult pending routing before its current kickoff-history early exit.

- [ ] **Step 1: Add a failing tool registration test.** `SCHEMAS` and `HANDLERS` match; the new tool is registered through `_wrap`/the context-aware wrapper, returns JSON errors rather than raising, and rejects missing trusted session context for mutations.
- [ ] **Step 2: Implement status/proposal glue.** Resolve only the selected managed install, use its manifest provenance, collect all six reports once with shared node/model inventory, and call Task 1 `library_proposal`. Return concise structured facts and one next-step instruction. Do not perform downloads or node installation inside this tool.
- [ ] **Step 3: Test and implement fresh post-install handoff.** Both same-turn install completion and resumed installation via `setup_status/start` must return onboarding status/next action. Replace the hardcoded ordinary ready-card suffix on the first-install branch; preserve ordinary cards for returning/existing installations. The first form has independent node/model choices, optional setting consent, and correct known/unknown totals. Skip categories with no missing items.
- [ ] **Step 4: Test all four choices.** `(now,now)`, `(now,on_use)`, `(on_use,now)`, `(on_use,on_use)` must produce exactly the approved category instructions and no hidden API execution. Deferred first-image requirements are separately consent-gated. Detect newly missing extra files before execution; do not treat old consent as unlimited.
- [ ] **Step 5: Test the actual command boundary.** Invoke `_command('tutorial', session_id='chat-without-marker', platform='desktop')` via the installed public `invoke_plugin_command` in an optional SDK integration test. Assert it returns “Describe…” lesson content, saves routing, and does not print a tool recipe as the final user response. Follow with `_pre_llm_call(user_message='a red kite over the sea', session_id=..., conversation_history=[])`; assert the lesson and Qwen writing skill are selected despite no kickoff marker. No injection grant or Hermes-core patch is required.
- [ ] **Step 6: Add natural-language/replay tests.** Exact actionable “tutorial”, “start tutorial”, “skip tutorial” in Recipe sessions route correctly; unrelated chats, quoted phrases and image descriptions containing the word tutorial are not intercepted. `/comfy tutorial` works after completion/skip and in an ordinary existing-user session. Unknown tutorial names give a truthful available-lesson response, not invented lessons.
- [ ] **Step 7: Add second-session tests.** First-session polling never suppresses the lesson; chat B receives ordinary opening without marking A completed. Explicit tutorial replay in B works and preserves node/model preferences. Returning existing-user kickoff is unchanged.
- [ ] **Step 8: Wire completion/skip to Task 3.** `complete(prompt_id=...)` performs read-only proof and state transition, returns the next ordinary-question instruction. `skip` never queues a run. User cancellation, dependency failure and generation error remain distinct from success.
- [ ] **Step 9: Run new and existing integration tests.** Inspect tool schemas and handler signatures in an isolated registration process. Do not claim activation in the currently running Hermes process.

## Task 6: Documentation, full verification and release handoff

**Files:** `plugin/skills/session/SKILL.md`, `references/workflow-library.md`, README/development/library docs and test coverage as needed.

- [ ] **Step 1: Update session instructions.** Remove “never install anything else in this step” as a blanket post-install rule only where it conflicts with the newly consented setup phase; keep base installation itself separate. Remove any first-run card instruction that prematurely forces the ordinary question. Teach replay, deferred dependencies, lesson exit and second-session routing.
- [ ] **Step 2: Update per-workflow dependency guidance.** Preserve one combined readiness proposal for ordinary workflow use, but distinguish the post-install two-category form. Document optional enhancement-model exclusion and explicit extra settings consent.
- [ ] **Step 3: Add documentation contract tests.** Read shipped instructions and assert correct tool/command/skill names, one available lesson, correct prompt enhancer behaviour, and no old contradictory “ask what first” requirement on the first-install branch.
- [ ] **Step 4: Run the full suite.** `python -m unittest discover -s tests -v`. Report exact discovered count and failures from real output. Reproduce baseline watchdog failures separately; do not silently deselect them or modify unrelated watchdog production code.
- [ ] **Step 5: Run `hermes plugins validate plugin`, `git diff --check`, JS syntax validation if any JS changed.** Include untracked new files in review; verify tests did not modify real plugin data, download weights or touch private input media.
- [ ] **Step 6: Perform one fresh whole-change review.** Review state ownership, category consent, command handoff, stale result acceptance, optional model totals and migration. Resolve new issues and rerun their tests. For native execution use a fresh independent reviewer; for subagent execution also review each task boundary.
- [ ] **Step 7: Report source verification separately from live activation.** List changed files and tests, leave changes uncommitted. Ask permission before backend/plugin restart. A live acceptance run needs an isolated fresh-install identity/profile and explicit download/generation scope; no current-user state resets. Check first form, defer, skip, replay, next-session ordinary greeting, and a consented successful first image visibly when the user authorizes that test.

## Self-review and coverage map

| Spec section | Owning tasks |
| --- | --- |
| Setup order, independent choices, verified totals | 1, 5, 6 |
| Install identity, atomic state, migration/concurrency | 2 |
| Tutorial completion and stale/cached run rejection | 3, 5 |
| First-image lesson and reusable writing skill | 4, 5 |
| Replay command and natural-language routing | 5 |
| Second distinct session, retained preferences | 2, 5 |
| Assets authoring structure, no invented media | 4 |
| Visible actions, no hidden runs, user-copy protection | 4, 5, 6 |
| Deferred other five lessons and no forced upgrades | 4, 6 |

All new cross-task symbols are introduced in the interfaces above. Code blocks are design/test instructions to implement and execute, not fabricated passing results. Every production slice must have its own observed RED→GREEN cycle. The only open gate is user review of this plan and execution-method selection; no unresolved dependency requires inventing a framework API.

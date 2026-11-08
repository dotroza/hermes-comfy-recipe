# Skills and Shared Workflow Library Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the six approved ComfyUI workflows once, register native plugin skills independently of workflows, and safely hand working copies to managed installations with dependency checks on demand.

**Architecture:** Keep skill instructions in `plugin/skills/*/SKILL.md` and shared UI-format assets plus metadata in `plugin/workflows/`. Add small Hermes-independent modules for library publication, skill discovery, and dependency checks; wire them into the existing plugin registration, startup paths, and `comfy_workflows` tool. Reuse the visible ComfyUI-Manager for consent-gated installation rather than build another package manager.

**Tech Stack:** Python standard library, PyYAML already present in Hermes, native Hermes plugin skill/tool APIs, existing ComfyUI HTTP client, `unittest` with isolated temporary directories and a controlled HTTP server. No new Python packages, service, database, or frontend application.

**Spec:** `docs/superpowers/specs/2026-11-08-recipe-workflow-library-design.md` (approved, updated to native skills; no separate recipe registry).

## Global Constraints

- Brand: **Comfy Recipe**. Technical concepts: **skills**, **workflows**, and **tools**.
- Exactly six initial shared workflows; skills reference zero, one, or multiple stable workflow IDs, and IDs may be shared across skills.
- Automatically provision workflow JSON only to the plugin-managed instance after it answers; foreign instances require an explicit install action.
- Destination: `workflows/Comfy Recipe/` through the userdata API. Source entries are never rewritten.
- Never overwrite working copies. New bundled revisions are offered as explicitly requested versioned siblings.
- Read back every external write before recording/reporting success; state lives in the existing profile-safe plugin data folder.
- No first-run node/model installation, personal-media upload, generation, paid API calls, or restart as a publication side effect.
- Preserve graph layout and all source widget values. Only distributed top-level identity normalization is allowed during capture.
- Use native `ctx.register_skill`. No `recipes/index.json`, second skill catalog, or custom skill execution engine.
- Optional skill references: frontmatter `metadata.comfy_recipe.workflow_ids`; absent or `[]` means workflow-free.
- All manual ComfyUI edits and generation tests in this session use `drive_preview`; never use `comfy_run`.
- Keep source code, assets, docs, and tests uncommitted. Do not install packages into Hermes or touch another profile.
- Version the feature addition as `0.4.0`; this is not a claim that a final cross-platform v1 release has been certified.

## Review Focus

1. Existing same-name JSON without an installation record: preserve it, even on first setup; Task 2 pins this.
2. A save succeeds but read-back fails or differs: never mark publication complete; Task 2 pins this.
3. One workflow fails while five succeed, then retry: retain verified successes and do not duplicate them; Task 2 pins this.
4. Frontend-only nodes and stale model-description metadata: don't claim missing backend packs or required alternative weights without evidence; Task 3 pins this.
5. Skill-only use or startup with a foreign/unavailable instance: skill loading stays offline and no implicit writes/start/stop occur; Tasks 1 and 4 pin this.

## Verified prerequisites

- `python` is the active Hermes-managed Python 3.14.9. PyYAML is importable. `pytest` is not installed; use `python -m unittest discover -s tests -v` rather than changing that environment.
- Existing extension points have been read: `plugin.__init__.register`, `_workflows`, `_session_start`, `core.setup_start`, `core._object_info_path`, `core.active`, and `comfy_client._req/load_workflow/list_workflows`.
- Existing template publication uses POST `/api/userdata/{encoded_path}?overwrite=false`; reuse the client, but add exact read-back verification.
- The saved six source files pass a read-only node/link endpoint-and-slot audit. This is structural evidence, not proof that every workflow can execute.
- Two MiniMax source files share an internal top-level UUID; distribution must isolate their identities.
- The source repository began clean except for the newly written design docs. No product-code changes have been made while preparing this plan.

## File map

| File | Responsibility |
| --- | --- |
| `plugin/workflows/catalog.json` and six `.json` assets | Versioned shared workflow library and verified/unknown requirement metadata. |
| `plugin/library.py` | Catalog/path/hash validation and non-destructive working-copy publication with read-back and installation state. |
| `plugin/skill_registration.py` | Ordinary SKILL.md discovery/frontmatter validation and optional workflow references; no ComfyUI calls. |
| `plugin/dependencies.py` | Read-only, separated requirement reports from catalog, graph, and live backend evidence. |
| `plugin/__init__.py` | Existing tool schema/handler, native skills, commands, and session fast-path integration. |
| `plugin/core.py` | Managed-start provisioning helper and current profile-safe runtime data integration. |
| `plugin/skills/session/SKILL.md` and references | Visible library/check/Manager procedure and authoring rules. |
| `tests/test_library.py`, `tests/test_skills.py`, `tests/test_dependencies.py`, `tests/test_plugin_integration.py` | Standard-library unit and controlled-server integration tests. |
| `docs/WORKFLOW_LIBRARY.md`, README, DEVELOPMENT.md, plugin.yaml | Authoring, consent/update behavior, activation instructions, and version. |

## Interfaces to implement

These are proposed interfaces, not existing verified implementations:

```python
# plugin/library.py
load_catalog(root: Path | None = None) -> dict
load_asset(entry: dict, root: Path | None = None) -> dict
publish(inst: dict, data_dir: Path, workflow_ids: list[str] | None = None,
        versioned: bool = False, root: Path | None = None) -> dict

# plugin/skill_registration.py
skills_for_registration(skills_dir: Path, workflow_ids: set[str]) -> list[dict]
# rows: {name, path: Path, description, workflow_ids: list[str]}

# plugin/dependencies.py
check(inst: dict, entry: dict, workflow: dict, object_info: dict) -> dict

# plugin/core.py
ensure_managed_library() -> dict
# guard setup == managed and a verified live managed instance; never starts it
```

`publish` returns per-workflow results with statuses such as `installed`, `unchanged`, `conflict`, `update_available`, and `error`, plus actual counts computed from those results. It does not hide partial failures behind a single success boolean. Use stable canonical JSON hashing for semantic comparison while retaining a byte checksum for package integrity.

## Task 1: Capture the six assets and register native skills

**Files:** Create `plugin/workflows/catalog.json`, the six asset files, `plugin/skill_registration.py`, `tests/test_skills.py`, and catalog tests in `tests/test_library.py`. Modify native skill registration in `plugin/__init__.py` only after tests pass.

**Consumes:** The six approved source paths in the spec, the visible open tabs, and existing `ctx.register_skill`.
**Produces:** Valid catalog/assets, `load_catalog`, `load_asset`, and `skills_for_registration` as declared above.

- [ ] Reopen/select the existing ComfyUI preview tab, inventory the six workflow tabs, and click each by hand to check the title's dirty marker. Do not discard or save dirty tabs silently. Resolve any unsaved-source choice with the user before capture.
- [ ] Freeze the agreed source bytes and hashes in a scratch capture directory before generating package assets; subsequent generation reads only that frozen input, never its own output. Do not commit author-machine source paths.
- [ ] Write failing `unittest` cases for exactly six IDs, asset hash mismatch, traversal/absolute paths, duplicate catalog IDs/UUIDs, and zero/shared/multiple skill references. Start skill tests with temporary SKILL.md fixtures:

```python
import tempfile
import unittest
from pathlib import Path
from plugin.skill_registration import skills_for_registration

class SkillDiscoveryTests(unittest.TestCase):
    def test_workflow_free_skill_is_offline(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            p = root / 'diagnostics' / 'SKILL.md'
            p.parent.mkdir()
            p.write_text('---\nname: diagnostics\ndescription: Diagnose workflows.\n---\nRead-only instructions.\n', encoding='utf-8')
            rows = skills_for_registration(root, {'shared'})
            self.assertEqual(rows[0]['name'], 'diagnostics')
            self.assertEqual(rows[0]['workflow_ids'], [])
```

- [ ] Run `python -m unittest discover -s tests -p test_skills.py -v` and record the expected failure before implementation. Add equivalent fixtures with `metadata: {comfy_recipe: {workflow_ids: [shared]}}` in two skills, one skill with two different IDs, a missing ID, malformed YAML/types, and an escaped/symlinked path. Assert discovery performs no network calls.
- [ ] Implement package-contained path checking and ordinary YAML frontmatter parsing. Require stable directory names and nonempty descriptions. Permit absent/empty workflow metadata. Register each discovered skill using the existing API, preserving the public `session` name. Validation errors must be clear; do not silently reinterpret malformed metadata as workflow-free.
- [ ] Capture the six JSON files without changing widget values or wiring. Assign deterministic unique distributed top-level UUIDs using a documented UUID5 namespace derived from stable library IDs. Keep source originals unchanged. Record allowed identity differences and scans for personal paths/secrets/input files; require author resolution for any actual secret before bundling.
- [ ] Build a schema-version-1 catalog with library version `1.0.0`, asset versions `1.0.0`, stable IDs from the spec, relative filenames, SHA-256 package hashes, descriptions/media types, and requirement records. Take node providers/versions from source metadata and live evidence; unknowns stay unresolved. No invented tested versions or model sizes.
- [ ] Run skill/catalog tests and compare every captured asset against its frozen source after removing only the documented top-level identity change. Assert original source hashes still match. Check diff; do not commit.

## Task 2: Implement safe workflow publication

**Files:** Implement `plugin/library.py`; extend `tests/test_library.py`. Reuse `plugin/comfy_client.py` without changing its existing call contracts.

**Consumes:** Task 1 catalog and assets; `cc._req`, `cc.list_workflows`, and `cc.load_workflow`.
**Produces:** `publish` as declared above and profile-local installation records.

- [ ] Add a controlled local HTTP fixture implementing the existing userdata GET/list/POST behavior. Reject overwrite-enabled requests and record every method/path. Tests must use disposable directories and cannot connect to port 8190.
- [ ] Add first-publication and identical-repeat tests: six files created, each read back, six exact IDs, then zero additional POSTs on repeat. Use a fresh temporary state folder per test.
- [ ] Run the tests and record RED before implementing publication.
- [ ] Implement the decision table explicitly:

```python
# Inside the per-entry loop, after listing/loading the existing target:
if destination_exists:
    if canonical_hash(existing) == canonical_hash(asset):
        status = 'unchanged'
    elif trusted_record_matches_existing:
        status = 'update_available'
    else:
        status = 'conflict'
else:
    # POST must keep overwrite=false; a concurrent HTTP 409 becomes conflict.
    # GET the exact target and compare before recording installed status.
    status = create_and_verify_target()
```

`canonical_hash` and `create_and_verify_target` are private helpers owned by this task. Compare JSON semantically; do not overwrite user files to normalize formatting. Use atomic writes for publication records and scope them to instance URL/root/destination rather than a short display name alone.

- [ ] Add tests for: same-name foreign file with missing state; edited user copy; old bundled revision; explicit versioned sibling publication/repeat; HTTP 409 race; unavailable server; invalid/corrupt local state; POST success with read-back mismatch; one failed entry followed by a successful retry. Assert correct per-entry statuses and counts, no accidental duplicate names, and no misleading installed record after unverified writes.
- [ ] Make state-loss/corruption fail conservatively: an existing identical file can be recognized as unchanged; an existing different file remains protected. A changed version's sibling name is deterministic from its stable ID/version; never overwrite a conflicting sibling.
- [ ] Assert the HTTP fixture saw only workflow userdata operations; no `/prompt`, `/interrupt`, model download, package installation, or process lifecycle calls.
- [ ] Run all library tests to GREEN, inspect paths and diff, and leave changes uncommitted.

## Task 3: Add honest per-workflow dependency reports

**Files:** Create `plugin/dependencies.py` and `tests/test_dependencies.py`; finish catalog requirement metadata. Do not add an automatic custom-node installer.

**Consumes:** Catalog entries and UI graphs from Task 1, live `/object_info`, read-only model listings through `cc.get_json`, and source node provider metadata.
**Produces:** `check` with separate report dimensions: node compatibility, missing/custom/unresolved providers, models, input assets, external programs, credentials/services, and hardware/compatibility notes.

- [ ] Write failing tests using small explicit graph fixtures: available core node; embedded subgraph plus UI note; missing declared custom pack; absent node with no provider; a declared frontend-only helper; a model whose source-description metadata lists an unused alternative; required user media; paid-service workflow. Do not mark unused alternative weights missing merely because `properties.models` lists them.
- [ ] Run `python -m unittest discover -s tests -p test_dependencies.py -v` and record RED.
- [ ] Implement graph traversal including subgraph definitions. Exclude embedded definition UUIDs and known UI-only nodes. Frontend-only helpers require explicit catalog evidence; do not globally hide every unknown class. Prefer exact selected-model metadata curated in the catalog over stale descriptive alternatives. Validate model paths and filenames without fuzzy substitutions.
- [ ] Report missing nodes separately from proven import failures. If the pack's installation/import state was not queried, say unavailable/unresolved rather than inventing an import-failed diagnosis. Likewise, a paid API credential cannot be considered valid merely because the node exists.
- [ ] Group missing nodes by verified registry pack ID and expose tested versions/source only when known. Unresolved providers get no automatic repository/installation recommendation. Return a concise Manager-first installation plan with consent and restart requirements; the agent follows it visibly in the ComfyUI window.
- [ ] Test a stale object-info scenario: the caller's refreshed information removes a missing-node result after installation, while cached information does not falsely claim it changed. Include unavailable model-list endpoints as unknown/error, not an empty installed-model list reported as certain.
- [ ] Run dependency tests to GREEN and inspect actual reports for all six bundled entries read-only. Verify collection count against six. Do not install missing Wan dependencies or trigger MiniMax jobs.

## Task 4: Wire startup/tools, document, and verify

**Files:** Modify `plugin/core.py`, `plugin/__init__.py`, `plugin/plugin.yaml`, README, DEVELOPMENT.md, and session skill/reference instructions. Create `tests/test_plugin_integration.py` and `docs/WORKFLOW_LIBRARY.md`.

**Consumes:** Tasks 1–3 interfaces and existing setup/session functions read during planning.
**Produces:** Working startup provisioning, public tool actions, command guidance, native skills, docs, and a verified local change set.

- [ ] Add failing integration tests before wiring: `core.setup_start` attaches a separate library result only when managed startup reports running; a library failure does not change successful server health; the running-session fast path calls the managed guard; foreign setup never auto-publishes; library listing and skill discovery work offline; existing tool actions still dispatch as before.
- [ ] Extend `comfy_workflows` with `action=library`, `action=install`, and `action=check`. Retain `list`, `describe`, and `timings`. Add `workflow_ids` for selective publication and `versioned` for explicit sibling updates. `check` takes a bundled stable ID in `workflow`; do not silently treat an ambiguous saved filename as a bundled ID. Make descriptions explicit about side effects and consent. Do not add a separate recipe tool.
- [ ] Implement `core.ensure_managed_library()` using `_load_state`, `_managed_instance`, live-health evidence, and `core.DATA`. It never starts/stops anything. Call it after `core.setup_start` succeeds and from `_session_start` for an already-running managed setup. Protect the fast path with the publication record so repeated sessions do not recopy or repeatedly scan every remote file unnecessarily; verify external writes whenever they happen. Surface failures separately and make explicit retry possible.
- [ ] Add `/comfy library`, `/comfy library install`, and `/comfy check <stable-id>` command routes reusing the same library/check functions. Preserve existing command routes and startup-card behavior.
- [ ] Replace the single hardcoded session-skill registration with Task 1 discovery and registration, keeping `comfy-recipe:session` available. Update tool schemas, `plugin.yaml`, and version `0.4.0` consistently.
- [ ] Write authoring documentation with this ordinary skill metadata example:

```yaml
---
name: image-editing
description: Use when editing an image with references.
metadata:
  comfy_recipe:
    workflow_ids:
      - qwen-image-2-1-i2i
---
```

Also show a workflow-free skill (metadata absent), two skills sharing an ID, and one skill using multiple IDs. Explain shared library asset versions, capture/UUID rules, conflict-safe working copies, Manager-first installation, personal-media exclusions, and paid-service requirements. Do not create placeholder product skills from these examples.

- [ ] Extend session guidance: locate bundled working copies in `Comfy Recipe/`, run preflight for the selected workflow, ask consent before node/model installs, use Manager version selection, ask before restarts, refresh readiness, and continue to type prompts/select media/click Run visibly. Distinguish workflow publication from graph editing; retain all existing safety rules.
- [ ] Run the complete suite: `python -m unittest discover -s tests -v`; run `python -m compileall -q plugin tests`; run `hermes plugins validate C:/Users/pablo/Documents/GitHub/hermes-comfy-recipe/plugin`. Record real counts, failures, and warnings rather than inferred success. Do not mutate Hermes's environment to obtain a test runner.
- [ ] Perform a consented real library handoff integration check only against the plugin-managed instance, writing new copies exclusively under `Comfy Recipe/` and reading every target back. Do not overwrite the six source entries. Verify the copies are visible in ComfyUI's workflow browser with `drive_preview`, and open representative variants by hand. If consent for the live write is not yet explicit, ask before this step rather than bypassing the session's UI rule. Do not start generation to test publication.
- [ ] Obtain one fresh whole-change review after implementation, address findings, and rerun affected/full checks. Inspect `git diff --check`, `git status`, and secret/path scans. The final report separates tested repository behavior from live activation pending a full Hermes restart. Do not restart Hermes or commit on the user's behalf.

## Plan self-review

- Spec sections 1–4: Task 1 supplies the six shared assets, native skill registration, identity/path/hash checks, and no recipe registry.
- Spec section 5: Task 2 supplies idempotent, read-back-verified publication; Task 4 integrates both managed startup paths and explicit foreign installation.
- Spec section 6: Task 3 separates readiness dimensions; Task 4 supplies the consented visible Manager workflow without a second installer.
- Spec section 7: Task 1 reconciles open/saved sources, freezes inputs, preserves widgets/wiring, and scans packaging content.
- Spec sections 8–9: Task 4 preserves public contracts, updates docs/version, runs validation/tests, and distinguishes activation from implementation.
- All five Review Focus conditions have owning tests. No implementation snippet in this plan is claimed to have been run; only the listed prerequisite probes were executed.
- No commits, hidden generation, blanket dependency installation, or unrelated environment changes are included.

## Execution selection

Recommended: **Native**, because the four tasks share a small set of closely coupled interfaces. The agent implements sequentially in this session with one fresh independent review at the end. **Subagent-driven** is also available for independent implementation/review gates per task at greater context cost. User review and method selection precede product-code changes.

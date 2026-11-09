# Post-install setup and first-image tutorial

Fresh managed installations open text-to-image first. After the ready summary, the agent asks one setup form:
- Missing node packs: install now (recommended), or when a workflow needs them.
- Missing models: download on use (recommended), or download now with the verified missing-download total.

The choices are independent. Shared/installed models are excluded; duplicate files are counted once. Sizes are
summed in bytes, rounded once to decimal GB and cached for an hour. Unknown sizes/inventory and files without
verified URLs remain explicit. Node-pack Python dependency download sizes are not included in the models-only total.
The proposal retains per-workflow missing-media, executable, external-service and portability warnings, separate
from installable packs/models. These limitations must be shown before consent; downloading dependencies does not
supply author-specific input files. Frontend settings require separate explicit consent. No installation occurs
merely from reading a proposal.

Approved work is done visibly through ComfyUI-Manager/the pane, checked again, and the managed instance restarted
only with disclosed consent and an idle queue. For packs spanning several graphs, open each affected workflow and
install only the approved missing packs; do not assume the current Issues panel lists the entire library.

## The first-image lesson

The user describes an image in chat. The native `qwen-image-2-1-prompting` skill writes a concise, faithful prompt,
including exact requested lettering. It does not load the optional enhancement model. The tutorial selects the
text-to-image working copy, types the prompt and clicks Run visibly. A backend baseline and prompt hash are recorded
immediately before Run; completion requires a new matching successful image with uncached sampling and visual review.

The bundled text-to-image graph is version 1.1.0: its prompt preview/encoder path receives the agent-written text
directly. The old built-in enhancement branch is disconnected from the output path so a fresh user need not download
that unused model just to pass validation. Every graph widget value is preserved. Existing user copies are never
overwritten; request a versioned bundle sibling when upgrading an existing graph. The image-edit graph is unchanged:
its connected enhancement loader may still require the file for validation even when refinement is off.

After one successful image, “skip tutorial”, or a second distinct Recipe chat, the ordinary question is available.
A failed or cached run does not count as completion. A technically successful inspected image can complete the
lesson even if a sign is misspelled: disclose that mismatch and offer an optional retry, never claim fidelity
without evidence. The second image in the SAME chat is not a second session.
The other five workflow tutorials are not implemented yet.

## Replay and state

`/comfy tutorial` displays the first-image introduction and records routing for that chat. Its next image description
reaches the tutorial hook even without a Recipe kickoff marker. In Recipe chats, “tutorial” / “start tutorial” replay
and “skip tutorial” exits. Quoted phrases and unrelated chats are not commands. Replay preserves setup preferences.

`comfy_onboarding` provides status, preferences, tutorial, complete and skip actions. Calling-session identity comes
from Hermes runtime context, not model arguments. `status refresh=true` rechecks all six workflows; `status
workflow=qwen-image-2-1-t2i` checks the lesson only. `tutorial begin_run=true prompt=<exact entered text>` prepares
verification; include `workflow_path=<exact visibly selected saved path>` when using a versioned sibling. The
selected copy's real UUID is checked; only the prompt hash is retained, not the description. Onboarding resolves
its backend from the managed manifest, rejects active-instance mismatches, and binds preparation/completion to
that backend identity. A switch or move during the prepared run requires preparation again.

Versioned JSON records live transactionally in `<hermes home>/plugin-data/comfy-recipe/onboarding.sqlite3`.
Fresh manifests have a stable install UUID and onboarding provenance. Legacy installs are not forced through the
wizard after an update. Corrupt state fails closed without assuming consent. Concurrent chats have separate lesson
records; a returning chat cannot replace another chat's initial setup choices. Adopt/move retains install identity.

Reference media belongs in [`plugin/assets/`](../plugin/assets/README.md). The folders are empty until approved,
redistributable assets are supplied. The first-image lesson needs no input media.

## Activation and verification

Python tools/hooks/skills require restarting the Hermes backend that loaded them; starting a new chat is not a reload.
Do not restart a user's backend or reset their onboarding history without permission. Unit/integration tests use
isolated temporary state and mock backend history; they do not download models or generate images. A live fresh-install
acceptance test is separate and requires explicit installation/download/generation scope.

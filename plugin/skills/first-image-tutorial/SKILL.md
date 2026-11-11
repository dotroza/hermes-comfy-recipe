---
name: first-image-tutorial
description: "Use when guiding tutorial step 1/4, the first image."
version: 0.3.0
author: dotroza, Hermes Agent
license: MIT
platforms: [windows, linux, macos]
metadata:
  comfy_recipe:
    workflow_ids: [qwen-image-2-1-t2i]
  hermes:
    tags: [comfyui, onboarding, tutorial, first-image]
    related_skills: [session, qwen-image-2-1-prompting, modify-image-tutorial]
---

# Tutorial (step 1/4): Generate your first image

## When to use
After fresh-install setup choices, or when the user asks for the tutorial (`/comfy tutorial`, “tutorial”, “start/
replay the tutorial”). The tutorial has 4 steps: 1 first image (this skill), 2 modify an image or create a
reference sheet (`comfy-recipe:modify-image-tutorial`), 3 first video (`comfy-recipe:first-video-tutorial`),
4 add sound (`comfy-recipe:add-sound-tutorial`).

## Procedure
1. Load `comfy-recipe:session` and `references/pane-recipe.md`. Call `comfy_onboarding action=tutorial step=1`
   once (idempotent; for an explicit restart request use `replay=true` once, never on every turn). Replay resets
   lesson progress, never node/model preferences. The result carries `downloads` for this step.
2. Start the reply with the heading `### 🎓 Tutorial (step 1/4): Generate your first image`, so the user sees they
   are in the tutorial. Open `Local Recipe/RCPlocal_t2i_qwen_image_2-1.json` visibly with `drive_preview` right away:
   the user should see the text-to-image workflow they are about to use. Re-read the page; never discard a dirty
   tab or overwrite a changed working copy. If the saved graph differs from the bundle, offer a versioned copy.
3. If `downloads.progress_card` is present, put that `MEDIA:<path>` line once, alone on its own line: it becomes a
   live progress card in the chat and a chip in the status bar. Do not repeat it.
4. Finish model readiness before asking for the image description: if this step's downloads are pending/running,
   call `comfy_downloads action=wait group=tutorial-1 wait_s=300` until done, with one short line per call.
   Do not poll the page while waiting. On completion immediately click the Missing Models header Refresh
   (`[data-testid='missing-model-header-refresh']`) in Issues and verify with `desktop_preview read` that this
   workflow no longer reports missing models. If the control is absent and warnings are already clear, no click is
   needed. Preserve dirty prompts/tabs; do not reload or close/reopen the page. Failed/stalled downloads are blockers,
   not readiness. If consent is needed, obtain it before waiting as described in step 6.
   Then, if the user has not supplied an image idea, ask:
   “Let’s create your first image: a person, a pet, an object or a place. Describe it here in the chat—who or
   what it is, where, a style, or just an idea. I’ll turn it into a prompt and make it in the ComfyUI window. You
   can say ‘skip tutorial’ at any time.” Do not substitute “What should I do first?” Other workflows may continue downloading in the background.
5. When a description arrives, note the subject kind (person, pet, object, outdoor location or indoor room): it
   picks the reference-sheet layout in steps 2-3. A single clearly visible subject, full body / whole object, on a
   simple background makes the later sheet and video easier; suggest it only when the idea allows, never force it.
   Load `comfy-recipe:qwen-image-2-1-prompting` and lightly clean the user's wording
   without adding a pose, setting or palette. The Image Gen defaults are `refine_prompt` ON, 25 steps,
   Lightning disabled (strength 0); preserve any explicit user settings.
6. Readiness before Run:
   - `downloads.consent_needed` (setup choice unanswered, legacy install): ask once with the verified GB, then
     `comfy_downloads action=start workflow_ids=["qwen-image-2-1-t2i"]`.
   - Queued downloads not done: `comfy_downloads action=wait group=tutorial-1 wait_s=300`, one short line per call.
   - `models_without_url`: search existing installs for the EXACT filename (hard-link offer); otherwise blocker.
   - Files added on disk while the pane is open still show as missing: click the Missing Models header Refresh
     (`[data-testid='missing-model-header-refresh']`) before Run. No pane reload needed.
   Settings need explicit consent. Unknown is not missing. No input image is needed for this step.
7. Briefly show the lightly cleaned prompt. Type it into the proper textarea using `drive_preview`. Preserve resolution,
   seed and other values unless a change is necessary and disclosed. Do not edit prompt, number, seed or image values
   through workflow JSON. Do not save the tab unless asked.
8. Read the exact saved path of the visibly selected working copy (including any `-v1.1.0` suffix).
   Immediately before Run, call `comfy_onboarding action=tutorial begin_run=true prompt=<exact entered prompt> workflow_path=<exact selected saved path>`
   to bind its actual UUID, managed backend, history baseline and prompt hash (not the text).
   If the active/visible instance differs from the managed installation, stop and ask for an explicit switch.
   Tell the user the described image will now be generated, then click Run in the window with `drive_preview`.
   Never queue the lesson with `comfy_run` or a direct API request.
9. Read `comfy_result prompt_id=latest`. Keep the explicit returned prompt id and verify it is the job just queued
   in this window. Inspect the image with `vision_analyze`, including requested text/counts. If it failed or was
   fully cached, explain and offer retry/skip; do not complete.
10. Call `comfy_onboarding action=complete prompt_id=<explicit corresponding id>` only after the successful image is
    inspected. The tool checks backend evidence; if rejected, investigate, never force state.
    Technical generation success is not a guarantee of image fidelity: a misspelled sign or wrong count must be disclosed honestly; offer
    an optional retry rather than claiming the lettering is correct.
11. Show the image with `MEDIA:<output path>` and a short timing line. Then ONE `clarify` call, one question:
    “What next? Continue the tutorial, or type a description to generate another image with the same workflow.”
    with the single choice **“Tutorial (step 2/4): Modify an image or create a reference sheet”** (the form's
    Other row is the text box).
    - Step 2 → `comfy_onboarding action=tutorial step=2`, then follow `comfy-recipe:modify-image-tutorial`.
    - A typed description → write the prompt, type it in the same text-to-image tab, Run visibly (no begin_run),
      show the image, then offer the same choice again.
    - Once the image and next-step choice are shown, stop: do not poll the page, run `elements`, or call `strobe`
      while waiting for the user. For read-only title/status checks use `desktop_preview read`; inventory only
      when a real action needs refs and reuse the refs/deltas already returned.

## Skip, replay and failures
- “skip tutorial”: call `comfy_onboarding action=skip`; do not generate. Say they can come back any time by asking
  for the tutorial in the chat, and can bring their own workflows and ask to install their dependencies.
- “Back to the tutorial” later: `comfy_onboarding action=tutorial resume=true` (lands on step 2 after step 1).
- A second distinct Comfy Recipe session opens normally. It is not tutorial completion.
- Missing dependencies, unavailable media, backend errors and failed jobs are blockers, not completed lessons.
- No input asset is required for this step; do not import private pictures or download example media.

## Verification
Completion requires an uncached successful image job associated with this lesson and a visual inspection.
One successful image completes the lesson; another image is optional, not a requirement.

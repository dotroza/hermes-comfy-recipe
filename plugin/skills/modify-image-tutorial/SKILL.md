---
name: modify-image-tutorial
description: "Use when guiding tutorial step 2/4, edit or sheet."
version: 0.2.0
author: dotroza, Hermes Agent
license: MIT
platforms: [windows, linux, macos]
metadata:
  comfy_recipe:
    workflow_ids: [qwen-image-2-1-i2i]
  hermes:
    tags: [comfyui, onboarding, tutorial, image-edit, reference-sheet]
    related_skills: [session, qwen-image-2-1-editing, first-image-tutorial, first-video-tutorial]
---

# Tutorial (step 2/4): Modify an image or create a reference sheet

## When to use
After step 1 when the user picks "Tutorial (step 2/4): Modify an image or create a reference sheet", says "modify an
image" / "create a reference sheet", asks to continue the tutorial after step 1, or runs `/comfy tutorial 2`.
Step 3 also sends you here to make a missing sheet first. The tutorial has exactly 4 steps.

## Procedure
1. Load `comfy-recipe:session` + `references/pane-recipe.md` and `comfy-recipe:qwen-image-2-1-editing`.
   Call `comfy_onboarding action=tutorial step=2` once (idempotent). It returns readiness and, when the setup choice
   allows, queues this step's models (group `tutorial-2`) and gives a `progress_card`.
2. Start the reply with `### 🎓 Tutorial (step 2/4): Modify an image or create a reference sheet`. Put the
   `progress_card` MEDIA line once, alone on its line, if there is one.
3. Switch the pane to the `RCPlocal_ti2i_qwen_image_2-1` tab (open since first launch; else Workflows sidebar →
   `Local Recipe`). Re-read the page; never discard a dirty tab. Point out in one line the Load Image node (`image_1`,
   the image that gets edited) and the before/after compare node. The bundled graph has ONE Load Image.
4. Offer the two paths (unless the user's message already chose):
   - **Modify an image**: use the step-1 image or attach one or several images and say what to change
     (example: "make it night time"). The first image is edited; the others are references.
   - **Create a reference sheet**: several views of the step-1 subject on one page; step 3 uses it to keep the
     subject consistent in the video. Then wait.
5. Readiness before any Run, in ONE consent form when something needs a yes:
   - `settings`: Nodes 2.0 (`Comfy.VueNodes.Enabled`) draws the ImageCompare slider; separate explicit consent. On yes:
     `comfy_workflows action=apply_settings workflow=qwen-image-2-1-i2i`, then `desktop_preview close` + `open` and
     switch back to the i2i tab. Never toggle it by hand in the Settings dialog.
   - `downloads.consent_needed`: ask once with the verified GB, then `comfy_downloads action=start workflow_ids=["qwen-image-2-1-i2i"]`.
   - `models_without_url`: search existing installs for the EXACT filename (hard-link offer); otherwise blocker.
   - Queued downloads: `comfy_downloads action=wait group=tutorial-2 wait_s=300` (one short line per call), then click
     the Missing Models header Refresh in the Issues panel so the window sees the new files.
6. Images (pane recipe §5: copy each attachment into `<root>/input/`, md5-dedupe, close + reopen the pane once,
   pick it with the node's file button, verify the label changed). Copy the step-1 output from `output/` into
   `input/` the same way.
   - **Modify**: image 1 → the Load Image (`image_1`). Each extra reference gets its own Load Image wired to the
     next free `image_N` (pane recipe §1b, API-mode wiring; standing consent).
   - **Reference sheet**: `comfy_onboarding action=reference_sheet kind=<person|pet|object|location|indoor>` with the
     step-1 subject kind (person → character sheet, outdoor place → location, room → indoor). It copies the bundled
     layout sheet into `input/` and returns `input_name`. `image_1` = the subject image, `image_2` = `input_name`
     (add and wire the second Load Image when the graph has one).
7. Write the prompt with `qwen-image-2-1-editing`, show it briefly, type it into `positive_prompt`.
   - Modify: change + reference jobs + keep list. Defaults `refine_prompt` OFF, 25 steps, Lightning LoRA 0.
   - Reference sheet: "Make a reference sheet of the subject in <image1>, using exactly the panel grid, views,
     framing and plain background of <image2>. Take only the layout from <image2>, never its subject, colours or
     text. Keep the subject's identity, proportions, colours and details from <image1> identical in every panel."
     Keep the bundled 25 steps and Lightning LoRA strength 0 (never switch a sheet to the 4-step Lightning mode). Why:
     the 4-step Lightning mode drifts a whole layout (a sheet came out ~80 px left and squeezed, even with an
     exact-size input); 25 steps kept every panel border within 1-2 px. `refine_prompt` OFF, resolution 1024.
   Preserve explicit user settings and the existing seed/resolution otherwise.
8. Read the exact saved path of the selected tab. Immediately before Run:
   `comfy_onboarding action=tutorial step=2 begin_run=true prompt=<exact text typed> workflow_path=<exact path>`.
   Tell the user the run starts, click Run with `drive_preview`. Never `comfy_run` or a direct API call.
9. `comfy_result prompt_id=latest`; keep the explicit prompt id. `vision_analyze` the output against the inputs:
   change landed / sheet follows the layout? keep list intact? reference leaks (the layout sheet's own subject)?
   For sheets also compare panel border positions with `<image2>`. Errors or fully cached runs are not completion:
   explain and offer a retry or "skip tutorial".
10. `comfy_onboarding action=complete prompt_id=<explicit id>` after the inspected success, then follow its
    instruction: show the result with `MEDIA:` plus a one-line summary (mention the before/after slider), disclose
    any fidelity problem honestly, and offer step 3 ("Tutorial (step 3/4): Create your first video").

## Skip and return
"skip tutorial" → `comfy_onboarding action=skip`; say they can come back by asking for the tutorial in the chat.
"Back to the tutorial" later → `comfy_onboarding action=tutorial resume=true`.

## Verification
Completion = one uncached successful edit job of this step's workflow, prepared with begin_run, visually compared
with its inputs. One success is enough; more edits are optional.

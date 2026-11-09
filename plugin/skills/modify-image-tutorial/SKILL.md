---
name: modify-image-tutorial
description: "Use when guiding tutorial step 2/6, Modify an image."
version: 0.1.0
author: dotroza, Hermes Agent
license: MIT
platforms: [windows, linux, macos]
metadata:
  comfy_recipe:
    workflow_ids: [qwen-image-2-1-i2i]
  hermes:
    tags: [comfyui, onboarding, tutorial, image-edit]
    related_skills: [session, qwen-image-2-1-editing, first-image-tutorial]
---

# Tutorial (step 2/6): Modify an image

## When to use
After step 1 when the user picks "Tutorial (step 2/6): Modify an image", says "modify an image", asks to continue
the tutorial after step 1, or runs `/comfy tutorial 2`. Steps 3-6 do not exist yet: never invent them.

## Procedure
1. Load `comfy-recipe:session` + `references/pane-recipe.md` and `comfy-recipe:qwen-image-2-1-editing`.
   Call `comfy_onboarding action=tutorial step=2` once (idempotent). It returns readiness and, when the setup choice
   allows, queues this step's models (group `tutorial-2`) and gives a `progress_card`.
2. Start the reply with `### 🎓 Tutorial (step 2/6): Modify an image`. Put the `progress_card` MEDIA line once, alone
   on its line, if there is one.
3. Switch the pane to `Comfy Recipe/RCP_qwen_image_2_1_i2i.json` visibly (Workflows sidebar). Re-read the page; never
   discard a dirty tab. Point out in one line the two Load Image nodes and the before/after compare node.
4. Tell the user (unless their message already did it): attach **one or several images** to this chat and say what to
   change. The first image is the one edited; the others are references (an outfit, an object, a style…).
   Give one example. Then wait.
5. Readiness before any Run, in ONE consent form when something needs a yes:
   - `settings`: Nodes 2.0 (`Comfy.VueNodes.Enabled`) draws the ImageCompare slider; separate explicit consent.
   - `downloads.consent_needed`: ask once with the verified GB, then `comfy_downloads action=start workflow_ids=["qwen-image-2-1-i2i"]`.
   - `models_without_url`: search existing installs for the EXACT filename (hard-link offer); otherwise blocker.
   - Queued downloads: `comfy_downloads action=wait group=tutorial-2 wait_s=300` (one short line per call), then click
     the Missing Models header Refresh in the Issues panel so the window sees the new files.
6. Load the images (pane recipe §5: copy each attachment into `<root>/input/`, md5-dedupe, pick it with the node's
   file button, verify the label changed):
   - image 1 → first Load Image (`image_1`, the canvas); image 2 → second Load Image (`image_2`).
   - One image only: mute the second Load Image (select it, Ctrl+M) and verify in the delta; if the backend then
     rejects a missing input, load the same image into both and leave `<image2>` out of the prompt.
   - Three or more: add one Load Image per extra image, wired to the next free `image_N` input of the edit
     subgraph (up to 10), visibly; say you did it.
7. Write the edit prompt with `qwen-image-2-1-editing` (change + reference jobs + keep list, `<imageN>` tokens).
   Show it briefly, type it into `positive_prompt`. Keep refine_prompt OFF, seed/steps/resolution unchanged.
8. Read the exact saved path of the selected tab. Immediately before Run:
   `comfy_onboarding action=tutorial step=2 begin_run=true prompt=<exact text typed> workflow_path=<exact path>`.
   Tell the user the edit starts, click Run with `drive_preview`. Never `comfy_run` or a direct API call.
9. `comfy_result prompt_id=latest`; keep the explicit prompt id. `vision_analyze` the output against image 1 (and
   the references): change landed? keep list intact? reference leaks? Errors or fully cached runs are not
   completion: explain and offer a retry or "skip tutorial".
10. `comfy_onboarding action=complete prompt_id=<explicit id>` after the inspected success. Show the result with
    `MEDIA:` plus a one-line summary of what changed (mention the before/after slider in the window). Disclose
    any fidelity problem honestly and offer one optional retry. Say steps 3-6 are coming later, then ask
    "What would you like to do?"

## Skip and return
"skip tutorial" → `comfy_onboarding action=skip`; say they can come back by asking for the tutorial in the chat.
"Back to the tutorial" later → `comfy_onboarding action=tutorial resume=true`.

## Verification
Completion = one uncached successful edit job of this step's workflow, prepared with begin_run, visually compared
with its inputs. One success is enough; more edits are optional.

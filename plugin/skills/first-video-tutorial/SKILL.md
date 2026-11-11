---
name: first-video-tutorial
description: "Use when guiding tutorial step 3/4, Create your first video."
version: 0.1.0
author: dotroza, Hermes Agent
license: MIT
platforms: [windows, linux, macos]
metadata:
  comfy_recipe:
    workflow_ids: [minimax-h3-r2v-mix, qwen-image-2-1-i2i]
  hermes:
    tags: [comfyui, onboarding, tutorial, video, minimax-h3, reference-sheet]
    related_skills: [session, modify-image-tutorial, add-sound-tutorial]
---

# Tutorial (step 3/4): Create your first video

## When to use
After step 2 when the user picks "Tutorial (step 3/4): Create your first video", says "create your first video",
asks to continue the tutorial after step 2, or runs `/comfy tutorial 3`. Workflow: `RCPlocal_r2v_video_minimax_h3`
(MiniMax H3 reference-to-video). Graph map, toggles and measured limits: `comfy-recipe:session`
`references/minimax-h3-mix.md` — load it.

## Inputs
| Role | Node | Source |
|---|---|---|
| First frame `<Picture 1>` | 150 Load Image (Use First Frame 160 = on) | the step-1 image, or the step-2 edit |
| Last frame `<Picture 2>` | 151 Load Image (Use Last Frame 161 = off) | bundled `assets/images/placeholder.png` (copy to `input/`) |
| Reference sheet `<Picture 3>` | 165 Load Image | the subject's sheet from step 2 |
| Motion `<Video 1>` | 155 Load Video (+ 157 Video Info -> 132 Float (Duration)) | optional short clip from the user |

The saved video takes its SOUND from the reference clip (155 `audio` -> 130 Create Video); MiniMax's own audio
decoder (121) is not wired. No clip = a silent video; step 4 then adds the soundtrack.

## Procedure
1. Load `comfy-recipe:session` + `references/pane-recipe.md` + `references/minimax-h3-mix.md`. Call
   `comfy_onboarding action=tutorial step=3` once (idempotent); it queues group `tutorial-3` when the setup choice
   allows and may return a `progress_card` (post it once).
2. Start the reply with `### 🎓 Tutorial (step 3/4): Create your first video`. Switch the pane to the
   `RCPlocal_r2v_video_minimax_h3` tab visibly (open since first launch; else Workflows sidebar → `Local Recipe`).
3. Sheet check: if the session has no reference sheet of the subject yet, say so in one line and make it first:
   switch to the image-edit tab and follow the reference-sheet path of `comfy-recipe:modify-image-tutorial`
   (`comfy_onboarding action=reference_sheet kind=<subject kind>`, 25 steps, Lightning 0, visible run, visual check).
   Do not call `begin_run`/`complete` for step 2 here; then come back to the video tab.
4. Ask (unless the message already says it): "Describe the action: what happens, how the subject moves, how the
   camera moves. You can also attach a short reference video (a few seconds) for the motion." Then wait.
5. Prepare media (pane recipe §5): copy the first-frame image, the sheet and `placeholder.png` into `input/`
   (md5-dedupe). A reference clip: `comfy_media action=convert` to 544x960 (or the image's aspect), 24 fps and
   <= 3.04 s (73 frames) with `to_input=true`. Reopen the pane once, then pick every file visibly: 150 = first frame,
   151 = placeholder, 165 = sheet, 155 = clip (combobox `opt-<file>`; check `select_every_nth` = 1).
6. No reference clip: select Load Video (155) and Video Info (157) and bypass both (`Bypass/Unbypass Selected Nodes`
   in the selection toolbar, or Ctrl+B); verify both show as bypassed. Then set Float (Duration) (132) to 3 visibly
   (reveal its number field, type, confirm). Never delete the nodes; un-bypass them later when a clip is used.
7. Prompt (type into Input Text (Prompt), 138): "Start exactly on `<Picture 1>`. `<Picture 3>` is the reference sheet
   of the same subject: keep its identity, colours and details in every frame. `<Picture 2>` is a blank white
   placeholder: ignore it completely." + the user's action + camera + (clip) "take only the motion and camera from
   `<Video 1>`; its subject is a different one and must not be copied" + (clip) its sound. Show it briefly.
8. Before Run: downloads `tutorial-3` done (`comfy_downloads action=wait group=tutorial-3 wait_s=300`), Lightning
   (146) on, Resolution Selector 0.5 MP or less on 24 GB. Read the exact saved path of the tab, then
   `comfy_onboarding action=tutorial step=3 begin_run=true prompt=<exact prompt typed> workflow_path=<path>`.
   Click Run visibly. A first run loads ~20 GB of models; tell the user it takes a few minutes.
9. `comfy_result prompt_id=latest` (call again while running; long runs: read `/internal/logs/raw`). Check the
   contact sheet visually: frame 0 matches `<Picture 1>`, the subject stays consistent with the sheet, no subject
   from the clip leaked in. Errors or fully cached runs are not completion: explain, offer retry or skip.
10. `comfy_onboarding action=complete prompt_id=<explicit id>`, then follow its instruction: show the video
    (`MEDIA:<path>`), one timing line, and offer step 4 ("Tutorial (step 4/4): Add sound to your video").

## Skip and return
"skip tutorial" → `comfy_onboarding action=skip`. "Back to the tutorial" → `comfy_onboarding action=tutorial resume=true`.

## Verification
Completion = one uncached successful video job of the r2v workflow, prepared with begin_run, its contact sheet
inspected. Technical success is not fidelity: disclose identity drift or a leaked subject honestly.

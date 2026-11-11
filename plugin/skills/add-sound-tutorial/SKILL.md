---
name: add-sound-tutorial
description: "Use when guiding tutorial step 4/4, Add sound to your video."
version: 0.1.0
author: dotroza, Hermes Agent
license: MIT
platforms: [windows, linux, macos]
metadata:
  comfy_recipe:
    workflow_ids: [ace-step1-5-xl-base]
  hermes:
    tags: [comfyui, onboarding, tutorial, audio, music, ace-step, mux]
    related_skills: [session, first-video-tutorial]
---

# Tutorial (step 4/4): Add sound to your video

## When to use
After step 3 when the user picks "Tutorial (step 4/4): Add sound to your video", says "add sound to your video",
asks to continue the tutorial after step 3, or runs `/comfy tutorial 4`. Workflow:
`RCPlocal_audio_ace_step1-5_xl_base` (ACE-Step 1.5 XL text-to-music), then `comfy_media action=mux`.

## Graph map (bundled file)
| What | Node | Notes |
|---|---|---|
| Tags (style, mood, instruments, bpm, key) | 94 `TextEncodeAceStepAudio1.5`, `tags` textarea | the prompt |
| Lyrics | 94, `lyrics` textarea | empty = instrumental |
| Song Duration (s) | 99 `PrimitiveNode` "Song Duration" | feeds both the latent (98) and the encoder; default 18 |
| Steps / CFG | 3 `KSampler` | 50 steps, CFG 5 |
| Output | 107 `SaveAudioMP3` | `output/audio/ace_step1.5_xl_base_*.mp3` |
| Load Audio 111 -> VAE Encode 112 | not connected to the sampler | never executed; its missing example file does not block a run |

## Procedure
1. Load `comfy-recipe:session` + `references/pane-recipe.md`. Call `comfy_onboarding action=tutorial step=4` once
   (idempotent); post a `progress_card` once if returned.
2. Start the reply with `### 🎓 Tutorial (step 4/4): Add sound to your video`. Switch the pane to the
   `RCPlocal_audio_ace_step1-5_xl_base` tab visibly.
3. Ask (unless the message already says it): "Describe the music or sound you want—style, mood, instruments, tempo."
   Give one example. Then wait.
4. Find the step-3 video (the completed step-3 run's output, or the one the user names) and
   `comfy_media action=probe` it: duration, and whether it already has sound (a reference clip carries its sound).
5. Write comma-separated tags from the description (genre, mood, instruments, tempo in bpm, key, "clean mix"); no
   invented lyrics unless asked (instrumental by default). Type them into the `tags` textarea of 94. Set Song
   Duration (99) to the video duration rounded UP to the next second (reveal its number field, type, confirm).
6. Before Run: downloads `tutorial-4` done (`comfy_downloads action=wait group=tutorial-4 wait_s=300`). Read the
   exact saved path of the tab, then `comfy_onboarding action=tutorial step=4 begin_run=true prompt=<exact tags typed>
   workflow_path=<path>`. Click Run visibly.
7. `comfy_result prompt_id=latest`: output MP3 path, timing, duration and level. Silence or a much shorter track is a
   failure to report, not completion.
8. `comfy_onboarding action=complete prompt_id=<explicit id>`.
9. `comfy_media action=mux path=<step-3 video> audio=<ACE mp3>`: when the video has its own sound the music is mixed
   UNDER it (music_volume 0.5, adjustable); a silent video gets it as its soundtrack. Trimmed/padded to the video
   length with a 0.5 s fade-out; the video stream is copied untouched; output `<video>_with_sound.mp4` next to the
   video. Check the result has an audio stream and the video's duration.
10. Show `MEDIA:<muxed path>`, one line on what was mixed, say the tutorial is complete (4/4) and any step can be
    replayed by asking for it, then ask "What would you like to do?"

## Skip and return
"skip tutorial" → `comfy_onboarding action=skip`. "Back to the tutorial" → `comfy_onboarding action=tutorial resume=true`.

## Verification
Completion = one uncached successful audio job of the ACE workflow, prepared with begin_run, its MP3 checked; then a
mux whose output has both the video and an audio stream.

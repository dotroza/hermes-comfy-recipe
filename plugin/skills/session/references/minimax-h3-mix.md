# MiniMax H3 mix workflow (`minimax-h3-r2v-mix`) — reference video + optional first/last frame

One graph covers both old workflows (`minimax-h3-r2v`, `minimax-h3-r2v-f2lf`, retired in library 1.3.0). Verified on
an RTX 3090 (24 GB) with the w6a8 diffusion model, the 8B text encoder, Lightning 4 steps and 0.3-0.5 MP.

## Graph map (node ids of the bundled file)

| What | Node | Notes |
|---|---|---|
| Reference video `<Video 1>` | 155 `VHS_LoadVideo` -> `ref_video_0` | its length sets the output length (157 `VHS_VideoInfo` -> 132 `Float (Duration)`) |
| First-frame image | 150 `LoadImage` -> guide 152 (`frame_idx 0`) AND `ref_image_0` = `<Picture 1>` | |
| Last-frame image | 151 `LoadImage` -> guide 153 (`frame_idx -1`) AND `ref_image_1` = `<Picture 2>` | |
| Character sheet | 162 `LoadImage` -> `ref_image_2` = `<Picture 3>` | bundled `assets/character-sheets/miskinou_sheet.png` |
| Toggles | 160 `Boolean (Use First Frame)`, 161 `Boolean (Use Last Frame)` | group "First frame / last frame" |
| Switches | 158 / 159 `If/Else Switch (First Frame / Last Frame)` | lazy: a switched-off guide is never computed |
| Speed | 146 `Boolean (Enable Lightning LoRA)`, 115 `Resolution Selector` | |

Conditioning path: `MiniMax positive -> [158 first] -> guide 153 -> [159 last] -> BasicGuider`.

| First | Last | Behaviour (measured, SSIM vs the guide image) |
|---|---|---|
| off | off | pure reference-to-video |
| on | off | frame 0 = first image (0.77) |
| off | on | last frame = last image (0.71) |
| on | on | same as the old f2lf graph |

## Rules that come from runs

- A Load Image that is switched off is still validated (its file must exist) and still feeds its `ref_image_N`.
  Point it at the bundled `assets/images/placeholder.png` (copy it to `input/`) and say in the prompt:
  "`<Picture 2>` is a blank white placeholder: ignore it completely."
- Rewrite the prompt for the toggles: never ask to "end on the last-frame image" with Last off.
- Duration: `Float (Duration)` is driven by the reference video's SOURCE duration. Cut the reference to the wanted
  output length first (`comfy_media convert` / `split`); 73 frames (3.04 s) at 0.5 MP is the safe size on 24 GB.
- `MiniMax H3 reference videos need at least 5 frames`: check Load Video's `select_every_nth` / `frame_load_cap`
  (a stray scroll set `select_every_nth=34` and cut 72 frames to 3).
- Each extra reference picture rides along every step: 21-26 s/step with 1-2 pictures, 34-84 s/step with three
  (frame + placeholder + sheet) at 0.5 MP. Drop unneeded pictures when speed matters.
- Pure r2v (both toggles off) did NOT swap the character in one test: with frame images still wired as
  `<Picture 1/2>` and w6a8 + 8B, the output kept the reference video's cat. The earlier successful swap used int8 + the
  32B encoder with sheet + photo only. Untested which factor matters; for a swap, prefer a first-frame guide that
  already shows the new character, or try the int8/32B models in the window.

## Long clips: chained 3 s segments (verified, 4 x 3 s -> 12.04 s, seams SSIM 0.97)

1. `comfy_media action=split seconds=3 chained=true width=544 height=960 fps=24 to_input=true` on the source: every
   segment starts on the previous segment's last frame (73 frames each).
2. Segment 1: the normal run (character sheet + photo, or first-frame image).
3. Segment k>1: `comfy_media action=frames which=["last"] to_input=true` on segment k-1's OUTPUT -> First frame image
   (150), Use First Frame on, Use Last Frame off (placeholder in 151), same sheet in 162, same megapixels as segment 1,
   reference video = source segment k. Prompt: "Continue the scene: start exactly on the supplied first-frame image
   `<Picture 1>` ..." + the action of this part of the source + the character description + "`<Picture 2>` is a blank
   white placeholder" + audio.
4. Reopen the pane after adding files to `input/` (the dropdowns and the Load Image asset list are cached).
5. `comfy_media action=join drop_first=1` on the outputs in order (removes each repeated first frame). Check every seam:
   SSIM(segment k frame 0, segment k-1 last frame) >= 0.95.

## Identity drift when the subject turns away or gets small

The guide only pins frame 0. When the subject walks away (back view, small in frame) the model copies the reference
video's subject (a calico cat came back). A prompt that says "take only the motion and camera from `<Video 1>`; the
cat in `<Video 1>` is a different cat and must NOT be copied" + an explicit back-view colour description fixed the
close part only. Next options: recolour the reference clip, or turn on the last-frame guide with a still of the
character from behind and far away.

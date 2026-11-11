---
name: qwen-image-2-1-editing
description: "Use when writing Qwen Image 2.1 image-edit prompts."
version: 0.1.0
author: Julien (dotroza), Hermes Agent
license: MIT
platforms: [windows, linux, macos]
metadata:
  comfy_recipe:
    workflow_ids: [qwen-image-2-1-i2i]
  hermes:
    tags: [comfyui, qwen-image, image-edit, multi-reference, keep-list, prompt-writing]
    related_skills: [session, modify-image-tutorial, qwen-image-2-1-prompting]
    source: hermes-comfy-recipe-spices comfy-change-only-x and comfy-multi-reference (adapted from scenario-labs/skills, MIT)
---

# Qwen Image 2.1 edit — agent-written edit prompts

## When to use
The user gives one or several images and asks for a change: in the tutorial step 2 or in normal work with
`Local Recipe/RCPlocal_ti2i_qwen_image_2-1.json`. For a brand-new picture from text use `qwen-image-2-1-prompting`.

An edit request has two halves: **the change** and **everything that must stay**. Anything unnamed is open to
change, so the keep list is the specification, not politeness.

## How the graph reads images
- `<image1>` is the **canvas**: the picture that gets edited. Output size and aspect follow it (custom_size off).
- `<image2>` … `<image10>` are references. Each reference has **exactly one job** (who, outfit, object, style,
  place, light…) and is told what NOT to lend: a reference lends everything it shows unless the prompt says otherwise.
- The bundled graph has two Load Image nodes (image_1, image_2). More references need one extra Load Image per
  image wired to the next free `image_N` input of the edit subgraph, in the window.
- Bundled defaults: Lightning LoRA OFF (strength 0), 25 steps, CFG 1, `refine_prompt` OFF. Hermes composes the explicit edit
  and keep-list; refinement stays off by default for localized edits. Preserve explicit user settings; do not
  silently switch modes. With CFG 1 the negative prompt does nothing: put constraints in the positive text.

## Prompt contract
One paragraph, in this order:
1. **The change**, concrete and located: `In <image1>, make only the middle lantern red.`
   Use frame sides: "on the left side of the frame", never "her left".
2. **Each reference's job** (only when there are references), one sentence each:
   `Use the jacket from <image2> exactly as designed in <image2> (colour, collar, stitching). Do not copy the
   person, pose or background of <image2>.`
3. **The keep list**, by name: identity and face, skin texture with visible pores, hair, garments, the other
   objects, background, light direction, framing and camera angle of `<image1>` — "exactly unchanged".
4. Finish with `Seamless photorealistic edit` (or the source medium), and `no added text` unless text is the change.

Edit-type patterns:

| Edit | Say it like this |
|---|---|
| Recolour one object | `Make only the middle lantern red. The other two lanterns stay yellow.` |
| One of a pair | `Change only the earring on the left side of the frame … the one on the right side of the frame stays exactly as it is.` |
| Replace from a reference | `Replace the jacket of the woman in <image1> with the jacket from <image2>, exactly as designed in <image2>.` |
| Add something | `Add a fine gold chain necklace resting on her collarbone.` + neckline unchanged |
| Remove something | `Remove the bicycle leaning on the wall; continue the brick wall naturally behind it.` |
| Text on a sign | `Change the sign from MOSSLY to FERNLY, same typeface, size and position.` (exact letters in quotes) |
| Background / world | Map each element: `the brick wall becomes a coral reef with the same shapes and positions` |
| Two changes | `Change two things, and nothing else. 1. … 2. …` (only when they are separate objects) |
| Whole-picture restyle | That is a regeneration, not an edit: say so and propose text-to-image or a style reference |

Example (two images, "put the hat from the second photo on my dog"):
`In <image1>, put the red knitted beanie from <image2> on the dog's head, exactly as designed in <image2> (red wool,
white pompom, folded brim), sitting naturally between the ears. Use <image2> only for the beanie: do not copy its
mannequin, background or lighting. Keep everything else in <image1> exactly unchanged, including the dog's face,
fur colour and texture, eyes, collar, the sofa, the window light from the left and the framing. Seamless
photorealistic edit, no added text.`

## Visible use
Show the prompt briefly, type it into the `positive_prompt` textarea with `drive_preview` (pane recipe), keep seed,
steps and resolution unless a change is needed and said. Never edit prompts or images through the JSON.

## Check the result
1. `vision_analyze` the output **and** `<image1>`: did the change land (done / missed / overdone / wrong one)?
2. Walk the keep list: face and identity, the other objects, background, framing. A glance misses a redraw, so
   compare details (eyes, hands, text, edges). Each reference: its job visible AND nothing else of it leaked.
3. Report honestly: technical success is not fidelity.

Fix by cause, always re-running from the **original** `<image1>`, max 3 rounds:

| Symptom | Fix |
|---|---|
| Change missed or too weak | More concrete wording (colour names, sizes, location in the frame) |
| Neighbours changed too | Name them in the keep list; "only the … on the left side of the frame" |
| Whole picture slightly redrawn / shifted | Keep `<image1>` as canvas, custom_size off, same resolution; say "exact framing of <image1>" |
| Reference leaked (its person, colours, background) | Tighten that reference's "Do not …" line |
| Reference ignored | Move its line first; describe what it lends concretely |
| Stacked edits drift | Each new edit's keep list includes every earlier finished edit |

## Limits
- Pixel-exact preservation needs a mask/inpaint lane; this graph is an instruction editor. Say so when the user needs
  provably untouched pixels (logos, product labels, faces with legal weight).
- Letter-perfect text is not guaranteed: inspect every letter and disclose mistakes.

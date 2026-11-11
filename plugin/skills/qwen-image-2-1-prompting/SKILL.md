---
name: qwen-image-2-1-prompting
description: "Use when writing Qwen text-to-image prompts."
version: 0.1.0
author: dotroza, Hermes Agent
license: MIT
platforms: [windows, linux, macos]
metadata:
  comfy_recipe:
    workflow_ids: [qwen-image-2-1-t2i]
  hermes:
    tags: [comfyui, qwen-image, prompt-writing, text-to-image]
    related_skills: [session]
---

# Qwen Image 2.1 — faithful prompts with built-in refinement

## When to use
A user describes an image for Qwen Image 2.1, in the first-image tutorial or normal generation.
Use `Local Recipe/RCPlocal_t2i_qwen_image_2-1.json`. Hermes lightly cleans the wording; the Image Gen
`refine_prompt` model handles creative expansion by default. Do not treat agent cleanup as a substitute for it.
For editing an existing image, use editing-specific guidance instead of inventing a text-to-image interpretation.

## Prompt contract
Write one concise, coherent paragraph ready for the positive-prompt textarea:
- Start with the requested subject and action; retain composition, environment, lighting and style only when supplied.
- Preserve intent, explicit counts, identities, relationships, framing and exclusions.
- Preserve **exact text** to appear in the image, including accents, case and punctuation, inside quotes.
  Keep the requested lettering language even if the rest of the descriptive prose is English.
- Lightly clean grammar and ambiguity without imposing an unrequested pose, setting, palette or photographic recipe.
  Do not add extra people, brands, reference images, unwanted text or camera hardware. A short clear idea needs a
  short clear prompt; let the built-in refiner expand it rather than converging different ideas on one composition.
- Ask one focused question only when a meaningful choice cannot be inferred. Do not make beginners fill out a form
  for subject/style/lighting when their request is already usable.

Example user idea: `A quiet little café in rain, watercolor, with the exact sign "Chez Léa"`.
Prompt: `A quiet little café in the rain, watercolor. The sign reads exactly "Chez Léa".`

## Visible use
Briefly show the lightly cleaned prompt, then use the session pane recipe to type it with `drive_preview`.
Bundled Image Gen defaults: `refine_prompt` ON, 25 steps, Lightning disabled with strength 0. Preserve any explicit
user settings; disclose a proposed mode change instead of silently overriding them. Check model readiness independently
of refinement mode: the connected enhancement loader can still require its file even with refinement off.
Do not change prompts or controls through JSON, or substitute a headless API run.
For CFG 1, the negative-prompt field is not an effective control: express essential constraints clearly in the
positive paragraph rather than claiming an ignored negative field will enforce them.

## Verification and limits
Compare the rewritten prompt against every explicit user constraint before entering it. After a consented visible
run, inspect the result (especially spelling and counts); enhancement does not guarantee exact rendered text.
Tutorial completion, skip and replay are handled by `comfy-recipe:first-image-tutorial`, not this writing skill.

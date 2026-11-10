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

# Qwen Image 2.1 — agent-written prompts

## When to use
A user describes an image for Qwen Image 2.1, in the first-image tutorial or normal generation.
This skill rewrites the description in the agent; it does not load another model or enable graph enhancement.
For editing an existing image, use editing-specific guidance instead of inventing a text-to-image interpretation.

## Prompt contract
Write one concise, coherent paragraph ready for the positive-prompt textarea:
- Start with the requested subject and action, then useful composition, environment, lighting and requested style.
- Preserve intent, explicit counts, identities, relationships, framing and exclusions.
- Preserve **exact text** to appear in the image, including accents, case and punctuation, inside quotes.
  Keep the requested lettering language even if the rest of the descriptive prose is English.
- Fill in only low-stakes visual details that support the idea. Do not add extra people, brands, reference images,
  unwanted text, camera hardware or stylistic contradictions. A short clear idea needs a short clear prompt.
- Ask one focused question only when a meaningful choice cannot be inferred. Do not make beginners fill out a form
  for subject/style/lighting when their request is already usable.

Example user idea: `A quiet little café in rain, watercolor, with the exact sign "Chez Léa"`.
Prompt: `A quiet little café on a rainy street, rendered in delicate watercolor. The café sign reads exactly
"Chez Léa". Soft reflections on the wet pavement and gentle washes of muted color create a peaceful atmosphere.`

## Visible use
Briefly show the rewritten prompt, then use the session pane recipe to type it with `drive_preview`.
Keep `refine_prompt` OFF: Hermes already enhanced the description. The enhancement model file is still a
required download (the window's Missing Models check blocks Run without it); it is fetched with the workflow's
other models, but never switched on. Do not change prompts or controls through JSON, or substitute a headless API run.
For CFG 1, the negative-prompt field is not an effective control: express essential constraints clearly in the
positive paragraph rather than claiming an ignored negative field will enforce them.

## Verification and limits
Compare the rewritten prompt against every explicit user constraint before entering it. After a consented visible
run, inspect the result (especially spelling and counts); enhancement does not guarantee exact rendered text.
Tutorial completion, skip and replay are handled by `comfy-recipe:first-image-tutorial`, not this writing skill.

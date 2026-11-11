---
name: comfy-refine-loop
description: Use when generated output must meet a brief through iteration.
metadata:
  comfy_recipe:
    workflow_ids: []
---
# ComfyUI Refinement Loop
Use for deliberate generate–review–adjust work, batches, or when the output must satisfy a concrete brief. Skip for a one-off exploratory image: show it and ask what the user thinks.

## Procedure
1. Translate the brief into 3–7 observable checks before generation. Preserve the user's style and intent; don't add taste criteria they did not request.
2. Record the baseline workflow, prompt, references, seed/settings, and intended output. Keep the original workflow untouched.
3. Make a small, inexpensive first batch. Use the visible ComfyUI pane by default; use `comfy_run` for headless batches only when appropriate and approved.
4. Inspect each output against the same checks using `vision_analyze` or `comfy_media action=sheet` for a contact sheet. Judge fine details on individual images, not downscaled sheets.
5. Route each failure to the smallest relevant change. Change one meaningful variable per round; re-run only failed items when possible.
6. Stop when the agreed checks pass, or after three unsuccessful rounds. At the limit, show the best results, remaining gaps, and ask before spending more GPU time.
7. Verify the delivered-size output itself, then report paths and unresolved issues.

## Fix routing
- Wrong content/composition: adjust only the relevant prompt clause or reference.
- Local defect: use an appropriate edit/inpaint workflow if available.
- Color/crop/format issue: prefer deterministic finishing over regeneration.
- Identity/style drift: load `comfy-recipe:comfy-consistency` when this is the actual problem.
- Run error: load `comfy-recipe:comfy-run-recovery`.

Never chain every failed output as the next input; it compounds drift. Never claim a quality gate passed without checking the actual delivered file. Cloud workflows require explicit approval before each paid run.

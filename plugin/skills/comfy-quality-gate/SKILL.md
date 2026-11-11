---
name: comfy-quality-gate
description: Use when ComfyUI outputs need review before delivery.
metadata:
  comfy_recipe:
    workflow_ids: []
---
# ComfyUI Output Quality Gate
Use before delivering a batch or when the user asks whether an output meets a brief. This is a review and verdict, not an automatic regeneration loop.

## Procedure
1. Write down the user's acceptance checks before reviewing. Include format, dimensions, reference fidelity, and any must-not-change details that apply.
2. Verify the job completed and identify the exact output files with `comfy_result`. Do not treat cached/partial/error results as successful outputs.
3. Inspect each delivered file with `vision_analyze`. Use `comfy_media action=probe` for media metadata and `action=sheet` for broad video/batch triage; inspect individual frames/images when details matter.
4. Compare references item by item: mark each required feature as preserved, changed, missing, or uncertain. Read visible text carefully and disclose uncertainty.
5. Give each item a `pass`, `warn`, or `fail` with specific evidence tied to the checks. A composite contact sheet is not enough to certify tiny text, fine edges, or every video frame.
6. For failures, suggest one concrete fix or load `comfy-recipe:comfy-refine-loop` if iterative work is requested.
7. Deliver only the files that were actually inspected. Include the verdict and any accepted warnings; show outputs with `MEDIA:`.

Do not invent numerical quality scores, call an unverified result a pass, or silently regenerate. Get approval before more runs, especially for paid cloud workflows.

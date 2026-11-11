---
name: comfy-consistency
description: Use when a character, product, or style must stay consistent.
metadata:
  comfy_recipe:
    workflow_ids: []
---
# ComfyUI Consistency
Use when generating a set of images or video where a subject, design, or style must remain recognizably consistent. Not needed for a single image or a precise local edit.

## Procedure
1. Ask what must stay fixed and what may change. Record visible identity cues (silhouette, colors, markings, proportions, text, framing) and the requested variation.
2. Pick the least complex available approach: (a) repeat a stable base prompt and append only the requested change; (b) reuse an approved reference image in a compatible workflow; (c) use a style or control reference if the selected workflow supports it. Check actual workflow inputs with `comfy_workflows` before promising a lane.
3. Use one consistent workflow and reference ordering across the set. Do not assume seed reuse guarantees identity.
4. Generate a small sample first. Compare each result against the fixed cues and the reference using `vision_analyze`; note changed, missing, or added features.
5. If drift appears, strengthen the written description or improve/re-role the reference before considering another workflow. Never use an unapproved, off-model output as the new identity anchor.
6. For video, inspect multiple frames with `comfy_media action=frames` or `action=sheet`; first/last frames alone may miss drift.
7. Report what stayed consistent, what changed, and any limitation. Ask before downloads, custom-node installs, paid cloud runs, or large batches.

Keep the baseline description identical across items and express each requested change explicitly. Don't promise character identity, style fidelity, or frame consistency beyond what the output inspection supports.

---
name: comfy-workflow-authoring
description: Use when building or changing a saved ComfyUI workflow.
metadata:
  comfy_recipe:
    workflow_ids: []
---
# ComfyUI Workflow Authoring
Use when the user asks to build a workflow, add a stage, or change saved graph wiring. For prompt, seed, or widget changes, use the visible ComfyUI interface instead. Follow `comfy-recipe:session` for UI-JSON editing details when applicable.

## Procedure
1. Inspect available workflows and templates with `comfy_workflows` and `comfy_templates`; prefer a ready graph close to the request over starting blank.
2. Describe the source graph and confirm its relevant inputs, outputs, node types, and dependency readiness. Do not guess widget or socket names.
3. Preserve the original. Make graph changes in a separately named sibling copy or in the visible UI with explicit user direction; do not overwrite a user's saved graph.
4. Make the smallest coherent change. Explain any required custom nodes, model downloads, external services, or paid cloud execution and ask before installing, downloading, or running paid work.
5. Validate with `comfy_run` `dry_run=true` when the workflow and instance support it. A clean validation is not proof of a successful generation.
6. If approved, run once at low-cost settings, inspect the result with `comfy_result` and `vision_analyze`, and confirm the output is usable.
7. Report the new saved path, the graph changes, validation/run outcome, and requirements still missing.

## Guardrails
- A batch of references wired into one image input may condition one generation on all of them; it does not necessarily create one output per reference.
- Images grouped into a batch may need matching dimensions; check the graph's expected input shape before batching.
- Nodes that do not feed an output may not execute.
- A saved-graph headless run does not include unsaved edits in the open pane.
- Never bundle secrets, machine-specific paths, personal media, or model binaries into distributed graph definitions.
- Workflow definitions, node availability, and readiness do not establish that a run is free or authorized. Obtain explicit consent before paid cloud execution.

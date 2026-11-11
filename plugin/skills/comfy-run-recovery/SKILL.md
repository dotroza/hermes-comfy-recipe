---
name: comfy-run-recovery
description: Use when a ComfyUI run fails, hangs, or returns no output.
metadata:
  comfy_recipe:
    workflow_ids: []
---
# ComfyUI Run Recovery
Use this only when a ComfyUI job errors, stalls, produces no output, or returns an obviously broken result. Diagnose before retrying; do not duplicate jobs or change user files without consent.

## Procedure
1. Capture the exact error, prompt/job ID, workflow name, and what changed since the last successful run.
2. Check the instance with `comfy_instances`. A transport timeout is not proof of job failure: check `comfy_result` for that prompt ID before retrying.
3. Validate the saved workflow with `comfy_run` using `dry_run=true`; use `comfy_workflows` to inspect the workflow and connected image inputs. Distinguish missing node types, disconnected inputs, invalid model names, and missing files.
4. Check model/node readiness with `comfy_workflows action=check workflow=<stable ID>` for bundled workflows, or inspect the template/workflow requirements for user workflows. Ask before installing packs or downloading models; cloud workflows may incur costs and require explicit per-run approval.
5. For OOM, propose one lower-cost change at a time (resolution, frames, batch size, or model precision). Do not restart another person's ComfyUI. Restart only the managed instance with the user's approval and an idle queue.
6. Apply a minimal fix in the visible window or a separate workflow copy, then retry once at the cheapest useful settings. If the same error persists, re-evaluate the diagnosis rather than looping.
7. Verify with `comfy_result` and inspect the actual output. Report the cause, fix, output path, and any remaining limitation; use `MEDIA:` for deliverables.

## Common clues
- Same output again: check `cached_nodes`; change a relevant input or seed only if the user wants a new sample.
- Missing node type: the required custom-node pack is unavailable; ask before installation.
- Missing model: report the exact filename/folder and ask before download.
- No output: check whether a reachable output node exists and whether the job is still running.
- Wrong image or video shape: inspect the failing node's expected input types, frame count, dimensions, and model-family pairing.

## Boundaries
Do not queue duplicate work, overwrite the original graph, install/download/restart without consent, or claim a fix based solely on a successful validation. A real result must be read back and inspected.

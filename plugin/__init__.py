"""Comfy Recipe - Hermes plugin to work in a local ComfyUI, visibly in the preview pane or headless.

Tools: comfy_setup, comfy_onboarding, comfy_downloads, comfy_instances, comfy_workflows, comfy_templates, comfy_run,
comfy_result.  Command: /comfy.
First run: the kickoff asks whether to install Comfy Recipe's OWN ComfyUI (installer.py, uv-based, separate from any
other ComfyUI on the machine) or to use an existing one.
Hook: pre_llm_call (ComfyUI-session instructions, model-side only).  Skill: comfy-recipe:session.
Logic lives in core.py (Hermes-independent); this file wires schemas, settings, the hook and the command.
"""
from __future__ import annotations

import json
import shlex
import time
from pathlib import Path

from . import core
from . import templates
from . import installer
from . import library, dependencies, skill_registration, onboarding_flow, download_flow, media

TOOLSET = "comfy_recipe"
SKILL = "comfy-recipe:session"
SETTING_KEYS = ("personal_skill", "motto", "extra_urls", "stabilitymatrix_dirs", "converter_python", "stop_with_hermes")
_CTX = None


def _settings() -> dict:
    out = {}
    if _CTX is not None:
        for k in SETTING_KEYS:
            try:
                out[k] = _CTX.get_config(k)
            except Exception:
                pass
    return out


def _sync_settings() -> dict:
    s = _settings()
    core.configure({k: v for k, v in s.items() if k in core.SETTINGS})
    return s


def _ok(data) -> str:
    return json.dumps({"success": True, **(data if isinstance(data, dict) else {"result": data})}, ensure_ascii=False, default=str)


def _wrap(fn):
    def handler(params, **kwargs):
        try:
            _sync_settings()
            result = fn(params or {})
            if fn is _setup and isinstance(result, dict) and (result.get('running') or result.get('state') == 'done'):
                result['onboarding_instruction'] = ('After ComfyUI is running and open in the pane, call comfy_onboarding action=status. '
                    'Follow its next_step before the ordinary question. Base install consent does not authorize node/model downloads.')
            if isinstance(result, dict) and result.get('progress_card'):
                result['progress_card_rule'] = onboarding_flow.CARD_RULE.strip()
            return _ok(result)
        except Exception as e:  # tools must return JSON, not raise
            return json.dumps({"success": False, "error": f"{type(e).__name__}: {e}"}, ensure_ascii=False)
    return handler


def _onboarding_handler(params, *, session_id=None, task_id=None, **kwargs):
    try:
        _sync_settings()
        return _ok(onboarding_flow.handle(params or {}, session_id or task_id))
    except Exception as exc:
        return json.dumps({'success': False, 'error': f'{type(exc).__name__}: {exc}'})


SCHEMAS = {
    "comfy_onboarding": {
        "name": "comfy_onboarding",
        "description": "Managed-install setup choices and the step-by-step tutorial (step 1/6 Generate your first image = text-to-image, step 2/6 Modify an image = image edit; steps 3-6 not built yet). status reports missing requirements and verified model download GB; preferences records the submitted setup answers and DOES the approved work itself: nodes=now installs the missing node packs through ComfyUI-Manager (no window clicks), models=now queues every download (tutorial step 1 first), settings=apply turns on the proposed frontend settings (e.g. Nodes 2.0); its instruction lists the remaining steps in order (wait, comfy_setup restart, reopen pane). tutorial starts or continues a step (step=1|2, replay=true restarts, resume=true goes back to where the user left off) and queues that step's model downloads when the setup choice allows; begin_run=true snapshots history immediately before a visible Run. complete verifies an explicit prompt_id against backend image evidence; skip exits. Results may carry progress_card (a MEDIA line to post once). All runs stay visible through drive_preview. Session identity comes from runtime, not arguments.",
        "parameters": {"type": "object", "properties": {
            "action": {"type": "string", "enum": ["status", "preferences", "tutorial", "complete", "skip"]},
            "nodes": {"type": "string", "enum": ["now", "on_use"]},
            "models": {"type": "string", "enum": ["now", "on_use"]},
            "settings": {"type": "string", "enum": ["apply", "skip"], "description": "preferences: the user's answer to the separate settings question (e.g. Nodes 2.0)"},
            "step": {"type": "integer", "enum": [1, 2], "description": "tutorial: which step (1 = first image, 2 = modify an image)"},
            "resume": {"type": "boolean", "description": "tutorial: go back to the tutorial where the user left off"},
            "workflow": {"type": "string", "description": "status: optional bundled workflow id for on-use readiness"},
            "workflow_path": {"type": "string", "description": "tutorial begin_run: exact selected saved path of this step's workflow, including any -v1.1.0 suffix; read it from the visible workflow selection"},
            "replay": {"type": "boolean"}, "begin_run": {"type": "boolean"},
            "refresh": {"type": "boolean", "description": "status: recheck all bundled workflows after approved setup work"},
            "prompt": {"type": "string", "description": "tutorial begin_run: exact enhanced text entered visibly; only a hash is stored"},
            "prompt_id": {"type": "string", "description": "complete: explicit id of the corresponding window run, not latest"}
        }, "required": ["action"], "additionalProperties": False},
    },
    "comfy_downloads": {
        "name": "comfy_downloads",
        "description": "Download model files for ComfyUI in the BACKGROUND with live progress (byte-accurate, resumable). "
                       "Order: tutorial step 1 files, then tutorial step 2, then the rest (smallest first). "
                       "action=start queues missing files of bundled workflows (workflow_ids, omitted = all), of a "
                       "saved workflow the user brought (workflow=<saved path>: reads the model links its loader nodes "
                       "declare) or an explicit models list - only after the user agreed to the download. Returns "
                       "progress_card: post that MEDIA:<path> line ONCE on its own line, the desktop app shows a live "
                       "progress card + status-bar chip. action=status reads progress; action=wait group=tutorial-1|"
                       "tutorial-2 (wait_s up to 900) blocks until that group is ready; action=cancel stops queued files. "
                       "action=install_nodes (after consent; packs=[ids or names], omitted = every missing pack of the bundled "
                       "workflows) installs node packs itself through ComfyUI-Manager's API - nothing to click, never search "
                       "packs in the Nodes Manager - and returns a live card; action=nodes_status wait_s=300 blocks until done "
                       "and says the next step (managed: comfy_setup action=restart). watch_nodes only mirrors an install "
                       "someone started in the window. Models "
                       "without a download link are listed in models_without_url (never substitute similar files).",
        "parameters": {"type": "object", "properties": {
            "action": {"type": "string", "enum": ["start", "status", "wait", "cancel", "install_nodes", "watch_nodes", "nodes_status"]},
            "workflow_ids": {"type": "array", "items": {"type": "string"}, "description": "start: bundled workflow IDs"},
            "workflow": {"type": "string", "description": "start: a saved workflow (name or path) whose missing models to fetch"},
            "models": {"type": "array", "items": {"type": "object", "properties": {
                "folder": {"type": "string"}, "name": {"type": "string"}, "url": {"type": "string"},
                "size_bytes": {"type": "integer"}}, "required": ["folder", "name", "url"]},
                "description": "start: explicit files (e.g. a check's setup_proposal.models)"},
            "group": {"type": "string", "description": "wait: tutorial-1 | tutorial-2 | other (omitted = everything)"},
            "wait_s": {"type": "integer", "description": "wait / nodes_status: max seconds to block (up to 900)"},
            "packs": {"type": "array", "items": {"type": "string"}, "description": "install_nodes / watch_nodes: registry ids or names (setup_proposal.node_packs)"},
            "instance": {"type": "string", "description": "Optional ComfyUI instance (default: active)"}},
            "required": ["action"]},
    },
    "comfy_setup": {
        "name": "comfy_setup",
        "description": "Comfy Recipe's OWN ComfyUI (separate from any other ComfyUI on the machine). action=check: facts for the "
                       "first-run questions (GPUs and whether to ask which one, default folder, free disk, existing ComfyUI "
                       "installs with model folders). action=install (dir, gpu, share_models_from=[install names]) starts the "
                       "download/install in the BACKGROUND (about 6 GB, 5-20 min) and returns at once. action=status "
                       "(wait_s up to 900) waits until the current step finishes and returns progress + log tail - call it "
                       "repeatedly until state is done or error. action=start starts the installed ComfyUI and waits until it "
                       "answers (only ever this plugin's own install). action=stop stops it. action=restart = stop + start + wait in ONE call "
                       "(use it after node packs were installed; never the Manager's Apply Changes); then close + reopen the pane. action=use_existing = the user "
                       "prefers a ComfyUI they already have. action=check_dir dir=<path> checks a folder the user typed (writable, "
                       "free space, empty, not cloud-synced) before installing. action=reset forgets the choice (no files deleted). "
                       "action=adopt dir=<folder> uses an existing Comfy Recipe install again (after reset, or after the user "
                       "moved the folder: paths are fixed and the venv is checked; no download).",
        "parameters": {"type": "object", "properties": {
            "action": {"type": "string", "enum": ["check", "check_dir", "install", "status", "start", "stop", "restart", "use_existing", "reset", "adopt"]},
            "dir": {"type": "string", "description": "install / check_dir: folder for the new ComfyUI (default from check). adopt: existing install folder."},
            "allow_synced": {"type": "boolean", "description": "install: the user insists on a cloud-synced folder."},
            "gpu": {"type": ["integer", "string"], "description": "install: GPU index the user chose (required when check says ask_gpu)."},
            "share_models_from": {"type": "array", "items": {"type": "string"},
                                  "description": "install: names (from check.existing_installs) whose models the new ComfyUI may use."},
            "wait_s": {"type": "integer", "description": "status/start/restart: max seconds to wait."}},
            "required": ["action"]},
    },
    "comfy_instances": {
        "name": "comfy_instances",
        "description": "List the ComfyUI installs found on this machine (StabilityMatrix, ComfyUI Desktop, servers on standard ports "
                       "and the plugin's extra_urls) with running state, launch args, GPU and free VRAM, and which one is ACTIVE. "
                       "action='switch' with name=<instance> changes the active one. If the active instance is down and exactly one "
                       "other is running, it switches automatically (field 'switched'). If the result has 'action_required', do "
                       "exactly what it says before anything else.",
        "parameters": {"type": "object", "properties": {
            "action": {"type": "string", "enum": ["list", "switch"], "description": "Default list (also re-discovers)."},
            "name": {"type": "string", "description": "Instance name for switch."}}},
    },
    "comfy_workflows": {
        "name": "comfy_workflows",
        "description": "Saved ComfyUI workflows: list, describe (workflow=<saved name>), timings. "
                       "action=library lists bundled workflow IDs offline. action=install copies bundled workflows "
                       "into their Local Recipe/ or Cloud Recipe/ folders without overwriting user files; ask consent on existing/foreign instances. "
                       "Optional workflow_ids selects a subset; versioned=true creates separate versioned siblings. "
                       "action=check with workflow=<bundled stable ID> reports node/model/media/service/frontend-setting "
                       "requirements read-only (refresh=true by default) plus setup_proposal: ALL missing node packs, models "
                       "(link, folder, size) and settings (e.g. Nodes 2.0) to propose TOGETHER in one consent form. "
                       "Copying JSON never installs nodes/models or runs jobs. After the one OK: comfy_downloads "
                       "action=install_nodes / action=start, and action=apply_settings workflow=<ID> writes the proposed "
                       "frontend settings (e.g. Nodes 2.0) through the API (reopen the pane to see them) - skill "
                       "comfy-recipe:session, workflow-library.md.",
        "parameters": {"type": "object", "properties": {
            "action": {"type": "string", "enum": ["list", "describe", "timings", "library", "install", "check", "apply_settings"]},
            "workflow": {"type": "string", "description": "Workflow name or path fragment (describe / timings filter)."},
            "filter": {"type": "string", "description": "Substring filter for list/library."},
            "workflow_ids": {"type": "array", "items": {"type": "string"}, "description": "install: bundled IDs; omitted = all, [] = none."},
            "versioned": {"type": "boolean", "description": "install: explicit separate versioned copies, never overwrite."},
            "refresh": {"type": "boolean", "description": "check: refresh backend node schema (default true)."},
            "instance": {"type": "string", "description": "Optional existing instance name."}}, "required": ["action"]},
    },
    "comfy_templates": {
        "name": "comfy_templates",
        "description": "ComfyUI's built-in workflow templates (the Templates panel: ~650 official ones). action=search with a query "
                       "(task, model or medium, e.g. 'image edit turbo', 'video with audio', '3d from image') returns the best "
                       "matches with title, short description, inputs, download size, a thumbnail (thumbnail_path - show it with "
                       "MEDIA:) and readiness: which models are installed, missing_models (folder + download URL) and missing "
                       "custom node types. local_only=true (default) hides paid cloud-API templates. Use it to PROPOSE 2-4 "
                       "templates as a starting point; prefer ready ones and say what is missing for the others. action=describe "
                       "name=<template> gives full details. action=save name=<template> copies it into the user's workflows "
                       "(folder 'templates') so it shows in the Workflows sidebar and works with comfy_run. In a ComfyUI session, "
                       "OPEN a template in the window by hand: click the Templates button, type the title in its Search box, then "
                       "click the result's window_card_selector. Never download missing models without the user's OK.",
        "parameters": {"type": "object", "properties": {
            "action": {"type": "string", "enum": ["search", "describe", "save"]},
            "query": {"type": "string", "description": "search: what the user wants to make."},
            "media": {"type": "string", "description": "search: optional filter: image, video, audio, 3d, or a category name."},
            "local_only": {"type": "boolean", "description": "search: hide cloud-API templates (default true)."},
            "limit": {"type": "integer", "description": "search: max results (default 6, max 12)."},
            "name": {"type": "string", "description": "describe/save: template name from search results."},
            "new_name": {"type": "string", "description": "save: file name for the copy (default = template name)."},
            "folder": {"type": "string", "description": "save: workflows subfolder (default 'templates')."}},
            "required": ["action"]},
    },
    "comfy_run": {
        "name": "comfy_run",
        "description": "HEADLESS run: queue a saved ComfyUI UI workflow (subgraphs supported) through the API, WITHOUT modifying "
                       "the .json file. The job does NOT appear in any open ComfyUI window. In a [ComfyUI session] do NOT use "
                       "this tool - work in the window with drive_preview (skill comfy-recipe:session) - unless the user explicitly "
                       "asks for a headless/API run. Applies: prompt (auto-targets the main prompt input), overrides "
                       "[{node: id|title|type, widget: name|label, value}], images {LoadImage node id|title: local file path "
                       "(uploaded) or existing input filename}, seed (int or 'random'). dry_run=true converts and validates "
                       "without queueing. Returns prompt_id; then call comfy_result. Runs the SAVED file - unsaved tab edits "
                       "are not included. Needs comfy-cli (see /comfy setup).",
        "parameters": {"type": "object", "properties": {
            "workflow": {"type": "string"},
            "prompt": {"type": "string"},
            "overrides": {"type": "array", "items": {"type": "object", "properties": {
                "node": {"type": ["string", "integer"]}, "widget": {"type": "string"}, "value": {}}, "required": ["node", "widget", "value"]}},
            "images": {"type": "object", "additionalProperties": {"type": "string"}},
            "seed": {"type": ["integer", "string"]},
            "instance": {"type": "string"},
            "dry_run": {"type": "boolean"}}, "required": ["workflow"]},
    },
    "comfy_result": {
        "name": "comfy_result",
        "description": "Read-only. Wait for a ComfyUI job (up to wait_s, default 600) and return status, per-stage timing (total, "
                       "sampling steps/rate, prompt-enhancer time, overhead, models loaded, LoRA patches, hints), output file "
                       "paths and, for videos, ffprobe info + a 4x2 contact sheet and audio loudness. prompt_id='latest' = the job "
                       "running now or the last finished one, including jobs started with Run in the ComfyUI window - use it "
                       "after clicking Run in a ComfyUI session. If still running when wait_s expires, call again.",
        "parameters": {"type": "object", "properties": {
            "prompt_id": {"type": "string", "description": "A prompt_id from comfy_run, or 'latest'."},
            "wait_s": {"type": "integer"}, "instance": {"type": "string"}}, "required": ["prompt_id"]},
    },
    "comfy_media": {
        "name": "comfy_media",
        "description": "Prepare video/image inputs with ffmpeg (no ComfyUI run). Outputs go NEXT TO THE SOURCE file and are "
                       "probed back. action=probe (size, fps, frames, duration, audio); convert = one pass of trim "
                       "(start/duration/end s) + resize (width/height, mode cover=crop|fit=pad|stretch) + fps; frames = "
                       "PNG stills (which: 'first', 'last', frame index, or 't=<s>') e.g. for first/last-frame workflows; "
                       "split = consecutive segments of `seconds` (e.g. 3 s chunks for MiniMax on 24 GB); join = "
                       "concatenate clips (paths, normalised to the first clip, audio kept when all have it); sheet = "
                       "tiled contact sheet for a visual check. to_input=true also copies results into the instance's "
                       "input/ folder (reuses identical files, never overwrites different ones) and returns input_name; "
                       "then close + reopen the pane and pick the file visibly in the Load node.",
        "parameters": {"type": "object", "properties": {
            "action": {"type": "string", "enum": ["probe", "convert", "frames", "split", "join", "sheet"]},
            "path": {"type": "string", "description": "Source file (all actions except join)."},
            "paths": {"type": "array", "items": {"type": "string"}, "description": "join: clips in order."},
            "start": {"type": "number"}, "duration": {"type": "number"}, "end": {"type": "number"},
            "width": {"type": "integer"}, "height": {"type": "integer"}, "fps": {"type": "number"},
            "mode": {"type": "string", "enum": ["cover", "fit", "stretch"], "description": "convert resize mode (default cover)."},
            "which": {"type": "array", "items": {"type": ["string", "integer"]}, "description": "frames: default ['first','last']."},
            "seconds": {"type": "number", "description": "split: segment length."},
            "chained": {"type": "boolean", "description": "split: each segment starts on the previous segment's last frame (one shared frame) - for segment-by-segment generation that uses the previous output's last frame as first-frame guide."},
            "drop_first": {"type": "integer", "description": "join: drop this many leading frames from every clip after the first (1 for chained segments)."},
            "count": {"type": "integer"}, "columns": {"type": "integer"},
            "out": {"type": "string", "description": "convert/join/sheet: optional output file (relative = next to source)."},
            "out_dir": {"type": "string", "description": "frames/split: optional output folder."},
            "to_input": {"type": "boolean", "description": "Also copy outputs into ComfyUI input/."},
            "instance": {"type": "string"}}, "required": ["action"]},
    },
}


def _workflows(p: dict):
    a = p.get("action", "list")
    if a == 'library':
        c = library.load_catalog()
        rows = [e for e in c['workflows'] if (p.get('filter') or '').lower() in (e['id'] + ' ' + e['title']).lower()]
        return {'source': 'bundled_library', 'library_version': c['library_version'], 'workflows': rows}
    if a == 'install':
        return library.publish(core._inst(p.get('instance')), core.DATA,
                               workflow_ids=p.get('workflow_ids'), versioned=bool(p.get('versioned')))
    if a == 'apply_settings':
        c = library.load_catalog()
        entry = next((e for e in c['workflows'] if e['id'] == p.get('workflow')), None)
        if entry is None:
            raise ValueError('apply_settings requires an exact bundled workflow ID (action=library)')
        inst = core._inst(p.get('instance'))
        settings = core.cc.get_json(inst['url'], '/settings')
        rows = [r for r in dependencies._settings_rows(entry.get('requirements') or {}, settings, None)
                if r['status'] == 'needs_change']
        if not rows:
            return {'applied': [], 'note': 'Settings already match', 'instance': inst['name']}
        return dict(core.apply_settings(inst['url'], [{'id': r['id'], 'value': r['value']} for r in rows]),
                    instance=inst['name'], next='desktop_preview action=close, then action=open with the same url')
    if a == 'check':
        c = library.load_catalog()
        entry = next((e for e in c['workflows'] if e['id'] == p.get('workflow')), None)
        if entry is None:
            raise ValueError('check requires an exact bundled workflow ID (action=library)')
        inst = core._inst(p.get('instance'))
        wf = library.load_asset(entry)
        info = json.loads(core._object_info_path(inst, refresh=p.get('refresh', True) is not False).read_text(encoding='utf-8'))
        try:
            settings, settings_error = core.cc.get_json(inst['url'], '/settings'), None
            if not isinstance(settings, dict):
                settings, settings_error = None, 'Invalid /settings response'
        except Exception as exc:
            settings, settings_error = None, str(exc)
        packs = downloads.installed_packs(inst['url']) if (entry.get('requirements') or {}).get('frontend_nodes') else None
        result = dependencies.check(inst, entry, wf, info, settings, settings_error,
                                    size_of=dependencies.remote_size, installed_packs=packs)
        rel = library.publication_folder(entry) + '/' + Path(entry['file']).name
        result['definition']['path'] = rel
        result['definition']['scope'] = 'bundled_asset'
        try:
            names = core.cc.list_workflows(inst['url'])
            if rel not in names:
                result['definition']['working_copy'] = 'missing'
            else:
                saved = core.cc.load_workflow(inst['url'], rel)
                same = library.canonical_hash(saved) == library.canonical_hash(wf)
                result['definition']['working_copy'] = 'identical' if same else 'modified'
                if not same:
                    result['definition']['note'] = 'These dependency requirements describe the bundled revision, not your modified graph.'
        except Exception as exc:
            result['definition'].update(working_copy='unknown', error=str(exc))
        return result
    if a not in ('list', 'describe', 'timings'):
        raise ValueError(f'Unknown workflow action: {a}')
    if a == "describe":
        return core.describe(p["workflow"], p.get("instance"))
    if a == "timings":
        return {"runs": core.timing_history(p.get("workflow"))}
    from . import comfy_client as cc
    inst = core.active()
    names = [n for n in cc.list_workflows(inst["url"]) if (p.get("filter") or "").lower() in n.lower()]
    return {"instance": inst["name"], "workflows": names}


def _setup(p: dict):
    a = p.get("action", "check")
    if a == "check":
        return core.setup_check()
    if a == "install":
        return core.setup_install(p.get("dir"), p.get("gpu"), p.get("share_models_from"), bool(p.get("allow_synced")))
    if a == "check_dir":
        return installer.check_dir(p.get("dir") or installer.default_dir())
    if a == "status":
        return core.setup_status(int(p.get("wait_s") or 0))
    if a == "start":
        return core.setup_start(int(p.get("wait_s") or 180))
    if a == "stop":
        return core.setup_stop()
    if a == "restart":
        return core.setup_restart(int(p.get("wait_s") or 240))
    if a == "use_existing":
        return core.setup_use_existing()
    if a == "reset":
        return core.setup_reset()
    if a == "adopt":
        return core.setup_adopt(p.get("dir"))
    raise ValueError(f"unknown action {a!r}")


HANDLERS = {
    "comfy_onboarding": _onboarding_handler,
    "comfy_downloads": download_flow.handle,
    "comfy_setup": _setup,
    "comfy_instances": lambda p: core.instances(p.get("action", "list"), p.get("name")),
    "comfy_workflows": _workflows,
    "comfy_templates": lambda p: (
        templates.search(p.get("query") or "", p.get("media"), p.get("local_only", True) is not False, p.get("limit", 6))
        if p.get("action", "search") == "search" else
        templates.describe(p["name"]) if p["action"] == "describe" else
        templates.save(p["name"], p.get("folder") or "templates", p.get("new_name"))),
    "comfy_run": lambda p: core.run(p["workflow"], p.get("prompt"), p.get("overrides"), p.get("images"), p.get("seed"),
                                    p.get("instance"), bool(p.get("dry_run"))),
    "comfy_result": lambda p: core.result(p["prompt_id"], int(p.get("wait_s", 600)), p.get("instance")),
    "comfy_media": lambda p: media.handle(p, lambda name: Path(core._inst(name)["root"]) / "input"),
}

USAGE = ("/comfy tutorial [2] | /comfy downloads | /comfy status | /comfy start | /comfy stop | /comfy switch <instance> | /comfy workflows [filter] | /comfy templates <query> | /comfy library [install] | /comfy check <id> | /comfy setup | "
         "/comfy run <workflow> :: <prompt>   (headless; ask Hermes for the result)")


def _setup_text() -> str:
    s = _sync_settings()
    env = core.environment_report()
    conv = env["converter"]
    lines = [
        "Comfy Recipe setup",
        f"  data folder        : {env['data_dir']}",
        f"  own ComfyUI        : {core.setup_state()}",
        f"  personal skill     : {s.get('personal_skill') or '(none)'}",
        f"  extra URLs         : {', '.join(core.SETTINGS.get('extra_urls') or []) or '(none)'}",
        f"  StabilityMatrix    : {', '.join(core.SETTINGS.get('stabilitymatrix_dirs') or []) or '(auto)'}",
        f"  converter (headless): {conv['python'] if conv['ok'] else 'NOT FOUND - ' + conv['hint']}",
        f"  ffmpeg (video checks): {'yes' if env['ffmpeg'] else 'no'}",
        "Change these in Settings -> Plugins -> Comfy Recipe (or plugins.entries.comfy-recipe.settings in config.yaml).",
    ]
    return "\n".join(lines)


def _command(raw_args: str, *, session_id: str = '', session_key: str = '', platform: str = '', source=None) -> str:
    args = (raw_args or "").strip()
    try:
        _sync_settings()
        if not args or args.startswith("status"):
            s = core.instances("list")
            lines = [f"{'*' if r['active'] else ' '} {r['name']:<22} {'running' if r['running'] else 'stopped':<8} {r['url']}  "
                     f"gpu={r.get('configured_gpu')}  " + ", ".join(f"{d['name'][:28]} {d['vram_free_gb']}/{d['vram_total_gb']} GB free"
                                                             for d in r.get("devices", [])) for r in s["instances"]]
            head = "ComfyUI instances (* = active):\n"
            if s.get("switched"):
                head = f"Switched active instance: {s['switched']['reason']}\n" + head
            if not s.get("any_running"):
                head = core.NO_BACKEND_MESSAGE + "\n" + head
            return head + ("\n".join(lines) or "(none found - add your server URL to extra_urls, see /comfy setup)")
        if args == 'tutorial':
            return onboarding_flow.command(session_id)
        if args.startswith('tutorial '):
            step = args.split(None, 1)[1].strip().removeprefix('step').strip()
            if step in ('1', '2'):
                return onboarding_flow.command(session_id, int(step))
            return 'Tutorial steps 1 (Generate your first image) and 2 (Modify an image) are available: /comfy tutorial 2.'
        if args.startswith('downloads'):
            r = download_flow.handle({'action': 'status'})
            if r.get('state') in (None, 'idle'):
                return 'No model downloads queued.'
            rows = [f"Model downloads: {r['state']} - {r['done_files']}/{r['files']} files, "
                    f"{r['bytes'] / 1e9:.2f}/{r['total_bytes'] / 1e9:.2f} GB ({r['percent']}%)"]
            rows += [f"  {g['label']}: {g['state']} ({g['done_files']}/{g['files']})" for g in r.get('groups', [])]
            return '\n'.join(rows)
        if args == 'library':
            r = _workflows({'action': 'library'})
            return '\n'.join(f"{e['id']} — {e['title']}" for e in r['workflows'])
        if args == 'library install':
            return json.dumps(_workflows({'action': 'install'}), ensure_ascii=False)
        if args.startswith('check '):
            return json.dumps(_workflows({'action': 'check', 'workflow': args.split(None, 1)[1].strip()}), ensure_ascii=False)
        if args.startswith("setup"):
            return _setup_text()
        if args.startswith("start"):
            r = core.setup_start(180)
            return f"Comfy Recipe ComfyUI: {'running' if r['running'] else 'still starting'} at {r['url']}"
        if args.startswith("stop"):
            r = core.setup_stop()
            return "Comfy Recipe ComfyUI stopped." if r.get("stopped") else r.get("note", "not running")
        if args.startswith("switch"):
            name = args.split(None, 1)[1].strip()
            core.instances("switch", name)
            return f"Active ComfyUI instance: {name}"
        if args.startswith("workflows"):
            flt = args.split(None, 1)[1] if " " in args else ""
            return "\n".join(_workflows({"action": "list", "filter": flt})["workflows"]) or "(none)"
        if args.startswith("templates"):
            q = args.split(None, 1)[1] if " " in args else ""
            r = templates.search(q, check_models=True, limit=8)
            rows = [f"{'ready  ' if x.get('ready') else 'missing'} {x['title']}  [{x['name']}]"
                    + (f"  - needs {', '.join(m['name'] for m in x.get('missing_models', []))}" if x.get("missing_models") else "")
                    for x in r["results"]]
            rows.insert(0, f"{r['matches']} matching local templates, best {r['shown']}:")
            return "\n".join(rows)
        if args.startswith("run"):
            wf, _, prompt = args[3:].strip().partition("::")
            wf = shlex.split(wf)[0] if wf.strip() else ""
            if not wf:
                return USAGE
            r = core.run(wf, prompt.strip() or None)
            return f"Queued {r['workflow']} on {r['instance']}: prompt_id {r['prompt_id']} ({'; '.join(r['notes'])})"
        return USAGE
    except Exception as e:
        return f"/comfy error: {type(e).__name__}: {e}"


# ---------------------------------------------------------------- ComfyUI session (pre_llm_call hook)
SESSION_MARKER = "[ComfyUI session]"
TITLE_PREFIX = "ComfyUI session "


def _skills_to_load(personal_skill: str) -> str:
    skills = f"skill_view(\"{SKILL}\") and its file references/pane-recipe.md"
    if personal_skill:
        skills += (f", then the user's own skill skill_view(\"{personal_skill}\") (their paths, workflows and preferences - "
                   "it wins where it differs from the generic one)")
    return skills


CARD = (
    "Answer with exactly this structure, filling every <field> from the facts above and the page title (never copy "
    "example values, never write an @url: reference). After this summary follow onboarding when present:\n"
    "### 🎨 ComfyUI ready\n"
    "The ComfyUI window on the right is open and under my control.\n\n"
    "- **Instance:** `<name>` (<launcher>) · [<url>](<url>)\n"
    "- **GPU:** <device name> (<cuda:N from argv, or 'not pinned'>) · <free> / <total> GB free\n"
    "- **Workflow:** `<active workflow name from the page title, without ' - ComfyUI'; add * if the title starts with *>`\n\n"
    "I'll make every change and start every run myself in that window. You can also work in the window yourself "
    "to show me what you want.\n"
    "For a fresh managed install, call comfy_onboarding action=status and follow setup_choices/tutorial before asking the ordinary question. "
    "For returning sessions (next_step=ordinary), finish with: **What would you like to do?**"
)

CARD_LATER = ("The card below is ONLY for the moment ComfyUI is open in the pane - NOT for this first answer, which is "
              "the short explanation + the question(s).\n")

MOTTO_NOTE = ("[comfy-recipe] The user just opened a ComfyUI session from the Comfy Recipe sidebar entry. Any text after the "
              "\"[ComfyUI session]\" marker in their message is only a motto - it is NOT a request, do not comment on it.\n")


def _open_pane_now(url: str) -> bool:
    """Open the preview pane on ComfyUI right away, from the hook, before the model's first token (same event the
    desktop_preview tool emits, routed to the window running this turn). Best-effort: False = let the model open it."""
    try:
        from gateway.session_context import get_session_env
        from tools import desktop_ui
        if not desktop_ui.available() or not get_session_env("HERMES_UI_SESSION_ID", ""):
            return False
        return bool(desktop_ui.emit("preview.open", {"url": url, "label": "ComfyUI"}))
    except Exception:
        return False


FIRST_RUN = (
    "FIRST RUN of Comfy Recipe: no ComfyUI has been set up for it yet. The user may never have used ComfyUI. Facts from "
    "the plugin (comfy_setup check): {facts}\n"
    "Do this, in plain friendly words, no jargon:\n"
    "1. In 3-4 short lines: ComfyUI is the free app that makes images/videos from building blocks; Comfy Recipe installs "
    "its OWN copy for you, separate from anything else on the computer (other ComfyUI installs keep working and can run "
    "at the same time); it downloads about {dl} GB and needs about {need} GB of disk ({free} GB free); it takes 5-20 "
    "minutes. Individual workflows may need extra models or nodes; ask about those separately later.\n"
    "2. Ask with ONE clarify call (all questions in one form, recommended option first): "
    "(a) 'Install a new ComfyUI just for Comfy Recipe (recommended)' vs 'Use a ComfyUI I already have'; "
    "{gpu_q}{models_q}({folder_letter}) 'Where should the new ComfyUI be installed? (only used for a new install)' with "
    "{dir_choices} as choices; the form's Other row lets them type any full folder path. "
    "Without a clarify tool, ask the same in one short numbered message and stop.\n"
    "3. New install: if the user typed their own folder, first comfy_setup action=check_dir dir=<it>; if not ok or "
    "synced_by is set, tell them why in one line and ask again. Then comfy_setup action=install with dir, gpu{share_arg}. Then call comfy_setup action=status wait_s=300 "
    "again and again; after each finished step tell the user ONE short line (step x/7 and what it was); on error show the "
    "error and the log tail, and suggest a fix. The install result carries progress_card: put that MEDIA:<path> line "
    "ONCE alone on its own line in your reply right after starting the install (it becomes a live progress bar in the "
    "chat and the status bar). When state is done: comfy_setup action=start, then desktop_preview open "
    "its url (label ComfyUI), ONE drive_preview elements call with max 5, then the card below, then this tip: 'Bring your "
    "workflows: drag a workflow .json (or an image made by ComfyUI) from your files into the ComfyUI window - the whole "
    "graph opens exactly as saved; save it with Ctrl+S to keep it in the Workflows list.'\n"
    "   Existing ComfyUI: comfy_setup action=use_existing, then follow its result (it may say no backend is running).\n"
    "The ten bundled workflow definitions (five Local Recipe, five Cloud Recipe) are copied after startup; this does not install their dependencies. "
    "Do not open the preview pane before ComfyUI runs. Base installation itself does not authorize extra nodes/models. "
    "Once the pane is open, open Local Recipe/RCPlocal_t2i_qwen_image_2-1.json visibly in the Workflows sidebar before setup choices, "
    "even if this localhost origin restored a tab from an older installation. Preserve all other tabs and drafts. "
    "Call comfy_onboarding action=status: ask the independent setup choices, perform only approved work, "
    "then start the first-image tutorial. Do not end a fresh install with the ordinary question.\n"
)

INSTALLING = ("Comfy Recipe's own ComfyUI is being installed right now (started earlier): {facts}. Tell the user in one "
              "line and put its progress_card MEDIA:<path> line once alone on its own line (live progress bar), "
              "then keep calling comfy_setup action=status wait_s=300, one short line per finished step, and when "
              "done: comfy_setup action=start, desktop_preview open its url (label ComfyUI), ONE drive_preview elements "
              "call with max 5, then the card below.\n")

INSTALL_FAILED = ("The last install of Comfy Recipe's own ComfyUI failed: {facts}. Explain the error simply and ask the user "
                  "whether to retry (comfy_setup action=install with the same dir) or use an existing ComfyUI "
                  "(comfy_setup action=use_existing). Do not open the preview pane.\n")

INSTALL_MISSING = (
    "Comfy Recipe's own ComfyUI was installed in {dir}, but that install is gone (folder or its .comfy-recipe marker "
    "deleted or moved). {orphan}Tell the user this in ONE plain line, then follow the FIRST RUN instructions below with "
    "ONE change: question (a) gets a third choice 'I moved it - I will give the new folder'. If they pick it, ask for the "
    "full folder path (one short question), then comfy_setup action=adopt dir=<it> (no download; it fixes the paths and "
    "checks the install still works); on success comfy_setup action=start, desktop_preview open its url (label "
    "ComfyUI), ONE drive_preview elements call with max 5, then the card. If adopt fails, say why in one line and offer a "
    "new install.\n")

STOPPED = ("Comfy Recipe's own ComfyUI is installed but not running. Call comfy_setup action=start (it waits until ComfyUI "
           "answers, usually 15-60 s), then desktop_preview open its url (label ComfyUI), then ONE drive_preview elements "
           "call with max 5 - its result carries the page title '<workflow name> - ComfyUI'. Do NOT inspect the workflow "
           "now unless onboarding requires setup. Call comfy_onboarding action=status and follow next_step before the ordinary question.\n")


def _first_run_text() -> str:
    c = core.setup_check()
    ex = [e for e in c["existing_installs"] if e.get("model_folders")]
    letters = iter("abcd")
    next(letters)  # (a) = install vs existing
    gpu_q = (f"({next(letters)}) which GPU ComfyUI should use - one choice per GPU from facts.gpus as 'GPU <index>: <name> (<vram> GB)'; "
             "say the other GPU stays free for games/other apps; " if c["ask_gpu"] else "")
    models_q = (f"({next(letters)}) 'Also use the models already in <launcher> ComfyUI (nothing is copied, new downloads go into the new "
                "install) (recommended)' vs 'Start with an empty models folder' - one line per install in "
                "facts.existing_installs; " if ex else "")
    share_arg = ", share_models_from=[the chosen existing_installs names]" if ex else ""
    dd, alt = c["default_dir_check"], c.get("alternative_dir")
    if dd.get("synced_by") and alt:
        dir_choices = (f"'{alt}' (recommended) first, then '{c['default_dir']}' - say the Documents folder is synced by "
                       f"{dd['synced_by']}, so about 15 GB would be uploaded")
    elif not dd["ok"] and alt:
        dir_choices = f"'{alt}' (recommended) - the Documents folder can't be used: {dd.get('problem')}"
    else:
        dir_choices = f"'{c['default_dir']}' (recommended)"
    return FIRST_RUN.format(dir_choices=dir_choices, facts=json.dumps(c, ensure_ascii=False), dl=c["download_gb"], need=c["disk_needed_gb"],
                            free=c["disk_free_gb"], gpu_q=gpu_q, models_q=models_q, dir=c["default_dir"], share_arg=share_arg,
                            folder_letter=next(letters))


def _session_start(personal_skill: str) -> str:
    """Kickoff turn. The plugin already resolved the instance and (normally) opened the pane, so the model needs ONE
    tool call before the card. Skills are loaded on the first real request, not now."""
    try:
        _sync_settings()
        phase = core.setup_state()
    except Exception as e:
        phase = {"phase": "first_run", "error": str(e)}
    try:
        if phase["phase"] == "first_run":
            return MOTTO_NOTE + _first_run_text() + CARD_LATER + CARD
        if phase["phase"] == "install_missing":
            core.forget_missing()  # before the first-run facts, so other installs are offered for model sharing again
            orphan = ("Its old ComfyUI process is still running without its folder: call comfy_setup action=stop first. "
                      if phase.get("old_comfyui_still_running") else "")
            return (MOTTO_NOTE + INSTALL_MISSING.format(dir=phase["dir"], orphan=orphan) + _first_run_text()
                    + CARD_LATER + CARD)
        if phase["phase"] == "installing":
            return MOTTO_NOTE + INSTALLING.format(facts=json.dumps(core.setup_status(0), ensure_ascii=False)) + CARD_LATER + CARD
        if phase["phase"] == "install_failed":
            return MOTTO_NOTE + INSTALL_FAILED.format(facts=json.dumps(phase["install"], ensure_ascii=False)[:3000])
        if phase["phase"] == "stopped":
            return MOTTO_NOTE + STOPPED + CARD
    except Exception as e:
        return MOTTO_NOTE + f"The plugin could not read its setup state ({e}). Call comfy_setup action=check and tell the user."
    try:
        inst = core.instances("list")
    except Exception as e:
        inst = {"any_running": False, "action_required": f"Could not query ComfyUI: {e}"}
    if inst.get("action_required"):
        return (MOTTO_NOTE + "The plugin checked ComfyUI for you: " + inst["action_required"] +
                "\nDo not call any tool for this turn unless that instruction says to.")
    row = next(r for r in inst["instances"] if r["active"])
    if phase.get("phase") == "running":  # managed ComfyUI already up (e.g. started by an earlier session): re-bind
        try:
            core.bind_to_hermes()
        except Exception:
            pass
    provision = core.ensure_managed_library()
    opened = _open_pane_now(row["url"])
    facts = {"name": row["name"], "launcher": row.get("launcher"), "url": row["url"], "argv": row.get("argv"),
             "devices": row.get("devices"), "switched": inst.get("switched", {}).get("reason"),
             "workflow_library": provision}
    step = ("The plugin has ALREADY opened that ComfyUI in the preview pane - do not call comfy_instances or "
            "desktop_preview open. Your only tool call now: ONE drive_preview elements call with max 5; its result carries "
            "the page title '<workflow name> - ComfyUI' (0 elements or 'no page' = still loading: terminal sleep 3, retry "
            "once; if it still has no page, call desktop_preview open with the url above).") if opened else (
            f"Call desktop_preview open with url {row['url']} (label ComfyUI), then ONE drive_preview elements call with "
            "max 5; its result carries the page title '<workflow name> - ComfyUI'.")
    return (MOTTO_NOTE +
            "ComfyUI facts resolved by the plugin (use them, don't re-query): " + json.dumps(facts, ensure_ascii=False) + "\n"
            + ("Mention in one line that the plugin switched instance: " + facts["switched"] + "\n" if facts["switched"] else "")
            + step + " Do NOT inspect the workflow now (no prompt, nodes, widgets, other tabs or queue) and do not load "
            "skills yet ONLY for ordinary returning sessions. If onboarding provides a next step, follow it instead of waiting.\n" + CARD)


SESSION_RULES = (
    "[comfy-recipe] RULE for this whole session: do every change and every run BY HAND in that ComfyUI window with "
    "drive_preview (type the prompt into the textarea, set images with the Load Image file button, click Run) so I see it "
    "happen - follow references/pane-recipe.md of "
    f"the {SKILL} skill. Never use comfy_run here unless I say \"headless\" - its jobs do not show up in the window. After "
    "clicking Run, use comfy_result with prompt_id \"latest\" (read-only) for the timing and output files. Never start "
    "or stop any ComfyUI yourself, except Comfy Recipe's own install with comfy_setup start/stop. Call drive_preview elements only when the delta returned by your last action is not enough - every "
    "elements call flashes boxes over the whole ComfyUI page. Never call strobe. Do not poll elements while waiting "
    "for downloads, generation or a user answer; use download/result tools or desktop_preview read for read-only status. "
    "After handing control back to the user, stop interacting. I may also work in the window myself (open a workflow, "
    "select or edit nodes) to guide you or ask about the graph: before acting or answering, re-read the part of the "
    "window concerned instead of assuming its earlier state. Never change a prompt, number, seed or image by editing the "
    "workflow JSON. Act as a graph-editing assistant: edit the current workflow in place by default. If a reference "
    "input is missing, add a Load Image node and connect IMAGE to the Image Edit subgraph's image_2 (or next image_N) "
    "in that same graph. Duplicate only for substantial restructuring (many coordinated edits, including inside "
    "group/subgraph nodes), or when the user explicitly asks for a copy. Explain a substantial fork first. Missing "
    "inputs and unsaved edits are not a reason to duplicate. Preserve live unsaved state. Match the graph's Load "
    "Image/Load Video/Load Audio nodes to the media I give: add the missing ones next to the existing loaders, delete "
    "extras, and connect them (image_N, ref_image_N, ref_video_N...). drive_preview cannot drag wires: when a link cannot "
    "be made in the window, use the API-mode wiring fallback of references/workflow-json-editing.md (backup, save the "
    "tab from the window, edit only nodes/links on disk, close + reopen the tab, verify the sockets), keeping the same "
    "workflow identity - this standing consent covers loader add/delete/connect only. Never change values via "
    "workflow JSON. Never click Fit View to find a node: zoomed out, ComfyUI hides the textareas and file buttons - use "
    "the right panel's Nodes tab -> 'Locate node on canvas' instead. Never use browser_* tools (a different, invisible "
    "browser). If drive_preview says no window answered, ask me to click into this chat and wait. "
    "If I ask for the tutorial (start, replay, continue, go back to it), call comfy_onboarding action=tutorial "
    "(resume=true to continue, step=2 for 'Modify an image'). If I bring my own workflow and ask to install its "
    "dependencies: comfy_workflows describe/check, ONE consent form, then comfy_downloads action=start workflow=<path> for "
    "models (post its progress_card once); node packs of that open graph: comfy_downloads action=watch_nodes, then the "
    "Issues tab's Install All (one click, it lists every missing pack of the open graph; never search packs one by one in "
    "the Nodes Manager), then comfy_downloads action=nodes_status wait_s=300 and comfy_setup action=restart. Bundled "
    "workflows: comfy_downloads action=install_nodes instead (no window clicks). Settings such as Nodes 2.0: "
    "comfy_workflows action=apply_settings, never by hand. Never click the Manager's Apply Changes. "
    "Bundled workflows live in Local Recipe/ and Cloud Recipe/; preserve old Comfy Recipe/ copies and every open draft. "
    "Local Qwen t2i: soft plugin refinement (preserve the user's idea), refine_prompt on, 25 steps, Lightning LoRA strength 0. "
    "Local Qwen i2i: explicit edit instruction plus preservation, refine_prompt off, 4 steps, Lightning LoRA strength 1. "
    "Respect an explicitly chosen mode. Cloud Recipe workflows use paid core ComfyUI API nodes, account authentication "
    "and credits, not local weights. Copying/installing them is not run consent; never queue paid runs during setup, "
    "and obtain explicit consent for each paid run."
)


def _rules(personal_skill: str, first_request: bool) -> str:
    if not first_request:
        return SESSION_RULES
    return (SESSION_RULES + "\n[comfy-recipe] Before your first action for this request, load " + _skills_to_load(personal_skill)
            + ", and follow the recipe step by step.")


def _text(content) -> str:
    if isinstance(content, list):  # multimodal parts
        content = " ".join(str(p.get("text", "")) if isinstance(p, dict) else str(p) for p in content)
    return str(content or "").lstrip()


def _with_session_db(fn):
    """Run fn(db) on Hermes' shared SessionDB handle; never fatal (titles are cosmetic)."""
    try:
        import hermes_state_registry as reg
        db = reg.acquire()
    except Exception:
        return None
    try:
        return fn(db)
    except Exception:
        return None
    finally:
        try:
            reg.release(db)
        except Exception:
            pass


def _hold_placeholder_title(session_id) -> None:
    """Kickoff turn: pin a placeholder title at ``llm`` rank so neither the instant title nor the model title is derived
    from the kickoff/motto (equal-or-lower ranks cannot overwrite it)."""
    if not session_id:
        return
    base = TITLE_PREFIX + time.strftime("%d %b %H:%M")

    def _do(db):
        for title in (base, base + time.strftime(":%S"), f"{base} {str(session_id)[-6:]}"):
            try:
                if db.set_auto_title(session_id, title, source="llm"):
                    return
            except ValueError:  # title already used by another session
                continue
    _with_session_db(_do)


def _release_placeholder_title(session_id) -> None:
    """First real request: clear the placeholder (only if still ours) so Hermes titles the session from that request.
    pre_llm_call runs before Hermes' turn-start titling, so the request itself gets titled this turn."""
    if not session_id:
        return

    def _do(db):
        if str(db.get_session_title(session_id) or "").startswith(TITLE_PREFIX):
            db.set_session_title(session_id, "")  # user-rank clear = untitled again
    _with_session_db(_do)


def _pre_llm_call(user_message=None, conversation_history=None, is_first_turn=None, session_id=None, **kwargs):
    """Inject the ComfyUI-session instructions invisibly (model-side only), so the visible kickoff stays one line."""
    del kwargs
    history = [m for m in (conversation_history or []) if isinstance(m, dict)]
    users = [m for m in history if m.get("role") == "user"]
    if _text(user_message).startswith(SESSION_MARKER):
        if is_first_turn is None:
            is_first_turn = not any(m.get("role") == "assistant" for m in history)
        if is_first_turn:
            _hold_placeholder_title(session_id)
            personal = str(_settings().get("personal_skill") or "").strip()
            return {"context": _session_start(personal) + "\n" + SESSION_RULES + "\n" + onboarding_flow.context(session_id)}
        return {"context": SESSION_RULES}
    recipe_session = bool(users and _text(users[0].get("content")).startswith(SESSION_MARKER))
    routed = onboarding_flow.route(user_message, session_id, recipe_session=recipe_session)
    if routed:
        return {"context": SESSION_RULES + "\n" + routed}
    if recipe_session:
        requests = [m for m in users if not _text(m.get("content")).startswith((SESSION_MARKER, "[System", "[SYSTEM]"))]
        first = len(requests) <= 1  # this turn is the user's first real request
        if first:
            _release_placeholder_title(session_id)
        personal = str(_settings().get("personal_skill") or "").strip()
        return {"context": _rules(personal, first)}
    return None


def register(ctx):
    global _CTX
    _CTX = ctx
    for name, schema in SCHEMAS.items():
        ctx.register_tool(name=name, toolset=TOOLSET, schema=schema, handler=(_onboarding_handler if name == "comfy_onboarding" else _wrap(HANDLERS[name])), emoji="🎨")
    ctx.register_hook("pre_llm_call", _pre_llm_call)
    ids = {e['id'] for e in library.load_catalog()['workflows']}
    for skill in skill_registration.skills_for_registration(Path(__file__).parent / 'skills', ids):
        ctx.register_skill(skill['name'], skill['path'], description=skill['description'])
    ctx.register_command("comfy", handler=_command, description="ComfyUI: status, switch, workflows, setup, run",
                         args_hint="status|switch|workflows|setup|tutorial|run")

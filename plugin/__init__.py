"""Comfy Recipe - Hermes plugin to work in a local ComfyUI, visibly in the preview pane or headless.

Tools: comfy_instances, comfy_workflows, comfy_templates, comfy_run, comfy_result.  Command: /comfy.
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

TOOLSET = "comfy_recipe"
SKILL = "comfy-recipe:session"
SETTING_KEYS = ("personal_skill", "motto", "extra_urls", "stabilitymatrix_dirs", "converter_python")
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
        del kwargs
        try:
            _sync_settings()
            return _ok(fn(params or {}))
        except Exception as e:  # tools must return JSON, not raise
            return json.dumps({"success": False, "error": f"{type(e).__name__}: {e}"}, ensure_ascii=False)
    return handler


SCHEMAS = {
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
        "description": "List saved workflows on the active ComfyUI (action=list, optional filter), describe one (action=describe, "
                       "workflow=<name>) to see its subgraph controls, LoadImage nodes, prompt/text nodes and key nodes, or show "
                       "measured run timings (action=timings).",
        "parameters": {"type": "object", "properties": {
            "action": {"type": "string", "enum": ["list", "describe", "timings"]},
            "workflow": {"type": "string", "description": "Workflow name or path fragment (describe / timings filter)."},
            "filter": {"type": "string", "description": "Substring filter for list."}}, "required": ["action"]},
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
}


def _workflows(p: dict):
    a = p.get("action", "list")
    if a == "describe":
        return core.describe(p["workflow"], p.get("instance"))
    if a == "timings":
        return {"runs": core.timing_history(p.get("workflow"))}
    from . import comfy_client as cc
    inst = core.active()
    names = [n for n in cc.list_workflows(inst["url"]) if (p.get("filter") or "").lower() in n.lower()]
    return {"instance": inst["name"], "workflows": names}


HANDLERS = {
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
}

USAGE = ("/comfy status | /comfy switch <instance> | /comfy workflows [filter] | /comfy templates <query> | /comfy setup | "
         "/comfy run <workflow> :: <prompt>   (headless; ask Hermes for the result)")


def _setup_text() -> str:
    s = _sync_settings()
    env = core.environment_report()
    conv = env["converter"]
    lines = [
        "Comfy Recipe setup",
        f"  data folder        : {env['data_dir']}",
        f"  personal skill     : {s.get('personal_skill') or '(none)'}",
        f"  extra URLs         : {', '.join(core.SETTINGS.get('extra_urls') or []) or '(none)'}",
        f"  StabilityMatrix    : {', '.join(core.SETTINGS.get('stabilitymatrix_dirs') or []) or '(auto)'}",
        f"  converter (headless): {conv['python'] if conv['ok'] else 'NOT FOUND - ' + conv['hint']}",
        f"  ffmpeg (video checks): {'yes' if env['ffmpeg'] else 'no'}",
        "Change these in Settings -> Plugins -> Comfy Recipe (or plugins.entries.comfy-recipe.settings in config.yaml).",
    ]
    return "\n".join(lines)


def _command(raw_args: str) -> str:
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
        if args.startswith("setup"):
            return _setup_text()
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
    "example values, never write an @url: reference), and nothing else:\n"
    "### 🎨 ComfyUI ready\n"
    "The ComfyUI window on the right is open and under my control.\n\n"
    "- **Instance:** `<name>` (<launcher>) · [<url>](<url>)\n"
    "- **GPU:** <device name> (<cuda:N from argv, or 'not pinned'>) · <free> / <total> GB free\n"
    "- **Workflow:** `<active workflow name from the page title, without ' - ComfyUI'; add * if the title starts with *>`\n\n"
    "I'll make every change and start every run myself in that window. You can also work in the window yourself "
    "to show me what you want. **What should I do first?**"
)

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


def _session_start(personal_skill: str) -> str:
    """Kickoff turn. The plugin already resolved the instance and (normally) opened the pane, so the model needs ONE
    tool call before the card. Skills are loaded on the first real request, not now."""
    try:
        _sync_settings()
        inst = core.instances("list")
    except Exception as e:
        inst = {"any_running": False, "action_required": f"Could not query ComfyUI: {e}"}
    if inst.get("action_required"):
        return (MOTTO_NOTE + "The plugin checked ComfyUI for you: " + inst["action_required"] +
                "\nDo not call any tool for this turn unless that instruction says to.")
    row = next(r for r in inst["instances"] if r["active"])
    opened = _open_pane_now(row["url"])
    facts = {"name": row["name"], "launcher": row.get("launcher"), "url": row["url"], "argv": row.get("argv"),
             "devices": row.get("devices"), "switched": inst.get("switched", {}).get("reason")}
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
            "skills yet. Then wait for my instructions.\n" + CARD)


SESSION_RULES = (
    "[comfy-recipe] RULE for this whole session: do every change and every run BY HAND in that ComfyUI window with "
    "drive_preview (type the prompt into the textarea, click Run) so I see it happen - follow references/pane-recipe.md of "
    f"the {SKILL} skill. Never use comfy_run here unless I say \"headless\" - its jobs do not show up in the window. After "
    "clicking Run, use comfy_result with prompt_id \"latest\" (read-only) for the timing and output files. Never start "
    "ComfyUI yourself. Call drive_preview elements only when the delta returned by your last action is not enough - every "
    "elements call flashes boxes over the whole ComfyUI page. I may also work in the window myself (open a workflow, "
    "select or edit nodes) to guide you or ask about the graph: before acting or answering, re-read the part of the "
    "window concerned instead of assuming its earlier state."
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
            return {"context": _session_start(personal) + "\n" + SESSION_RULES}
        return {"context": SESSION_RULES}
    if users and _text(users[0].get("content")).startswith(SESSION_MARKER):
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
        ctx.register_tool(name=name, toolset=TOOLSET, schema=schema, handler=_wrap(HANDLERS[name]), emoji="🎨")
    ctx.register_hook("pre_llm_call", _pre_llm_call)
    ctx.register_skill("session", Path(__file__).parent / "skills" / "session" / "SKILL.md",
                       description="Use when driving ComfyUI live in the Hermes preview pane (Comfy Recipe).")
    ctx.register_command("comfy", handler=_command, description="ComfyUI: status, switch, workflows, setup, run",
                         args_hint="status|switch|workflows|setup|run")

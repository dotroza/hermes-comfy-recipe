"""ComfyUI workflow templates (the frontend's Templates panel): search, readiness check, save as a user workflow.

Sources on the ComfyUI server:
  /templates/index.json            categories -> templates (name, title, description, tags, models, openSource, size, io)
  /templates/<name>.json           the template workflow (UI format); nodes carry properties.models [{name, url, directory}]
  /templates/<name>-1.<ext>        thumbnail
  /models/<folder>                 installed model files per folder
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from urllib import parse

from . import comfy_client as cc
from . import core

INDEX_TTL = 3600


def _cache_dir() -> Path:
    p = core.DATA / "templates"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _index(inst: dict, refresh: bool = False) -> list[dict]:
    p = _cache_dir() / f"index_{inst['name']}.json"
    if refresh or not p.exists() or time.time() - p.stat().st_mtime > INDEX_TTL:
        p.write_text(json.dumps(cc.get_json(inst["url"], "/templates/index.json", timeout=60)), encoding="utf-8")
    cats = json.loads(p.read_text(encoding="utf-8"))
    out = []
    for c in cats:
        for t in c.get("templates", []):
            out.append(t | {"_category": c.get("title"), "_group": c.get("category")})
    return out


def _safe_name(name, what: str = "template name") -> str:
    """Template names (and thumbnail extensions) from the server or the agent become cache file names."""
    name = str(name or "")
    if not name or "/" in name or "\\" in name or ".." in name or ":" in name or "\0" in name:
        raise ValueError(f"invalid {what}: {name!r}")
    return name


def _template_json(inst: dict, name: str) -> dict:
    name = _safe_name(name)
    p = _cache_dir() / f"{name}.json"
    if not p.exists():
        p.write_bytes(cc._req(inst["url"], "/templates/" + parse.quote(name) + ".json", timeout=60))
    return json.loads(p.read_text(encoding="utf-8"))


def _all_nodes(wf: dict) -> list[dict]:
    nodes = list(wf.get("nodes", []))
    for sg in (wf.get("definitions") or {}).get("subgraphs", []):
        nodes += sg.get("nodes", [])
    return nodes


def _readiness(inst: dict, wf: dict, installed: dict, object_info: dict) -> dict:
    models, missing = [], []
    for n in _all_nodes(wf):
        for m in (n.get("properties") or {}).get("models", []) or []:
            folder, name = m.get("directory"), m.get("name")
            if not folder or not name or any(x["name"] == name for x in models):
                continue
            if folder not in installed:
                try:
                    installed[folder] = set(cc.get_json(inst["url"], "/models/" + parse.quote(folder), timeout=30))
                except Exception:
                    installed[folder] = set()
            have = name in installed[folder] or any(f.replace("\\", "/").endswith("/" + name) for f in installed[folder])
            models.append({"name": name, "folder": folder, "installed": have})
            if not have:
                missing.append({"name": name, "folder": folder, "url": m.get("url")})
    defs = {sg["id"] for sg in (wf.get("definitions") or {}).get("subgraphs", [])}
    ui_only = {"Note", "MarkdownNote", "Reroute", "PrimitiveNode"}
    missing_nodes = sorted({n.get("type") for n in _all_nodes(wf)
                            if n.get("type") and n["type"] not in object_info and n["type"] not in defs and n["type"] not in ui_only})
    return {"model_files": models, "missing_models": missing, "missing_node_types": missing_nodes,
            "ready": not missing and not missing_nodes}


def _thumbnail(inst: dict, t: dict) -> dict:
    ext = t.get("mediaSubtype") or "webp"
    url = f"{inst['url']}/templates/{parse.quote(t['name'])}-1.{ext}"
    try:
        p = _cache_dir() / "thumbs" / f"{_safe_name(t['name'])}.{_safe_name(ext, 'thumbnail type')}"
    except ValueError:
        return {"thumbnail_url": url}
    if not p.exists():
        try:
            data = cc._req(inst["url"], f"/templates/{parse.quote(t['name'])}-1.{ext}", timeout=30)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)
        except Exception:
            return {"thumbnail_url": url}
    return {"thumbnail_url": url, "thumbnail_path": str(p)}


def _summary(t: dict) -> dict:
    inputs = [{"type": i.get("nodeType"), "example_file": i.get("file")} for i in (t.get("io") or {}).get("inputs", [])]
    return {"name": t["name"], "title": t.get("title"), "category": t.get("_category"), "media": t.get("mediaType"),
            "tags": t.get("tags"), "models": t.get("models"),
            "runs": "locally" if t.get("openSource") else ("cloud API (paid, Comfy account)" if t.get("openSource") is False else "unknown"),
            "download_gb": round((t.get("size") or 0) / 1e9, 1) or None, "inputs": inputs,
            "description": (t.get("description") or "")[:260],
            "window_card_selector": f"[data-testid=\"template-workflow-{t['name']}\"]"}


_WORD = re.compile(r"[a-z0-9.]+")


def _score(t: dict, words: list[str]) -> float:
    if not words:
        return 0.0
    fields = [((t.get("title") or "").lower(), 3), (" ".join(t.get("tags") or []).lower(), 2),
              (" ".join(t.get("models") or []).lower(), 2), ((t.get("name") or "").lower().replace("_", " "), 1.5),
              ((t.get("description") or "").lower(), 1), ((t.get("_category") or "").lower(), 1)]
    s = 0.0
    for w in words:
        for text, weight in fields:
            if w in text:
                s += weight
    return s


def search(query: str = "", media: str | None = None, local_only: bool = True, limit: int = 6,
           check_models: bool = True, instance: str | None = None) -> dict:
    inst = core._inst(instance)
    ts = _index(inst)
    if local_only:
        ts = [t for t in ts if t.get("openSource") is not False]
    if media:
        ts = [t for t in ts if (t.get("mediaType") or "").lower() == media.lower()
              or media.lower() in (t.get("_category") or "").lower()]
    words = [w for w in _WORD.findall((query or "").lower()) if len(w) > 1]
    scored = [(_score(t, words), t.get("usage") or 0, t) for t in ts]
    if words:
        scored = [x for x in scored if x[0] > 0]
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    limit = max(1, min(int(limit or 6), 12))
    installed = {}
    object_info = json.loads(core._object_info_path(inst).read_text(encoding="utf-8")) if check_models else {}
    pool = []
    # Check readiness on a wider pool, then let ready templates win over equally relevant ones that need downloads.
    for score, usage, t in scored[: limit * 3 if check_models else limit]:
        ready = {}
        if check_models:
            try:
                ready = _readiness(inst, _template_json(inst, t["name"]), installed, object_info)
            except Exception as e:
                ready = {"readiness_error": str(e)[:200]}
        pool.append((score + (1.5 if ready.get("ready") else 0), usage, t, ready))
    pool.sort(key=lambda x: (x[0], x[1]), reverse=True)
    results = [_summary(t) | _thumbnail(inst, t) | ready for _, _, t, ready in pool[:limit]]
    return {"instance": inst["name"], "matches": len(scored), "shown": len(results), "results": results,
            "how_to_open_in_window": "drive_preview click the Templates button, type the template title into its Search box, "
                                    "then click window_card_selector; the template opens as a new unsaved tab."}


def describe(name: str, instance: str | None = None) -> dict:
    inst = core._inst(instance)
    t = next((x for x in _index(inst) if x["name"] == name), None)
    if not t:
        raise ValueError(f"no template named {name!r} (use comfy_templates action=search)")
    wf = _template_json(inst, name)
    object_info = json.loads(core._object_info_path(inst).read_text(encoding="utf-8"))
    r = _summary(t) | _thumbnail(inst, t) | _readiness(inst, wf, {}, object_info)
    r["description"] = t.get("description")
    r["tutorial_url"] = t.get("tutorialUrl")
    r["min_comfyui_version"] = t.get("minComfyUIVersion")
    r["outputs"] = [{"type": o.get("nodeType"), "media": o.get("mediaType")} for o in (t.get("io") or {}).get("outputs", [])]
    r["nodes"] = len(wf.get("nodes", [])) + sum(len(sg.get("nodes", [])) for sg in (wf.get("definitions") or {}).get("subgraphs", []))
    return r


def save(name: str, folder: str = "templates", new_name: str | None = None, instance: str | None = None) -> dict:
    """Copy a template into the user's workflows (appears in the Workflows sidebar; usable by comfy_run)."""
    inst = core._inst(instance)
    if folder and (".." in folder.replace("\\", "/").split("/") or ":" in folder):
        raise ValueError(f"invalid folder: {folder!r}")
    wf = _template_json(inst, name)
    stem = re.sub(r"[^\w.\- ]", "_", new_name or name).strip() or name
    rel = f"workflows/{folder.strip('/')}/{stem}.json" if folder else f"workflows/{stem}.json"
    try:
        cc._req(inst["url"], "/api/userdata/" + parse.quote(rel, safe="") + "?overwrite=false",
                json.dumps(wf, ensure_ascii=False).encode("utf-8"), {"Content-Type": "application/json"})
    except cc.ComfyError as e:
        if "409" in str(e):
            raise ValueError(f"{rel} already exists - pass new_name to save another copy") from None
        raise
    return {"saved": rel.removeprefix("workflows/"), "instance": inst["name"],
            "note": "Appears in the Workflows sidebar (reopen the pane if the list is stale); runnable with comfy_run."}

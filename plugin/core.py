"""Core logic of the comfy-live plugin. No Hermes imports at module level, so it runs and tests standalone.

Settings come from Hermes (Settings -> Plugins -> Comfy Live, i.e. ``plugins.entries.comfy-live.settings``)
and are pushed in by ``__init__.py`` through ``configure()``; standalone use falls back to the defaults below.
"""
from __future__ import annotations

import json
import os
import platform
import random
import re
import shutil
import subprocess
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

from . import comfy_client as cc

PLUGIN_DIR = Path(__file__).resolve().parent
CLIENT_ID = "hermes-comfy-live-" + uuid.uuid4().hex[:8]
OBJECT_INFO_TTL = 600
PROBE_PORTS = [8188, 8189, 8190, 8000]
NO_BACKEND_MESSAGE = "No ComfyUI backend is running. Please start your ComfyUI backend, then tell me when it is up."

SETTINGS: dict = {
    "extra_urls": [],            # ComfyUI servers on non-standard ports, e.g. ["http://127.0.0.1:8283"]
    "stabilitymatrix_dirs": [],  # StabilityMatrix data folders (portable installs), e.g. ["D:/StabilityMatrix/Data"]
    "converter_python": "",      # a Python with comfy-cli installed; empty = auto-detect
}


def configure(settings: dict) -> None:
    for k, v in (settings or {}).items():
        if v not in (None, ""):
            SETTINGS[k] = v


def _hermes_home() -> Path:
    try:
        from hermes_constants import get_hermes_home
        return Path(get_hermes_home())
    except Exception:
        if os.environ.get("HERMES_HOME"):
            return Path(os.environ["HERMES_HOME"])
        if os.name == "nt" and os.environ.get("LOCALAPPDATA"):
            return Path(os.environ["LOCALAPPDATA"]) / "hermes"
        return Path.home() / ".hermes"


# Runtime data lives outside the plugin folder: never committed, never scanned as plugin code.
DATA = _hermes_home() / "plugin-data" / "comfy-live"
STATE = DATA / "instances.json"
RUNS = DATA / "runs.jsonl"
TIMINGS = DATA / "timings.jsonl"


# ---------------------------------------------------------------- state
def _load_state() -> dict:
    if STATE.exists():
        return json.loads(STATE.read_text(encoding="utf-8"))
    return {"active": None, "instances": {}, "learned_sm_dirs": [], "converter": None}


def _save_state(st: dict) -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(st, indent=2, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------- discovery
def _app_config_dirs(app: str) -> list[Path]:
    home = Path.home()
    if os.name == "nt":
        return [Path(os.environ.get("APPDATA", home)) / app]
    if sys.platform == "darwin":
        return [home / "Library" / "Application Support" / app]
    return [Path(os.environ.get("XDG_CONFIG_HOME", home / ".config")) / app]


def _sm_installs(data_dir: Path) -> list[dict]:
    try:
        s = json.loads((data_dir / "settings.json").read_text(encoding="utf-8-sig"))
    except Exception:
        return []
    out = []
    for p in s.get("InstalledPackages", []):
        if "comfy" not in (p.get("PackageName") or "").lower():
            continue
        args = {a.get("Name"): a.get("OptionValue") for a in p.get("LaunchArgs", [])}
        extra = args.get("") or ""
        port = args.get("--port") or "8188"
        gpu = re.search(r"--cuda-device\s+(\d+)", extra)
        out.append({
            "name": f"sm-{(p.get('DisplayName') or 'comfyui').lower().replace(' ', '-')}",
            "url": f"http://127.0.0.1:{port}",
            "root": str(data_dir / (p.get("LibraryPath") or "")),
            "launcher": "StabilityMatrix",
            "gpu": f"cuda:{gpu.group(1)}" if gpu else "default",
        })
    return out


def _root_from_stats(stats: dict) -> str | None:
    argv = (stats or {}).get("system", {}).get("argv") or []
    if argv and argv[0].lower().endswith("main.py"):
        return str(Path(argv[0]).parent)
    return None


def _sm_data_dir_of(root: str | None) -> str | None:
    """A ComfyUI root inside a StabilityMatrix tree (<Data>/Packages/<name>) -> <Data>."""
    if not root:
        return None
    p = Path(root)
    if p.parent.name.lower() == "packages" and (p.parent.parent / "settings.json").exists():
        return str(p.parent.parent)
    return None


def discover() -> dict:
    """Find ComfyUI installs (StabilityMatrix, ComfyUI Desktop, servers on standard/extra ports) and merge into state."""
    st = _load_state()
    found: dict[str, dict] = {}
    sm_dirs = [Path(d) for d in list(SETTINGS.get("stabilitymatrix_dirs") or []) + st.get("learned_sm_dirs", [])]
    sm_dirs += _app_config_dirs("StabilityMatrix")
    for d in dict.fromkeys(sm_dirs):
        for inst in _sm_installs(d):
            found[inst["name"]] = inst
    for d in _app_config_dirs("ComfyUI"):
        cfg = d / "config.json"
        if cfg.exists():
            try:
                base = json.loads(cfg.read_text(encoding="utf-8")).get("basePath")
                found["comfyui-desktop"] = {"name": "comfyui-desktop", "url": "http://127.0.0.1:8000", "root": base,
                                            "launcher": "ComfyUI Desktop", "gpu": "default"}
            except Exception:
                pass
    known_urls = {i["url"] for i in found.values()}
    probe = [f"http://127.0.0.1:{p}" for p in PROBE_PORTS] + [u.rstrip("/") for u in SETTINGS.get("extra_urls") or []]
    learned = False
    for url in dict.fromkeys(probe):
        if url in known_urls:
            continue
        stats = cc.alive(url)
        if not stats:
            continue
        root = _root_from_stats(stats)
        sm_dir = _sm_data_dir_of(root)
        if sm_dir and sm_dir not in st.setdefault("learned_sm_dirs", []):
            st["learned_sm_dirs"].append(sm_dir)  # portable StabilityMatrix found through its running server
            learned = True
        name = f"port-{url.rsplit(':', 1)[-1]}"
        found[name] = {"name": name, "url": url, "root": root, "launcher": "unknown", "gpu": "?"}
    if learned:  # re-read the newly learned StabilityMatrix settings so the instance gets its real name
        for inst in _sm_installs(Path(st["learned_sm_dirs"][-1])):
            stale = [n for n, i in found.items() if i["url"] == inst["url"] and n.startswith("port-")]
            for n in stale:
                found.pop(n)
            found[inst["name"]] = inst
    for name, inst in found.items():
        st["instances"][name] = {**st["instances"].get(name, {}), **inst}
    _save_state(st)
    return st


def instances(action: str = "list", name: str | None = None) -> dict:
    st = discover() if action in ("list", "discover") or not STATE.exists() else _load_state()
    if action == "switch":
        if name not in st["instances"]:
            raise ValueError(f"unknown instance {name!r}; known: {list(st['instances'])}")
        st["active"] = name
        _save_state(st)
    stats_by_name = {n: cc.alive(i["url"]) for n, i in st["instances"].items()}
    running, seen_urls = [], set()
    for n, s in stats_by_name.items():  # one entry per server: a named install and a port probe can share a URL
        url = st["instances"][n]["url"]
        if s and url not in seen_urls:
            seen_urls.add(url)
            running.append(n)
    if st.get("active") in stats_by_name and stats_by_name[st["active"]]:
        active_url = st["instances"][st["active"]]["url"]
        running = [st["active"]] + [n for n in running if st["instances"][n]["url"] != active_url]
    out: dict = {}
    if action != "switch" and st.get("active") not in running:
        if len(running) == 1:
            out["switched"] = {"from": st.get("active"), "to": running[0],
                               "reason": f"{st.get('active') or 'no instance'} was not running; "
                                         f"{running[0]} is the only running ComfyUI."}
            st["active"] = running[0]
            _save_state(st)
        elif len(running) > 1:
            out["action_required"] = ("The active instance is not running and several ComfyUI backends are: "
                                      f"{', '.join(running)}. Ask the user which one to use, then call "
                                      "comfy_instances action=switch name=<it>.")
    if not running:
        out["action_required"] = ("Tell the user exactly this and nothing more, then wait for their reply: "
                                  f"\"{NO_BACKEND_MESSAGE}\" Do not open the preview pane, do not try to start ComfyUI "
                                  "yourself and do not suggest how to start it. When the user says it is up, call "
                                  "comfy_instances again. (A server on a non-standard port is only found if its URL "
                                  "is in the plugin's extra_urls setting.)")
    rows = []
    for n, i in st["instances"].items():
        stats = stats_by_name[n]
        row = {"name": n, "active": n == st["active"], "url": i["url"], "launcher": i.get("launcher"),
               "root": i.get("root"), "configured_gpu": i.get("gpu"), "running": bool(stats)}
        if stats:
            row["argv"] = stats["system"].get("argv", [])[1:]
            row["devices"] = [{"name": d["name"], "vram_free_gb": round(d["vram_free"] / 2**30, 1),
                               "vram_total_gb": round(d["vram_total"] / 2**30, 1)} for d in stats.get("devices", [])]
        rows.append(row)
    return {"active": st["active"], "any_running": bool(running), **out, "instances": rows}


def active() -> dict:
    st = _load_state() if STATE.exists() else discover()
    if not st.get("active"):
        st = instances("list") and _load_state()
    if not st.get("active"):
        raise ValueError("No ComfyUI instance found. " + NO_BACKEND_MESSAGE)
    return st["instances"][st["active"]] | {"name": st["active"]}


def _inst(name: str | None) -> dict:
    if not name:
        return active()
    st = _load_state()
    if name not in st["instances"]:
        raise ValueError(f"unknown instance {name!r}")
    return st["instances"][name] | {"name": name}


# ---------------------------------------------------------------- converter (comfy-cli, GPL-3.0, run out of process)
def _converter_candidates() -> list[str]:
    cands = []
    if SETTINGS.get("converter_python"):
        cands.append(str(SETTINGS["converter_python"]))
    exe = "python.exe" if os.name == "nt" else "python"
    comfy = shutil.which("comfy")
    if comfy:
        cands.append(str(Path(comfy).parent / exe))
    cands.append(sys.executable)
    home = Path.home()
    if os.name == "nt":
        cands.append(str(Path(os.environ.get("LOCALAPPDATA", home)) / "Programs" / "comfy-mcp" / "venv" / "Scripts" / exe))
        cands.append(str(home / "pipx" / "venvs" / "comfy-cli" / "Scripts" / exe))
    cands.append(str(home / ".local" / "pipx" / "venvs" / "comfy-cli" / ("Scripts" if os.name == "nt" else "bin") / exe))
    return list(dict.fromkeys(cands))


def find_converter(refresh: bool = False) -> dict:
    st = _load_state()
    cached = st.get("converter")
    if cached and not refresh and Path(cached).exists() and cached in _converter_candidates() + [cached]:
        return {"python": cached, "ok": True}
    tried = []
    for py in _converter_candidates():
        if not Path(py).exists():
            continue
        env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
        r = subprocess.run([py, "-c", "import comfy_cli.workflow_to_api"], capture_output=True, text=True, env=env, timeout=60)
        tried.append(py)
        if r.returncode == 0:
            st["converter"] = py
            _save_state(st)
            return {"python": py, "ok": True}
    return {"ok": False, "tried": tried,
            "hint": "Headless runs need comfy-cli: `pip install comfy-cli` (or `pipx install comfy-cli`), or set "
                    "converter_python in Settings -> Plugins -> Comfy Live. Visible sessions work without it."}


def _convert(inst: dict, wf: dict, host_overrides: list[dict]) -> dict:
    conv = find_converter()
    if not conv["ok"]:
        raise RuntimeError(conv["hint"])
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    req = {"workflow": wf, "object_info_path": str(_object_info_path(inst)), "host_overrides": host_overrides}
    r = subprocess.run([conv["python"], str(PLUGIN_DIR / "convert_bridge.py")], input=json.dumps(req), capture_output=True,
                       text=True, encoding="utf-8", env=env, timeout=180)
    try:
        res = json.loads(r.stdout)
    except json.JSONDecodeError:
        raise RuntimeError(f"converter failed (python={conv['python']}): {r.stderr[-1500:] or r.stdout[-500:]}") from None
    if not res.get("ok"):
        raise RuntimeError("converter: " + res["error"])
    return res


# ---------------------------------------------------------------- workflows
def _object_info_path(inst: dict, refresh: bool = False) -> Path:
    DATA.mkdir(parents=True, exist_ok=True)
    p = DATA / f"object_info_{inst['name']}.json"
    if refresh or not p.exists() or time.time() - p.stat().st_mtime > OBJECT_INFO_TTL:
        p.write_text(json.dumps(cc.get_json(inst["url"], "/object_info", timeout=120)), encoding="utf-8")
    return p


def _resolve_workflow(inst: dict, workflow: str) -> str:
    names = cc.list_workflows(inst["url"])
    w = workflow.replace("\\", "/")
    for cand in (w, w + ".json"):
        if cand in names:
            return cand
    hits = [n for n in names if n.rsplit("/", 1)[-1] in (w, w + ".json")] or [n for n in names if w.lower() in n.lower()]
    hits = [h for h in hits if ".bak" not in h] or hits
    if len(hits) == 1:
        return hits[0]
    raise ValueError(f"workflow {workflow!r} matches {len(hits)} files: {hits[:12]}")


def _subgraph_defs(wf: dict) -> dict:
    return {sg["id"]: sg for sg in (wf.get("definitions") or {}).get("subgraphs", [])}


def _host_widgets(node: dict) -> list[dict]:
    vals = iter(node.get("widgets_values") or [])
    out = []
    for i in node.get("inputs", []):
        if i.get("widget"):
            v = next(vals, None)
            out.append({"name": i["name"], "label": i.get("label"),
                        "value": v if not isinstance(v, str) or len(v) < 120 else v[:117] + "..."})
    return out


def describe(workflow: str, instance: str | None = None) -> dict:
    inst = _inst(instance)
    rel = _resolve_workflow(inst, workflow)
    wf = cc.load_workflow(inst["url"], rel)
    defs = _subgraph_defs(wf)
    hosts, loads, texts, others = [], [], [], []
    for n in wf.get("nodes", []):
        t, title = n.get("type"), n.get("title")
        if t in defs:
            hosts.append({"id": n["id"], "subgraph": defs[t].get("name"), "mode": n.get("mode"), "controls": _host_widgets(n),
                          "image_sockets": [i.get("label") or i["name"] for i in n.get("inputs", []) if i.get("type") == "IMAGE"]})
        elif t == "LoadImage":
            linked = any(n.get("outputs", [{}])[0].get("links") or [])
            loads.append({"id": n["id"], "title": title, "image": (n.get("widgets_values") or [None])[0], "connected": linked})
        elif t in ("PrimitiveStringMultiline", "PrimitiveString", "CLIPTextEncode") or (title and "prompt" in title.lower()):
            v = (n.get("widgets_values") or [""])[0]
            texts.append({"id": n["id"], "type": t, "title": title,
                          "text": v[:160] + ("..." if isinstance(v, str) and len(v) > 160 else "")})
        elif t in ("KSampler", "KSamplerAdvanced", "RandomNoise", "BasicScheduler", "SaveImage", "SaveImageAdvanced",
                   "SaveVideo", "PrimitiveFloat", "PrimitiveInt", "PrimitiveBoolean", "LoraLoader", "LoraLoaderModelOnly",
                   "UNETLoader", "CheckpointLoaderSimple", "CLIPLoader"):
            others.append({"id": n["id"], "type": t, "title": title, "widgets_values": n.get("widgets_values")})
    return {"workflow": rel, "instance": inst["name"], "subgraph_hosts": hosts, "load_images": loads,
            "text_nodes": texts, "key_nodes": others}


def _find_node(wf: dict, spec) -> dict:
    nodes = wf.get("nodes", [])
    if isinstance(spec, int) or (isinstance(spec, str) and spec.isdigit()):
        hit = [n for n in nodes if n["id"] == int(spec)]
    else:
        s = str(spec).lower()
        hit = [n for n in nodes if (n.get("title") or "").lower() == s] or [n for n in nodes if (n.get("type") or "").lower() == s]
    if len(hit) != 1:
        raise ValueError(f"node spec {spec!r} matched {len(hit)} nodes")
    return hit[0]


def _prompt_target(wf: dict) -> tuple[str, dict, str]:
    defs = _subgraph_defs(wf)
    for n in wf.get("nodes", []):
        if n.get("type") in defs and n.get("mode") not in (2, 4):
            for i in n.get("inputs", []):
                if i.get("widget") and (i["name"] in ("prompt", "positive_prompt", "text")
                                        or (i.get("label") or "").lower() in ("prompt", "positive_prompt")):
                    return "host", n, i["name"]
    for n in wf.get("nodes", []):
        if n.get("type") in ("PrimitiveStringMultiline", "PrimitiveString") and "prompt" in (n.get("title") or "").lower():
            return "api", n, "value"
    enc = [n for n in wf.get("nodes", []) if n.get("type") == "CLIPTextEncode"]
    pos = [n for n in enc if "pos" in (n.get("title") or "").lower()] or (enc if len(enc) == 1 else [])
    if pos:
        return "api", pos[0], "text"
    raise ValueError("Could not find the prompt input automatically; pass it via overrides (see comfy_workflows describe).")


def run(workflow: str, prompt: str | None = None, overrides: list[dict] | None = None, images: dict | None = None,
        seed=None, instance: str | None = None, dry_run: bool = False) -> dict:
    inst = _inst(instance)
    if not cc.alive(inst["url"]):
        raise RuntimeError(f"ComfyUI {inst['name']} at {inst['url']} is not running. {NO_BACKEND_MESSAGE}")
    rel = _resolve_workflow(inst, workflow)
    wf = cc.load_workflow(inst["url"], rel)
    defs = _subgraph_defs(wf)
    host_ovr, api_ovr, notes = [], [], []

    if prompt is not None:
        kind, node, widget = _prompt_target(wf)
        (host_ovr if kind == "host" else api_ovr).append({"node_id": node["id"], "widget": widget, "value": prompt})
        notes.append(f"prompt -> node {node['id']} ({node.get('title') or node.get('type')}).{widget}")
    for o in overrides or []:
        node = _find_node(wf, o["node"])
        (host_ovr if node.get("type") in defs else api_ovr).append({"node_id": node["id"], "widget": o["widget"], "value": o["value"]})
    if seed is not None:
        val = random.randint(0, 2**50) if str(seed).lower() == "random" else int(seed)
        for n in wf.get("nodes", []):
            if n.get("type") in defs and any(i.get("widget") and i["name"] in ("seed", "noise_seed") for i in n.get("inputs", [])):
                w = next(i["name"] for i in n["inputs"] if i.get("widget") and i["name"] in ("seed", "noise_seed"))
                host_ovr.append({"node_id": n["id"], "widget": w, "value": val})
        notes.append(f"seed={val}")
        seed = val

    res = _convert(inst, wf, host_ovr)
    api = res["prompt"]
    if seed is not None:
        for n in api.values():
            for k in ("seed", "noise_seed"):
                if k in n["inputs"] and not isinstance(n["inputs"][k], list):
                    n["inputs"][k] = seed
    for o in api_ovr:
        key = str(o["node_id"])
        if key not in api:
            raise ValueError(f"node {key} is not in the executed graph (muted/bypassed or UI-only)")
        api[key]["inputs"][o["widget"]] = o["value"]
    for spec, path in (images or {}).items():
        node = _find_node(wf, spec)
        name = cc.upload_image(inst["url"], path) if Path(path).exists() else path
        api[str(node["id"])]["inputs"]["image"] = name
        notes.append(f"image node {node['id']} <- {name}")

    summary = {"workflow": rel, "instance": inst["name"], "nodes": len(api), "converter_fixes": res["fixes"],
               "host_overrides": res["host_overrides_applied"], "notes": notes}
    DATA.mkdir(parents=True, exist_ok=True)
    if dry_run:
        p = DATA / "last_dry_run_api.json"
        p.write_text(json.dumps(api, indent=1, ensure_ascii=False), encoding="utf-8")
        return summary | {"dry_run": True, "api_prompt_path": str(p)}
    # embed the UI workflow like the browser does, so output PNGs can be dragged back into ComfyUI
    pid, node_errors = cc.queue_prompt(inst["url"], api, CLIENT_ID,
                                       {"extra_pnginfo": {"workflow": wf}, "comfy_usage_source": "hermes-comfy-live"})
    if node_errors:
        summary["warning"] = ("Partial run: these output nodes failed validation and will NOT execute: "
                              + json.dumps({k: [e.get("message") for e in v.get("errors", [])] for k, v in node_errors.items()})[:1500])
    with RUNS.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"prompt_id": pid, "queued_at": time.time(), **summary, "prompt": prompt, "overrides": overrides,
                            "images": images}, ensure_ascii=False) + "\n")
    q = cc.queue_state(inst["url"])
    return summary | {"prompt_id": pid, "queue_running": len(q.get("queue_running", [])),
                      "queue_pending": len(q.get("queue_pending", []))}


# ---------------------------------------------------------------- results & timing
_TS = re.compile(r"^\[(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\.\d+)\]")
_BAR = re.compile(r"(\d+)/(\d+) \[(\d+:\d\d(?::\d\d)?)<[^,\]]*,\s*([\d.]+)(s/it|it/s)")


def _secs(mmss: str) -> float:
    parts = [int(x) for x in mmss.split(":")]
    return float(sum(v * 60 ** i for i, v in enumerate(reversed(parts))))


def _log_window(inst: dict, t0: float, t1: float) -> list[str]:
    """Server log lines between t0 and t1: HTTP log buffer first (works remotely), log file on disk as fallback."""
    entries = cc.log_entries(inst["url"])
    if entries:
        text = ""
        for e in entries:
            try:
                ts = datetime.fromisoformat(e["t"]).timestamp()
            except (KeyError, ValueError):
                continue
            if t0 - 2 <= ts <= t1 + 2:
                text += e.get("m", "")
        if text:
            return [ln for ln in text.replace("\r", "\n").splitlines() if ln.strip()]
    root = Path(inst.get("root") or "")
    port = inst["url"].rsplit(":", 1)[-1]
    log = next((p for p in (root / "user" / f"comfyui_{port}.log", root / "user" / "comfyui.log") if p.exists()), None)
    if not log:
        return []
    out, inside = [], False
    for ln in log.read_text(encoding="utf-8", errors="replace").replace("\r", "\n").splitlines():
        m = _TS.match(ln)
        if m:
            inside = t0 - 2 <= datetime.strptime(m.group(1)[:23], "%Y-%m-%d %H:%M:%S.%f").timestamp() <= t1 + 2
        if inside and ln.strip():
            out.append(ln)
    return out


def _timing(inst: dict, h: dict) -> dict:
    msgs = {m[0]: m[1] for m in h.get("status", {}).get("messages", [])}
    cached_nodes = (msgs.get("execution_cached") or {}).get("nodes") or []
    t0 = (msgs.get("execution_start") or {}).get("timestamp", 0) / 1000
    t1 = ((msgs.get("execution_success") or msgs.get("execution_error") or msgs.get("execution_interrupted") or {})
          .get("timestamp", 0)) / 1000
    total = round(t1 - t0, 1) if t0 and t1 else None
    lines = _log_window(inst, t0, t1) if t0 and t1 else []
    bars: dict[tuple, dict] = {}
    gen_tokens = 0.0
    for ln in lines:
        if "Generating tokens" in ln:
            for m in _BAR.finditer(ln):
                gen_tokens = max(gen_tokens, _secs(m.group(3)))
            continue
        for m in _BAR.finditer(ln):
            done, n, el = int(m.group(1)), int(m.group(2)), _secs(m.group(3))
            if done == n:
                bars[(n, el)] = {"steps": n, "seconds": el, "rate": f"{m.group(4)} {m.group(5)}"}
    sampling = max(bars.values(), key=lambda b: b["seconds"]) if bars else None
    loads = [re.sub(r".*Requested to load ", "", ln).strip() for ln in lines if "Requested to load" in ln]
    patches = max([int(x) for ln in lines for x in re.findall(r"(\d+) patches attached", ln)] or [0])
    t = {"total_s": total, "sampling": sampling, "prompt_enhancer_s": gen_tokens or None,
         "other_s": round(total - (sampling["seconds"] if sampling else 0) - gen_tokens, 1) if total else None,
         "models_loaded": list(dict.fromkeys(loads)), "lora_patches": patches,
         "errors": [ln[-300:] for ln in lines if re.search(r"Error|Exception|out of memory", ln)][:5],
         "cached_nodes": len(cached_nodes)}
    if cached_nodes and not sampling:
        t["hint"] = (f"{len(cached_nodes)} nodes were served from ComfyUI's cache (same inputs as a previous run), "
                     "so nothing was regenerated - change the seed or prompt to force a new result.")
    if patches and sampling and t["other_s"] and t["other_s"] > 15:
        t["hint"] = ("Large non-sampling overhead with LoRA patches: patches are re-applied each run under dynamic VRAM; "
                     "consider --highvram or a checkpoint with the LoRA merged in.")
    return t


def _media_check(path: Path) -> dict:
    ffprobe, ffmpeg = shutil.which("ffprobe"), shutil.which("ffmpeg")
    if not (ffprobe and ffmpeg):
        return {"note": "ffmpeg/ffprobe not on PATH - no video checks"}
    pr = json.loads(subprocess.run([ffprobe, "-v", "error", "-show_entries", "stream=codec_type,codec_name,width,height,r_frame_rate,nb_frames",
                                    "-show_entries", "format=duration", "-of", "json", str(path)], capture_output=True, text=True).stdout or "{}")
    dur = float(pr.get("format", {}).get("duration", 0) or 0)
    info = {"duration_s": round(dur, 2), "streams": pr.get("streams", [])}
    if dur:
        sheet = DATA / "frames" / (path.stem + "_contact.png")
        sheet.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run([ffmpeg, "-v", "error", "-y", "-i", str(path), "-vf", f"fps=8/{dur},scale=270:-1,tile=4x2",
                        "-frames:v", "1", str(sheet)], capture_output=True)
        if sheet.exists():
            info["contact_sheet"] = str(sheet)
            info["contact_sheet_layout"] = f"4x2 frames, evenly spaced over {dur:.1f}s (row-major)"
    if any(s.get("codec_type") == "audio" for s in info["streams"]):
        vd = subprocess.run([ffmpeg, "-v", "info", "-i", str(path), "-af", "volumedetect", "-f", "null", "-"],
                            capture_output=True, text=True).stderr
        info["audio"] = dict(re.findall(r"(mean_volume|max_volume): (-?[\d.]+) dB", vd))
    return info


def _resolve_latest(inst: dict, wait_s: int) -> str | None:
    """'latest' = the job running now (waited for), else the most recently finished one - also jobs queued by the browser tab."""
    q = cc.queue_state(inst["url"])
    running = q.get("queue_running") or []
    if running:
        return running[0][1]
    lh = cc.latest_history(inst["url"])
    return lh[0] if lh else None


def result(prompt_id: str, wait_s: int = 600, instance: str | None = None) -> dict:
    inst = _inst(instance)
    if str(prompt_id).lower() == "latest":
        prompt_id = _resolve_latest(inst, wait_s)
        if not prompt_id:
            return {"status": "none", "hint": "No job has run on this ComfyUI since it started."}
    deadline = time.time() + max(0, min(wait_s, 1700))
    h = cc.history(inst["url"], prompt_id)
    while (not h or not h.get("status", {}).get("completed") and h.get("status", {}).get("status_str") != "error") \
            and time.time() < deadline:
        time.sleep(3)
        h = cc.history(inst["url"], prompt_id)
    if not h:
        q = cc.queue_state(inst["url"])
        pos = [i for i, item in enumerate(q.get("queue_running", []) + q.get("queue_pending", [])) if item[1] == prompt_id]
        return {"prompt_id": prompt_id, "status": "running" if pos == [0] else "queued" if pos else "unknown",
                "queue_position": pos[0] if pos else None, "hint": "call comfy_result again to keep waiting"}
    status = h.get("status", {}).get("status_str")
    outputs = []
    root = Path(inst.get("root") or "")
    for nid, o in (h.get("outputs") or {}).items():
        for key, items in o.items():
            if not isinstance(items, list):
                continue
            for it in items:
                if not isinstance(it, dict) or "filename" not in it:
                    continue
                local = root / it.get("type", "output") / it.get("subfolder", "") / it["filename"]
                if not local.exists():
                    local = DATA / "outputs" / it["filename"]
                    local.parent.mkdir(parents=True, exist_ok=True)
                    local.write_bytes(cc.view_bytes(inst["url"], it["filename"], it.get("subfolder", ""), it.get("type", "output")))
                entry = {"node": nid, "kind": key, "type": it.get("type"), "path": str(local)}
                if local.suffix.lower() in (".mp4", ".webm", ".mov", ".mkv", ".gif") and it.get("type") == "output":
                    entry["media"] = _media_check(local)
                outputs.append(entry)
    timing = _timing(inst, h)
    err = next((m[1] for m in h.get("status", {}).get("messages", []) if m[0] == "execution_error"), None)
    extra = (h.get("prompt") or [None] * 4)[3] or {}
    source = "comfy-live headless run" if str(extra.get("client_id", "")).startswith("hermes-comfy-live") else "ComfyUI window / other client"
    rec = {"prompt_id": prompt_id, "status": status, "instance": inst["name"], "queued_by": source, "timing": timing,
           "outputs": [o for o in outputs if o.get("type") == "output"] or outputs}
    if err:
        rec["error"] = {k: err.get(k) for k in ("node_id", "node_type", "exception_type", "exception_message")}
    run_meta = {}
    if RUNS.exists():
        for ln in RUNS.read_text(encoding="utf-8").splitlines():
            if prompt_id in ln:
                run_meta = json.loads(ln)
    workflow = run_meta.get("workflow") or ((extra.get("extra_pnginfo") or {}).get("workflow") or {}).get("extra", {}).get("title")
    DATA.mkdir(parents=True, exist_ok=True)
    with TIMINGS.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"prompt_id": prompt_id, "workflow": workflow, "notes": run_meta.get("notes"), "queued_by": source,
                            "status": status, "finished_at": time.time(), **timing}, ensure_ascii=False) + "\n")
    return rec


def timing_history(workflow: str | None = None, limit: int = 20) -> list[dict]:
    if not TIMINGS.exists():
        return []
    rows = [json.loads(ln) for ln in TIMINGS.read_text(encoding="utf-8").splitlines() if ln.strip()]
    if workflow:
        rows = [r for r in rows if workflow.lower() in (r.get("workflow") or "").lower()]
    return rows[-limit:]


def environment_report() -> dict:
    conv = find_converter()
    return {"data_dir": str(DATA), "settings": SETTINGS, "converter": conv,
            "ffmpeg": bool(shutil.which("ffmpeg") and shutil.which("ffprobe")), "os": platform.platform()}

"""Tiny stdlib HTTP client for the ComfyUI server API."""
from __future__ import annotations

import json
import mimetypes
import uuid
from pathlib import Path
from urllib import error, parse, request

TIMEOUT = 30


class ComfyError(RuntimeError):
    pass


def _req(base: str, path: str, data: bytes | None = None, headers: dict | None = None, timeout: float = TIMEOUT):
    url = base.rstrip("/") + path
    req = request.Request(url, data=data, headers=headers or {})
    try:
        with request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        raise ComfyError(f"HTTP {e.code} on {path}: {body[:2000]}") from None
    except error.URLError as e:
        raise ComfyError(f"Cannot reach ComfyUI at {base}: {e.reason}") from None


def get_json(base: str, path: str, timeout: float = TIMEOUT):
    return json.loads(_req(base, path, timeout=timeout))


def post_json(base: str, path: str, payload: dict):
    raw = _req(base, path, json.dumps(payload).encode("utf-8"), {"Content-Type": "application/json"})
    return json.loads(raw) if raw else {}


def alive(base: str) -> dict | None:
    try:
        return get_json(base, "/system_stats", timeout=3)
    except ComfyError:
        return None


def list_workflows(base: str) -> list[str]:
    q = "/api/userdata?dir=workflows&recurse=true&split=false&full_info=false"
    return sorted(get_json(base, q))


def load_workflow(base: str, rel_path: str) -> dict:
    """rel_path is relative to user/default/workflows, e.g. 'my_folder/foo.json'."""
    enc = parse.quote("workflows/" + rel_path, safe="")
    return json.loads(_req(base, f"/api/userdata/{enc}"))


def upload_image(base: str, file_path: str | Path, subfolder: str = "") -> str:
    """Upload a local image to the instance's input dir; returns the name to put in LoadImage."""
    p = Path(file_path)
    boundary = uuid.uuid4().hex
    ctype = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
    parts = [
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"overwrite\"\r\n\r\ntrue\r\n".encode(),
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"subfolder\"\r\n\r\n{subfolder}\r\n".encode(),
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"image\"; filename=\"{p.name}\"\r\n"
        f"Content-Type: {ctype}\r\n\r\n".encode() + p.read_bytes() + b"\r\n",
        f"--{boundary}--\r\n".encode(),
    ]
    raw = _req(base, "/upload/image", b"".join(parts), {"Content-Type": f"multipart/form-data; boundary={boundary}"}, timeout=120)
    info = json.loads(raw)
    return f"{info['subfolder']}/{info['name']}" if info.get("subfolder") else info["name"]


def queue_prompt(base: str, api_prompt: dict, client_id: str, extra: dict | None = None) -> tuple[str, dict]:
    """Returns (prompt_id, node_errors). ComfyUI still queues the valid outputs when only some
    output nodes fail validation, so a prompt_id with node_errors is a partial run, not a failure."""
    payload = {"prompt": api_prompt, "client_id": client_id}
    if extra:
        payload["extra_data"] = extra
    res = post_json(base, "/prompt", payload)
    if not res.get("prompt_id"):
        raise ComfyError("Validation failed: " + json.dumps(res.get("node_errors") or res)[:3000])
    return res["prompt_id"], res.get("node_errors") or {}


def history(base: str, prompt_id: str) -> dict | None:
    h = get_json(base, f"/history/{prompt_id}")
    return h.get(prompt_id)


def queue_state(base: str) -> dict:
    return get_json(base, "/queue")


def view_bytes(base: str, filename: str, subfolder: str, ftype: str) -> bytes:
    q = parse.urlencode({"filename": filename, "subfolder": subfolder, "type": ftype})
    return _req(base, f"/view?{q}", timeout=300)


def latest_history(base: str) -> tuple[str, dict] | None:
    """Most recent finished job (any client, e.g. one queued from the browser tab)."""
    h = get_json(base, "/history?max_items=1")
    if not h:
        return None
    pid = next(iter(h))
    return pid, h[pid]


def log_entries(base: str) -> list[dict]:
    """Server log ring buffer: [{"t": iso-local-time, "m": text chunk}, ...] (empty if unsupported)."""
    try:
        return get_json(base, "/internal/logs/raw", timeout=10).get("entries") or []
    except (ComfyError, ValueError, AttributeError):
        return []

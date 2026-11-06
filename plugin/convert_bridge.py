"""UI-workflow -> API-prompt bridge.

Runs in a Python that has comfy-cli installed (`pip install comfy-cli`), as a
separate process, so this repo only *calls* comfy-cli's GPL-3.0 converter and never
vendors it.

stdin : {"workflow": {...UI json...}, "object_info_path": "...", "host_overrides": [...]}
stdout: {"ok": true, "prompt": {...API json...}, "fixes": [...]}  |  {"ok": false, "error": "..."}

host_overrides = [{"node_id": 459, "widget": "prompt", "value": "..."}] — values for
widget inputs on *subgraph host* nodes, applied to the UI json before conversion
(host widgets_values map 1:1 onto host inputs that carry a `widget`).
"""
from __future__ import annotations

import json
import sys


def _is_link(v) -> bool:
    return isinstance(v, list) and len(v) == 2 and isinstance(v[0], str)


def apply_host_overrides(wf: dict, overrides: list[dict]) -> list[str]:
    done = []
    nodes = {n["id"]: n for n in wf.get("nodes", [])}
    for o in overrides:
        n = nodes.get(o["node_id"])
        if n is None:
            raise ValueError(f"host node {o['node_id']} not found")
        widget_inputs = [i for i in n.get("inputs", []) if i.get("widget")]
        names = [(i["name"], i.get("label")) for i in widget_inputs]
        idx = next((k for k, (nm, lb) in enumerate(names) if o["widget"] in (nm, lb)), None)
        if idx is None:
            raise ValueError(f"node {o['node_id']} has no widget {o['widget']!r}; widgets: {names}")
        n["widgets_values"][idx] = o["value"]
        done.append(f"{o['node_id']}.{names[idx][0]}")
    return done


def fix_subgraph_socket_values(wf: dict, api: dict) -> list[str]:
    """comfy-cli drops subgraph-host widget values that feed a *non-widget* socket inside the
    subgraph (e.g. a prompt routed into ComfySwitchNode.on_false). Re-inject them (depth 1)."""
    fixes = []
    defs = {sg["id"]: sg for sg in (wf.get("definitions") or {}).get("subgraphs", [])}
    for host in wf.get("nodes", []):
        sg = defs.get(host.get("type"))
        if not sg or host.get("mode") in (2, 4):
            continue
        inner = {n["id"]: n for n in sg.get("nodes", [])}
        values = iter(host.get("widgets_values") or [])
        widget_vals = {}
        for slot, inp in enumerate(host.get("inputs", [])):
            if inp.get("widget"):
                widget_vals[slot] = next(values, None)
        for slot, val in widget_vals.items():
            if host["inputs"][slot].get("link") is not None:
                continue  # value comes from an outer link, converter handles it
            for l in sg.get("links", []):
                if l["origin_id"] != -10 or l["origin_slot"] != slot:
                    continue
                tn = inner.get(l["target_id"])
                if tn is None:
                    continue
                tin = tn["inputs"][l["target_slot"]]
                if tin.get("widget"):
                    continue
                key = f"{host['id']}:{tn['id']}"
                if key in api and not _is_link(api[key]["inputs"].get(tin["name"])) and api[key]["inputs"].get(tin["name"]) is None:
                    api[key]["inputs"][tin["name"]] = val
                    fixes.append(f"{key}.{tin['name']} <- host input {host['inputs'][slot]['name']}")
    return fixes


def drop_frontend_only_viewers(api: dict, object_info: dict) -> list[str]:
    """Nodes with a required *socketless* widget the converter cannot fill (e.g. ImageCompare.compare_view,
    a browser-only DOM widget) are pure viewers with no outputs: drop them instead of guessing a value
    (['',''] is parsed by the server as a link to node '' and fails validation)."""
    fixes = []
    for nid in list(api):
        n = api[nid]
        info = object_info.get(n["class_type"], {})
        req = (info.get("input") or {}).get("required") or {}
        missing = [k for k, spec in req.items()
                   if k not in n["inputs"] and isinstance(spec, list) and len(spec) > 1 and isinstance(spec[1], dict) and spec[1].get("socketless")]
        if missing and not info.get("output"):
            del api[nid]
            fixes.append(f"dropped viewer node {nid} ({n['class_type']}): browser-only input {missing}")
    return fixes


def main() -> None:
    try:
        req = json.load(sys.stdin)
        from comfy_cli.workflow_to_api import convert_ui_to_api

        object_info = json.load(open(req["object_info_path"], encoding="utf-8"))
        wf = req["workflow"]
        applied = apply_host_overrides(wf, req.get("host_overrides") or [])
        api = convert_ui_to_api(wf, object_info)
        fixes = fix_subgraph_socket_values(wf, api) + drop_frontend_only_viewers(api, object_info)
        json.dump({"ok": True, "prompt": api, "host_overrides_applied": applied, "fixes": fixes}, sys.stdout)
    except Exception as e:  # report, never crash silently
        json.dump({"ok": False, "error": f"{type(e).__name__}: {e}"}, sys.stdout)


if __name__ == "__main__":
    main()

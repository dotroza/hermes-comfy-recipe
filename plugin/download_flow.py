"""Which model files to download, in which order, for which ComfyUI - the planning half of downloads.py.

Order: tutorial step 1 files, then tutorial step 2 files, then everything else (smallest first). Works for the bundled
library (catalog requirements), for a user's own saved workflow (models embedded in node ``properties.models``, the
same data ComfyUI's Issues tab uses) and for an explicit list. Never installs node packs; only watches their queue.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import quote

from . import core, dependencies, downloads, installer, library, onboarding


def _key(folder: str, name: str) -> tuple[str, str]:
    return folder, str(name).replace('\\', '/')


def tutorial_keys() -> dict[str, set]:
    """{'tutorial-1': {(folder, name)}, 'tutorial-2': {...}} from the catalog requirements of each tutorial step."""
    by_id = {e['id']: e for e in library.load_catalog()['workflows']}
    out = {}
    for n, step in onboarding.STEPS.items():
        req = (by_id.get(step['workflow_id']) or {}).get('requirements') or {}
        out[f'tutorial-{n}'] = {_key(m['folder'], m['name']) for m in req.get('models', []) if not m.get('optional')}
    return out


def group_for(folder: str, name: str, keys: dict | None = None) -> str:
    keys = keys or tutorial_keys()
    for group in sorted(keys, key=lambda g: downloads.GROUP_ORDER.get(g, 5)):
        if _key(folder, name) in keys[group]:
            return group
    return 'other'


def target(instance: str | None = None) -> tuple[dict, Path, Path]:
    """(instance, folder for progress files, models root). Managed install: its own folder; another ComfyUI: a
    folder under the plugin data dir for progress, and that ComfyUI's models/ for the files."""
    inst = core._inst(instance)
    if inst['name'] == core.MANAGED_NAME:
        d = core._managed_dir()
        m = installer.manifest(d) if d else None
        if not m:
            raise ValueError("Comfy Recipe's own ComfyUI is not installed")
        return inst, Path(d), Path(m['comfyui_dir']) / 'models'
    if not inst.get('root') or not Path(inst['root']).is_dir():
        raise ValueError(f"The models folder of {inst['name']} is unknown; download into a known ComfyUI only")
    safe = re.sub(r'[^A-Za-z0-9_.-]+', '_', inst['name'])
    return inst, core.DATA / 'downloads' / safe, Path(inst['root']) / 'models'


def queue(progress_dir: Path, models_root: Path, models: list[dict], spawn: bool = True) -> dict:
    """Queue every model with a URL, grouped tutorial-1 -> tutorial-2 -> other; one progress card for all."""
    keys = tutorial_keys()
    grouped: dict[str, list] = {}
    for m in models:
        if m.get('url'):
            grouped.setdefault(group_for(m['folder'], m['name'], keys), []).append(m)
    result = None
    for group in sorted(grouped, key=lambda g: downloads.GROUP_ORDER.get(g, 5)):
        result = downloads.enqueue(progress_dir, models_root, grouped[group], group=group, spawn=spawn)
    if result is None:
        result = dict(downloads.status(progress_dir), added=[], note='nothing to download')
    result['models_without_url'] = [m for m in models if not m.get('url')]
    return result


def bundled_proposal(inst: dict, workflow_ids: list[str] | None) -> dict:
    """Missing files of bundled workflows (deduplicated, sizes from the 1-hour cache)."""
    catalog = library.load_catalog()
    entries = [e for e in catalog['workflows'] if workflow_ids is None or e['id'] in workflow_ids]
    unknown = set(workflow_ids or []) - {e['id'] for e in entries}
    if unknown:
        raise ValueError('Unknown bundled workflow id(s): ' + ', '.join(sorted(unknown)))
    info = json.loads(core._object_info_path(inst).read_text(encoding='utf-8'))
    reports = [dependencies.check(inst, e, library.load_asset(e), info, {}, None) for e in entries]
    return dependencies.library_proposal(reports, size_of=dependencies.cached_size_lookup(core.DATA))


def embedded_models(workflow: dict) -> list[dict]:
    """Model files a saved UI workflow declares on its loader nodes (``properties.models``: name, url, directory)."""
    nodes, _ = dependencies._nodes(workflow)
    out, seen = [], set()
    for node in nodes:
        for m in (node.get('properties') or {}).get('models') or []:
            if not isinstance(m, dict) or not m.get('name') or not m.get('directory'):
                continue
            key = _key(m['directory'], m['name'])
            if key in seen:
                continue
            seen.add(key)
            out.append({'folder': m['directory'], 'name': key[1], 'url': m.get('url') or None,
                        'source_node_type': node.get('type')})
    return out


def saved_workflow_missing(inst: dict, path: str) -> list[dict]:
    wf = core.cc.load_workflow(inst['url'], core._resolve_workflow(inst, path))
    rows, inventory = [], {}
    for m in embedded_models(wf):
        downloads.safe_target(Path(inst.get('root') or '.') / 'models', m['folder'], m['name'])  # validate early
        if m['folder'] not in inventory:
            try:
                have = core.cc.get_json(inst['url'], '/models/' + quote(m['folder'], safe=''))
                inventory[m['folder']] = {str(v).replace('\\', '/') for v in have} if isinstance(have, list) else None
            except Exception:
                inventory[m['folder']] = None
        have = inventory[m['folder']]
        if have is not None and m['name'] in have:
            continue
        rows.append(dict(m, status='missing' if have is not None else 'unknown'))
    return rows


def start(params: dict) -> dict:
    inst, d, root = target(params.get('instance'))
    if params.get('models'):
        models = [{'folder': m['folder'], 'name': m['name'], 'url': m.get('url'), 'size_bytes': m.get('size_bytes')}
                  for m in params['models']]
        source = 'explicit list'
    elif params.get('workflow'):
        models = saved_workflow_missing(inst, params['workflow'])
        source = 'saved workflow ' + params['workflow']
    else:
        ids = params.get('workflow_ids')
        prop = bundled_proposal(inst, ids)
        models = prop['models'] + prop['models_without_url']
        source = 'bundled workflows ' + (', '.join(ids) if ids else '(all)')
    result = queue(d, root, models)
    result.update(instance=inst['name'], models_root=str(root), source=source)
    return result


def handle(params: dict) -> dict:
    action = params.get('action', 'status')
    if action == 'start':
        return start(params)
    inst, d, _ = target(params.get('instance'))
    if action == 'status':
        return downloads.status(d)
    if action == 'wait':
        return downloads.wait(d, params.get('group'), int(params.get('wait_s') or 300))
    if action == 'cancel':
        return downloads.cancel(d)
    if action == 'watch_nodes':
        return downloads.start_nodes_watch(d, inst['url'], [str(p) for p in params.get('packs') or []])
    if action == 'nodes_status':
        card = downloads.card_path(d, 'nodes')
        return dict(downloads._read(card, {}) or {'state': 'idle'}, progress_card='MEDIA:' + str(card))
    raise ValueError(f'Unknown downloads action: {action}')

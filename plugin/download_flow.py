"""Which model files to download, in which order, for which ComfyUI - the planning half of downloads.py.

Order: tutorial step 1 files, then steps 2, 3 and 4, then everything else (smallest first). Works for the bundled
library (catalog requirements), for a user's own saved workflow (models embedded in node ``properties.models``, the
same data ComfyUI's Issues tab uses) and for an explicit list. Node packs (``install_nodes``) are queued in
ComfyUI-Manager through its API - the same request as the window's Install All - only after the user's consent.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from urllib.parse import quote

from . import core, dependencies, downloads, installer, library, onboarding


def _key(folder: str, name: str) -> tuple[str, str]:
    return folder, str(name).replace('\\', '/')


def tutorial_keys() -> dict[str, set]:
    """{'tutorial-1': {(folder, name)}, ..., 'tutorial-4': {...}} from the catalog requirements of each tutorial step."""
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
    """Queue every model with a URL, grouped tutorial-1 -> ... -> tutorial-4 -> other; one progress card for all."""
    keys = tutorial_keys()
    grouped: dict[str, list] = {}
    for m in models:
        if m.get('url'):
            grouped.setdefault(group_for(m['folder'], m['name'], keys), []).append(m)
    result = None
    for group in sorted(grouped, key=lambda g: downloads.GROUP_ORDER.get(g, 5)):
        result = downloads.enqueue(progress_dir, models_root, grouped[group], group=group, spawn=spawn,
                                   allow_local=bool(core.SETTINGS.get('allow_local_mirrors')))
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
    inventory = {}
    packs = downloads.installed_packs(inst['url']) if any(
        (e.get('requirements') or {}).get('frontend_nodes') for e in entries) else None
    reports = [dependencies.check(inst, e, library.load_asset(e), info, {}, None,
                                  model_inventory=inventory, installed_packs=packs) for e in entries]
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


def catalog_packs() -> dict[str, dict]:
    """Registry packs the bundled workflows declare, keyed by lower-case id."""
    out = {}
    for e in library.load_catalog()['workflows']:
        for p in (e.get('requirements') or {}).get('custom_node_packs', []):
            out.setdefault(str(p['id']).lower(), {'id': p['id'], 'name': p.get('name', p['id'])})
    return out


def resolve_packs(packs) -> list[dict]:
    """Pack ids or display names (or {id, name}) -> [{id, name}]; catalog names are matched case-insensitively."""
    known = catalog_packs()
    by_name = {v['name'].lower(): v for v in known.values()}
    rows = []
    for p in packs or []:
        key = str(p.get('id') if isinstance(p, dict) else p).strip()
        row = known.get(key.lower()) or by_name.get(key.lower())
        if row is None:
            row = {'id': key, 'name': str(p.get('name') or key) if isinstance(p, dict) else key}
        if row['id'] and row not in rows:
            rows.append(row)
    return rows


def nodes_next(inst: dict, state: str | None) -> str:
    restart = ('comfy_setup action=restart (one call: stops, starts and waits; never the Manager\'s Apply Changes '
               'button), then desktop_preview action=close and action=open on the same url so the window loads the '
               'new nodes, then comfy_onboarding action=status refresh=true (or comfy_workflows action=check) to verify'
               if inst['name'] == core.MANAGED_NAME else
               'ask the user to restart this ComfyUI (another launcher owns it), then desktop_preview close + open')
    if state == 'done':
        return 'All packs are installed. Do NOT open the Nodes Manager or search packs. Next: ' + restart + '.'
    if state == 'error':
        return ('Some packs failed (see error / pack_states). Show the error, offer one retry with '
                'comfy_downloads action=install_nodes; never install them one by one in the Manager.')
    if state == 'idle':
        return 'No node-pack install is running. After consent: comfy_downloads action=install_nodes.'
    return ('Still installing. Call comfy_downloads action=nodes_status wait_s=300 again (one short line per call). '
            'Do not touch the Nodes Manager meanwhile.')


def install_nodes(inst: dict, d: Path, packs=None, workflow_ids=None) -> dict:
    """Install node packs after consent: one call queues them in ComfyUI-Manager (API) and starts a live card."""
    rows = resolve_packs(packs) if packs else bundled_proposal(inst, workflow_ids)['node_packs']
    rows = [{'id': r['id'], 'name': r.get('name', r['id'])} for r in rows]
    if not rows:
        return {'state': 'done', 'queued': [], 'note': 'No missing node packs', 'instruction': nodes_next(inst, 'done')}
    try:
        res = downloads.queue_pack_installs(inst['url'], rows)
    except Exception as exc:
        raise ValueError(f'ComfyUI-Manager did not accept the install ({type(exc).__name__}: {exc}). '
                         'Is ComfyUI running with --enable-manager?') from None
    if not res['queued']:
        card = downloads.card_path(d, 'nodes')
        downloads._write(card, downloads._nodes_card(rows, {r['id'].lower() for r in rows}, 'done', time.time(),
                                                     note=downloads.NODES_DONE_NOTE))
        return dict(res, state='done', progress_card='MEDIA:' + str(card), instruction=nodes_next(inst, 'done'))
    watch = downloads.start_nodes_watch(d, inst['url'], rows, queued=True)
    return dict(res, state='running', progress_card=watch['progress_card'], instruction=(
        'Installing in the background through ComfyUI-Manager: nothing to click in the window, do NOT open the '
        'Nodes Manager. Post progress_card once, then call comfy_downloads action=nodes_status wait_s=300 until '
        'state is done (pip dependencies can take a few minutes).'))


def handle(params: dict) -> dict:
    action = params.get('action', 'status')
    if action == 'start':
        return start(params)
    inst, d, _ = target(params.get('instance'))
    if action in ('status', 'wait'):
        result = (downloads.wait(d, params.get('group'), int(params.get('wait_s') or 300))
                  if action == 'wait' else downloads.status(d))
        group_id = params.get('group')
        group = next((g for g in result.get('groups', []) if g['id'] == group_id), None) if group_id else None
        ready = group is not None and group.get('state') == 'done' if group_id else result.get('state') == 'done'
        if ready:
            result = dict(result, instance=inst['name'], url=inst['url'], instruction=(
                'Downloads for this scope are complete. Before asking for a prompt, refresh the visible model lists '
                'NOW, not after the user replies: confirm the pane is on this result\'s URL, then click the '
                'Missing Models header Refresh ([data-testid="missing-model-header-refresh"]) in Issues with '
                'drive_preview. Use desktop_preview read to verify the selected workflow\'s missing-model warnings '
                'have cleared. If the refresh control is absent and no warnings remain, no click is needed. '
                'Preserve dirty prompts and tabs; do not close/reopen or reload the page. Other workflows may still '
                'be downloading. This is download completion, not proof of node/settings or execution readiness.'))
        return result
    if action == 'cancel':
        return downloads.cancel(d)
    if action == 'install_nodes':
        return install_nodes(inst, d, params.get('packs'), params.get('workflow_ids'))
    if action == 'watch_nodes':
        return downloads.start_nodes_watch(d, inst['url'], resolve_packs(params.get('packs')))
    if action == 'nodes_status':
        result = downloads.nodes_status(d, int(params.get('wait_s') or 0))
        return dict(result, instruction=nodes_next(inst, result.get('state')))
    raise ValueError(f'Unknown downloads action: {action}')

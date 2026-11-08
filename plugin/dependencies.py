"""Read-only dependency evidence, deliberately separate from installation/execution."""
from __future__ import annotations
import shutil
from pathlib import PurePosixPath, PureWindowsPath
from urllib.parse import quote
from . import comfy_client as cc

UI_ONLY = {'Note', 'MarkdownNote', 'Reroute', 'PrimitiveNode'}


def _nodes(workflow: dict) -> tuple[list[dict], set[str]]:
    result = list(workflow.get('nodes', []))
    definitions = set()
    pending = list((workflow.get('definitions') or {}).get('subgraphs', []))
    while pending:
        graph = pending.pop()
        if graph['id'] in definitions:
            continue
        definitions.add(graph['id'])
        result.extend(graph.get('nodes', []))
        pending.extend((graph.get('definitions') or {}).get('subgraphs', []))
    return result, definitions


def remote_size(url: str, timeout: float = 8.0) -> int | None:
    """Best-effort download size (HEAD, redirects followed). None when unknown - never blocks the report."""
    import urllib.request
    try:
        req = urllib.request.Request(url, method='HEAD', headers={'User-Agent': 'comfy-recipe'})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            size = r.headers.get('x-linked-size') or r.headers.get('Content-Length')
            return int(size) if size and int(size) > 0 else None
    except Exception:
        return None


def _settings_rows(req: dict, settings: dict | None, settings_error: str | None) -> list[dict]:
    rows = []
    for s in req.get('frontend_settings', []):
        if settings is None:
            status = 'unknown'
        else:
            status = 'ok' if settings.get(s['id'], s.get('default', False)) == s['value'] else 'needs_change'
        row = dict(s, status=status, current=None if settings is None else settings.get(s['id']),
                   window_selector='#' + s['id'].replace('.', r'\.'))
        if settings_error:
            row['error'] = settings_error
        rows.append(row)
    return rows


def setup_proposal(report: dict, size_of=remote_size) -> dict:
    """ONE combined proposal: every missing node pack, model and frontend setting, approved with a single OK."""
    packs = [{'id': p['id'], 'name': p.get('name', p['id']), 'missing_node_types': p['missing_node_types'],
              'tested_version': p.get('tested_version')} for p in report['nodes']['missing_packs']]
    models, manual = [], []
    for m in report['models']:
        if m['status'] != 'missing':
            continue
        row = {'name': m['name'], 'folder': m['folder'], 'url': m.get('url')}
        if m.get('url'):
            row['size_gb'] = (lambda b: round(b / 1e9, 2) if b else None)(size_of(m['url']))
            models.append(row)
        else:
            manual.append(dict(row, note='No verified download link: the user must provide this file.'))
    settings = [s for s in report.get('settings', []) if s['status'] == 'needs_change']
    blockers = report['nodes']['missing_core'] + report['nodes']['unresolved']
    needed = bool(packs or models or manual or settings)
    sizes = [m['size_gb'] for m in models if m.get('size_gb')]
    return {
        'needed': needed,
        'consent': 'Ask ONCE with one clarify form listing all items below; never ask per item.' if needed else 'nothing to install',
        'node_packs': packs, 'models': models, 'models_without_url': manual, 'settings': settings,
        'download_gb': round(sum(sizes), 2) if sizes else None,
        'download_gb_note': None if len(sizes) == len(models) else 'size unknown for some models',
        'restart_after_packs': bool(packs),
        'blockers': blockers,
        'window_steps': [step for step in (
            'Issues tab (right panel) -> Missing Node Packs -> Install All' if packs else None,
            'Each model -> <ComfyUI root>/models/<folder>/<name> from its url (Issues tab download button when shown)' if models else None,
            'Settings (Ctrl + ,) -> click switch ' + ', '.join(s['window_selector'] for s in settings) + ' (verify value in the delta) -> Close dialog' if settings else None,
            'Queue idle -> restart ComfyUI (managed: comfy_setup stop/start; never Manager Apply Changes) -> desktop_preview close + open' if packs else None,
            'comfy_workflows action=check workflow=<ID> refresh=true to verify' if needed else None,
        ) if step],
    }


def check(inst: dict, entry: dict, workflow: dict, object_info: dict,
          settings: dict | None = None, settings_error: str | None = None, size_of=None) -> dict:
    req = entry.get('requirements') or {}
    nodes, definitions = _nodes(workflow)
    types = {n['type'] for n in nodes} - definitions - UI_ONLY
    frontend = {n['type']: n for n in req.get('frontend_nodes', [])}
    core = set(req.get('core_node_types', []))
    providers = {t: p for p in req.get('custom_node_packs', []) for t in p.get('node_types', [])}
    missing = types - set(object_info) - set(frontend)
    packs = []
    for pack in req.get('custom_node_packs', []):
        absent = sorted(missing & set(pack.get('node_types', [])))
        if absent:
            packs.append({**pack, 'missing_node_types': absent})
    unresolved = sorted(missing - core - set(providers))
    models, inventory = [], {}
    for model in req.get('models', []):
        folder, name = model.get('folder'), model.get('name')
        if (not isinstance(folder, str) or not folder or '/' in folder or '\\' in folder or folder in ('.', '..')
                or not isinstance(name, str) or not name or PureWindowsPath(name).drive
                or PurePosixPath(name.replace('\\', '/')).is_absolute()
                or '..' in PurePosixPath(name.replace('\\', '/')).parts):
            raise ValueError('Unsafe model folder or filename')
        if folder not in inventory:
            try:
                values = cc.get_json(inst['url'], '/models/' + quote(folder, safe=''))
                if not isinstance(values, list) or any(not isinstance(v, str) for v in values):
                    raise ValueError('Invalid installed-model response')
                inventory[folder] = (set(v.replace('\\', '/') for v in values), None)
            except (cc.ComfyError, ValueError, OSError) as exc:
                inventory[folder] = (None, str(exc))
        have, error = inventory[folder]
        row = dict(model, status='unknown' if have is None else 'available' if name.replace('\\', '/') in have else 'missing')
        if error:
            row['error'] = error
        models.append(row)
    inputs = []
    for media in req.get('inputs', []):
        schema = object_info.get(media.get('type'), {}).get('input', {})
        choices = next((spec[0] for group in ('required', 'optional') for spec in schema.get(group, {}).values()
                        if isinstance(spec, list) and spec and isinstance(spec[0], list)), [])
        status = 'unused' if not media.get('connected', True) else 'configured' if media.get('filename') in choices else 'needs_user_media'
        inputs.append(dict(media, status=status))
    services = [dict(service, credentials_status='not_checked') for service in req.get('services', [])]
    executables = [{'name': name, 'status': 'available' if shutil.which(name) else 'missing'} for name in req.get('executables', [])]
    report = {'models': models, 'inputs': inputs, 'settings': _settings_rows(req, settings, settings_error), 'services': services, 'executables': executables,
            'compatibility': dict(req.get('compatibility', {}), hardware_validation='not_checked'),
            'portability_warnings': req.get('portability_warnings', []),
            'installation_plan': {'method': 'ComfyUI-Manager in the visible window', 'requires_consent': True,
                                  'packs': packs, 'unresolved_node_types': unresolved, 'requires_restart_consent': True,
                                  'security_note': 'Custom nodes execute third-party Python. A venv is not a security sandbox.'},
            'workflow_id': entry['id'], 'definition': {'status': 'bundled', 'working_copy': 'not_checked'},
            'nodes': {'available_types': sorted(types & set(object_info)), 'missing_core': sorted(missing & core),
                      'missing_packs': packs, 'unresolved': unresolved,
                      'frontend_checks': [dict(frontend[t], status='requires_frontend_check') for t in sorted(types & set(frontend))],
                      'import_failures': 'not_checked'},
            'execution_ready': 'not_tested'}
    report['setup_proposal'] = setup_proposal(report, size_of) if size_of else setup_proposal(report, lambda u: None)
    return report

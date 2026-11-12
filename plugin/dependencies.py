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
    """Best-effort download size (HEAD, redirects followed). None when unknown - never blocks the report.
    Same public-host rules as the downloads (safe_http): private/loopback/link-local hosts and hops are refused."""
    import urllib.request
    from . import core, safe_http
    try:
        req = urllib.request.Request(url, method='HEAD', headers={'User-Agent': 'comfy-recipe'})
        with safe_http.urlopen(req, timeout=timeout,
                               allow_local=bool(core.SETTINGS.get('allow_local_mirrors'))) as r:
            size = r.headers.get('x-linked-size') or r.headers.get('Content-Length')
            return int(size) if size and int(size) > 0 else None
    except Exception:
        return None


def cached_size_lookup(data_dir, lookup=remote_size, clock=None):
    """One-hour bounded metadata cache. No model payload is downloaded."""
    from contextlib import closing
    import sqlite3
    import time
    from pathlib import Path
    clock = clock or time.time
    root = Path(data_dir)
    root.mkdir(parents=True, exist_ok=True)
    path = root / 'model-sizes.sqlite3'
    with closing(sqlite3.connect(path, timeout=10)) as db, db:
        db.execute('CREATE TABLE IF NOT EXISTS sizes (url TEXT PRIMARY KEY, bytes INTEGER, checked REAL)')
    def size_of(url):
        now = clock()
        with closing(sqlite3.connect(path, timeout=10)) as db, db:
            row = db.execute('SELECT bytes, checked FROM sizes WHERE url=?', (url,)).fetchone()
        if row and 0 <= now - row[1] < 3600:
            return row[0]
        value = lookup(url)
        with closing(sqlite3.connect(path, timeout=10)) as db, db:
            db.execute('INSERT OR REPLACE INTO sizes VALUES (?,?,?)', (url, value, now))
            db.execute('DELETE FROM sizes WHERE url NOT IN (SELECT url FROM sizes ORDER BY checked DESC LIMIT 512)')
        return value
    return size_of


def _positive_size(value) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else None


def library_proposal(reports: list[dict], size_of=remote_size) -> dict:
    """Missing default requirements across workflows; no installation or generation."""
    from concurrent.futures import ThreadPoolExecutor
    packs, targets, settings = {}, {}, {}
    blockers, unknown, optional = [], [], []
    inputs, executables, services, warnings, compatibility = [], [], [], [], []
    for report in reports:
        workflow_id = report.get('workflow_id')
        inputs.extend(dict(row, workflow_id=workflow_id) for row in report.get('inputs', []))
        executables.extend(dict(row, workflow_id=workflow_id) for row in report.get('executables', []))
        services.extend(dict(row, workflow_id=workflow_id) for row in report.get('services', []))
        warnings.extend({'workflow_id': workflow_id, 'warning': row} for row in report.get('portability_warnings', []))
        if report.get('compatibility'):
            compatibility.append(dict(report['compatibility'], workflow_id=workflow_id))
        nodes = report['nodes']
        blockers.extend(nodes.get('missing_core', []) + nodes.get('unresolved', []))
        unknown.extend(dict(pack, workflow_id=workflow_id) for pack in nodes.get('unknown_packs', []))
        for pack in nodes.get('missing_packs', []):
            packs.setdefault(pack['id'], pack)
        for setting in report.get('settings', []):
            if setting.get('status') == 'unknown':
                unknown.append({'setting': setting['id']})
            if setting.get('status') != 'needs_change':
                continue
            old = settings.get(setting['id'])
            if old and old['value'] != setting['value']:
                blockers.append('Conflicting frontend setting: ' + setting['id'])
            settings[setting['id']] = setting
        for model in report.get('models', []):
            if model.get('status') == 'unknown':
                unknown.append(model)
                continue
            if model.get('status') != 'missing':
                continue
            if model.get('optional'):
                optional.append(model)
                continue
            folder, name = model['folder'], model['name'].replace('\\', '/')
            if ('/' in folder or '\\' in folder or folder in ('', '.', '..') or
                    PureWindowsPath(name).drive or PurePosixPath(name).is_absolute() or
                    '..' in PurePosixPath(name).parts):
                raise ValueError('Unsafe model destination')
            key = (folder, name)
            row = dict(model, name=name)
            if key in targets and targets[key].get('url') != row.get('url'):
                blockers.append('Conflicting model URLs: ' + folder + '/' + name)
                targets[key]['url'] = None
            else:
                existing = targets.setdefault(key, row)
                if _positive_size(existing.get('size_bytes')) is None and _positive_size(row.get('size_bytes')) is not None:
                    existing['size_bytes'] = row['size_bytes']
    urls = sorted({row['url'] for row in targets.values()
                   if row.get('url') and _positive_size(row.get('size_bytes')) is None})
    def lookup(url):
        try:
            return _positive_size(size_of(url))
        except Exception:
            return None
    with ThreadPoolExecutor(max_workers=4) as pool:
        sizes = dict(zip(urls, pool.map(lookup, urls)))
    models, manual = [], []
    for row in targets.values():
        size = _positive_size(row.get('size_bytes')) or sizes.get(row.get('url'))
        row = dict(row, size_bytes=size, size_gb=round(size / 1e9, 2) if size else None)
        (models if row.get('url') else manual).append(row)
    total = sum(row['size_bytes'] or 0 for row in models)
    unknown_sizes = sum(row['size_bytes'] is None for row in models) + len(manual)
    return {'node_packs': list(packs.values()), 'models': models, 'optional_models': optional,
            'settings': list(settings.values()), 'blockers': sorted(set(blockers)),
            'inputs': inputs, 'missing_media': [row for row in inputs if row.get('status') == 'needs_user_media'],
            'executables': executables, 'services': services, 'readiness_warnings': warnings,
            'compatibility': compatibility,
            'models_without_url': manual, 'unknown_inventory': unknown,
            'download_bytes': total, 'download_gb': round(total / 1e9, 2),
            'unknown_size_count': unknown_sizes, 'size_complete': not unknown_sizes and not unknown,
            'needed': bool(packs or targets or settings),
            'consent': 'Ask independent node/model choices; settings require separate explicit consent. No installs have run.'}


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
        if m['status'] != 'missing' or m.get('optional'):
            continue
        row = {'name': m['name'], 'folder': m['folder'], 'url': m.get('url')}
        if m.get('url'):
            row['size_bytes'] = _positive_size(m.get('size_bytes'))
            if row['size_bytes'] is None:
                try:
                    row['size_bytes'] = _positive_size(size_of(m['url']))
                except Exception:
                    row['size_bytes'] = None
            row['size_gb'] = round(row['size_bytes'] / 1e9, 2) if row['size_bytes'] else None
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
        'download_bytes': sum(m.get('size_bytes') or 0 for m in models),
        'download_gb': round(sum(m.get('size_bytes') or 0 for m in models) / 1e9, 2) if models else 0,
        'download_gb_note': None if len(sizes) == len(models) else 'size unknown for some models',
        'restart_after_packs': bool(packs),
        'blockers': blockers,
        'unknown_inventory': report['nodes'].get('unknown_packs', []),
        'window_steps': [step for step in (
            'comfy_downloads action=install_nodes packs=[these ids] (plugin installs via ComfyUI-Manager; never search packs in the Nodes Manager) -> comfy_downloads action=nodes_status wait_s=300 until done' if packs else None,
            'comfy_downloads action=start workflow_ids=[<ID>] (background download with a live card)' if models else None,
            'comfy_workflows action=apply_settings workflow=<ID> (' + ', '.join(s['id'] for s in settings) + '; never toggle by hand)' if settings else None,
            'Restart: managed = comfy_setup action=restart (never Manager Apply Changes); other launchers = ask the user' if packs else None,
            'desktop_preview close + open (loads new nodes/settings)' if packs or settings else None,
            'comfy_workflows action=check workflow=<ID> refresh=true to verify' if needed else None,
        ) if step],
    }


def check(inst: dict, entry: dict, workflow: dict, object_info: dict,
          settings: dict | None = None, settings_error: str | None = None, size_of=None,
          model_inventory: dict | None = None, installed_packs: set[str] | None = None) -> dict:
    """Check one workflow; callers may share model inventory within one report only.

    Inventory keys include the backend URL/root so a batch cannot leak evidence between installations.
    Never retain this snapshot across reports: downloads/restarts must be visible on the next check.
    installed_packs is explicit Manager installed+enabled evidence; None means unknown (no implicit request).
    """
    req = entry.get('requirements') or {}
    nodes, definitions = _nodes(workflow)
    types = {n['type'] for n in nodes} - definitions - UI_ONLY
    frontend = {n['type']: n for n in req.get('frontend_nodes', [])}
    core = set(req.get('core_node_types', []))
    providers = {t: p for p in req.get('custom_node_packs', []) for t in p.get('node_types', [])}
    missing = types - set(object_info) - set(frontend)
    packs, unknown_packs = [], []
    for pack in req.get('custom_node_packs', []):
        absent = sorted(missing & set(pack.get('node_types', [])))
        frontend_types = sorted(t for t in types & set(frontend)
                                if frontend[t].get('pack_id') == pack['id'])
        if frontend_types and installed_packs is not None and pack['id'].lower() not in installed_packs:
            absent = sorted(set(absent) | set(frontend_types))
        if absent:
            packs.append({**pack, 'missing_node_types': absent})
        elif frontend_types and installed_packs is None:
            unknown_packs.append({**pack, 'status': 'unknown', 'node_types': frontend_types})
    unresolved = sorted(missing - core - set(providers))
    models = []
    inventory = {} if model_inventory is None else model_inventory
    for model in req.get('models', []):
        folder, name = model.get('folder'), model.get('name')
        if (not isinstance(folder, str) or not folder or '/' in folder or '\\' in folder or folder in ('.', '..')
                or not isinstance(name, str) or not name or PureWindowsPath(name).drive
                or PurePosixPath(name.replace('\\', '/')).is_absolute()
                or '..' in PurePosixPath(name.replace('\\', '/')).parts):
            raise ValueError('Unsafe model folder or filename')
        key = (inst['url'].rstrip('/'), str(inst.get('root') or ''), folder)
        if key not in inventory:
            try:
                values = cc.get_json(inst['url'], '/models/' + quote(folder, safe=''))
                if not isinstance(values, list) or any(not isinstance(v, str) for v in values):
                    raise ValueError('Invalid installed-model response')
                inventory[key] = (set(v.replace('\\', '/') for v in values), None)
            except (cc.ComfyError, ValueError, OSError) as exc:
                inventory[key] = (None, str(exc))
        have, error = inventory[key]
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
            'installation_plan': {'method': 'ComfyUI-Manager API via comfy_downloads action=install_nodes', 'requires_consent': True,
                                  'packs': packs, 'unresolved_node_types': unresolved, 'requires_restart_consent': True,
                                  'security_note': 'Custom nodes execute third-party Python. A venv is not a security sandbox.'},
            'workflow_id': entry['id'], 'definition': {'status': 'bundled', 'working_copy': 'not_checked'},
            'nodes': {'available_types': sorted(types & set(object_info)), 'missing_core': sorted(missing & core),
                      'missing_packs': packs, 'unknown_packs': unknown_packs, 'unresolved': unresolved,
                      'frontend_checks': [dict(frontend[t], status='requires_frontend_check') for t in sorted(types & set(frontend))],
                      'import_failures': 'not_checked'},
            'execution_ready': 'not_tested'}
    report['setup_proposal'] = setup_proposal(report, size_of) if size_of else setup_proposal(report, lambda u: None)
    return report

"""Versioned shared workflows. Package assets are never user working copies."""
from __future__ import annotations
import hashlib
import json
import re
from pathlib import Path, PurePosixPath, PureWindowsPath

ROOT = Path(__file__).resolve().parent / 'workflows'
FOLDER = 'Comfy Recipe'


def publication_folder(entry: dict) -> str:
    """One portable userdata directory; absent fields keep legacy catalogs compatible."""
    folder = entry.get('folder', FOLDER)
    if (not isinstance(folder, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9 _-]{0,95}', folder)
            or folder != folder.strip() or re.fullmatch(r'CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9]', folder, re.I)):
        raise ValueError('Invalid publication folder')
    return folder


# First-launch tabs, in this order (tutorial steps 1-4, then 3D); the first one is selected.
# Cloud Recipe workflows stay in the Workflows sidebar only.
STARTUP_TABS = ('qwen-image-2-1-t2i', 'qwen-image-2-1-i2i', 'minimax-h3-r2v-mix',
                'ace-step1-5-xl-base', 'pixal3d-img-to-3d')


def startup_paths() -> list[str]:
    by_id = {entry['id']: entry for entry in load_catalog()['workflows']}
    return ['workflows/' + publication_folder(by_id[ident]) + '/' + PurePosixPath(by_id[ident]['file']).name
            for ident in STARTUP_TABS if ident in by_id]


def provision_startup(comfyui_root: Path) -> None:
    """Install a frontend-only extension in our managed ComfyUI before it starts."""
    paths = startup_paths()
    source = (ROOT.parent / 'comfyui' / 'startup.js').read_text(encoding='utf-8')
    source = source.replace('__WORKFLOW_PATHS__', json.dumps(paths))
    package = Path(comfyui_root) / 'custom_nodes' / 'hermes_comfy_recipe_startup'
    (package / 'web').mkdir(parents=True, exist_ok=True)
    (package / '__init__.py').write_text(
        '"""Comfy Recipe first-launch tabs (no nodes or dependencies)."""\n'
        'NODE_CLASS_MAPPINGS = {}\nWEB_DIRECTORY = "./web"\n', encoding='utf-8')
    (package / 'web' / 'startup.js').write_text(source, encoding='utf-8')


def canonical_hash(value: dict) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')
    return hashlib.sha256(raw).hexdigest()


def _asset_path(filename: str, root: Path) -> Path:
    if not isinstance(filename, str) or not filename or '\\' in filename:
        raise ValueError('Asset filename must be a relative POSIX path')
    rel = PurePosixPath(filename)
    if rel.is_absolute() or PureWindowsPath(filename).drive or any(p in ('.', '..') for p in rel.parts):
        raise ValueError('Asset path escapes package')
    path = (root / filename).resolve()
    if not path.is_relative_to(root.resolve()) or path.suffix != '.json':
        raise ValueError('Asset path escapes package or is not JSON')
    return path


def load_asset(entry: dict, root: Path | None = None) -> dict:
    raw = _asset_path(entry['file'], Path(root or ROOT)).read_bytes()
    if hashlib.sha256(raw).hexdigest() != entry.get('sha256'):
        raise ValueError(f"Asset checksum mismatch: {entry.get('id')}")
    wf = json.loads(raw.decode('utf-8-sig'))
    if not isinstance(wf, dict) or not isinstance(wf.get('nodes'), list) or not isinstance(wf.get('links'), list) or not isinstance(wf.get('id'), str):
        raise ValueError('Asset is not an identified UI-format workflow')
    return wf


def load_catalog(root: Path | None = None) -> dict:
    root = Path(root or ROOT)
    data = json.loads((root / 'catalog.json').read_text(encoding='utf-8-sig'))
    if data.get('schema_version') != 1 or not isinstance(data.get('workflows'), list):
        raise ValueError('Unsupported workflow catalog schema')
    ids, uuids, destinations = set(), set(), set()
    for entry in data['workflows']:
        if not isinstance(entry, dict):
            raise ValueError('Invalid workflow catalog entry')
        ident = entry.get('id')
        if not isinstance(ident, str) or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,95}', ident) or ident in ids:
            raise ValueError('Invalid or duplicate workflow ID')
        if not isinstance(entry.get('title'), str) or not entry['title'].strip() or not re.fullmatch(r'\d+\.\d+\.\d+', str(entry.get('version', ''))):
            raise ValueError(f'Invalid workflow title/version: {ident}')
        destination = (publication_folder(entry) + '/' + PurePosixPath(entry.get('file', '')).name).casefold()
        if destination in destinations:
            raise ValueError('Duplicate working-copy destination filename')
        destinations.add(destination)
        wf = load_asset(entry, root)
        if wf['id'] in uuids:
            raise ValueError('Duplicate distributed workflow UUID')
        ids.add(ident); uuids.add(wf['id'])
    return data


# Publication deliberately uses only the workflow userdata API.
from collections import Counter
import os
import uuid
from urllib.parse import quote
from . import comfy_client as cc


def _record_path(inst: dict, data_dir: Path) -> Path:
    scope = {'url': inst['url'].rstrip('/'), 'root': inst.get('root'), 'folder': FOLDER}
    return Path(data_dir) / 'library' / (canonical_hash(scope) + '.json')


def _records(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_records(path: Path, records: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        tmp.write_text(json.dumps(records, indent=2), encoding='utf-8')
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def publish(inst: dict, data_dir: Path, workflow_ids: list[str] | None = None,
            versioned: bool = False, root: Path | None = None) -> dict:
    catalog = load_catalog(root)
    known = {e['id']: e for e in catalog['workflows']}
    selected = list(known) if workflow_ids is None else workflow_ids
    if not isinstance(selected, list) or any(not isinstance(x, str) or x not in known for x in selected):
        raise ValueError('Unknown workflow IDs')
    if len(set(selected)) != len(selected):
        raise ValueError('Duplicate workflow selection')
    record_path = _record_path(inst, data_dir)
    records = _records(record_path)
    results = []
    try:
        existing_names = set(cc.list_workflows(inst['url']))
        list_error = None
    except (cc.ComfyError, ValueError, TypeError) as exc:
        existing_names, list_error = set(), str(exc)
    for ident in selected:
        entry = known[ident]
        asset = load_asset(entry, root)
        stem = PurePosixPath(entry['file']).stem
        suffix = '-v' + entry['version'] if versioned else ''
        rel = publication_folder(entry) + '/' + stem + suffix + '.json'
        if versioned:
            # A versioned sibling must not share the base tab's internal identity.
            asset['id'] = str(uuid.uuid5(uuid.NAMESPACE_URL, 'comfy-recipe/' + ident + '@' + entry['version']))
        expected = canonical_hash(asset)
        row = {'id': ident, 'path': rel, 'version': entry['version']}
        try:
            if list_error:
                raise cc.ComfyError(list_error)
            if rel in existing_names:
                actual = cc.load_workflow(inst['url'], rel)
                actual_hash = canonical_hash(actual)
                if actual_hash == expected:
                    row['status'] = 'unchanged'
                else:
                    previous = records.get(rel, {})
                    row['status'] = 'update_available' if isinstance(previous, dict) and previous.get('hash') == actual_hash else 'conflict'
                    row['note'] = 'Working copy preserved. Request versioned=true for a separate bundled revision.'
            else:
                path = '/api/userdata/' + quote('workflows/' + rel, safe='') + '?overwrite=false'
                try:
                    cc._req(inst['url'], path, json.dumps(asset, ensure_ascii=False).encode('utf-8'), {'Content-Type': 'application/json'})
                except cc.ComfyError as exc:
                    if 'HTTP 409 ' in str(exc):
                        row.update(status='conflict', note='A concurrent file appeared; it was not overwritten.')
                    else:
                        raise
                else:
                    actual = cc.load_workflow(inst['url'], rel)
                    if canonical_hash(actual) != expected:
                        raise ValueError('Published workflow read-back mismatch')
                    row['status'] = 'installed'
                    existing_names.add(rel)
            if row['status'] in ('installed', 'unchanged'):
                records[rel] = {'id': ident, 'version': entry['version'], 'hash': expected, 'workflow_id': asset['id']}
                _save_records(record_path, records)
        except (OSError, ValueError, TypeError, cc.ComfyError) as exc:
            row.update(status='error', error=str(exc))
        results.append(row)
    counts = dict(Counter(r['status'] for r in results))
    return {'instance': inst.get('name'), 'library_version': catalog['library_version'],
            'workflows': results, 'counts': counts,
            'complete': all(r['status'] in ('installed', 'unchanged') for r in results)}

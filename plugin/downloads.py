"""Comfy Recipe's own model downloader and node-pack progress watcher. Stdlib only, no Hermes imports.

Models are downloaded by ONE detached worker per install (``python downloads.py run <install dir>``), so downloads
survive the chat turn. Priority groups decide the order: tutorial step 1 files first, then tutorial step 2, then the
rest (smallest first). New items can be queued while the worker runs; it re-reads the queue after every file.

Everything the desktop progress card needs is written to JSON files in ``<install>/.comfy-recipe/progress/``:
    downloads.json   models (per file and per group bytes, speed, ETA)
    nodes.json       ComfyUI-Manager install queue (``python downloads.py nodes <install dir> --url U --pack id::name``)
The installer's own ``.comfy-recipe/status.json`` is the third card (kind=install).
"""
from __future__ import annotations

import json
import os
import sys
import time
from contextlib import contextmanager
from pathlib import Path, PurePosixPath, PureWindowsPath
from urllib import request
from urllib.error import HTTPError
from urllib.parse import urlsplit

try:  # imported as plugin.downloads, or run as a script by the detached worker
    from . import installer
except ImportError:  # pragma: no cover - script mode
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import installer  # type: ignore

CHUNK = 1 << 20
WRITE_EVERY_S = 0.5
RETRIES = 5
GROUP_ORDER = {'tutorial-1': 0, 'tutorial-2': 1, 'tutorial-3': 2, 'tutorial-4': 3}
GROUP_LABELS = {'tutorial-1': 'Tutorial step 1 - Generate your first image',
                'tutorial-2': 'Tutorial step 2 - Modify an image or create a reference sheet',
                'tutorial-3': 'Tutorial step 3 - Create your first video',
                'tutorial-4': 'Tutorial step 4 - Add sound to your video'}
ACTIVE = ('pending', 'downloading')


def progress_dir(install_dir) -> Path:
    return Path(install_dir) / '.comfy-recipe' / 'progress'


def _queue_path(install_dir) -> Path:
    return progress_dir(install_dir) / 'queue.json'


def card_path(install_dir, kind: str = 'downloads') -> Path:
    return progress_dir(install_dir) / f'{kind}.json'


def _read(p: Path, default=None):
    try:
        return json.loads(Path(p).read_text(encoding='utf-8'))
    except Exception:
        return default


def _write(p: Path, data) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + f'.{os.getpid()}.tmp')
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding='utf-8')
    for _ in range(20):  # Windows: a reader may hold the target open for a moment
        try:
            os.replace(tmp, p)
            return
        except PermissionError:
            time.sleep(0.05)
    os.replace(tmp, p)


def _write_card(p: Path, data) -> None:
    """Progress is cosmetic: a card that cannot be replaced right now (reader holding it) must not stop a download."""
    try:
        _write(p, data)
    except OSError:
        pass


@contextmanager
def _locked(install_dir, timeout: float = 15.0):
    lock = progress_dir(install_dir) / 'queue.lock'
    lock.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.time() + timeout
    while True:
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError:
            try:
                if time.time() - lock.stat().st_mtime > 30:  # a crashed holder never cleans up
                    lock.unlink(missing_ok=True)
                    continue
            except OSError:
                pass
            if time.time() > deadline:
                raise TimeoutError('download queue is locked')
            time.sleep(0.05)
    try:
        yield
    finally:
        os.close(fd)
        lock.unlink(missing_ok=True)


# ---------------------------------------------------------------- validation
def safe_target(models_root, folder: str, name: str) -> Path:
    """<models_root>/<folder>/<name>, refusing traversal, absolute names and drive letters."""
    name = str(name or '').replace('\\', '/')
    if (not isinstance(folder, str) or not folder or '/' in folder or '\\' in folder or folder in ('.', '..')
            or not name or PureWindowsPath(name).drive or PurePosixPath(name).is_absolute()
            or '..' in PurePosixPath(name).parts):
        raise ValueError(f'Unsafe model destination: {folder}/{name}')
    root = Path(models_root).resolve()
    target = (root / folder / name).resolve()
    if not target.is_relative_to(root):
        raise ValueError(f'Unsafe model destination: {folder}/{name}')
    return target


def safe_url(url: str) -> str:
    u = urlsplit(str(url or ''))
    if u.scheme == 'https' and u.netloc:
        return url
    if u.scheme == 'http' and u.hostname in ('127.0.0.1', 'localhost'):  # local mirrors and tests
        return url
    raise ValueError(f'Only https download links are accepted: {url!r}')


# ---------------------------------------------------------------- queue
def _sort_key(item: dict):
    return (item.get('priority', 9), item.get('size_bytes') or 1 << 62, item.get('seq', 0))


def enqueue(install_dir, models_root, models: list[dict], *, group: str = 'other', priority: int | None = None,
            spawn: bool = True) -> dict:
    """Queue model files ({folder, name, url, size_bytes?}) and make sure the worker runs. Already-present files of
    the expected size count as done; queued or finished files are not added twice."""
    install_dir = Path(install_dir)
    prio = GROUP_ORDER.get(group, 5) if priority is None else int(priority)
    added, skipped = [], []
    with _locked(install_dir):
        q = _read(_queue_path(install_dir), {}) or {}
        q.setdefault('items', [])
        q['models_root'] = str(models_root)
        q.pop('cancelled', None)
        if not worker_alive(install_dir):  # a crashed or closed worker leaves its file half-done: resume it
            for it in q['items']:
                if it['state'] == 'downloading':
                    it['state'] = 'pending'
        by_key = {it['key']: it for it in q['items']}
        seq = max([it.get('seq', 0) for it in q['items']] + [0])
        for m in models:
            target = safe_target(models_root, m['folder'], m['name'])
            url = safe_url(m.get('url'))
            key = f"{m['folder']}/{str(m['name']).replace(chr(92), '/')}"
            size = m.get('size_bytes') if isinstance(m.get('size_bytes'), int) and m['size_bytes'] > 0 else None
            old = by_key.get(key)
            if old and (old['state'] in ACTIVE or old['state'] == 'done' and target.exists()):
                if prio < old.get('priority', 9) and old['state'] == 'pending':  # promote, e.g. a tutorial file
                    old.update(priority=prio, group=group)
                skipped.append(key)
                continue
            seq += 1
            item = {'key': key, 'folder': m['folder'], 'name': str(m['name']).replace('\\', '/'), 'url': url,
                    'size_bytes': size, 'group': group, 'priority': prio, 'seq': seq, 'state': 'pending', 'bytes': 0,
                    'workflows': m.get('workflows') or ([m['workflow_id']] if m.get('workflow_id') else [])}
            if target.exists() and (size is None or target.stat().st_size == size):
                item.update(state='done', bytes=target.stat().st_size, size_bytes=target.stat().st_size, note='already on disk')
            if old:  # an earlier failed/cancelled attempt: retry in place (its .part file is resumed)
                old.update(item, seq=old.get('seq', seq))
            else:
                q['items'].append(item)
                by_key[key] = item
            added.append(key)
        q['items'].sort(key=_sort_key)
        q['updated_at'] = time.time()
        _write(_queue_path(install_dir), q)
        snap = snapshot(q)
        _write_card(card_path(install_dir), snap)
    worker = ensure_worker(install_dir) if spawn and snap['state'] in ('pending', 'running') else None
    return dict(snap, added=added, already_queued_or_done=skipped, worker=worker,
                progress_card='MEDIA:' + str(card_path(install_dir)))


def snapshot(q: dict, live: dict | None = None) -> dict:
    """The progress card content: overall bytes, groups, files, speed and ETA."""
    live = live or {}
    items = q.get('items', [])
    groups = {}
    for it in items:
        g = groups.setdefault(it['group'], {'id': it['group'], 'label': GROUP_LABELS.get(it['group'], 'Other workflows'),
                                            'priority': it.get('priority', 9), 'files': 0, 'done_files': 0,
                                            'bytes': 0, 'total_bytes': 0, 'unknown_sizes': 0, 'errors': 0})
        g['files'] += 1
        g['done_files'] += it['state'] == 'done'
        g['errors'] += it['state'] == 'error'
        g['bytes'] += it.get('bytes', 0)
        if it.get('size_bytes'):
            g['total_bytes'] += it['size_bytes']
        else:
            g['unknown_sizes'] += 1
    for g in groups.values():
        g['state'] = ('done' if g['done_files'] == g['files'] else 'error' if g['errors'] and
                      g['done_files'] + g['errors'] == g['files'] else 'running')
    current = next((it for it in items if it['state'] == 'downloading'), None)
    total = sum(it.get('size_bytes') or 0 for it in items)
    done = sum(min(it.get('bytes', 0), it.get('size_bytes') or it.get('bytes', 0)) for it in items)
    errors = [it for it in items if it['state'] == 'error']
    if q.get('cancelled'):
        state = 'cancelled'
    elif any(it['state'] in ACTIVE for it in items):
        state = 'running' if current else 'pending'
    elif errors:
        state = 'error'
    else:
        state = 'done' if items else 'idle'
    speed = live.get('speed_bps') if state == 'running' else None
    remaining = max(0, total - done)
    return {'kind': 'downloads', 'title': 'Downloading models', 'state': state,
            'bytes': done, 'total_bytes': total, 'percent': round(100 * done / total, 1) if total else (100.0 if state == 'done' else 0.0),
            'speed_bps': speed, 'eta_s': round(remaining / speed) if speed else None,
            'files': len(items), 'done_files': sum(it['state'] == 'done' for it in items),
            'current': current and {'key': current['key'], 'name': current['name'], 'bytes': current.get('bytes', 0),
                                    'size_bytes': current.get('size_bytes')},
            'groups': sorted(groups.values(), key=lambda g: g['priority']),
            'items': [{k: it.get(k) for k in ('key', 'name', 'folder', 'group', 'state', 'bytes', 'size_bytes', 'error')}
                      for it in items],
            'errors': [{'key': it['key'], 'error': it.get('error')} for it in errors],
            'updated_at': time.time()}


def status(install_dir) -> dict:
    q = _read(_queue_path(install_dir), {}) or {}
    snap = _read(card_path(install_dir)) or snapshot(q)
    alive = worker_alive(install_dir)
    if snap.get('state') in ('running', 'pending') and not alive:
        snap = dict(snapshot(q), state='stalled',
                    note='the download worker is not running; comfy_downloads action=start resumes it')
    return dict(snap, worker_alive=alive, progress_card='MEDIA:' + str(card_path(install_dir)))


def wait(install_dir, group: str | None = None, wait_s: int = 0) -> dict:
    """Block until ``group`` (or everything) is finished, failed, or wait_s passes."""
    deadline = time.time() + max(0, min(int(wait_s or 0), 900))
    while True:
        st = status(install_dir)
        target = next((g for g in st.get('groups', []) if g['id'] == group), None) if group else None
        finished = (target['state'] in ('done', 'error') if target else
                    st.get('state') not in ('running', 'pending') if not group else True)
        if finished or time.time() >= deadline:
            return dict(st, group=target, waited_for=group, finished=finished)
        time.sleep(2)


def cancel(install_dir) -> dict:
    with _locked(install_dir):
        q = _read(_queue_path(install_dir), {}) or {}
        q['cancelled'] = True
        for it in q.get('items', []):
            if it['state'] == 'pending':
                it['state'] = 'cancelled'
        _write(_queue_path(install_dir), q)
        _write_card(card_path(install_dir), snapshot(q))
    return status(install_dir)


# ---------------------------------------------------------------- worker
def _marker(install_dir, cmd: str = 'run') -> str:
    return f'downloads.py {cmd} ' + Path(install_dir).resolve().as_posix()


def worker_alive(install_dir) -> bool:
    w = _read(progress_dir(install_dir) / 'worker.json', {}) or {}
    return installer._pid_alive(w.get('pid'), _marker(install_dir))


def ensure_worker(install_dir) -> dict:
    install_dir = Path(install_dir)
    if worker_alive(install_dir):
        return {'pid': (_read(progress_dir(install_dir) / 'worker.json', {}) or {}).get('pid'), 'new': False}
    d = progress_dir(install_dir)
    d.mkdir(parents=True, exist_ok=True)
    args = [installer._host_python(), str(Path(__file__).resolve()), 'run', install_dir.resolve().as_posix()]
    p = installer._detached(args, d / 'worker.out', cwd=str(d))
    _write(d / 'worker.json', {'pid': p.pid, 'started_at': time.time()})
    return {'pid': p.pid, 'new': True}


def _fetch(item: dict, target: Path, on_bytes) -> None:
    part = target.with_name(target.name + '.part')
    target.parent.mkdir(parents=True, exist_ok=True)
    have = part.stat().st_size if part.exists() else 0
    size = item.get('size_bytes')
    if size and have == size:
        os.replace(part, target)
        return
    if size and have > size:
        part.unlink()
        have = 0
    headers = {'User-Agent': 'comfy-recipe'}
    if have:
        headers['Range'] = f'bytes={have}-'
    try:
        resp = request.urlopen(request.Request(item['url'], headers=headers), timeout=60)
    except HTTPError as e:
        e.close()
        if e.code == 416 and have and (not size or have == size):  # already complete
            os.replace(part, target)
            return
        raise
    with resp:
        if have and resp.status != 206:  # server ignored the range: start over
            have = 0
        if not size:
            length = resp.headers.get('Content-Length')
            if length and length.isdigit():
                size = have + int(length)
                item['size_bytes'] = size
        on_bytes(have, size)
        with open(part, 'ab' if have else 'wb') as f:
            while True:
                chunk = resp.read(CHUNK)
                if not chunk:
                    break
                f.write(chunk)
                have += len(chunk)
                on_bytes(have, size)
    if size and have != size:
        raise IOError(f'incomplete download: {have} of {size} bytes')
    os.replace(part, target)


def run(install_dir) -> str:
    """Worker loop: next pending item by priority, resumable with retries; progress every WRITE_EVERY_S."""
    install_dir = Path(install_dir)
    _write(progress_dir(install_dir) / 'worker.json', {'pid': os.getpid(), 'started_at': time.time()})
    live = {'speed_bps': None}
    with _locked(install_dir):  # only one worker runs: anything marked downloading was interrupted
        q = _read(_queue_path(install_dir), {}) or {}
        for it in q.get('items', []):
            if it['state'] == 'downloading':
                it['state'] = 'pending'
        _write(_queue_path(install_dir), q)
    while True:
        with _locked(install_dir):
            q = _read(_queue_path(install_dir), {}) or {}
            if q.get('cancelled'):
                _write_card(card_path(install_dir), snapshot(q))
                return 'cancelled'
            item = next((it for it in sorted(q.get('items', []), key=_sort_key) if it['state'] == 'pending'), None)
            if item is None:
                _write_card(card_path(install_dir), snapshot(q))
                return 'done'
            item['state'] = 'downloading'
            item.pop('error', None)
            _write(_queue_path(install_dir), q)
            _write_card(card_path(install_dir), snapshot(q, live))
            root, key = q['models_root'], item['key']
        target = safe_target(root, item['folder'], item['name'])
        last = {'t': 0.0, 'b': None, 'tb': time.time()}

        def on_bytes(done, size, key=key):
            now = time.time()
            if last['b'] is None:
                last['b'], last['tb'] = done, now
            if now - last['t'] < WRITE_EVERY_S:
                return
            if now - last['tb'] >= 1.0:
                rate = (done - last['b']) / (now - last['tb'])
                live['speed_bps'] = rate if live['speed_bps'] is None else 0.7 * live['speed_bps'] + 0.3 * rate
                last['b'], last['tb'] = done, now
            last['t'] = now
            try:
                with _locked(install_dir, timeout=2):
                    q2 = _read(_queue_path(install_dir), {}) or {}
                    for it in q2.get('items', []):
                        if it['key'] == key:
                            it['bytes'] = done
                            if size and not it.get('size_bytes'):
                                it['size_bytes'] = size
                    _write(_queue_path(install_dir), q2)
                    _write_card(card_path(install_dir), snapshot(q2, live))
            except (TimeoutError, OSError):
                pass

        error = None
        for attempt in range(RETRIES):
            try:
                _fetch(item, target, on_bytes)
                error = None
                break
            except Exception as e:  # network hiccup: resume from the .part file
                error = f'{type(e).__name__}: {e}'
                time.sleep(min(30, 2 ** attempt))
        with _locked(install_dir):
            q = _read(_queue_path(install_dir), {}) or {}
            for it in q.get('items', []):
                if it['key'] == key:
                    if error:
                        it.update(state='error', error=error)
                    else:
                        got = target.stat().st_size
                        it.update(state='done', bytes=got, size_bytes=it.get('size_bytes') or got)
            _write(_queue_path(install_dir), q)
            _write_card(card_path(install_dir), snapshot(q, live))


# ---------------------------------------------------------------- node packs (ComfyUI-Manager queue)
NODES_DONE_NOTE = 'Node packs installed. Next: comfy_setup action=restart (never the Manager\'s Apply Changes)'


def _pack_rows(packs) -> list[dict]:
    """[{'id', 'name'}] from dicts, 'id' strings or 'id::name' strings (worker command line)."""
    rows = []
    for p in packs or []:
        if isinstance(p, dict):
            pid = str(p.get('id') or p.get('name') or '')
            rows.append({'id': pid, 'name': str(p.get('name') or pid)})
        else:
            pid, _, name = str(p).partition('::')
            rows.append({'id': pid, 'name': name or pid})
    return [r for r in rows if r['id']]


def _http_json(url: str, path: str, payload=None, timeout: float = 10):
    """GET (payload None) or JSON POST. Manager rejects form content types, so a POST always sends JSON."""
    data = None if payload is None else json.dumps(payload).encode('utf-8')
    req = request.Request(url.rstrip('/') + path, data=data,
                          headers={'Content-Type': 'application/json'} if data is not None else {})
    with request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
    try:
        return json.loads(raw) if raw else {}
    except ValueError:
        return {}


def installed_packs(url: str) -> set | None:
    """Registry ids (and folder keys) ComfyUI-Manager reports as installed+enabled; None when it cannot tell."""
    try:
        d = _http_json(url, '/v2/customnode/installed')
    except Exception:
        return None
    if not isinstance(d, dict):
        return None
    out = set()
    for key, v in d.items():
        if isinstance(v, dict) and v.get('enabled') is False:
            continue
        out.add(str(key).lower())
        for k in ('cnr_id', 'aux_id'):
            if isinstance(v, dict) and v.get(k):
                out.add(str(v[k]).lower())
    return out


def queue_pack_installs(url: str, packs, client_id: str = 'comfy-recipe') -> dict:
    """Queue registry packs in ComfyUI-Manager with the same payload as the frontend's Install All, then start its
    worker (the queue never runs by itself: a queued-but-unstarted install stays pending forever)."""
    rows = _pack_rows(packs)
    have = installed_packs(url) or set()
    queued, already = [], []
    for r in rows:
        if r['id'].lower() in have:
            already.append(r['id'])
            continue
        _http_json(url, '/v2/manager/queue/task', {
            'kind': 'install', 'ui_id': f"comfy-recipe-{r['id']}-{int(time.time() * 1000)}", 'client_id': client_id,
            'params': {'id': r['id'], 'version': 'latest', 'selected_version': 'latest', 'repository': '',
                       'channel': 'default', 'mode': 'cache'}})
        queued.append(r['id'])
    status = _http_json(url, '/v2/manager/queue/status')
    if queued or (isinstance(status, dict) and int(status.get('pending_count') or 0)):
        _http_json(url, '/v2/manager/queue/start', {})
    return {'queued': queued, 'already_installed': already}


REGISTRY_NOT_READY = ('Cannot resolve install target', 'is not a CNR node')
REGISTRY_WAIT_NOTE = "Waiting for ComfyUI-Manager's registry list (first start after install), then retrying"


def registry_not_ready(url: str, ids) -> list[str]:
    """Pack ids whose LATEST Manager result is 'not a CNR node': the registry list is not loaded yet. On a fresh
    install Manager fetches it in the background for ~10-60 s after startup; installs queued before that fail."""
    try:
        hist = (_http_json(url, '/v2/manager/queue/history') or {}).get('history') or {}
    except Exception:
        return []
    latest = {}
    for item in hist.values():
        pid = str(((item or {}).get('params') or {}).get('id') or '').lower()
        if pid and (pid not in latest or str(item.get('timestamp')) > str(latest[pid].get('timestamp'))):
            latest[pid] = item
    wanted = {str(i).lower() for i in ids}
    return [pid for pid, item in latest.items()
            if pid in wanted and any(t in str(item.get('result')) for t in REGISTRY_NOT_READY)]


def _nodes_card(rows: list[dict], have: set | None, state: str, started: float, **extra) -> dict:
    states = {r['name']: ('done' if have is not None and r['id'].lower() in have else
                          'error' if state in ('done', 'error') else 'pending') for r in rows}
    done = sum(v == 'done' for v in states.values())
    total = len(rows)
    card = {'kind': 'nodes', 'title': 'Installing node packs', 'state': state, 'packs': [r['name'] for r in rows],
            'pack_ids': [r['id'] for r in rows], 'pack_states': states, 'done': done, 'total': total,
            'percent': round(100 * done / total, 1) if total else 0.0, 'started_at': started, 'updated_at': time.time()}
    card.update(extra)
    return card


def watch_nodes(install_dir, url: str, packs=None, poll: float = 1.0,
                idle_exit_s: float = 8.0, start_timeout_s: float = 600.0, max_loops: int | None = None,
                queued: bool = False, registry_wait_s: float = 300.0, retry_pause_s: float = 10.0) -> str:
    """Mirror ComfyUI-Manager's install queue into nodes.json. Per-pack state comes from Manager's installed list,
    so a pack that failed (or was never queued) shows as failed instead of a ticked row. queued=True: the plugin
    queued the installs itself, so a queue that is already idle means finished, not 'not started yet'."""
    path = card_path(install_dir, 'nodes')
    rows = _pack_rows(packs)
    started, seen, idle_since, loops = time.time(), queued, None, 0
    have = installed_packs(url)
    _write(path, _nodes_card(rows, have, 'pending', started))
    while max_loops is None or loops < max_loops:
        loops += 1
        try:
            s = _http_json(url, '/v2/manager/queue/status', timeout=5)
            busy = bool(s.get('is_processing')) or int(s.get('total_count') or 0) > 0
            have = installed_packs(url)
            all_in = bool(rows) and have is not None and all(r['id'].lower() in have for r in rows)
            if busy:
                seen, idle_since = True, None
                _write(path, _nodes_card(rows, have, 'running', started))
            elif seen or all_in:
                idle_since = idle_since or time.time()
                if all_in or time.time() - idle_since >= idle_exit_s:
                    if have is None or all_in:
                        _write(path, _nodes_card(rows, have, 'done', started, note=NODES_DONE_NOTE))
                        return 'done'
                    absent = [r for r in rows if r['id'].lower() not in have]
                    retry = set(registry_not_ready(url, [r['id'] for r in absent])) if queued else set()
                    if retry and time.time() - started < registry_wait_s:
                        _write(path, _nodes_card(rows, have, 'running', started, note=REGISTRY_WAIT_NOTE))
                        time.sleep(retry_pause_s)
                        queue_pack_installs(url, [r for r in absent if r['id'].lower() in retry])
                        idle_since = None
                        continue
                    missing = [r['name'] for r in absent]
                    _write(path, _nodes_card(rows, have, 'error', started,
                                             error='Not installed: ' + ', '.join(missing),
                                             note='Some packs did not install: retry comfy_downloads action=install_nodes'))
                    return 'error'
                _write(path, _nodes_card(rows, have, 'running', started))
            elif time.time() - started > start_timeout_s:
                _write(path, _nodes_card(rows, have, 'idle', started, note='No node-pack install was started'))
                return 'never started'
            else:
                _write(path, _nodes_card(rows, have, 'pending', started))
        except Exception as e:
            card = _read(path, {}) or {}
            card.update(error=f'{type(e).__name__}: {e}', updated_at=time.time())
            _write(path, card)
        time.sleep(poll)
    return 'max loops'


def start_nodes_watch(install_dir, url: str, packs=None, queued: bool = False) -> dict:
    d = progress_dir(install_dir)
    d.mkdir(parents=True, exist_ok=True)
    rows = _pack_rows(packs)
    w = _read(d / 'nodes-worker.json', {}) or {}
    if installer._pid_alive(w.get('pid'), _marker(install_dir, 'nodes')):
        return {'pid': w['pid'], 'new': False, 'progress_card': 'MEDIA:' + str(card_path(install_dir, 'nodes'))}
    _write(card_path(install_dir, 'nodes'), _nodes_card(rows, None, 'pending', time.time()))
    args = [installer._host_python(), str(Path(__file__).resolve()), 'nodes', Path(install_dir).resolve().as_posix(),
            '--url', url] + [a for r in rows for a in ('--pack', f"{r['id']}::{r['name']}")] + (['--queued'] if queued else [])
    p = installer._detached(args, d / 'nodes-worker.out', cwd=str(d))
    _write(d / 'nodes-worker.json', {'pid': p.pid, 'started_at': time.time()})
    return {'pid': p.pid, 'new': True, 'progress_card': 'MEDIA:' + str(card_path(install_dir, 'nodes'))}


def nodes_status(install_dir, wait_s: int = 0) -> dict:
    """Read the node-pack card; with wait_s, block until it is done/error/idle (or the time is up)."""
    card = card_path(install_dir, 'nodes')
    deadline = time.time() + max(0, min(int(wait_s or 0), 900))
    while True:
        data = _read(card, {}) or {'state': 'idle'}
        if data.get('state') in ('done', 'error', 'idle') or time.time() >= deadline:
            return dict(data, progress_card='MEDIA:' + str(card))
        time.sleep(2)


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['run', 'nodes'])
    ap.add_argument('dir')
    ap.add_argument('--url')
    ap.add_argument('--pack', action='append')
    ap.add_argument('--queued', action='store_true')
    a = ap.parse_args()
    if a.cmd == 'run':
        print(time.strftime('%Y-%m-%d %H:%M:%S'), 'downloads', run(Path(a.dir)), flush=True)
    else:
        print(time.strftime('%Y-%m-%d %H:%M:%S'), 'nodes', watch_nodes(Path(a.dir), a.url, a.pack, queued=a.queued), flush=True)

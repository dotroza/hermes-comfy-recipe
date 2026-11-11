"""Small transactional onboarding records. Never installs, downloads or queues a job."""
from __future__ import annotations

from contextlib import contextmanager
import json
import hashlib
from pathlib import Path
import sqlite3
import time
import uuid

VERSION = 1
TOTAL_STEPS = 4
# The four tutorial steps; each one runs one bundled Local Recipe workflow visibly in the window.
STEPS = {
    1: {'id': 'first-image', 'title': 'Generate your first image', 'workflow_id': 'qwen-image-2-1-t2i',
        'awaiting': 'awaiting_description', 'media': 'image'},
    2: {'id': 'modify-image', 'title': 'Modify an image or create a reference sheet',
        'workflow_id': 'qwen-image-2-1-i2i', 'awaiting': 'awaiting_images', 'media': 'image'},
    3: {'id': 'first-video', 'title': 'Create your first video', 'workflow_id': 'minimax-h3-r2v-mix',
        'awaiting': 'awaiting_action', 'media': 'video'},
    4: {'id': 'add-sound', 'title': 'Add sound to your video', 'workflow_id': 'ace-step1-5-xl-base',
        'awaiting': 'awaiting_sound', 'media': 'audio'},
}
WAITING = tuple(s['awaiting'] for s in STEPS.values())
INTRO = ('Let’s create your first image: a person, a pet, an object or a place. Describe it here in the chat—who or '
         'what it is, where, a style, or just an idea. I’ll turn it into a prompt and make it in the ComfyUI window. '
         'You can say “skip tutorial” at any time.')
INTRO_2 = ('Now let’s modify an image or turn it into a reference sheet—several views of the same subject on one '
           'page, which keeps it consistent in the video of the next step. Use the image you just made, or attach '
           'one or several images here (the first one is the image to edit, the others are references), and tell '
           'me what to change—for example “make it night time”—or say “make a reference sheet”. I’ll run it in the '
           'image-edit workflow in the ComfyUI window. You can say “skip tutorial” at any time.')
INTRO_3 = ('Let’s make your first video from your image and its reference sheet (if you don’t have a sheet yet, I’ll '
           'make it first). Describe the action: what happens, how the subject moves, how the camera moves. You can '
           'also attach a short reference video (a few seconds) for the motion. I’ll run it in the video workflow '
           'in the ComfyUI window. You can say “skip tutorial” at any time.')
INTRO_4 = ('Last step: let’s add sound to your video. Describe the music or sound you want—style, mood, instruments, '
           'tempo. I’ll generate it in the audio workflow in the ComfyUI window, then mix it under your video. '
           'You can say “skip tutorial” at any time.')
INTROS = {1: INTRO, 2: INTRO_2, 3: INTRO_3, 4: INTRO_4}


def heading(step: int) -> str:
    return f"Tutorial (step {step}/{TOTAL_STEPS}): {STEPS[step]['title']}"


def _step_of(tutorial: dict) -> int:
    step = tutorial.get('step', 1)
    return step if step in STEPS else 1


def _validate(install_id, session_id):
    if not isinstance(install_id, str) or str(uuid.UUID(install_id)) != install_id:
        raise ValueError('Invalid installation identity')
    if not isinstance(session_id, str) or not session_id.strip() or len(session_id) > 512:
        raise ValueError('A trusted calling-session identity is required')


@contextmanager
def _db(data_dir):
    root = Path(data_dir)
    root.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(root / 'onboarding.sqlite3', timeout=10)
    try:
        db.execute('CREATE TABLE IF NOT EXISTS installs (id TEXT PRIMARY KEY, record TEXT NOT NULL)')
        db.execute('CREATE TABLE IF NOT EXISTS sessions (install_id TEXT, session_id TEXT, record TEXT NOT NULL, PRIMARY KEY(install_id, session_id))')
        db.commit()
        db.execute('BEGIN IMMEDIATE')
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _decode(raw):
    record = json.loads(raw)
    if not isinstance(record, dict) or record.get('schema_version') != VERSION:
        raise ValueError('Unsupported onboarding record; use explicit tutorial replay after recovery')
    return record


@contextmanager
def _records(data_dir, install_id, session_id, manifest=None):
    _validate(install_id, session_id)
    with _db(data_dir) as db:
        raw = db.execute('SELECT record FROM installs WHERE id=?', (install_id,)).fetchone()
        if raw:
            install = _decode(raw[0])
        elif manifest is not None:
            install = {'schema_version': VERSION, 'install_id': install_id, 'first_session_id': session_id,
                       'fresh': manifest.get('onboarding_version') == VERSION,
                       'setup_choices': {'nodes': 'unanswered', 'models': 'unanswered'}}
        else:
            raise ValueError('Read onboarding status before changing preferences')
        raw = db.execute('SELECT record FROM sessions WHERE install_id=? AND session_id=?', (install_id, session_id)).fetchone()
        session = _decode(raw[0]) if raw else {'schema_version': VERSION, 'replay': False,
                                               'tutorial': {'id': 'first-image', 'state': 'not_offered'}}
        yield install, session
        db.execute('INSERT OR REPLACE INTO installs VALUES (?,?)', (install_id, json.dumps(install)))
        db.execute('INSERT OR REPLACE INTO sessions VALUES (?,?,?)', (install_id, session_id, json.dumps(session)))


def _view(install, session, session_id):
    state = session['tutorial']['state']
    first = install['fresh'] and install['first_session_id'] == session_id
    choices = install['setup_choices']
    if state in ('completed', 'skipped'):
        step = 'ordinary'
    elif session['replay'] or (first and state != 'not_offered'):
        step = 'tutorial'
    elif first and 'unanswered' in choices.values():
        step = 'setup_choices'
    elif first:
        step = 'tutorial'
    else:
        step = 'ordinary'
    n = _step_of(session['tutorial'])
    return {'install_id': install['install_id'], 'first_session_id': install['first_session_id'],
            'setup_choices': dict(choices), 'tutorial': dict(session['tutorial'], step=n), 'next_step': step,
            'tutorial_step': n, 'tutorial_heading': heading(n)}


def status(data_dir: Path, manifest: dict, session_id: str) -> dict:
    ident = manifest.get('install_id')
    _validate(ident, session_id)
    try:
        with _records(data_dir, ident, session_id, manifest) as (install, session):
            return _view(install, session, session_id)
    except (ValueError, sqlite3.DatabaseError, KeyError, TypeError) as exc:
        return {'install_id': ident, 'next_step': 'recovery',
                'error': str(exc), 'instruction': 'Onboarding state is unavailable; no installation or download consent is assumed. Preserve the record; ask for recovery.'}


def preferences(data_dir: Path, install_id: str, session_id: str, *, nodes: str, models: str) -> dict:
    if nodes not in ('now', 'on_use') or models not in ('now', 'on_use'):
        raise ValueError('Choose now or on_use independently for nodes and models')
    with _records(data_dir, install_id, session_id) as (install, session):
        if install['first_session_id'] != session_id:
            raise ValueError('Another session owns the post-install choices')
        install['setup_choices'] = {'nodes': nodes, 'models': models}
        return _view(install, session, session_id)


def tutorial(data_dir: Path, manifest: dict, session_id: str, *, replay: bool = False, step: int = 1) -> dict:
    """Start (or restart) a tutorial step. Step 1 is offered automatically in the first session; any step can be
    requested explicitly (replay=True) in any session, e.g. step 2 after step 1 or after coming back to the tutorial."""
    if step not in STEPS:
        raise ValueError(f'Tutorial step {step} is not available yet; steps 1-{max(STEPS)} exist')
    ident = manifest['install_id']
    with _records(data_dir, ident, session_id, manifest) as (install, session):
        first = install['fresh'] and install['first_session_id'] == session_id
        explicit = replay or step != 1
        if not explicit and not first and not session['replay']:
            raise ValueError('Use explicit tutorial replay in a returning session')
        current = session['tutorial']
        if explicit or current['state'] == 'not_offered':
            if not (current.get('state') in ('in_progress',) + WAITING and _step_of(current) == step and not replay):
                session['tutorial'] = {'id': STEPS[step]['id'], 'step': step, 'state': STEPS[step]['awaiting']}
        if explicit:
            session['replay'] = True
        return dict(_view(install, session, session_id), introduction=INTROS[step])


def _backend_key(inst):
    return {'url': inst['url'].rstrip('/'),
            'root': str(Path(inst['root']).resolve()) if inst.get('root') else None}


def begin_run(data_dir, install_id, session_id, inst, workflow_id, expected_prompt=None, workflow_path=None):
    from . import comfy_client as cc
    baseline = cc.get_json(inst['url'], '/history?max_items=100')
    if not isinstance(baseline, dict):
        raise ValueError('Cannot establish tutorial history baseline')
    with _records(data_dir, install_id, session_id) as (install, session):
        current = session['tutorial']
        if current['state'] not in WAITING + ('in_progress',):
            raise ValueError('Start the tutorial before preparing a run')
        n = _step_of(current)
        session['tutorial'] = {'id': STEPS[n]['id'], 'step': n, 'state': 'in_progress',
                               'workflow_id': workflow_id, 'workflow_path': workflow_path, 'backend': _backend_key(inst),
                               'started_after_ms': int(time.time() * 1000),
                               'baseline_prompt_ids': list(baseline),
                               'prompt_hash': hashlib.sha256(expected_prompt.encode('utf-8')).hexdigest() if expected_prompt else None}
        return _view(install, session, session_id)


_MEDIA_KEYS = {'image': ('images',), 'video': ('images', 'gifs', 'videos', 'video'), 'audio': ('audio', 'audios')}


def media_kind(raw: bytes) -> str | None:
    """Image / video / audio from the file signature (never from the file name)."""
    if raw.startswith(b'\x89PNG\r\n\x1a\n') or raw.startswith(b'\xff\xd8\xff') or \
            raw.startswith(b'RIFF') and raw[8:12] == b'WEBP':
        return 'image'
    if raw[4:8] == b'ftyp' or raw.startswith(b'\x1a\x45\xdf\xa3'):
        return 'video'
    if raw.startswith(b'ID3') or raw[:2] in (b'\xff\xfb', b'\xff\xf3', b'\xff\xf2') or raw.startswith(b'fLaC') or \
            raw.startswith(b'OggS') or raw.startswith(b'RIFF') and raw[8:12] == b'WAVE':
        return 'audio'
    return None


def verify_image_run(inst: dict, prompt_id: str, *, expected_workflow_id: str,
                     started_after_ms: int, baseline_prompt_ids: set[str], expected_prompt_hash: str | None = None,
                     media: str = 'image') -> dict:
    from . import comfy_client as cc
    if not prompt_id or prompt_id == 'latest' or prompt_id in baseline_prompt_ids:
        raise ValueError('Use the explicit new prompt id from the visible tutorial run')
    h = cc.history(inst['url'], prompt_id)
    if not h or not h.get('status', {}).get('completed') or h['status'].get('status_str') != 'success':
        raise ValueError('Tutorial run is not a successful completed job')
    try:
        prompt = h['prompt']
        if prompt[1] != prompt_id:
            raise ValueError('History prompt identity mismatch')
        extra = prompt[3]
        workflow = extra['extra_pnginfo']['workflow']
        if workflow.get('id') != expected_workflow_id or str(extra.get('client_id', '')).startswith('hermes-comfy-recipe'):
            raise ValueError('Not the expected workflow run queued in the window')
        if expected_prompt_hash:
            strings = [value for node in prompt[2].values() for value in node.get('inputs', {}).values() if isinstance(value, str)]
            if not any(hashlib.sha256(value.encode('utf-8')).hexdigest() == expected_prompt_hash for value in strings):
                raise ValueError('Another image prompt ran on the same workflow; not this tutorial run')
        messages = h['status']['messages']
        start = next(m[1]['timestamp'] for m in messages if m[0] == 'execution_start')
        finish = next(m[1]['timestamp'] for m in messages if m[0] == 'execution_success')
        if not isinstance(start, (int, float)) or start < started_after_ms or finish < start:
            raise ValueError('Execution predates this tutorial run')
        cached = {str(n) for m in messages if m[0] == 'execution_cached' for n in m[1].get('nodes', [])}
        samplers = {str(n) for n, row in prompt[2].items() if row.get('class_type') in ('KSampler', 'KSamplerAdvanced', 'SamplerCustom', 'SamplerCustomAdvanced')}
        if not samplers or samplers <= cached:
            raise ValueError('No fresh sampling: cached jobs do not complete the tutorial')
        files = [it for out in h['outputs'].values() for key in _MEDIA_KEYS[media]
                 for it in (out.get(key) or []) if isinstance(it, dict) and it.get('type') == 'output']
        if not files:
            raise ValueError(f'No saved {media} output')
        for item in files:
            raw = cc.view_bytes(inst['url'], item['filename'], item.get('subfolder', ''), item['type'])
            if media_kind(raw[:64]) == media:
                return {'prompt_id': prompt_id, 'workflow_id': expected_workflow_id, 'finished_ms': finish,
                        'media': media, 'output': item, 'image': item}
        raise ValueError(f'{media.capitalize()} output could not be verified')
    except (KeyError, TypeError, IndexError, StopIteration) as exc:
        raise ValueError('Missing or malformed tutorial execution evidence') from exc


def complete(data_dir, install_id, session_id, inst, prompt_id):
    # Copy the claim under lock; network reads happen outside the transaction.
    with _records(data_dir, install_id, session_id) as (install, session):
        claim = dict(session['tutorial'])
        if claim.get('state') in ('in_progress', 'completed') and claim.get('backend') != _backend_key(inst):
            raise ValueError('Tutorial backend changed since preparation; return to that backend or prepare a new visible run')
        if claim.get('state') == 'completed' and claim.get('prompt_id') == prompt_id:
            return _view(install, session, session_id)
        if claim.get('state') != 'in_progress':
            raise ValueError('No prepared tutorial run in this session')
    proof = verify_image_run(inst, prompt_id, expected_workflow_id=claim['workflow_id'],
                             started_after_ms=claim['started_after_ms'],
                             baseline_prompt_ids=set(claim['baseline_prompt_ids']), expected_prompt_hash=claim.get('prompt_hash'),
                             media=STEPS[_step_of(claim)].get('media', 'image'))
    with _records(data_dir, install_id, session_id) as (install, session):
        if session['tutorial'] != claim:
            raise ValueError('Tutorial changed while verifying; retry against the current lesson')
        n = _step_of(claim)
        session['tutorial'] = {'id': STEPS[n]['id'], 'step': n, 'state': 'completed', 'prompt_id': proof['prompt_id'],
                               'backend': claim['backend'], 'workflow_path': claim.get('workflow_path')}
        return _view(install, session, session_id)


def has_tutorial(data_dir, session_id):
    if not session_id or not (Path(data_dir) / 'onboarding.sqlite3').exists():
        return False
    try:
        with _db(data_dir) as db:
            rows = db.execute('SELECT record FROM sessions WHERE session_id=?', (session_id,)).fetchall()
            return any(_decode(row[0])['tutorial']['state'] in WAITING + ('in_progress',) for row in rows)
    except (ValueError, sqlite3.DatabaseError, KeyError, TypeError):
        return False


def skip(data_dir: Path, install_id: str, session_id: str) -> dict:
    with _records(data_dir, install_id, session_id) as (install, session):
        if session['tutorial']['state'] == 'not_offered' and install['first_session_id'] != session_id:
            raise ValueError('No tutorial is active in this session')
        n = _step_of(session['tutorial'])
        session['tutorial'] = {'id': STEPS[n]['id'], 'step': n, 'state': 'skipped'}
        return _view(install, session, session_id)

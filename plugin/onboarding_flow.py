"""Adapter between onboarding records, read-only readiness and agent instructions."""
from __future__ import annotations
import json
import re
import uuid
from pathlib import Path
from . import core, dependencies, download_flow, installer, library, onboarding

CARD_RULE = ('When a result carries progress_card, put that exact MEDIA:<path> line ONCE, alone on its own line, in your '
             'reply: the desktop app turns it into a live progress card (and a status-bar chip); never repeat it per poll. ')
SETUP = (
    'POST-INSTALL SETUP (before the ordinary question). Call comfy_onboarding action=status. '
    'Use ONE clarify form with independent questions. Nodes: install missing node packs now (recommended) vs on use. '
    'Models: (1) "Download on use (recommended): each tutorial step downloads its own models when you reach it; other '
    'workflows download theirs when you use them (I ask first)" vs (2) "Download everything now (<verified total GB>): '
    'tutorial step 1 first, then step 2, then the rest - the tutorial starts as soon as step 1 is ready". '
    'Deduplicate shared files. If size_complete=false, say at least the known GB plus the unknown count; inventory '
    'unknown is not missing. Skip categories already available (record on_use for a skipped empty category). '
    'Explain third-party Python and the managed restart required for node packs. '
    'List missing media, executable requirements, external-service checks and readiness warnings with their workflow names before consent: node/model installs do not supply author-specific inputs. '
    'List blockers and obtain SEPARATE settings consent in the same form when needed. '
    'After submitted answers call comfy_onboarding action=preferences nodes=now|on_use models=now|on_use. '
    + CARD_RULE +
    'models=now queues every download itself (tutorial step 1 first): do not click downloads in the window. '
    'Node packs now: call comfy_downloads action=watch_nodes packs=[pack names] BEFORE clicking Install All visibly, '
    'post its card, then finish the visible install/restart recipe and recheck. Preferences are not proof of installation. '
    'Then call comfy_onboarding action=tutorial at once (step 1 may start while other files download); do not ask What should I do first yet.'
)
LESSON = (
    'TUTORIAL STEP 1/6. Load skill_view("comfy-recipe:first-image-tutorial") and skill_view("comfy-recipe:qwen-image-2-1-prompting"). '
    'Unless this turn already has its result, call comfy_onboarding action=tutorial step=1 once first (idempotent: it '
    'keeps the lesson, returns readiness and queues this step\'s downloads). '
    'Start your reply with the line "### 🎓 Tutorial (step 1/6): Generate your first image" (tutorial_heading), '
    'then open Comfy Recipe/RCP_qwen_image_2_1_t2i.json visibly in the pane so the user sees the text-to-image workflow. '
    + CARD_RULE +
    'Prompt writing is by Hermes; leave refine_prompt off. '
    'If awaiting_description, ask the user to describe their first image in THIS chat, unless their current message '
    'already describes it; they may type while files download. Before a visible Run, if downloads.group tutorial-1 is '
    'not done, call comfy_downloads action=wait group=tutorial-1 wait_s=300 (one short line per call), then refresh '
    'the Missing Models panel. Then call comfy_onboarding action=tutorial begin_run=true. '
    'Include prompt=<the exact enhanced text entered in the window> and workflow_path=<the selected saved path, including any version suffix> in begin_run; only the prompt hash is stored. '
    'After Run use comfy_result prompt_id=latest, verify the corresponding image visually, then '
    'comfy_onboarding action=complete prompt_id=<the explicit corresponding prompt id>. '
    'Errors/cached/unrelated jobs are not completion. On success follow the completion instruction (step 2 offer). '
    'Steps 3-6 are not available yet. Asking for the tutorial in the chat replays it.'
)
LESSON_2 = (
    'TUTORIAL STEP 2/6. Load skill_view("comfy-recipe:modify-image-tutorial") and '
    'skill_view("comfy-recipe:qwen-image-2-1-editing") and follow them. '
    'Unless this turn already has its result, call comfy_onboarding action=tutorial step=2 once first (idempotent). '
    'Start your reply with the line "### 🎓 Tutorial (step 2/6): Modify an image" (tutorial_heading), '
    'then switch the pane to the Comfy Recipe/RCP_qwen_image_2_1_i2i.json tab visibly (Workflows sidebar). '
    + CARD_RULE +
    'Tell the user they can attach ONE OR SEVERAL images to this chat and say what to change (the first image is '
    'edited, the others are references), unless their current message already does. If awaiting_images, wait for them. '
    'Before Run: if downloads.group tutorial-2 is not done, comfy_downloads action=wait group=tutorial-2 wait_s=300; '
    'settings (Nodes 2.0) need explicit consent; models_without_url block the run until supplied. Then '
    'comfy_onboarding action=tutorial step=2 begin_run=true prompt=<exact edit text entered> workflow_path=<selected i2i path>, '
    'click Run visibly, comfy_result prompt_id=latest, compare output with the inputs visually, then '
    'comfy_onboarding action=complete prompt_id=<explicit id>. Steps 3-6 are not available yet.'
)
LESSONS = {1: LESSON, 2: LESSON_2}
NEXT_AFTER_1 = (
    'Show the verified image (MEDIA:<output path>) and a short timing line. Then ONE clarify call with ONE question: '
    '"What next? Continue the tutorial, or type a description to generate another image with the same workflow." '
    'with the single choice "Tutorial (step 2/6): Modify an image" (its Other row is the free-text box for a new '
    'description). Step 2 chosen -> comfy_onboarding action=tutorial step=2. A typed description -> write the prompt, '
    'type it in the text-to-image tab and Run visibly again (no begin_run needed), show the image, then offer the '
    'same choice again. Do not ask the ordinary question yet.'
)
NEXT_AFTER_2 = ('Show the verified edited image (MEDIA:<output path>) with a one-line summary of the change, say '
                'the other four tutorial steps are coming later, then ask: What would you like to do?')
SKIPPED = ('Tutorial skipped. Say in one line that they can come back to it any time by asking for the tutorial in '
           'this chat, and can bring their own workflows and ask to install their dependencies. '
           'Then ask: What would you like to do?')


def current():
    st = core._load_state()
    if st.get('setup') != 'managed':
        raise ValueError('This onboarding flow is for Comfy Recipe’s own installation')
    root = core._managed_dir(st)
    m = installer.manifest(root) if root else None
    if not m:
        raise ValueError('Finish the Comfy Recipe installation before starting its tutorial')
    m = dict(m)
    if not m.get('install_id'):
        # Older manifests always record installed_at; preserve its identity through moves.
        legacy_key = str(m.get('installed_at') or m.get('moved_from') or m.get('dir') or root)
        m['install_id'] = str(uuid.uuid5(uuid.NAMESPACE_URL, 'comfy-recipe/legacy/' + legacy_key))
    return m


def managed_backend():
    """Resolve from our manifest, never from a silently switched active backend."""
    m = current()
    inst = {'name': core.MANAGED_NAME, 'url': f"http://127.0.0.1:{int(m['port'])}",
            'root': m['comfyui_dir'], 'launcher': 'Comfy Recipe (own install)'}
    st = core._load_state()
    selected = (st.get('instances') or {}).get(core.MANAGED_NAME, {})
    if st.get('active') != core.MANAGED_NAME or (selected.get('url') and
            selected['url'].rstrip('/') != inst['url']):
        raise ValueError('Active instance/backend differs from the managed installation. '
                         'Open/switch explicitly to comfy-recipe before onboarding; no work was queued or installed.')
    if selected.get('root') and Path(selected['root']).resolve() != Path(inst['root']).resolve():
        raise ValueError('Active instance root differs from the managed backend; confirm the instance before onboarding')
    return inst


def _managed_target():
    """(progress folder, models root) of the managed install."""
    return Path(core._managed_dir()), Path(current()['comfyui_dir']) / 'models'


def reports(workflow_id=None):
    inst = managed_backend()
    catalog = library.load_catalog()
    entries = [e for e in catalog['workflows'] if workflow_id is None or e['id'] == workflow_id]
    if not entries:
        raise ValueError('Unknown bundled workflow')
    info = json.loads(core._object_info_path(inst, refresh=True).read_text(encoding='utf-8'))
    try:
        settings = core.cc.get_json(inst['url'], '/settings')
        if not isinstance(settings, dict):
            raise ValueError('Invalid settings inventory')
        error = None
    except Exception as exc:
        settings, error = None, str(exc)
    return [dependencies.check(inst, entry, library.load_asset(entry), info, settings, error) for entry in entries]


def _proposal(workflow_id=None):
    return dependencies.library_proposal(reports(workflow_id), size_of=dependencies.cached_size_lookup(core.DATA))


def step_downloads(step: int, models_choice: str | None) -> dict:
    """Readiness of one tutorial step's workflow; queue its missing files when the setup choice allows it
    ('now' queued them already - enqueue is idempotent; 'on_use' means: when the user reaches this step)."""
    wid = onboarding.STEPS[step]['workflow_id']
    group = f'tutorial-{step}'
    try:
        prop = _proposal(wid)
    except Exception as exc:
        return {'group': group, 'error': f'{type(exc).__name__}: {exc}'}
    out = {'group': group, 'workflow_id': wid, 'missing_models': [m['name'] for m in prop['models']],
           'download_gb': prop['download_gb'], 'models_without_url': prop['models_without_url'],
           'node_packs': prop['node_packs'], 'settings': prop['settings']}
    if prop['models'] and models_choice in ('now', 'on_use'):
        d, root = _managed_target()
        res = download_flow.queue(d, root, prop['models'])
        out.update(queued=True, progress_card=res['progress_card'],
                   state=next((g['state'] for g in res.get('groups', []) if g['id'] == group), res.get('state')))
    elif prop['models']:
        out.update(queued=False, consent_needed=True,
                   instruction=f'Ask once for these downloads ({prop["download_gb"]} GB), then '
                               f'comfy_downloads action=start workflow_ids=["{wid}"].')
    else:
        out.update(queued=False, state='done')
    return out


def context(session_id):
    if not session_id:
        return ''
    try:
        r = onboarding.status(core.DATA, current(), session_id)
    except ValueError:
        return ''
    if r['next_step'] == 'ordinary':
        return ''
    try:
        managed_backend()
    except ValueError as exc:
        return '[comfy-recipe onboarding] ' + str(exc)
    if r['next_step'] == 'setup_choices':
        instruction = SETUP
    elif r['next_step'] == 'tutorial':
        instruction = LESSONS[r.get('tutorial_step', 1)]
    else:
        instruction = r['instruction']
    return '[comfy-recipe onboarding] ' + json.dumps(r, ensure_ascii=False) + '\n' + instruction


def _working_copy_pattern(workflow_id: str) -> tuple[str, str]:
    entry = next(e for e in library.load_catalog()['workflows'] if e['id'] == workflow_id)
    stem = re.escape(Path(entry['file']).stem)
    return (re.escape(library.FOLDER) + '/' + stem + r'(?:-v\d+\.\d+\.\d+)?\.json',
            library.FOLDER + '/' + Path(entry['file']).name)


def _resume_step(tutorial: dict) -> tuple[int, bool]:
    """Where 'back to the tutorial' lands: the next step after a completed one, else the current step
    (restarted when it was skipped, finished or never offered)."""
    step = tutorial.get('step', 1)
    state = tutorial.get('state')
    if state == 'completed' and step + 1 in onboarding.STEPS:
        return step + 1, False
    return step, state in ('completed', 'skipped', 'not_offered')


def handle(params, session_id):
    if not isinstance(session_id, str) or not session_id.strip():
        raise ValueError('Trusted calling-session context is required')
    m = current()
    ident = m['install_id']
    action = params.get('action', 'status')
    inst = managed_backend()
    state = onboarding.status(core.DATA, m, session_id)
    if state['next_step'] == 'recovery':
        return state
    if action == 'status':
        if state['next_step'] == 'setup_choices' or params.get('workflow') or params.get('refresh') is True:
            rs = reports(params.get('workflow'))
            proposal = dependencies.library_proposal(rs, size_of=dependencies.cached_size_lookup(core.DATA))
            groups = download_flow.tutorial_keys()
            for row in proposal['models']:
                row['download_group'] = download_flow.group_for(row['folder'], row['name'], groups)
            state.update(proposal=proposal, instruction=(SETUP if state['next_step'] == 'setup_choices' else
                'Read-only readiness recheck. Ask consent for actual missing requirements not already approved; do approved work visibly, then resume the tutorial.'))
        return state
    if action == 'preferences':
        state = onboarding.preferences(core.DATA, ident, session_id, nodes=params.get('nodes'), models=params.get('models'))
        approved = [key for key in ('nodes', 'models') if state['setup_choices'][key] == 'now']
        result = dict(state, approved_categories=approved)
        if 'models' in approved:
            d, root = _managed_target()
            res = download_flow.queue(d, root, _proposal()['models'])
            result['downloads'] = {k: res.get(k) for k in ('state', 'progress_card', 'groups', 'total_bytes', 'files',
                                                           'models_without_url')}
        result['instruction'] = (
            (CARD_RULE + 'Models download in the background, tutorial step 1 first. ' if 'models' in approved else '')
            + ('Node packs (visibly): comfy_downloads action=watch_nodes packs=[names] first and post its card, then '
               'Install All, restart when idle, recheck. ' if 'nodes' in approved else '')
            + 'Settings need separate consent. Then call comfy_onboarding action=tutorial right away.')
        return result
    if action == 'tutorial':
        replay = params.get('replay') is True
        if params.get('resume'):
            step, replay = _resume_step(state['tutorial'])
        else:
            step = int(params.get('step') or state.get('tutorial_step') or 1)
        if step not in onboarding.STEPS:
            raise ValueError(f'Tutorial step {step} is not available yet (steps 1-{max(onboarding.STEPS)})')
        if params.get('begin_run'):
            if state['tutorial'].get('step', 1) != step:
                raise ValueError(f'Start tutorial step {step} (action=tutorial step={step}) before preparing its run')
            allowed, default = _working_copy_pattern(onboarding.STEPS[step]['workflow_id'])
            selected_path = params.get('workflow_path') or default
            if not isinstance(selected_path, str) or not re.fullmatch(allowed, selected_path):
                raise ValueError(f'Select the step {step} working copy ({default}) or its published versioned sibling')
            saved = core.cc.load_workflow(inst['url'], selected_path)
            if not isinstance(saved.get('id'), str) or not saved['id']:
                raise ValueError('The selected tutorial working copy has no workflow identity')
            if not isinstance(params.get('prompt'), str) or not params['prompt'].strip():
                raise ValueError('begin_run requires the exact enhanced prompt just entered visibly')
            return onboarding.begin_run(core.DATA, ident, session_id, inst, saved['id'], expected_prompt=params['prompt'], workflow_path=selected_path)
        state = onboarding.tutorial(core.DATA, m, session_id, replay=replay, step=step)
        if params.get('downloads', True) is False:  # hook/command path: records only, no network work
            return dict(state, instruction=LESSONS[step])
        return dict(state, downloads=step_downloads(step, state['setup_choices'].get('models')),
                    instruction=LESSONS[step])
    if action == 'skip':
        return dict(onboarding.skip(core.DATA, ident, session_id), instruction=SKIPPED)
    if action == 'complete':
        state = onboarding.complete(core.DATA, ident, session_id, inst, params.get('prompt_id'))
        step = state['tutorial'].get('step', 1)
        return dict(state, instruction=NEXT_AFTER_1 if step == 1 else NEXT_AFTER_2)
    raise ValueError('Unknown onboarding action')


def command(session_id, step: int = 1):
    handle({'action': 'tutorial', 'replay': step == 1, 'step': step, 'downloads': False}, session_id)
    return f"### 🎓 {onboarding.heading(step)}\n\n{onboarding.INTROS[step]}"


TUTORIAL_PHRASES = {'tutorial': {'replay': True, 'step': 1}, 'start tutorial': {'replay': True, 'step': 1},
                    'replay tutorial': {'replay': True, 'step': 1}, 'tutorial step 1': {'replay': True, 'step': 1},
                    'resume tutorial': {'resume': True}, 'back to the tutorial': {'resume': True},
                    'continue tutorial': {'resume': True}, 'continue the tutorial': {'resume': True},
                    'tutorial step 2': {'step': 2}, 'modify an image': {'step': 2},
                    'tutorial (step 2/6): modify an image': {'step': 2}}


def route(user_message, session_id, *, recipe_session=False):
    active = onboarding.has_tutorial(core.DATA, session_id)
    if not recipe_session and not active:
        return None
    message = str(user_message or '').strip().lower().rstrip('.!?')
    if message in TUTORIAL_PHRASES:
        handle(dict(TUTORIAL_PHRASES[message], action='tutorial', downloads=False), session_id)
    elif message in ('skip tutorial', 'skip the tutorial'):
        handle({'action': 'skip'}, session_id)
        return SKIPPED
    return context(session_id)

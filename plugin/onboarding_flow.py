"""Adapter between onboarding records, read-only readiness and agent instructions."""
from __future__ import annotations
import json
import re
import uuid
from pathlib import Path
from . import core, dependencies, download_flow, downloads, installer, library, media, onboarding

ASSETS = Path(__file__).resolve().parent / 'assets' / 'images'
# Bundled layout sheets: the grid/views a new reference sheet of that subject kind should follow.
REFERENCE_SHEETS = {'person': 'character_sheet.png', 'pet': 'pet_sheet.png', 'object': 'object_sheet.png',
                    'location': 'outdoor_sheet.png', 'indoor': 'indoor_sheet.png'}

CARD_RULE = ('When a result carries progress_card, put that exact MEDIA:<path> line ONCE, alone on its own line, in your '
             'reply: the desktop app turns it into a live progress card (and a status-bar chip); never repeat it per poll. ')
SETUP = (
    'POST-INSTALL SETUP (before the ordinary question). Call comfy_onboarding action=status. '
    'Keep the setup introduction to one short sentence, then use ONE clarify form with independent questions. '
    'Do not print an inventory, per-workflow caveat list, or an untested-execution disclaimer. Put only actionable '
    'blockers and consent disclosures briefly in the relevant question. '
    'Before the form, visibly select Local Recipe/RCPlocal_t2i_qwen_image_2-1.json (including when localhost restored '
    'an old installation\'s tab) and keep it selected; whenever the pane is reopened during setup, return to the text-to-image tab. '
    'Local Recipe contains local workflows; Cloud Recipe contains paid ComfyUI API nodes, requiring account authentication and credits, not local weights. '
    'Setup may copy cloud definitions but must never queue paid runs; obtain explicit per-run consent before using them. '
    'Nodes: install missing node packs now (recommended) vs on use. '
    'Models: (1) "Download on use (recommended): each tutorial step downloads its own models when you reach it; other '
    'workflows download theirs when you use them (I ask first)" vs (2) "Download everything now (<verified total GB>)". '
    'End the bulk-download choice at the closing size parenthesis; do not append download-order or tutorial commentary. '
    'Internally retain download priority: tutorial step 1, then steps 2, 3 and 4, then the rest. '
    'Deduplicate shared files. If size_complete=false, say at least the known GB plus the unknown count; inventory '
    'unknown is not missing. Skip categories already available (record on_use for a skipped empty category). '
    'Explain third-party Python and the managed restart required for node packs. '
    'Disclose actual missing media, executable requirements and external-service blockers with workflow names briefly '
    'in the relevant consent question, not as a separate preamble: node/model installs do not supply author-specific inputs. '
    'When proposal.settings is not empty, add a SEPARATE settings question: "Turn on <label> (recommended)" vs "Keep the '
    'classic look" (e.g. Nodes 2.0 = modern node design, needed for the image-compare slider). '
    'After submitted answers make ONE call: comfy_onboarding action=preferences nodes=now|on_use models=now|on_use '
    'settings=apply|skip. The plugin then does all approved work itself (node packs through ComfyUI-Manager, model '
    'downloads, settings) and returns the exact remaining steps in instruction: follow them in order. Never install '
    'packs in the Nodes Manager window, never search packs there, never click Apply Changes, never toggle settings by hand. '
    + CARD_RULE +
    'Then call comfy_onboarding action=tutorial (step 1 may start while other files download); do not ask What should I do first yet.'
)
LESSON = (
    'TUTORIAL STEP 1/4. Load skill_view("comfy-recipe:first-image-tutorial") and skill_view("comfy-recipe:qwen-image-2-1-prompting"). '
    'Unless this turn already has its result, call comfy_onboarding action=tutorial step=1 once first (idempotent: it '
    'keeps the lesson, returns readiness and queues this step\'s downloads). '
    'Start your reply with the line "### 🎓 Tutorial (step 1/4): Generate your first image" (tutorial_heading), '
    'then open Local Recipe/RCPlocal_t2i_qwen_image_2-1.json visibly in the pane so the user sees the text-to-image workflow. '
    + CARD_RULE +
    'The subject can be a person, a pet, an object or a place (outdoor location or indoor room); note which one: '
    'it picks the reference-sheet layout in steps 2-3. '
    'Use soft plugin refinement only (preserve the original idea, no invented scene details); refine_prompt on, 25 steps, Lightning LoRA strength 0. '
    'Finish this step\'s model readiness before asking for the image description: if tutorial-1 is downloading, '
    'call comfy_downloads action=wait group=tutorial-1 wait_s=300 until done (one short line per call; no page polling). '
    'On completion immediately refresh the Missing Models panel and verify with desktop_preview read that the '
    'selected t2i workflow no longer reports missing models; preserve prompts/tabs, do not reload the page. '
    'If awaiting_description, then ask the user to describe their first image in THIS chat, unless their current '
    'message already describes it. Before a visible Run recheck readiness if files or backend changed, then '
    'call comfy_onboarding action=tutorial begin_run=true. '
    'Include prompt=<the exact enhanced text entered in the window> and workflow_path=<the selected saved path, including any version suffix> in begin_run; only the prompt hash is stored. '
    'After Run use comfy_result prompt_id=latest, verify the corresponding image visually, then '
    'comfy_onboarding action=complete prompt_id=<the explicit corresponding prompt id>. '
    'Errors/cached/unrelated jobs are not completion. On success follow the completion instruction (step 2 offer). '
    'The tutorial has 4 steps. Asking for the tutorial in the chat replays it.'
)
LESSON_2 = (
    'TUTORIAL STEP 2/4. Load skill_view("comfy-recipe:modify-image-tutorial") and '
    'skill_view("comfy-recipe:qwen-image-2-1-editing") and follow them. '
    'Unless this turn already has its result, call comfy_onboarding action=tutorial step=2 once first (idempotent). '
    'Start your reply with the line "### 🎓 Tutorial (step 2/4): Modify an image or create a reference sheet" (tutorial_heading), '
    'then switch the pane to the Local Recipe/RCPlocal_ti2i_qwen_image_2-1.json tab visibly. '
    + CARD_RULE +
    'Two paths. (a) Modify an image: explicit edit instruction plus preservation, refine_prompt off, 25 steps, Lightning '
    'LoRA strength 0. (b) Create a reference sheet of the step-1 subject: comfy_onboarding action=reference_sheet '
    'kind=<person|pet|object|location|indoor> copies the matching bundled layout sheet into input/; image_1 = the '
    'subject image, image_2 = that layout sheet (add and wire the second Load Image when the graph has one); '
    'same settings (layout fidelity). '
    'Tell the user they can use the step-1 image or attach ONE OR SEVERAL images to this chat and say what to change, '
    'or ask for a reference sheet, unless their current message already does. If awaiting_images, wait for them. '
    'Before Run: if downloads.group tutorial-2 is not done, comfy_downloads action=wait group=tutorial-2 wait_s=300; '
    'settings (Nodes 2.0) need explicit consent; after a yes call comfy_workflows action=apply_settings '
    'workflow=qwen-image-2-1-i2i, then desktop_preview close + open (never toggle it by hand); '
    'models_without_url block the run until supplied. Then '
    'comfy_onboarding action=tutorial step=2 begin_run=true prompt=<exact edit text entered> workflow_path=<selected i2i path>, '
    'click Run visibly, comfy_result prompt_id=latest, compare output with the inputs visually, then '
    'comfy_onboarding action=complete prompt_id=<explicit id>.'
)
LESSON_3 = (
    'TUTORIAL STEP 3/4. Load skill_view("comfy-recipe:first-video-tutorial") and follow it. '
    'Unless this turn already has its result, call comfy_onboarding action=tutorial step=3 once first (idempotent). '
    'Start your reply with the line "### 🎓 Tutorial (step 3/4): Create your first video" (tutorial_heading), '
    'then switch the pane to the Local Recipe/RCPlocal_r2v_video_minimax_h3.json tab visibly. '
    + CARD_RULE +
    'Inputs: first frame (<Picture 1>, Load Image #150) = the step-1/2 image; reference sheet (<Picture 3>, Load Image '
    '#165) = the subject\'s sheet. No sheet yet: make it first in the image-edit tab (comfy_onboarding '
    'action=reference_sheet kind=<subject kind>, then a visible run there), then come back. The user describes the '
    'action; an optional short reference video drives the motion and carries its sound (comfy_media convert to <= 73 '
    'frames). No reference video: bypass Load Video (#155) and Video Info (#157) in the window and set Float (Duration) '
    'to about 3 s yourself. If awaiting_action, ask for the action in THIS chat. Before Run: if downloads.group '
    'tutorial-3 is not done, comfy_downloads action=wait group=tutorial-3 wait_s=300. Then '
    'comfy_onboarding action=tutorial step=3 begin_run=true prompt=<exact prompt entered> workflow_path=<selected r2v path>, '
    'click Run visibly, comfy_result prompt_id=latest (contact sheet), check it visually, then '
    'comfy_onboarding action=complete prompt_id=<explicit id>.'
)
LESSON_4 = (
    'TUTORIAL STEP 4/4. Load skill_view("comfy-recipe:add-sound-tutorial") and follow it. '
    'Unless this turn already has its result, call comfy_onboarding action=tutorial step=4 once first (idempotent). '
    'Start your reply with the line "### 🎓 Tutorial (step 4/4): Add sound to your video" (tutorial_heading), '
    'then switch the pane to the Local Recipe/RCPlocal_audio_ace_step1-5_xl_base.json tab visibly. '
    + CARD_RULE +
    'The user describes the music or sound; type the tags and set Song Duration to the step-3 video length in the '
    'window. If awaiting_sound, ask for it in THIS chat. Before Run: if downloads.group tutorial-4 is not done, '
    'comfy_downloads action=wait group=tutorial-4 wait_s=300. Then comfy_onboarding action=tutorial step=4 begin_run=true '
    'prompt=<exact tags entered> workflow_path=<selected audio path>, click Run visibly, comfy_result prompt_id=latest, '
    'check the audio (duration, level), comfy_onboarding action=complete prompt_id=<explicit id>, then '
    'comfy_media action=mux path=<step-3 video> audio=<ACE output> (the music is mixed under the video\'s own sound) '
    'and show the mixed video.'
)
LESSONS = {1: LESSON, 2: LESSON_2, 3: LESSON_3, 4: LESSON_4}


def _offer(next_step: int, what: str) -> str:
    return (f'Then ONE clarify call with ONE question: "What next? Continue the tutorial, or {what}" with the single '
            f'choice "Tutorial (step {next_step}/4): {onboarding.STEPS[next_step]["title"]}" (its Other row is the '
            f'free-text box). Step {next_step} chosen -> comfy_onboarding action=tutorial step={next_step}. ')


_WAIT = ('After asking What next, stop: do not poll the page, call elements, or strobe while waiting for the user. '
         'Read-only title/status checks use desktop_preview read, not elements. Do not ask the ordinary question yet.')
NEXT_AFTER_1 = (
    'Show the verified image (MEDIA:<output path>) and a short timing line. '
    + _offer(2, 'type a description to generate another image with the same workflow.') +
    'A typed description -> write the prompt, type it in the text-to-image tab and Run visibly again (no begin_run '
    'needed), show the image, then offer the same choice again. ' + _WAIT)
NEXT_AFTER_2 = (
    'Show the verified image (MEDIA:<output path>) with a one-line summary of the change. '
    + _offer(3, 'describe another edit.') +
    'A typed edit -> run it visibly in the same tab, show it, then offer the same choice again. ' + _WAIT)
NEXT_AFTER_3 = (
    'Show the verified video (MEDIA:<output path>) with a one-line timing summary. '
    + _offer(4, 'describe another action for a new video.') +
    'A typed action -> run it visibly in the same tab, show it, then offer the same choice again. ' + _WAIT)
CAPABILITIES_OFFER = ('Say briefly that you can guide them through Comfy Recipe’s capabilities and give examples. '
                      'Examples: create or edit images, make reference sheets and videos, add sound, use their own '
                      'workflows, check dependencies, troubleshoot failed runs, and refine results. Invite them to '
                      'name a goal or ask for examples; do not dump a full feature inventory. Load a plugin skill only '
                      'when the user request matches its trigger, never all skill instructions at session start. ')
NEXT_AFTER_4 = ('Mux the sound onto the step-3 video (comfy_media action=mux), then show the final video with sound '
                '(MEDIA:<muxed path>). Say the tutorial is complete (4/4) and any step can be replayed by asking for '
                'it. ' + CAPABILITIES_OFFER + 'Then ask: What would you like to do?')
NEXT_AFTER = {1: NEXT_AFTER_1, 2: NEXT_AFTER_2, 3: NEXT_AFTER_3, 4: NEXT_AFTER_4}
SKIPPED = ('Tutorial skipped. Say in one line that they can come back to it any time by asking for the tutorial in '
           'this chat, and can bring their own workflows and ask to install their dependencies. ' +
           CAPABILITIES_OFFER + 'Then ask: What would you like to do?')


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
    inventory = {}  # One snapshot per report, never a process-wide readiness cache.
    packs = downloads.installed_packs(inst['url']) if any(
        (e.get('requirements') or {}).get('frontend_nodes') for e in entries) else None
    return [dependencies.check(inst, entry, library.load_asset(entry), info, settings, error,
                               model_inventory=inventory, installed_packs=packs) for entry in entries]


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
    folder = library.publication_folder(entry)
    return (re.escape(folder) + '/' + stem + r'(?:-v\d+\.\d+\.\d+)?\.json',
            folder + '/' + Path(entry['file']).name)


def _resume_step(tutorial: dict) -> tuple[int, bool]:
    """Where 'back to the tutorial' lands: the next step after a completed one, else the current step
    (restarted when it was skipped, finished or never offered)."""
    step = tutorial.get('step', 1)
    state = tutorial.get('state')
    if state == 'completed' and step + 1 in onboarding.STEPS:
        return step + 1, False
    return step, state in ('completed', 'skipped', 'not_offered')


def reference_sheet(kind) -> dict:
    """Copy the bundled layout sheet for this subject kind into the managed input/ folder (identical file reused,
    a different file never overwritten). Choosing it in the Load Image node stays a visible window action."""
    if kind not in REFERENCE_SHEETS:
        raise ValueError('kind must be one of: ' + ', '.join(REFERENCE_SHEETS))
    src = ASSETS / REFERENCE_SHEETS[kind]
    if not src.is_file():
        raise ValueError(f'Bundled reference sheet missing: assets/images/{REFERENCE_SHEETS[kind]}')
    copied = media.copy_to_input(src, Path(current()['comfyui_dir']) / 'input')
    return {'kind': kind, 'sheet': REFERENCE_SHEETS[kind], **copied,
            'instruction': (
                'Layout reference ready. If input_name was not in the picker before, desktop_preview close + open '
                'first. In the image-edit tab: image_1 = the subject image, image_2 = input_name (add and wire a '
                'second Load Image when the graph has only one; standing consent covers it). Prompt: make a '
                'reference sheet of the subject in <image1> with exactly the panel grid, views, framing and plain '
                'background of <image2>; take only the layout from <image2>, never its subject, colours or text. '
                'refine_prompt off, 25 steps, Lightning LoRA strength 0, resolution 1024.')}


def apply_preferences(inst: dict, choices: dict, settings_choice) -> dict:
    """Do the approved setup work in the plugin (no window clicks) and spell out the remaining steps in order."""
    approved = [key for key in ('nodes', 'models') if choices[key] == 'now']
    out = {'approved_categories': approved}
    proposal = _proposal() if approved or settings_choice == 'apply' else {}
    d, root = _managed_target()
    if 'models' in approved:
        res = download_flow.queue(d, root, proposal['models'])
        out['downloads'] = {k: res.get(k) for k in ('state', 'progress_card', 'groups', 'total_bytes', 'files',
                                                    'models_without_url')}
    nodes_running = False
    if 'nodes' in approved:
        out['nodes'] = download_flow.install_nodes(inst, d, proposal.get('node_packs') or None) \
            if proposal.get('node_packs') else {'state': 'done', 'queued': [], 'note': 'No missing node packs'}
        nodes_running = out['nodes'].get('state') == 'running'
    settings_done = False
    if settings_choice == 'apply' and proposal.get('settings'):
        out['settings'] = core.apply_settings(inst['url'], [{'id': s['id'], 'value': s['value']} for s in proposal['settings']])
        settings_done = bool(out['settings']['applied'])
    steps = []
    if out.get('downloads') or nodes_running:
        steps.append('Post each progress_card MEDIA line once (models and/or nodes), alone on its own line.')
    if 'models' in approved:
        steps.append('Models download in the background (tutorial step 1 first); do not click downloads in the window.')
    if nodes_running:
        steps += ['Do NOT open the Nodes Manager: the packs are already queued there by the plugin.',
                  'comfy_downloads action=nodes_status wait_s=300, repeated until state=done (one short line per call).',
                  'comfy_setup action=restart (one call; never the Manager\'s Apply Changes).']
    if nodes_running or settings_done:
        steps.append('desktop_preview action=close, then action=open with the same url, so the window loads the new '
                     'nodes' + (' and shows Nodes 2.0' if settings_done else '') + '. Then select the text-to-image tab again.')
    if nodes_running:
        steps.append('comfy_onboarding action=status refresh=true: proposal.node_packs must be empty.')
    if settings_choice != 'apply' and proposal.get('settings'):
        steps.append('Settings were not approved: leave them unchanged.')
    steps.append('comfy_onboarding action=tutorial.')
    out['instruction'] = CARD_RULE + 'Remaining steps, in order: ' + ' '.join(
        f'({i}) {step}' for i, step in enumerate(steps, 1))
    return out


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
        return dict(state, **apply_preferences(inst, state['setup_choices'], params.get('settings')))
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
    if action == 'reference_sheet':
        return reference_sheet(params.get('kind'))
    if action == 'complete':
        state = onboarding.complete(core.DATA, ident, session_id, inst, params.get('prompt_id'))
        step = state['tutorial'].get('step', 1)
        return dict(state, instruction=NEXT_AFTER.get(step, NEXT_AFTER_1))
    raise ValueError('Unknown onboarding action')


def command(session_id, step: int = 1):
    handle({'action': 'tutorial', 'replay': step == 1, 'step': step, 'downloads': False}, session_id)
    return f"### 🎓 {onboarding.heading(step)}\n\n{onboarding.INTROS[step]}"


TUTORIAL_PHRASES = {'tutorial': {'replay': True, 'step': 1}, 'start tutorial': {'replay': True, 'step': 1},
                    'replay tutorial': {'replay': True, 'step': 1}, 'tutorial step 1': {'replay': True, 'step': 1},
                    'resume tutorial': {'resume': True}, 'back to the tutorial': {'resume': True},
                    'continue tutorial': {'resume': True}, 'continue the tutorial': {'resume': True},
                    'tutorial step 2': {'step': 2}, 'modify an image': {'step': 2},
                    'create a reference sheet': {'step': 2},
                    'tutorial step 3': {'step': 3}, 'create your first video': {'step': 3},
                    'tutorial step 4': {'step': 4}, 'add sound to your video': {'step': 4}}
TUTORIAL_PHRASES.update({onboarding.heading(n).lower(): {'step': n} for n in onboarding.STEPS if n > 1})


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

"""Background model downloads, tutorial-first ordering, tutorial steps 1-2 and the desktop progress card helpers.
Everything runs against temporary folders and a local HTTP server; no real model is downloaded."""
import json
import re
import shutil
import subprocess
import tempfile
import threading
import unittest
import uuid
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from plugin import core, download_flow, downloads, library, onboarding

ROOT = Path(__file__).resolve().parents[1]


@contextmanager
def file_server(files):
    """Serves {name: bytes} with Range support; records (path, range) per request."""
    log = []

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a): pass

        def do_GET(self):
            name = self.path.lstrip('/')
            log.append((name, self.headers.get('Range')))
            if name not in files:
                self.send_response(404); self.end_headers(); return
            data = files[name]
            rng = self.headers.get('Range')
            if rng:
                start = int(re.match(r'bytes=(\d+)-', rng).group(1))
                if start >= len(data):
                    self.send_response(416); self.end_headers(); return
                self.send_response(206)
                self.send_header('Content-Range', f'bytes {start}-{len(data) - 1}/{len(data)}')
                data = data[start:]
            else:
                self.send_response(200)
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    srv = ThreadingHTTPServer(('127.0.0.1', 0), H)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        yield f'http://127.0.0.1:{srv.server_port}', log
    finally:
        srv.shutdown(); srv.server_close(); t.join()


class CatalogTests(unittest.TestCase):
    def test_every_required_model_has_a_download_link(self):
        """Regression: files with url=null were never downloaded, so 'download everything' left ComfyUI with missing
        models (t2i text encoder + Lightning LoRA, i2i prompt-enhancer encoder, Wan VAE, SCAIL model)."""
        for entry in library.load_catalog()['workflows']:
            for m in entry['requirements']['models']:
                with self.subTest(workflow=entry['id'], model=m['name']):
                    self.assertTrue(m.get('optional') or str(m.get('url') or '').startswith('https://'))

    def test_tutorial_groups(self):
        keys = download_flow.tutorial_keys()
        self.assertEqual(download_flow.group_for('diffusion_models', 'qwen_image_2.1_int8_convrot.safetensors', keys), 'tutorial-1')
        self.assertEqual(download_flow.group_for('text_encoders', 'qwen3vl_8b_w4a8.safetensors', keys), 'tutorial-1')
        # The t2i window flags the prompt-enhancer file as missing (blocks Run): it ships with step 1.
        self.assertEqual(download_flow.group_for('text_encoders', 'qwen3.5_9b_qwen_image_2.1_pe_i2i_w4a8.safetensors', keys), 'tutorial-1')
        self.assertEqual(download_flow.group_for('vae', 'trellis_2_shape_vae_bf16.safetensors', keys), 'other')

    def test_embedded_models_of_a_users_workflow(self):
        wf = {'nodes': [{'type': 'UNETLoader', 'properties': {'models': [
            {'name': 'a.safetensors', 'url': 'https://h/a', 'directory': 'diffusion_models'}]}},
            {'type': 'VAELoader', 'properties': {'models': [{'name': 'a.safetensors', 'directory': 'diffusion_models'}]}}],
            'definitions': {'subgraphs': [{'id': 's', 'nodes': [{'type': 'LoraLoader', 'properties': {'models': [
                {'name': 'sub\\l.safetensors', 'url': None, 'directory': 'loras'}]}}]}]}}
        rows = download_flow.embedded_models(wf)
        self.assertEqual([(r['folder'], r['name'], r['url']) for r in rows],
                         [('diffusion_models', 'a.safetensors', 'https://h/a'), ('loras', 'sub/l.safetensors', None)])


class DownloaderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.install = Path(self.tmp.name) / 'install'
        self.models = self.install / 'ComfyUI' / 'models'
        p = patch.object(downloads, 'worker_alive', return_value=False); p.start(); self.addCleanup(p.stop)

    def test_tutorial_first_then_rest_and_card(self):
        files = {'big_t1': b'T' * 300_000, 'small_other': b'o' * 1000, 't2': b'2' * 5000}
        with file_server(files) as (url, log):
            downloads.enqueue(self.install, self.models, [{'folder': 'loras', 'name': 'o.safetensors', 'url': url + '/small_other', 'size_bytes': 1000}], group='other', spawn=False)
            downloads.enqueue(self.install, self.models, [{'folder': 'vae', 'name': 't2.safetensors', 'url': url + '/t2', 'size_bytes': 5000}], group='tutorial-2', spawn=False)
            r = downloads.enqueue(self.install, self.models, [{'folder': 'diffusion_models', 'name': 'big.safetensors', 'url': url + '/big_t1', 'size_bytes': 300_000}], group='tutorial-1', spawn=False)
            self.assertEqual(r['state'], 'pending')
            self.assertTrue(r['progress_card'].startswith('MEDIA:') and r['progress_card'].endswith('downloads.json'))
            self.assertEqual(downloads.run(self.install), 'done')
        self.assertEqual([name for name, _ in log], ['big_t1', 't2', 'small_other'])
        self.assertEqual((self.models / 'diffusion_models' / 'big.safetensors').read_bytes(), files['big_t1'])
        card = json.loads(downloads.card_path(self.install).read_text(encoding='utf-8'))
        self.assertEqual((card['kind'], card['state'], card['percent'], card['done_files']), ('downloads', 'done', 100.0, 3))
        self.assertEqual([g['id'] for g in card['groups']], ['tutorial-1', 'tutorial-2', 'other'])
        self.assertTrue(all(g['state'] == 'done' for g in card['groups']))
        self.assertFalse(list(self.models.rglob('*.part')))
        st = downloads.wait(self.install, 'tutorial-1', 0)
        self.assertTrue(st['finished'])

    def test_resume_from_part_and_size_unknown(self):
        data = bytes(range(256)) * 400
        target = self.models / 'vae' / 'v.safetensors'
        target.parent.mkdir(parents=True)
        target.with_name('v.safetensors.part').write_bytes(data[:10_000])
        with file_server({'v': data}) as (url, log):
            downloads.enqueue(self.install, self.models, [{'folder': 'vae', 'name': 'v.safetensors', 'url': url + '/v'}], spawn=False)
            downloads.run(self.install)
        self.assertEqual(log, [('v', 'bytes=10000-')])
        self.assertEqual(target.read_bytes(), data)

    def test_wrong_size_is_an_error_not_a_model(self):
        with file_server({'x': b'short'}) as (url, _), patch.object(downloads.time, 'sleep'):
            downloads.enqueue(self.install, self.models, [{'folder': 'vae', 'name': 'x.safetensors', 'url': url + '/x', 'size_bytes': 99}], spawn=False)
            downloads.run(self.install)
        card = downloads.status(self.install)
        self.assertEqual(card['state'], 'error')
        self.assertFalse((self.models / 'vae' / 'x.safetensors').exists())

    def test_present_file_is_done_without_request_and_not_queued_twice(self):
        f = self.models / 'vae' / 'have.safetensors'; f.parent.mkdir(parents=True); f.write_bytes(b'1234')
        r = downloads.enqueue(self.install, self.models, [{'folder': 'vae', 'name': 'have.safetensors', 'url': 'https://h/x', 'size_bytes': 4}], spawn=False)
        self.assertEqual(r['state'], 'done')
        r = downloads.enqueue(self.install, self.models, [{'folder': 'vae', 'name': 'have.safetensors', 'url': 'https://h/x', 'size_bytes': 4}], spawn=False)
        self.assertEqual(r['already_queued_or_done'], ['vae/have.safetensors'])
        self.assertEqual(r['files'], 1)

    def test_unsafe_destinations_and_links(self):
        for folder, name in [('..', 'a'), ('vae', '../a'), ('vae', 'C:/a'), ('a/b', 'x'), ('vae', '/abs')]:
            with self.subTest(folder=folder, name=name), self.assertRaises(ValueError):
                downloads.enqueue(self.install, self.models, [{'folder': folder, 'name': name, 'url': 'https://h/x'}], spawn=False)
        for url in ['http://example.com/x', 'file:///etc/passwd', '', None]:
            with self.subTest(url=url), self.assertRaises(ValueError):
                downloads.enqueue(self.install, self.models, [{'folder': 'vae', 'name': 'v', 'url': url}], spawn=False)

    def test_queue_groups_models_without_url_are_reported(self):
        with patch.object(downloads, 'enqueue', side_effect=lambda d, r, m, group, spawn: {'group': group, 'n': len(m)}) as enq:
            r = download_flow.queue(self.install, self.models, [
                {'folder': 'vae', 'name': 'wan_2.1_vae.safetensors', 'url': 'https://h/w'},
                {'folder': 'vae', 'name': 'qwen_image_2.1_vae_bf16.safetensors', 'url': 'https://h/q'},
                {'folder': 'loras', 'name': 'nolink.safetensors', 'url': None}])
        self.assertEqual([c.kwargs['group'] for c in enq.call_args_list], ['tutorial-1', 'other'])
        self.assertEqual([m['name'] for m in r['models_without_url']], ['nolink.safetensors'])

    def test_finished_download_group_requires_immediate_visible_refresh(self):
        inst = {'name': core.MANAGED_NAME, 'url': 'http://127.0.0.1:8190'}
        for action in ('wait', 'status'):
            for state in ('done', 'running', 'error', 'stalled'):
                with self.subTest(action=action, state=state), \
                     patch.object(download_flow, 'target', return_value=(inst, self.install, self.models)), \
                     patch.object(downloads, action, return_value={
                         'state': 'running', 'groups': [{'id': 'tutorial-1', 'state': state}],
                         'group': {'id': 'tutorial-1', 'state': state}}):
                    out = download_flow.handle({'action': action, 'group': 'tutorial-1'})
                if state == 'done':
                    self.assertIn('missing-model-header-refresh', out.get('instruction', ''))
                    self.assertIn('before asking for a prompt', out['instruction'].lower())
                    self.assertEqual(out['instance'], inst['name'])
                    self.assertEqual(out['url'], inst['url'])
                else:
                    self.assertNotIn('instruction', out)

    def test_install_status_is_a_progress_card(self):
        from plugin import installer
        d = Path(self.tmp.name) / 'inst'
        (d / '.comfy-recipe').mkdir(parents=True)
        installer._write(d / '.comfy-recipe' / 'status.json', {**installer.CARD, 'state': 'running', 'step': 3,
                                                               'started_at': 1, 'updated_at': 1, 'pid': None})
        st = installer.install_status(d)
        self.assertEqual(st['progress_card'], 'MEDIA:' + str(d / '.comfy-recipe' / 'status.json'))
        self.assertEqual((st['kind'], len(st['weights'])), ('install', len(installer.STEPS)))
        self.assertEqual(sum(installer.STEP_WEIGHTS), 100)


class TutorialStepTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.m = {'install_id': str(uuid.uuid4()), 'onboarding_version': 1, 'port': 8190, 'comfyui_dir': str(self.root / 'ComfyUI')}
        managed = {'name': core.MANAGED_NAME, 'url': 'http://127.0.0.1:8190', 'root': self.m['comfyui_dir']}
        for p in [patch.object(core, 'DATA', self.root), patch.object(core, '_managed_dir', return_value=self.root),
                  patch.object(core.installer, 'manifest', return_value=self.m),
                  patch.object(core, '_load_state', return_value={'setup': 'managed', 'managed': {'dir': str(self.root)},
                               'active': core.MANAGED_NAME, 'instances': {core.MANAGED_NAME: managed}})]:
            p.start(); self.addCleanup(p.stop)

    def complete_step1(self, sid='A'):
        onboarding.status(self.root, self.m, sid)
        onboarding.tutorial(self.root, self.m, sid)
        with onboarding._records(self.root, self.m['install_id'], sid) as (_, session):
            session['tutorial'] = {'id': 'first-image', 'step': 1, 'state': 'completed', 'prompt_id': 'p'}

    def test_heading_intro_and_step2_after_step1(self):
        from plugin import onboarding_flow as flow
        r = onboarding.tutorial(self.root, self.m, 'A')
        self.assertEqual(r['tutorial_heading'], 'Tutorial (step 1/6): Generate your first image')
        self.complete_step1()
        with patch.object(flow, 'step_downloads', return_value={'queued': True, 'progress_card': 'MEDIA:c'}) as sd:
            r = flow.handle({'action': 'tutorial', 'step': 2}, 'A')
        sd.assert_called_once_with(2, 'unanswered')
        self.assertEqual((r['tutorial']['step'], r['tutorial']['state']), (2, 'awaiting_images'))
        self.assertEqual(r['tutorial_heading'], 'Tutorial (step 2/6): Modify an image')
        self.assertIn('modify-image-tutorial', r['instruction'])
        self.assertIn('ONE OR SEVERAL images', r['instruction'])
        self.assertTrue(onboarding.has_tutorial(self.root, 'A'))
        # idempotent: calling step 2 again keeps the lesson
        self.assertEqual(onboarding.tutorial(self.root, self.m, 'A', step=2)['tutorial']['state'], 'awaiting_images')
        with self.assertRaises(ValueError):
            onboarding.tutorial(self.root, self.m, 'A', step=3)

    def test_begin_run_is_bound_to_the_steps_workflow(self):
        from plugin import onboarding_flow as flow
        self.complete_step1()
        onboarding.tutorial(self.root, self.m, 'A', step=2)
        with patch.object(core.cc, 'load_workflow') as read:
            for path in ['Comfy Recipe/RCP_qwen_image_2_1_t2i.json', '../x.json']:
                with self.subTest(path=path), self.assertRaisesRegex(ValueError, 'working copy'):
                    flow.handle({'action': 'tutorial', 'step': 2, 'begin_run': True, 'workflow_path': path, 'prompt': 'p'}, 'A')
            read.assert_not_called()
        with self.assertRaisesRegex(ValueError, 'Start tutorial step 1'):
            flow.handle({'action': 'tutorial', 'step': 1, 'begin_run': True, 'prompt': 'p'}, 'A')
        with patch.object(core.cc, 'load_workflow', return_value={'id': 'i2i-uuid'}), patch.object(core.cc, 'get_json', return_value={}):
            r = flow.handle({'action': 'tutorial', 'step': 2, 'begin_run': True, 'prompt': 'In <image1> make it night',
                             'workflow_path': 'Comfy Recipe/RCP_qwen_image_2_1_i2i-v1.0.1.json'}, 'A')
        self.assertEqual((r['tutorial']['step'], r['tutorial']['state'], r['tutorial']['workflow_id']), (2, 'in_progress', 'i2i-uuid'))

    def test_completion_offers_step2_and_step2_completion_asks_ordinary_question(self):
        from plugin import onboarding_flow as flow
        from test_tutorial_evidence import history
        onboarding.status(self.root, self.m, 'A'); onboarding.tutorial(self.root, self.m, 'A')
        for step, path, wid in [(1, 'Comfy Recipe/RCP_qwen_image_2_1_t2i.json', 't2i'), (2, 'Comfy Recipe/RCP_qwen_image_2_1_i2i.json', 'i2i')]:
            if step == 2:
                onboarding.tutorial(self.root, self.m, 'A', step=2)
            with patch.object(core.cc, 'load_workflow', return_value={'id': wid}), patch.object(core.cc, 'get_json', return_value={}), \
                 patch('plugin.onboarding.time.time', return_value=1):
                flow.handle({'action': 'tutorial', 'step': step, 'begin_run': True, 'workflow_path': path, 'prompt': 'a red kite'}, 'A')
            with patch.object(core.cc, 'history', return_value=history(wid)), patch.object(core.cc, 'view_bytes', return_value=b'\x89PNG\r\n\x1a\nimg'):
                r = flow.handle({'action': 'complete', 'prompt_id': 'job'}, 'A')
            self.assertEqual((r['tutorial']['step'], r['tutorial']['state']), (step, 'completed'))
            if step == 1:
                self.assertIn('Tutorial (step 2/6): Modify an image', r['instruction'])
                self.assertIn('clarify', r['instruction'])
            else:
                self.assertIn('What would you like to do?', r['instruction'])

    def test_resume_skip_and_phrases(self):
        from plugin import onboarding_flow as flow
        self.complete_step1()
        self.assertEqual(flow._resume_step({'step': 1, 'state': 'completed'}), (2, False))
        self.assertEqual(flow._resume_step({'step': 2, 'state': 'skipped'}), (2, True))
        hist = [{'role': 'user', 'content': '[ComfyUI session]'}]
        r = flow.route('Back to the tutorial', 'A', recipe_session=True)
        self.assertIn('TUTORIAL STEP 2/6', r)
        self.assertEqual(onboarding.status(self.root, self.m, 'A')['tutorial']['step'], 2)
        r = flow.route('skip tutorial', 'A', recipe_session=True)
        self.assertIn('come back', r)
        r = flow.route('modify an image', 'A', recipe_session=True)
        self.assertIn('TUTORIAL STEP 2/6', r)
        del hist

    def test_hook_paths_do_no_network_work(self):
        from plugin import onboarding_flow as flow
        onboarding.status(self.root, self.m, 'A')
        with patch.object(flow, 'step_downloads') as sd:
            out = flow.command('A', 2)
            flow.route('tutorial', 'A', recipe_session=True)
        sd.assert_not_called()
        self.assertTrue(out.startswith('### 🎓 Tutorial (step 2/6): Modify an image'))

    def test_step_downloads_policy(self):
        from plugin import onboarding_flow as flow
        prop = {'models': [{'folder': 'vae', 'name': 'qwen_image_2.1_vae_bf16.safetensors', 'url': 'https://h/v'}],
                'download_gb': 0.68, 'models_without_url': [], 'node_packs': [], 'settings': []}
        with patch.object(flow, '_proposal', return_value=prop), \
             patch.object(flow.download_flow, 'queue', return_value={'progress_card': 'MEDIA:c', 'groups': [{'id': 'tutorial-1', 'state': 'running'}]}) as q:
            self.assertEqual(flow.step_downloads(1, 'on_use')['progress_card'], 'MEDIA:c')
            self.assertEqual(flow.step_downloads(1, 'now')['state'], 'running')
            r = flow.step_downloads(1, 'unanswered')
        self.assertEqual(q.call_count, 2)
        self.assertTrue(r['consent_needed'])
        self.assertIn('qwen-image-2-1-t2i', r['instruction'])


class SkillAndSchemaTests(unittest.TestCase):
    def test_new_skills_registered_and_tool_schema(self):
        import plugin
        from plugin import skill_registration
        ids = {e['id'] for e in library.load_catalog()['workflows']}
        skills = {s['name']: s for s in skill_registration.skills_for_registration(ROOT / 'plugin' / 'skills', ids)}
        for name in ('modify-image-tutorial', 'qwen-image-2-1-editing'):
            self.assertEqual(skills[name]['workflow_ids'], ['qwen-image-2-1-i2i'])
            self.assertLessEqual(len(skills[name]['description']), 60)
        text = (ROOT / 'plugin/skills/modify-image-tutorial/SKILL.md').read_text(encoding='utf-8')
        for token in ('Tutorial (step 2/6): Modify an image', 'begin_run=true', 'one or several images', 'comfy_result', 'vision_analyze'):
            self.assertIn(token, text)
        first = (ROOT / 'plugin/skills/first-image-tutorial/SKILL.md').read_text(encoding='utf-8')
        self.assertIn('Tutorial (step 1/6): Generate your first image', first)
        self.assertIn('Tutorial (step 2/6): Modify an image', first)
        self.assertIn('comfy_downloads', plugin.SCHEMAS)
        self.assertIn('comfy_downloads', plugin.HANDLERS)
        self.assertIn('comfy_downloads', (ROOT / 'plugin/plugin.yaml').read_text(encoding='utf-8'))
        self.assertEqual(plugin.SCHEMAS['comfy_onboarding']['parameters']['properties']['step']['enum'], [1, 2])


@unittest.skipUnless(shutil.which('node'), 'node not installed')
class DesktopCardTests(unittest.TestCase):
    def test_summaries_and_file_filter(self):
        src = (ROOT / 'plugin/desktop/plugin.js').read_text(encoding='utf-8')
        body = re.sub(r'^import .*$', '', src, flags=re.M).replace('export default', 'const plugin =').replace('export ', '')
        script = body + r'''
const out = {
  dl: summarize({kind:'downloads', state:'running', bytes:5e9, total_bytes:1e10, percent:50, speed_bps:5e7, eta_s:100,
                 files:3, done_files:1, current:{name:'big.safetensors'}, updated_at: 1000,
                 groups:[{id:'tutorial-1', label:'Tutorial step 1', state:'done', files:2, done_files:2, bytes:3e9, total_bytes:3e9}]}, 1001),
  inst: summarize({kind:'install', state:'running', steps:['a','b','c'], weights:[10,60,30], step:2, step_name:'c', started_at: 940, updated_at:1000}, 1000),
  stale: summarize({kind:'nodes', state:'running', done:1, total:4, updated_at: 1}, 1000),
  nodes: summarize({kind:'nodes', state:'error', error:'Not installed: WAS', packs:['KJ','WAS'], pack_states:{KJ:'done', WAS:'error'}, updated_at: 1000}, 1000),
  legacy: summarize({state:'done', steps:['a','b'], step:2}, 1000).percent,
  b64: decodeDataUrl('data:application/json;base64,' + Buffer.from('{"é":1}').toString('base64')),
  files: [isProgressFile('C:\\X\\.comfy-recipe\\status.json'), isProgressFile('/x/.comfy-recipe/progress/downloads.json'),
          isProgressFile('/x/.comfy-recipe/progress/queue.json'), isProgressFile('/x/out.png')],
  plugin: typeof plugin.register
};
console.log(JSON.stringify(out));
'''
        stubs = 'const SDK = {}; const host = {}; const haptic = () => {}; const PALETTE_AREA="p", ROUTES_AREA="r", SIDEBAR_NAV_AREA="s"; ' \
                'const useEffect = () => {}, useSyncExternalStore = () => 0, jsx = () => null, jsxs = () => null;\n'
        r = subprocess.run(['node', '-e', stubs + script], capture_output=True, text=True, encoding='utf-8', timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout.strip().splitlines()[-1])
        self.assertEqual(out['dl']['state'], 'running')
        self.assertIn('big.safetensors', out['dl']['label'])
        self.assertIn('50 MB/s', out['dl']['label'])
        self.assertEqual(out['dl']['rows'][0]['state'], 'done')
        self.assertAlmostEqual(out['inst']['percent'], 70)
        self.assertEqual([r['state'] for r in out['inst']['rows']], ['done', 'done', 'running'])
        self.assertEqual(out['stale']['state'], 'stalled')
        self.assertEqual([r['state'] for r in out['nodes']['rows']], ['done', 'error'])
        self.assertIn('WAS', out['nodes']['label'])
        self.assertEqual(out['legacy'], 100)
        self.assertEqual(out['b64'], '{"é":1}')
        self.assertEqual(out['files'], [True, True, False, False])
        self.assertEqual(out['plugin'], 'function')

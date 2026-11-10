"""Node packs installed by the plugin through ComfyUI-Manager's API, one-call restart and API-applied settings.
Everything runs against a local fake server; nothing reaches a real ComfyUI or the registry."""
import json
import tempfile
import threading
import unittest
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from plugin import core, download_flow, downloads


@contextmanager
def manager(installed=None, install_ok=('comfyui-kjnodes',), registry_ready_after=0):
    """Fake ComfyUI + Manager 4: queue/task, queue/start, queue/status, customnode/installed, settings."""
    state = {'installed': dict(installed or {}), 'pending': [], 'events': [], 'settings': {}, 'queue_running': [],
             'history': {}, 'starts': 0}

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a): pass

        def answer(self, code, obj=None):
            raw = b'' if obj is None else json.dumps(obj).encode()
            self.send_response(code); self.send_header('Content-Length', str(len(raw))); self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):
            if self.path == '/v2/customnode/installed':
                return self.answer(200, {k: {'ver': '1', 'cnr_id': k, 'aux_id': None, 'enabled': True}
                                         for k in state['installed']})
            if self.path == '/v2/manager/queue/status':
                n = len(state['pending'])
                return self.answer(200, {'total_count': n, 'done_count': 0, 'in_progress_count': 0,
                                         'pending_count': n, 'is_processing': False})
            if self.path == '/settings':
                return self.answer(200, state['settings'])
            if self.path == '/v2/manager/queue/history':
                return self.answer(200, {'history': state['history']})
            if self.path == '/queue':
                return self.answer(200, {'queue_running': state['queue_running'], 'queue_pending': []})
            return self.answer(404, {})

        def do_POST(self):
            body = self.rfile.read(int(self.headers.get('Content-Length') or 0))
            ctype = self.headers.get('Content-Type')
            state['events'].append((self.path, ctype, json.loads(body) if body else None))
            if ctype in ('application/x-www-form-urlencoded', 'multipart/form-data', 'text/plain'):
                return self.answer(400, {'error': 'simple form post'})
            if self.path == '/v2/manager/queue/task':
                state['pending'].append(json.loads(body)['params']['id'])
                return self.answer(200)
            if self.path == '/v2/manager/queue/start':
                state['starts'] += 1
                for pid in state['pending']:
                    ready = state['starts'] > registry_ready_after
                    result = 'success' if ready and pid in install_ok else (
                        f"Cannot resolve install target: '{pid}@latest'" if not ready else 'failed')
                    state['history'][f"{pid}-{state['starts']}"] = {'params': {'id': pid}, 'result': result,
                                                                     'timestamp': f"2026-01-01T00:00:{state['starts']:02d}"}
                    if result == 'success':
                        state['installed'][pid] = True
                state['pending'].clear()
                return self.answer(200)
            if self.path.startswith('/settings/'):
                state['settings'][self.path.removeprefix('/settings/')] = json.loads(body)
                return self.answer(200)
            return self.answer(404, {})

    srv = ThreadingHTTPServer(('127.0.0.1', 0), H)
    t = threading.Thread(target=srv.serve_forever, daemon=True); t.start()
    try:
        yield f'http://127.0.0.1:{srv.server_port}', state
    finally:
        srv.shutdown(); srv.server_close(); t.join()


class NodePackInstallTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.d = Path(self.tmp.name)

    def test_queue_uses_frontend_payload_skips_installed_and_starts_queue(self):
        with manager(installed={'comfyui-kjnodes': True}, install_ok=('was-ns',)) as (url, st):
            res = downloads.queue_pack_installs(url, [{'id': 'comfyui-kjnodes', 'name': 'KJ'}, 'was-ns::WAS'])
        self.assertEqual(res, {'queued': ['was-ns'], 'already_installed': ['comfyui-kjnodes']})
        task = next(e for e in st['events'] if e[0] == '/v2/manager/queue/task')
        self.assertEqual(task[1], 'application/json')
        self.assertEqual(task[2]['kind'], 'install')
        self.assertEqual({k: task[2]['params'][k] for k in ('id', 'selected_version', 'version', 'mode', 'channel')},
                         {'id': 'was-ns', 'selected_version': 'latest', 'version': 'latest', 'mode': 'cache',
                          'channel': 'default'})
        start = [e for e in st['events'] if e[0] == '/v2/manager/queue/start']
        self.assertEqual(len(start), 1)
        self.assertEqual(start[0][1], 'application/json')  # a bare POST would be form-encoded and rejected
        self.assertIn('was-ns', st['installed'])

    def test_stale_pending_item_is_started_even_when_nothing_new_is_queued(self):
        with manager(installed={'was-ns': True}) as (url, st):
            st['pending'].append('comfyui-kjnodes')
            downloads.queue_pack_installs(url, ['was-ns'])
            self.assertIn('comfyui-kjnodes', st['installed'])

    def test_watcher_marks_failed_pack_instead_of_ticking_it(self):
        with manager(install_ok=('comfyui-kjnodes',)) as (url, st):
            downloads.queue_pack_installs(url, ['comfyui-kjnodes::KJ', 'was-ns::WAS'])
            out = downloads.watch_nodes(self.d, url, ['comfyui-kjnodes::KJ', 'was-ns::WAS'], poll=0.01,
                                        idle_exit_s=0, max_loops=50, queued=True)
        card = downloads._read(downloads.card_path(self.d, 'nodes'))
        self.assertEqual(out, 'error')
        self.assertEqual(card['pack_states'], {'KJ': 'done', 'WAS': 'error'})
        self.assertIn('WAS', card['error'])

    def test_registry_not_loaded_yet_is_retried_not_reported_as_failure(self):
        with manager(install_ok=('comfyui-kjnodes', 'was-ns'), registry_ready_after=1) as (url, st):
            downloads.queue_pack_installs(url, ['comfyui-kjnodes::KJ', 'was-ns::WAS'])
            self.assertEqual(st['installed'], {})  # first start: "not a CNR node"
            out = downloads.watch_nodes(self.d, url, ['comfyui-kjnodes::KJ', 'was-ns::WAS'], poll=0.01,
                                        idle_exit_s=0, max_loops=50, queued=True, retry_pause_s=0)
        card = downloads._read(downloads.card_path(self.d, 'nodes'))
        self.assertEqual(out, 'done')
        self.assertEqual(card['pack_states'], {'KJ': 'done', 'WAS': 'done'})

    def test_registry_wait_gives_up_after_its_budget(self):
        with manager(install_ok=('a',), registry_ready_after=99) as (url, _):
            downloads.queue_pack_installs(url, ['a'])
            out = downloads.watch_nodes(self.d, url, ['a'], poll=0.01, idle_exit_s=0, max_loops=50, queued=True,
                                        registry_wait_s=0, retry_pause_s=0)
        self.assertEqual(out, 'error')

    def test_watcher_done_when_every_pack_is_installed(self):
        with manager(installed={'a': True, 'b': True}) as (url, _):
            out = downloads.watch_nodes(self.d, url, ['a', 'b'], poll=0.01, idle_exit_s=0, max_loops=5)
        card = downloads._read(downloads.card_path(self.d, 'nodes'))
        self.assertEqual((out, card['state'], card['percent']), ('done', 'done', 100.0))
        self.assertIn('comfy_setup action=restart', card['note'])

    def test_install_nodes_flow_and_next_steps(self):
        inst = {'name': core.MANAGED_NAME, 'url': None}
        with manager(installed={'comfyui-kjnodes': True}) as (url, st), \
             patch.object(download_flow.downloads, 'start_nodes_watch', return_value={'progress_card': 'MEDIA:n'}) as w:
            inst['url'] = url
            res = download_flow.install_nodes(inst, self.d, ['ComfyUI-KJNodes', 'ComfyUI-Easy-Use'])
        self.assertEqual(res['queued'], ['comfyui-easy-use'])  # display name resolved to the registry id from the catalog
        self.assertEqual(res['state'], 'running')
        self.assertIn('do NOT open the Nodes Manager', res['instruction'])
        self.assertEqual([r['id'] for r in w.call_args.args[2]], ['comfyui-kjnodes', 'comfyui-easy-use'])
        with manager(installed={'comfyui-kjnodes': True}) as (url, _):
            inst['url'] = url
            done = download_flow.install_nodes(inst, self.d, ['comfyui-kjnodes'])
        self.assertEqual(done['state'], 'done')
        self.assertIn('comfy_setup action=restart', done['instruction'])
        self.assertIn('ask the user', download_flow.nodes_next({'name': 'other'}, 'done'))

    def test_nodes_status_waits_until_terminal_state(self):
        downloads._write(downloads.card_path(self.d, 'nodes'), {'state': 'done'})
        self.assertEqual(downloads.nodes_status(self.d, wait_s=60)['state'], 'done')
        downloads._write(downloads.card_path(self.d, 'nodes'), {'state': 'running'})
        self.assertEqual(downloads.nodes_status(self.d, wait_s=0)['state'], 'running')


class RestartAndSettingsTests(unittest.TestCase):
    def test_restart_refuses_while_a_job_runs_then_stops_and_starts(self):
        with manager() as (url, st):
            port = int(url.rsplit(':', 1)[1])
            with patch.object(core, '_managed_dir', return_value=Path('x')), \
                 patch.object(core.installer, 'manifest', return_value={'port': port}), \
                 patch.object(core, 'setup_stop', return_value={'stopped': True}) as stop, \
                 patch.object(core, 'setup_start', return_value={'running': True, 'url': url}) as start, \
                 patch.object(core.cc, 'alive', return_value={'system': {}}), \
                 patch.object(core.cc, 'port_open', return_value=False):
                st['queue_running'].append(['job'])
                busy = core.setup_restart()
                self.assertFalse(busy['restarted']); stop.assert_not_called()
                st['queue_running'].clear()
                ok = core.setup_restart(30)
        stop.assert_called_once(); start.assert_called_once_with(30)
        self.assertTrue(ok['restarted'])
        self.assertIn('desktop_preview action=close', ok['next'])

    def test_apply_settings_writes_and_verifies_through_api(self):
        with manager() as (url, st):
            res = core.apply_settings(url, [{'id': 'Comfy.VueNodes.Enabled', 'value': True}])
            self.assertEqual(st['settings'], {'Comfy.VueNodes.Enabled': True})
            with self.assertRaises(ValueError):
                core.apply_settings(url, [{'id': '../x', 'value': 1}])
        self.assertEqual((res['applied'], res['verified'], res['failed']),
                         (['Comfy.VueNodes.Enabled'], ['Comfy.VueNodes.Enabled'], []))

    def test_workflows_apply_settings_only_changes_needed_settings(self):
        import plugin
        from plugin import library
        entry = next(e for e in library.load_catalog()['workflows']
                     if (e.get('requirements') or {}).get('frontend_settings'))
        with manager() as (url, st), patch.object(core, '_inst', return_value={'name': 'x', 'url': url}):
            first = plugin._workflows({'action': 'apply_settings', 'workflow': entry['id']})
            second = plugin._workflows({'action': 'apply_settings', 'workflow': entry['id']})
        self.assertTrue(first['applied'])
        self.assertEqual(first['failed'], [])
        self.assertEqual(second['applied'], [])

    def test_schemas_expose_new_actions(self):
        import plugin
        props = lambda n: plugin.SCHEMAS[n]['parameters']['properties']
        self.assertIn('restart', props('comfy_setup')['action']['enum'])
        self.assertIn('install_nodes', props('comfy_downloads')['action']['enum'])
        self.assertIn('apply_settings', props('comfy_workflows')['action']['enum'])
        self.assertEqual(props('comfy_onboarding')['settings']['enum'], ['apply', 'skip'])


if __name__ == '__main__':
    unittest.main()

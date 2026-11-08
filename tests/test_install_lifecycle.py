"""Deleted / moved / reset managed installs: the plugin must notice, offer adopt or reinstall, and never lose track."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import plugin
from plugin import core, installer


def _fake_install(d: Path, port=8190) -> dict:
    (d / 'venv' / 'Scripts').mkdir(parents=True)
    (d / 'venv' / 'Scripts' / 'python.exe').write_text('')
    (d / 'ComfyUI').mkdir()
    (d / 'ComfyUI' / 'main.py').write_text('')
    m = {'version': 1, 'dir': str(d), 'comfyui_dir': str(d / 'ComfyUI'), 'python': str(d / 'venv' / 'Scripts' / 'python.exe'),
         'port': port, 'gpu': 1, 'shared_models': ['X:/elsewhere/ComfyUI']}
    installer._write(installer._meta(d) / 'manifest.json', m)
    return m


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.data = self.tmp / 'data'
        self.p = [patch.object(core, 'DATA', self.data), patch.object(core, 'STATE', self.data / 'instances.json')]
        for x in self.p:
            x.start()

    def tearDown(self):
        for x in self.p:
            x.stop()

    def _managed_state(self, d: Path):
        core._save_state({'active': 'comfy-recipe', 'setup': 'managed', 'managed': {'dir': str(d)}, 'learned_sm_dirs': [],
                          'instances': {'comfy-recipe': {'name': 'comfy-recipe', 'url': 'http://127.0.0.1:8190'}}})

    def test_deleted_install_is_install_missing_then_forgotten_with_previous_kept(self):
        self._managed_state(self.tmp / 'gone')
        with patch.object(installer, 'listener_pid', return_value=None):
            ph = core.setup_state()
        self.assertEqual(ph['phase'], 'install_missing')
        self.assertFalse(ph['old_comfyui_still_running'])
        prev = core.forget_missing()
        st = core._load_state()
        self.assertEqual((st['setup'], st['managed'], st['instances']), (None, None, {}))
        self.assertEqual(prev, {'dir': str(self.tmp / 'gone'), 'url': 'http://127.0.0.1:8190'})
        self.assertEqual(core.setup_state()['phase'], 'first_run')

    def test_running_install_is_not_missing(self):
        d = self.tmp / 'ok'
        _fake_install(d)
        self._managed_state(d)
        with patch.object(installer, 'server_running', return_value=False):
            self.assertEqual(core.setup_state()['phase'], 'stopped')

    def test_adopt_moved_folder_rebases_paths_and_checks_the_venv(self):
        old, new = self.tmp / 'old', self.tmp / 'new'
        _fake_install(old)
        old.rename(new)
        ok = subprocess.CompletedProcess([], 0, '2.14.1+cu130 True', '')
        with patch.object(installer, '_run', return_value=ok) as run:
            r = core.setup_adopt(str(new))
        m = installer.manifest(new)
        self.assertEqual(r['moved_from'], str(old))
        self.assertEqual(m['python'], str(new.resolve() / 'venv' / 'Scripts' / 'python.exe'))
        self.assertEqual(m['comfyui_dir'], str(new.resolve() / 'ComfyUI'))
        self.assertEqual(m['shared_models'], ['X:/elsewhere/ComfyUI'])  # outside the folder: untouched
        self.assertTrue((installer._meta(new) / 'manifest.moved-from.json').exists())
        self.assertEqual(run.call_args[0][0][0], m['python'])
        st = core._load_state()
        self.assertEqual((st['setup'], st['managed']['dir'], st['active']), ('managed', str(new.resolve()), 'comfy-recipe'))

    def test_adopt_refuses_non_install_and_broken_venv(self):
        with self.assertRaises(ValueError):
            core.setup_adopt(str(self.tmp))
        d = self.tmp / 'broken'
        _fake_install(d)
        bad = subprocess.CompletedProcess([], 1, '', 'No module named torch')
        with patch.object(installer, '_run', return_value=bad), self.assertRaises(RuntimeError):
            core.setup_adopt(str(d))
        self.assertIsNone(core._load_state().get('setup'))

    def test_reset_is_reversible_and_install_over_existing_points_to_adopt(self):
        d = self.tmp / 'inst'
        _fake_install(d)
        self._managed_state(d)
        r = core.setup_reset()
        self.assertIn('action=adopt dir=' + str(d), r['note'])
        with patch.object(installer, 'check_dir', return_value={'ok': True, 'path': str(d), 'existing_comfy_recipe_install': True}), \
             patch.object(installer, 'spawn_install') as spawn, self.assertRaises(ValueError):
            core.setup_install(str(d))
        spawn.assert_not_called()

    def test_stop_after_delete_uses_the_old_port_and_folder(self):
        self._managed_state(self.tmp / 'gone')
        core.forget_missing()
        with patch.object(installer, 'stop', return_value={'stopped': True}) as stop:
            core.setup_stop()
        self.assertEqual(stop.call_args[0][0], self.tmp / 'gone')
        self.assertEqual(stop.call_args[1]['port'], 8190)

    def test_kickoff_for_missing_install_offers_adopt_and_first_run(self):
        with patch.object(plugin, '_sync_settings'), \
             patch.object(core, 'setup_state', return_value={'phase': 'install_missing', 'dir': 'D:/old',
                                                              'old_comfyui_still_running': True}), \
             patch.object(core, 'forget_missing') as forget, patch.object(plugin, '_first_run_text', return_value='FIRST RUN'):
            text = plugin._session_start('')
        forget.assert_called_once()
        self.assertIn('action=adopt', text)
        self.assertIn('comfy_setup action=stop', text)
        self.assertIn('FIRST RUN', text)


if __name__ == '__main__':
    unittest.main()

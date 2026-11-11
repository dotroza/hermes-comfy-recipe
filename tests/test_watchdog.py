"""stop_with_hermes: the watchdog stops ComfyUI once every recorded Hermes owner process is gone."""
import tempfile
import itertools
import unittest
from pathlib import Path
from unittest.mock import patch
from plugin import core, installer


class WatchdogTests(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        installer._write(installer._meta(self.d) / 'manifest.json', {'port': 8999, 'dir': str(self.d)})

    def _owners(self, pids, **extra):
        installer._write(installer._meta(self.d) / 'owners.json', {'pids': pids, **extra})

    def _watch(self, alive_pids, running=True, loops=3):
        with patch.object(installer, '_comfy_running', return_value=running), \
             patch.object(installer, '_pid_alive', side_effect=lambda p, m=None: p in alive_pids), \
             patch.object(installer, 'stop', return_value={'stopped': True}) as stop, \
             patch.object(installer.time, 'sleep'), \
             patch.object(installer.time, 'time', side_effect=itertools.count(1)):
            r = installer.watch(self.d, poll=0, idle_exit_s=0, max_loops=loops)
        return r, stop

    def test_stops_comfyui_when_all_owners_are_gone(self):
        self._owners([11, 12])
        r, stop = self._watch(alive_pids={12}, loops=2)
        self.assertEqual(r, 'max loops'); stop.assert_not_called()  # one owner still open
        r, stop = self._watch(alive_pids=set())
        self.assertIn('ComfyUI stopped', r); stop.assert_called_once()

    def test_keep_running_and_idle_and_missing_install_exit_without_stopping(self):
        self._owners([], keep_running=True)
        r, stop = self._watch(alive_pids=set())
        self.assertIn('keep running', r); stop.assert_not_called()
        self._owners([11])
        r, stop = self._watch(alive_pids=set(), running=False)
        self.assertEqual(r, 'ComfyUI not running'); stop.assert_not_called()
        (installer._meta(self.d) / 'manifest.json').unlink()
        r, stop = self._watch(alive_pids=set())
        self.assertEqual(r, 'install gone'); stop.assert_not_called()

    def test_single_watchdog_owners_refreshed(self):
        class P: pid = 4242
        with patch.object(installer, '_detached', return_value=P()) as det, \
             patch.object(installer, '_pid_alive', side_effect=lambda p, m=None: p == 4242):
            a = installer.ensure_watchdog(self.d, [1])
            b = installer.ensure_watchdog(self.d, [2, 2])
        self.assertTrue(a['new']); self.assertFalse(b['new']); self.assertEqual(det.call_count, 1)
        self.assertEqual(installer._read(installer._meta(self.d) / 'owners.json')['pids'], [2])
        self.assertIn('watch', det.call_args[0][0])

    def test_owner_is_the_desktop_main_process_not_electron_helpers(self):
        class Proc:
            def __init__(self, pid, name, cmd): self.info = {'pid': pid, 'name': name, 'cmdline': cmd}
        procs = [Proc(1, 'Hermes.exe', ['Hermes.exe']), Proc(2, 'Hermes.exe', ['Hermes.exe', '--type=renderer']),
                 Proc(3, 'python.exe', ['python', '-m', 'hermes_cli.main', 'gateway'])]
        with patch('psutil.process_iter', return_value=procs):
            self.assertEqual(installer.hermes_owner_pids(), [1])
        with patch('psutil.process_iter', return_value=procs[2:]):
            self.assertEqual(installer.hermes_owner_pids(), [installer.os.getpid()])

    def test_setting_off_releases_instead_of_binding(self):
        with patch.object(core, '_managed_dir', return_value=self.d), patch.dict(core.SETTINGS, {'stop_with_hermes': False}), \
             patch.object(installer, 'ensure_watchdog') as ens:
            installer._write(installer._meta(self.d) / 'watchdog.json', {'pid': 1})
            r = core.bind_to_hermes()
        ens.assert_not_called()
        self.assertTrue(installer._read(installer._meta(self.d) / 'owners.json')['keep_running'])
        self.assertIn('keeps running', r['status'])

    def test_default_folder_is_comfyrecipeenv(self):
        self.assertEqual(installer.default_dir().name, 'ComfyRecipeEnv')


if __name__ == '__main__':
    unittest.main()

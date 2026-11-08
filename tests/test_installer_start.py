import tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from plugin import installer


class _Proc:
    def __init__(self, log, text):
        self.pid, self.log, self.text = 111, log, text
    def poll(self):
        with open(self.log, 'a', encoding='utf-8') as f:
            f.write(self.text)
        self.text = ''
        return 0


class StartTests(unittest.TestCase):
    def _run(self, log_text, http):
        d = Path(tempfile.mkdtemp())
        m = {'port': 8999, 'python': 'py', 'comfyui_dir': str(d)}
        calls = iter(http)
        with patch.object(installer, 'manifest', return_value=m), \
             patch.object(installer, 'server_running', return_value=False), \
             patch.object(installer, '_port_open', return_value=False), \
             patch.object(installer, '_http_ok', side_effect=lambda u: next(calls)), \
             patch.object(installer, '_detached', side_effect=lambda a, log, cwd: _Proc(log, log_text)), \
             patch.object(installer, 'listener_pid', return_value=222), \
             patch.object(installer.time, 'sleep'):
            return d, installer.start(d, wait_s=60)

    def test_manager_self_restart_is_not_a_crash_and_new_pid_is_recorded(self):
        d, r = self._run('[ComfyUI-Manager] Restarting to reapply dependency installation.\n', [False, False, True])
        self.assertTrue(r['running'])
        self.assertIn('ComfyUI-Manager', r['note'])
        self.assertEqual(installer._read(installer._meta(d) / 'server.json')['pid'], 222)

    def test_real_crash_still_raises(self):
        with self.assertRaises(RuntimeError):
            self._run('Traceback: boom\n', [False, False, False])

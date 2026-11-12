"""Catalog review hardening: declared PyYAML, minimal child-process env, public-host-only downloads (first request,
every redirect hop, connected peer), confined no-overwrite ffmpeg outputs, safe template cache names."""
import os
import shutil
import socket
import subprocess
import tempfile
import threading
import unittest
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import yaml

from plugin import core, dependencies, downloads, installer, media, safe_http, templates

ROOT = Path(__file__).resolve().parents[1]
HAVE_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


@contextmanager
def redirect_server(location):
    """Every GET/HEAD answers 302 -> location; counts requests."""
    hits = []

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a): pass

        def _go(self):
            hits.append(self.path)
            self.send_response(302)
            self.send_header("Location", location)
            self.send_header("Content-Length", "0")
            self.end_headers()

        do_GET = do_HEAD = _go

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        yield f"http://127.0.0.1:{srv.server_port}", hits
    finally:
        srv.shutdown(); srv.server_close(); t.join()


def fake_dns(table):
    """socket.getaddrinfo stand-in: host -> [ip, ...]; any other host fails to resolve."""
    def gai(host, port, *a, **kw):
        if host not in table:
            raise socket.gaierror("unknown host")
        return [(socket.AF_INET6 if ":" in ip else socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port))
                for ip in table[host]]
    return gai


class ManifestTests(unittest.TestCase):
    def test_pyyaml_is_declared(self):
        m = yaml.safe_load((ROOT / "plugin" / "plugin.yaml").read_text(encoding="utf-8"))
        self.assertIn("PyYAML>=6,<7", m["python_dependencies"])

    def test_local_mirrors_setting_is_declared_and_off(self):
        m = yaml.safe_load((ROOT / "plugin" / "plugin.yaml").read_text(encoding="utf-8"))
        self.assertIs(m["config_schema"]["allow_local_mirrors"]["default"], False)
        self.assertIs(core.SETTINGS["allow_local_mirrors"], False)


class ChildEnvTests(unittest.TestCase):
    ENV = {"PATH": "/bin", "SYSTEMROOT": r"C:\Windows", "TEMP": "/t", "USERPROFILE": "/u", "HOME": "/h",
           "LC_ALL": "C.UTF-8", "CUDA_VISIBLE_DEVICES": "0", "HF_HOME": "/hf", "XAUTHORITY": "/x",
           "HTTPS_PROXY": "http://proxy:3128",
           "OPENAI_API_KEY": "sk-1", "ANTHROPIC_API_KEY": "sk-2", "OPENROUTER_API_KEY": "sk-3", "HF_TOKEN": "hf_1",
           "UV_PUBLISH_TOKEN": "t", "GITHUB_TOKEN": "g", "NOUS_API_KEY": "n", "PYTHONPATH": "/hermes",
           "VIRTUAL_ENV": "/hermes/venv", "SOME_RANDOM_VAR": "x"}

    def test_allow_list_only(self):
        with patch.dict(os.environ, self.ENV, clear=True):
            env = installer.child_env({"UV_NO_PROGRESS": "1"})
        for k in ("PATH", "SYSTEMROOT", "TEMP", "USERPROFILE", "HOME", "LC_ALL", "CUDA_VISIBLE_DEVICES", "HF_HOME",
                  "XAUTHORITY", "HTTPS_PROXY", "UV_NO_PROGRESS"):
            self.assertIn(k, env)
        for k in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "OPENROUTER_API_KEY", "HF_TOKEN", "UV_PUBLISH_TOKEN",
                  "GITHUB_TOKEN", "NOUS_API_KEY", "PYTHONPATH", "VIRTUAL_ENV", "SOME_RANDOM_VAR"):
            self.assertNotIn(k, env)
        self.assertEqual((env["PYTHONUTF8"], env["PYTHONIOENCODING"]), ("1", "utf-8"))

    def _envs_passed(self, fn):
        seen = []

        def fake_run(*a, **kw):
            seen.append(kw.get("env"))
            return subprocess.CompletedProcess(a[0], 0, '{"ok": true}', "")

        with patch.dict(os.environ, self.ENV, clear=True), patch.object(subprocess, "run", fake_run), \
                patch.object(subprocess, "Popen", lambda *a, **kw: seen.append(kw.get("env")) or type("P", (), {"pid": 1})()):
            fn()
        return seen

    def test_installer_run_and_detached(self):
        with tempfile.TemporaryDirectory() as d:
            seen = self._envs_passed(lambda: (installer._run(["x"]), installer._detached(["x"], Path(d) / "o", d)))
        self.assertEqual(len(seen), 2)
        for env in seen:
            self.assertIsNotNone(env)
            self.assertNotIn("OPENAI_API_KEY", env)
            self.assertIn("PATH", env)

    def test_comfy_cli_converter(self):
        with tempfile.TemporaryDirectory() as d:
            py = Path(d) / "python.exe"
            py.write_text("")
            with patch.object(core, "_converter_candidates", return_value=[str(py)]), \
                    patch.object(core, "_load_state", return_value={}), patch.object(core, "_save_state"), \
                    patch.object(core, "_object_info_path", return_value=Path(d) / "oi.json"):
                seen = self._envs_passed(lambda: (core.find_converter(refresh=True),
                                                  core._convert({"name": "t"}, {}, [])))
        self.assertEqual(len(seen), 2)
        for env in seen:
            self.assertIsNotNone(env)
            self.assertNotIn("ANTHROPIC_API_KEY", env)
            self.assertNotIn("PYTHONPATH", env)

    def test_no_child_process_copies_os_environ(self):
        for f in (ROOT / "plugin").glob("*.py"):
            text = f.read_text(encoding="utf-8")
            self.assertNotIn("os.environ.items()", text.replace("for k, v in os.environ.items():\n", "")
                             if f.name == "installer.py" else text, f.name)


class SafeHttpTests(unittest.TestCase):
    def test_blocked_literals_and_schemes(self):
        for url in ["http://169.254.169.254/latest/meta-data/", "https://169.254.169.254/", "https://10.0.0.1/x",
                    "https://192.168.1.2/x", "https://172.16.0.1/x", "https://100.64.0.1/x", "https://127.0.0.1/x",
                    "https://localhost/x", "https://[::1]/x", "https://[::ffff:127.0.0.1]/x", "https://[fe80::1]/x",
                    "https://[fd00::1]/x", "https://0.0.0.0/x", "http://example.com/x", "file:///etc/passwd",
                    "ftp://example.com/x", "", None]:
            with self.subTest(url=url), self.assertRaises(safe_http.BlockedURL):
                safe_http.check_url(url, resolve=False)

    def test_resolved_hosts(self):
        dns = fake_dns({"huggingface.co": ["18.239.50.16"], "evil.example": ["93.184.216.34", "169.254.169.254"],
                        "lan.example": ["192.168.1.20"], "v6.example": ["::1"]})
        with patch.object(socket, "getaddrinfo", dns):
            self.assertEqual(safe_http.check_url("https://huggingface.co/a"), "https://huggingface.co/a")
            for host in ("evil.example", "lan.example", "v6.example", "unknown.example"):
                with self.subTest(host=host), self.assertRaises(safe_http.BlockedURL):
                    safe_http.check_url(f"https://{host}/a")
            with self.assertRaises(safe_http.BlockedURL):  # the mirror setting admits loopback only
                safe_http.check_url("https://lan.example/a", allow_local=True)

    def test_local_mirror_needs_setting(self):
        with self.assertRaises(safe_http.BlockedURL):
            safe_http.check_url("http://127.0.0.1:8000/m")
        self.assertTrue(safe_http.check_url("http://127.0.0.1:8000/m", allow_local=True))
        self.assertTrue(safe_http.check_url("http://localhost:8000/m", allow_local=True))
        with self.assertRaises(safe_http.BlockedURL):
            safe_http.check_url("http://192.168.1.5/m", allow_local=True)

    def test_redirect_hop_to_metadata_is_refused(self):
        with redirect_server("http://169.254.169.254/latest/meta-data/") as (url, hits):
            with self.assertRaises(safe_http.BlockedURL):
                safe_http.urlopen(url + "/m", timeout=5, allow_local=True)
        self.assertEqual(len(hits), 1)

    def test_redirect_hop_to_private_name_is_refused_before_connecting(self):
        real = socket.getaddrinfo
        dns = lambda host, *a, **kw: fake_dns({"internal.example": ["10.1.2.3"]})(host, *a, **kw) \
            if host == "internal.example" else real(host, *a, **kw)
        with redirect_server("https://internal.example/secret") as (url, hits), \
                patch.object(socket, "getaddrinfo", dns), \
                patch.object(safe_http._GuardedHTTPSConnection, "connect", side_effect=AssertionError("connected")):
            with self.assertRaises(safe_http.BlockedURL):
                safe_http.urlopen(url + "/m", timeout=5, allow_local=True)

    def test_connected_peer_is_checked(self):
        """DNS rebinding: a name that passed the check but connects to an internal address is still refused."""
        with redirect_server("https://x/") as (url, _):
            port = int(url.rsplit(":", 1)[1])
            with self.assertRaises(safe_http.BlockedURL):
                safe_http._GuardedHTTPConnection("127.0.0.1", port, timeout=5).connect()
            conn = safe_http._GuardedHTTPConnection("127.0.0.1", port, timeout=5, allow_local=True)
            conn.connect()
            conn.close()

    def test_remote_size_blocks_without_request(self):
        with patch.object(safe_http, "opener", side_effect=AssertionError("request sent")):
            self.assertIsNone(dependencies.remote_size("https://169.254.169.254/latest/meta-data/"))
            self.assertIsNone(dependencies.remote_size("http://127.0.0.1:1/x"))

    def test_remote_size_redirect_hop_blocked(self):
        with redirect_server("http://169.254.169.254/") as (url, hits), \
                patch.dict(core.SETTINGS, {"allow_local_mirrors": True}):
            self.assertIsNone(dependencies.remote_size(url + "/m"))
        self.assertEqual(len(hits), 1)


class DownloadWorkerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.install = Path(self.tmp.name) / "install"
        self.models = Path(self.tmp.name) / "models"

    def tearDown(self):
        self.tmp.cleanup()

    def test_local_link_refused_without_setting(self):
        with self.assertRaises(ValueError):
            downloads.enqueue(self.install, self.models, [{"folder": "vae", "name": "v", "url": "http://127.0.0.1:9/v"}],
                              spawn=False)

    def test_blocked_redirect_is_a_final_error_without_retries(self):
        with redirect_server("http://169.254.169.254/latest/meta-data/") as (url, hits), \
                patch.object(downloads.time, "sleep") as sleep:
            downloads.enqueue(self.install, self.models, [{"folder": "vae", "name": "v.safetensors", "url": url + "/v"}],
                              spawn=False, allow_local=True)
            downloads.run(self.install)
        item = downloads._read(downloads._queue_path(self.install))["items"][0]
        self.assertEqual(item["state"], "error")
        self.assertIn("BlockedURL", item["error"])
        self.assertEqual(len(hits), 1)
        sleep.assert_not_called()
        self.assertFalse((self.models / "vae" / "v.safetensors").exists())


@unittest.skipUnless(HAVE_FFMPEG, "ffmpeg not on PATH")
class MediaOutputTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name) / "src"
        self.dir.mkdir()
        self.elsewhere = Path(self.tmp.name) / "elsewhere"
        self.elsewhere.mkdir()
        self.png = self.dir / "still.png"
        subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=128x96", "-frames:v", "1",
                        str(self.png)], check=True)

    def tearDown(self):
        self.tmp.cleanup()

    def test_absolute_or_escaping_out_is_refused(self):
        for out in (str(self.elsewhere / "x.png"), "../elsewhere/x.png"):
            with self.subTest(out=out), self.assertRaises(ValueError):
                media.convert(str(self.png), width=64, out=out)
        with self.assertRaises(ValueError):
            media.frames(str(self.png), ["first"], out_dir=str(self.elsewhere))
        self.assertEqual(list(self.elsewhere.iterdir()), [])

    def test_allowed_roots_admit_plugin_and_instance_folders(self):
        r = media.handle({"action": "convert", "path": str(self.png), "width": 64, "out": str(self.elsewhere / "x.png")},
                         allowed_roots=lambda: [self.elsewhere])
        self.assertEqual(Path(r["output"]["path"]), (self.elsewhere / "x.png").resolve())
        with self.assertRaises(ValueError):  # the roots apply to that call only
            media.convert(str(self.png), width=64, out=str(self.elsewhere / "y.png"))

    def test_existing_files_are_never_overwritten(self):
        mine = self.dir / "keep.png"
        mine.write_bytes(b"user file")
        with self.assertRaises(FileExistsError):
            media.convert(str(self.png), width=64, out="keep.png")
        self.assertEqual(mine.read_bytes(), b"user file")
        a = media.convert(str(self.png), width=64)["output"]["path"]
        b = media.convert(str(self.png), width=64)["output"]["path"]
        self.assertNotEqual(a, b)
        self.assertTrue(Path(b).name.endswith("_1.png"))
        self.assertFalse([p for p in self.dir.iterdir() if ".part" in p.name])

    def test_render_never_replaces_a_target_that_appears(self):
        target = self.dir / "race.png"

        def run_then_appear(args):
            subprocess.run(args, check=True, capture_output=True)
            target.write_bytes(b"appeared")

        with patch.object(media, "_run", run_then_appear), self.assertRaises(FileExistsError):
            media.convert(str(self.png), width=64, out="race.png")
        self.assertEqual(target.read_bytes(), b"appeared")
        self.assertFalse([p for p in self.dir.iterdir() if ".part" in p.name])

    def test_no_dash_y_in_media(self):
        self.assertNotIn('"-y"', (ROOT / "plugin" / "media.py").read_text(encoding="utf-8"))


class TemplateNameTests(unittest.TestCase):
    def test_traversal_names_rejected_before_any_request(self):
        with patch.object(templates.cc, "_req", side_effect=AssertionError("request sent")):
            for name in ("../x", "a/b", "a\\b", "..", "", "C:x", None):
                with self.subTest(name=name), self.assertRaises(ValueError):
                    templates._template_json({"url": "http://127.0.0.1:1", "name": "t"}, name)

    def test_bad_thumbnail_names_skip_the_cache(self):
        with patch.object(templates.cc, "_req", side_effect=AssertionError("request sent")):
            r = templates._thumbnail({"url": "http://127.0.0.1:1", "name": "t"}, {"name": "../evil", "mediaSubtype": "png"})
        self.assertNotIn("thumbnail_path", r)


if __name__ == "__main__":
    unittest.main()

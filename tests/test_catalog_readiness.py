"""Admission regressions; offline fixtures, never execute downloaded payloads."""
import hashlib
import io
import sys
import tarfile
import tempfile
import unittest
import zipfile
import yaml
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import plugin
from plugin import installer


class BootstrapTests(unittest.TestCase):
    def _download(self, root, payload, digest=None):
        name = 'uv-x86_64-pc-windows-msvc.zip'
        pins = {name: digest or hashlib.sha256(payload).hexdigest()}
        def retrieve(url, dest):
            self.assertIn('/releases/download/' + installer.UV_VERSION + '/', url)
            self.assertNotIn('/latest/', url)
            Path(dest).write_bytes(payload)
        with patch.object(installer, 'UV_SHA256', pins), \
             patch.object(installer, 'IS_WIN', True), \
             patch.object(installer.platform, 'machine', return_value='AMD64'), \
             patch.object(installer.request, 'urlretrieve', side_effect=retrieve):
            return installer._download_uv(root, lambda _: None)

    def test_checksum_mismatch_never_extracts(self):
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(installer.zipfile, 'ZipFile') as extract:
            with self.assertRaisesRegex(RuntimeError, 'checksum'):
                self._download(Path(tmp), b'tampered', '0' * 64)
            extract.assert_not_called()
            self.assertFalse((Path(tmp) / 'uv.exe').exists())

    def test_verified_archive_copies_only_expected_executable(self):
        data = io.BytesIO()
        with zipfile.ZipFile(data, 'w') as archive:
            archive.writestr('uv.exe', b'fixture-not-executable')
            archive.writestr('../escape.txt', b'must not be extracted')
            archive.writestr('unrelated.dll', b'must not be extracted')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'tools'
            exe = self._download(root, data.getvalue())
            self.assertEqual(Path(exe).read_bytes(), b'fixture-not-executable')
            self.assertFalse((Path(tmp) / 'escape.txt').exists())
            self.assertFalse((root / 'unrelated.dll').exists())

    def test_unsupported_arch_fails_before_network(self):
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(installer.platform, 'machine', return_value='mips'), \
             patch.object(installer.request, 'urlretrieve') as retrieve:
            with self.assertRaisesRegex(RuntimeError, 'Unsupported'):
                installer._download_uv(Path(tmp), lambda _: None)
            retrieve.assert_not_called()

    def test_tar_symlink_is_not_an_executable(self):
        data = io.BytesIO()
        with tarfile.open(fileobj=data, mode='w:gz') as archive:
            member = tarfile.TarInfo('uv-x86_64-unknown-linux-gnu/uv')
            member.type = tarfile.SYMTYPE
            member.linkname = '/etc/passwd'
            archive.addfile(member)
        name = 'uv-x86_64-unknown-linux-gnu.tar.gz'
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(installer, 'IS_WIN', False), \
             patch.object(installer.sys, 'platform', 'linux'), \
             patch.object(installer.platform, 'machine', return_value='x86_64'), \
             patch.object(installer, 'UV_SHA256', {name: hashlib.sha256(data.getvalue()).hexdigest()}), \
             patch.object(installer.request, 'urlretrieve', side_effect=lambda url, dest: Path(dest).write_bytes(data.getvalue())):
            with self.assertRaisesRegex(RuntimeError, 'regular file'):
                installer._download_uv(Path(tmp), lambda _: None)

    def test_detached_closes_parent_log_handle(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(installer.subprocess, 'Popen') as popen:
            installer._detached(['fixture'], Path(tmp) / 'worker.log', cwd=tmp)
            self.assertTrue(popen.call_args.kwargs['stdout'].closed)


class PublicSurfaceTests(unittest.TestCase):
    def test_session_db_is_public_profile_scoped_and_closed(self):
        db = MagicMock()
        cls = MagicMock(return_value=db)
        home = Path('isolated-profile')
        with patch.dict(sys.modules, {
            'hermes_state': SimpleNamespace(SessionDB=cls),
            'hermes_constants': SimpleNamespace(get_hermes_home=lambda: home),
        }):
            plugin._with_session_db(lambda handle: handle.set_session_title('s', 'title'))
        cls.assert_called_once_with(db_path=home / 'state.db')
        db.set_session_title.assert_called_once_with('s', 'title')
        db.close.assert_called_once()

    def test_no_private_core_imports(self):
        source = Path(plugin.__file__).read_text(encoding='utf-8')
        self.assertNotIn('from tools import desktop_ui', source)
        self.assertNotIn('import hermes_state_registry', source)

    def test_kickoff_routes_through_agent_preview_tool(self):
        inst = {'any_running': True, 'instances': [{'name': 'test', 'active': True, 'url': 'http://test'}]}
        with patch.object(plugin, '_sync_settings'), \
             patch.object(plugin.core, 'setup_state', return_value={'phase': 'running'}), \
             patch.object(plugin.core, 'instances', return_value=inst), \
             patch.object(plugin.core, 'bind_to_hermes'), \
             patch.object(plugin.core, 'ensure_managed_library', return_value={'status': 'skipped'}):
            text = plugin._session_start('')
        self.assertIn('Call desktop_preview open', text)
        self.assertNotIn('ALREADY opened', text)


class SubmissionTests(unittest.TestCase):
    def test_entry_matches_manifest_and_pins_every_screenshot(self):
        from scripts.prepare_catalog import ROOT, render_entry
        manifest = yaml.safe_load((ROOT / 'plugin/plugin.yaml').read_text(encoding='utf-8'))
        # A syntax-only fixture pin; not a claim this commit exists upstream.
        sha = 'a' * 40
        text = render_entry(manifest, sha)
        entry = yaml.safe_load(text)
        self.assertIn('version: "' + manifest['version'] + '"', text)
        self.assertEqual(entry['requires_hermes'], manifest['requires_hermes'])
        self.assertEqual(entry['subdir'], 'plugin')
        self.assertEqual(entry['tier'], 'community')
        self.assertEqual(entry['sha'], sha)
        for key in ('provides_tools', 'provides_hooks', 'provides_middleware', 'requires_env'):
            self.assertEqual(entry['capabilities'][key], manifest.get(key) or [])
        for url in entry['screenshots']:
            path = url.split('/' + sha + '/', 1)[1]
            self.assertTrue((ROOT / path).is_file())

    def test_entry_rejects_nonliteral_commit_pins(self):
        from scripts.prepare_catalog import render_entry
        for sha in ['main', 'v0.4.0', 'a' * 7, 'a' * 39, 'a' * 41]:
            with self.subTest(sha=sha), self.assertRaises(ValueError):
                render_entry({}, sha)

    def test_generator_refuses_dirty_worktree_before_reading_manifest(self):
        from scripts import prepare_catalog
        with patch.object(prepare_catalog, 'git', return_value=' M plugin/plugin.yaml') as git, \
             patch.object(prepare_catalog, 'render_entry') as render:
            self.assertEqual(prepare_catalog.main(), 1)
        git.assert_called_once_with('status', '--porcelain', '--untracked-files=all')
        render.assert_not_called()

    def test_generator_uses_clean_committed_tree(self):
        from scripts import prepare_catalog
        sha = 'b' * 40
        manifest = (prepare_catalog.ROOT / 'plugin/plugin.yaml').read_text(encoding='utf-8')
        def git(*args):
            if args[0] == 'status': return ''
            if args[0] == 'rev-parse': return sha
            if args[0] == 'show': return manifest
            if args[0] == 'cat-file': return ''
            raise AssertionError(args)
        with patch.object(prepare_catalog, 'git', side_effect=git), \
             patch.object(prepare_catalog, 'print') as output:
            self.assertEqual(prepare_catalog.main(), 0)
        entry = yaml.safe_load(output.call_args.args[0])
        self.assertEqual(entry['sha'], sha)

    def test_catalog_subdir_readme_links_resolve_and_disclosures_exist(self):
        import re
        root = Path(plugin.__file__).resolve().parent
        text = (root / 'README.md').read_text(encoding='utf-8')
        for target in re.findall(r'\]\(([^)]+)\)', text):
            if not target.startswith(('https://', 'http://', '#')):
                self.assertTrue((root / target).is_file(), target)
        for name in ('README.md', '../README.md'):
            content = (root / name).read_text(encoding='utf-8').lower()
            for disclosure in ('network', 'credentials', 'stored data', 'telemetry', 'background', 'sha-256'):
                self.assertIn(disclosure, content)

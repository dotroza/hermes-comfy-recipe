"""Exercise the shipped browser startup callback, without touching real browser storage."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from plugin import library


class StartupTabsTests(unittest.TestCase):
    def test_fresh_browser_opens_text_to_image_first_and_selected(self):
        self.run_browser_check("""
          extension.init();
          const tabs = JSON.parse(localStorage.getItem('Comfy.Workflow.LastOpenPaths:personal'));
          assert.equal(tabs.activeIndex, 0);
          assert.equal(tabs.paths[0], 'workflows/Comfy Recipe/RCP_qwen_image_2_1_t2i.json');
          assert.equal(tabs.paths.length, 6);
          assert.equal(new Set(tabs.paths).size, 6);
          assert.equal(JSON.parse(localStorage.getItem('Comfy.Workflow.LastActivePath:personal')).path, tabs.paths[0]);
        """)

    def test_workflow_preferences_do_not_count_as_saved_work(self):
        self.run_browser_check("""
          localStorage.setItem('Comfy.Workflow.WorkflowTabsPosition', 'Top');
          localStorage.setItem('Comfy.Workflow.AutoSave', 'true');
          extension.init();
          const tabs = JSON.parse(localStorage.getItem('Comfy.Workflow.LastOpenPaths:personal'));
          assert.ok(tabs, 'UI preferences must not prevent first-launch tabs');
          assert.equal(tabs.paths[0], 'workflows/Comfy Recipe/RCP_qwen_image_2_1_t2i.json');
          assert.equal(localStorage.getItem('Comfy.Workflow.AutoSave'), 'true');
        """)

    def test_empty_draft_index_is_still_a_fresh_browser(self):
        self.run_browser_check("""
          localStorage.setItem('Comfy.Workflow.DraftIndex.v2:personal', JSON.stringify({order: [], entries: {}}));
          extension.init();
          assert.ok(localStorage.getItem('Comfy.Workflow.LastOpenPaths:personal'));
        """)

    def test_existing_tabs_drafts_and_legacy_sessions_are_untouched(self):
        self.run_browser_check("""
          for (const [key, value] of [
            ['Comfy.Workflow.LastOpenPaths:personal', '{"paths":["mine"],"activeIndex":0}'],
            ['Comfy.Workflow.DraftIndex.v2:personal', '{"order":["draft"],"entries":{}}'],
            ['workflow', '{"nodes":[]}']
          ]) {
            localStorage.data.clear(); sessionStorage.data.clear();
            localStorage.setItem(key, value);
            extension.init();
            assert.deepEqual([...localStorage.data], [[key, value]]);
          }
          localStorage.data.clear();
          sessionStorage.setItem('Comfy.Workflow.OpenPaths:old-client', 'existing');
          extension.init();
          assert.equal(localStorage.length, 0);
          assert.equal(sessionStorage.getItem('Comfy.Workflow.OpenPaths:old-client'), 'existing');
        """)

    def test_second_launch_does_not_reselect_or_reorder(self):
        self.run_browser_check("""
          extension.init();
          const mine = JSON.stringify({workspaceId:'personal', paths:['mine','other'], activeIndex:1});
          localStorage.setItem('Comfy.Workflow.LastOpenPaths:personal', mine);
          localStorage.setItem('Comfy.Workflow.LastActivePath:personal', 'other');
          extension.init();
          assert.equal(localStorage.getItem('Comfy.Workflow.LastOpenPaths:personal'), mine);
          assert.equal(localStorage.getItem('Comfy.Workflow.LastActivePath:personal'), 'other');
        """)

    def test_unavailable_storage_does_not_break_startup(self):
        self.run_browser_check("""
          localStorage.getItem = () => { throw new Error('blocked'); };
          assert.doesNotThrow(() => extension.init());
        """)

    def run_browser_check(self, assertions):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            library.provision_startup(root)
            package = root / 'custom_nodes' / 'hermes_comfy_recipe_startup'
            compile((package / '__init__.py').read_text(), str(package / '__init__.py'), 'exec')
            source = (package / 'web' / 'startup.js').read_text(encoding='utf-8')
            script = r"""
              const assert = require('node:assert/strict');
              const vm = require('node:vm');
              class Storage {
                constructor() { this.data = new Map(); }
                get length() { return this.data.size; }
                key(i) { return [...this.data.keys()][i] ?? null; }
                getItem(k) { return this.data.get(k) ?? null; }
                setItem(k, v) { this.data.set(k, String(v)); }
              }
              const localStorage = new Storage(), sessionStorage = new Storage();
              let extension;
              const app = { registerExtension(value) { extension = value; } };
              const source = SOURCE.replace(/^import .*;?\s*$/mg, '');
              vm.runInNewContext(source, { app, localStorage, sessionStorage, console });
              ASSERTIONS
            """.replace('SOURCE', json.dumps(source)).replace('ASSERTIONS', assertions)
            result = subprocess.run(['node', '-e', script], text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

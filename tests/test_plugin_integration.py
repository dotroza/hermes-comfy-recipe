import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import plugin
from plugin import core

class StartupTests(unittest.TestCase):
    def test_managed_start_provisions_tabs_before_server_starts(self):
        events = []
        with patch.object(core, '_managed_dir', return_value=Path('managed')), \
             patch.object(core.installer, 'manifest', return_value={'port':8190}), \
             patch('plugin.library.provision_startup', side_effect=lambda root: events.append(('tabs', root))), \
             patch.object(core.installer, 'start', side_effect=lambda *args: events.append(('server', args[0])) or {'running':True}), \
             patch.object(core, 'bind_to_hermes', return_value={}), \
             patch.object(core, 'ensure_managed_library', return_value={}):
            core.setup_start()
        self.assertEqual(events, [('tabs', Path('managed') / 'ComfyUI'), ('server', Path('managed'))])

    def test_managed_start_attaches_library_without_losing_health(self):
        with patch.object(core,'_managed_dir',return_value=Path('managed')), patch.object(core.installer,'manifest',return_value={'port':8190}), \
             patch.object(core.installer,'start',return_value={'running':True,'url':'http://test'}), \
             patch.object(core,'bind_to_hermes',return_value={'status':'test'}), \
             patch.object(core,'ensure_managed_library',return_value={'counts':{'installed':6}}):
            r=core.setup_start()
        self.assertTrue(r['running']); self.assertEqual(r['library']['counts'],{'installed':6})

    def test_foreign_setup_never_auto_publishes(self):
        with patch.object(core,'_load_state',return_value={'setup':'existing'}), patch('plugin.library.publish') as publish:
            result=core.ensure_managed_library()
        self.assertEqual(result['status'],'skipped'); publish.assert_not_called()

    def setUp(self):
        provision = patch('plugin.library.provision_startup')
        provision.start()
        self.addCleanup(provision.stop)
        core._LIBRARY_SYNC.clear()

    def tearDown(self):
        core._LIBRARY_SYNC.clear()

    def test_start_library_failure_does_not_change_server_health(self):
        with patch.object(core,'_managed_dir',return_value=Path('managed')), patch.object(core.installer,'manifest',return_value={'port':8190}), \
             patch.object(core.installer,'start',return_value={'running':True,'url':'http://test'}), \
             patch.object(core,'bind_to_hermes',return_value={'status':'test'}), \
             patch.object(core,'ensure_managed_library',side_effect=RuntimeError('library unavailable')):
            r=core.setup_start()
        self.assertTrue(r['running']); self.assertEqual(r['library']['status'],'error')

    def test_offline_and_managed_publication_is_cached_only_after_complete(self):
        st={'setup':'managed','managed':{'dir':'managed'}}
        inst={'name':'comfy-recipe','url':'http://test','root':'managed/ComfyUI'}
        with patch.object(core,'_load_state',return_value=st), patch.object(core,'_managed_instance',return_value=inst), \
             patch.object(core.installer,'server_running',return_value=True), patch.object(core.cc,'alive',return_value={'system':{}}), \
             patch('plugin.library.publish',return_value={'complete':True,'counts':{'installed':6}}) as publish:
            self.assertEqual(core.ensure_managed_library()['counts'],{'installed':6})
            self.assertEqual(core.ensure_managed_library()['status'],'already_checked_this_process')
            self.assertEqual(publish.call_count,1)
        with patch.object(core,'_load_state',return_value=st), patch.object(core,'_managed_instance',return_value=inst), \
             patch.object(core.installer,'server_running',return_value=False), patch('plugin.library.publish') as publish:
            self.assertEqual(core.ensure_managed_library()['status'],'skipped'); publish.assert_not_called()

class ToolTests(unittest.TestCase):
    def test_library_listing_works_without_active_backend(self):
        with patch.object(core,'active',side_effect=AssertionError('must be offline')):
            r=plugin._workflows({'action':'library'})
        self.assertEqual(len(r['workflows']),6)
        self.assertEqual(r['source'],'bundled_library')

    def test_install_dispatch_is_explicit(self):
        with patch.object(core,'_inst',return_value={'url':'http://test'}), patch('plugin.library.publish',return_value={'complete':True}) as publish:
            r=plugin._workflows({'action':'install','workflow_ids':['qwen-image-2-1-t2i'],'versioned':True})
        self.assertTrue(r['complete']); self.assertEqual(publish.call_args.kwargs['workflow_ids'],['qwen-image-2-1-t2i'])
        self.assertTrue(publish.call_args.kwargs['versioned'])

    def test_check_is_bundled_and_refreshes_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            info=Path(tmp)/'info.json'; info.write_text('{}')
            with patch.object(core,'_inst',return_value={'url':'http://test'}), \
                 patch.object(core,'_object_info_path',return_value=info) as refresh, \
                 patch('plugin.dependencies.check',return_value={'definition':{},'workflow_id':'qwen-image-2-1-t2i'}), \
                 patch.object(core.cc,'list_workflows',return_value=[]):
                r=plugin._workflows({'action':'check','workflow':'qwen-image-2-1-t2i'})
            self.assertEqual(r['workflow_id'],'qwen-image-2-1-t2i')
            self.assertEqual(r['definition']['working_copy'],'missing')
            self.assertTrue(refresh.call_args.kwargs['refresh'])

    def test_native_registration_keeps_session_and_all_tools(self):
        class Context:
            def __init__(self): self.skills=[]; self.tools=[]
            def register_tool(self,**kw): self.tools.append(kw['name'])
            def register_skill(self,name,path,**kw): self.skills.append(name)
            def register_hook(self,*a,**k): pass
            def register_command(self,*a,**k): pass
        ctx=Context(); old=plugin._CTX
        try: plugin.register(ctx)
        finally: plugin._CTX=old
        self.assertIn('session',ctx.skills); self.assertEqual(set(ctx.tools),set(plugin.SCHEMAS))
        self.assertIn('library',plugin.SCHEMAS['comfy_workflows']['parameters']['properties']['action']['enum'])

    def test_running_session_calls_managed_guard(self):
        inst={'any_running':True,'instances':[{'name':'test','active':True,'url':'http://test'}]}
        with patch.object(plugin,'_sync_settings'), patch.object(core,'setup_state',return_value={'phase':'running'}), \
             patch.object(core,'instances',return_value=inst), patch.object(plugin,'_open_pane_now',return_value=False), \
             patch.object(core,'ensure_managed_library',return_value={'status':'skipped'}) as ensure:
            text=plugin._session_start('')
        ensure.assert_called_once(); self.assertIn('ComfyUI facts',text)


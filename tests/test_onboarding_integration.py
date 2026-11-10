import json
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch
import plugin
from plugin import core,onboarding


class FlowTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.m={'install_id':str(uuid.uuid4()),'onboarding_version':1,
                                            'port':8190,'comfyui_dir':str(self.root/'ComfyUI')}
        self.managed={'name':core.MANAGED_NAME,'url':'http://127.0.0.1:8190','root':self.m['comfyui_dir']}
        self.patches=[patch.object(core,'DATA',self.root),patch.object(core,'_managed_dir',return_value=self.root),
                      patch.object(core.installer,'manifest',return_value=self.m),
                      patch.object(core,'_load_state',return_value={'setup':'managed','managed':{'dir':str(self.root)},
                                                                  'active':core.MANAGED_NAME,'instances':{core.MANAGED_NAME:self.managed}})]
        for p in self.patches:p.start();self.addCleanup(p.stop)

    def test_versioned_sibling_publication_prepare_and_complete(self):
        from plugin import onboarding_flow as flow,library
        from http_fixture import comfy_server
        from test_tutorial_evidence import history
        with comfy_server() as env:
            inst,files,*_=env
            inst=dict(inst,name=core.MANAGED_NAME)
            onboarding.status(self.root,self.m,'A');onboarding.tutorial(self.root,self.m,'A')
            published=library.publish(inst,self.root/'publication',workflow_ids=['qwen-image-2-1-t2i'],versioned=True)
            target=published['workflows'][0]['path']
            saved=files['workflows/'+target]
            base=library.load_asset(next(e for e in library.load_catalog()['workflows'] if e['id']=='qwen-image-2-1-t2i'))
            self.assertNotEqual(saved['id'],base['id'])
            # The fixture contains only the versioned sibling, never the base copy.
            with patch.object(flow,'managed_backend',return_value=inst,create=True), \
                 patch.object(core,'_inst',return_value=inst), \
                 patch.object(core.cc,'get_json',return_value={}), \
                 patch('plugin.onboarding.time.time',return_value=1):
                prepared=flow.handle({'action':'tutorial','begin_run':True,'workflow_path':target,'prompt':'a red kite'},'A')
            self.assertEqual(prepared['tutorial']['workflow_id'],saved['id'])
            with patch.object(flow,'managed_backend',return_value=inst,create=True),patch.object(core,'_inst',return_value=inst), \
                 patch.object(core.cc,'history',return_value=history(saved['id'])), \
                 patch.object(core.cc,'view_bytes',return_value=b'\x89PNG\r\n\x1a\nimage'):
                self.assertEqual(flow.handle({'action':'complete','prompt_id':'job'},'A')['tutorial']['state'],'completed')

    def test_foreign_active_instance_is_rejected_before_readiness(self):
        from plugin import onboarding_flow as flow
        from test_onboarding_dependencies import report
        st={'setup':'managed','managed':{'dir':str(self.root)},'active':'foreign',
            'instances':{'foreign':{'url':'http://foreign','root':'elsewhere'}}}
        with patch.object(core,'_load_state',return_value=st),patch.object(flow,'reports',return_value=[report()]), \
             patch.object(flow.dependencies,'cached_size_lookup',return_value=lambda u:1):
            with self.assertRaisesRegex(ValueError,'instance|backend'):
                flow.handle({'action':'status'},'A')

    def test_other_graph_or_escaping_workflow_path_is_rejected(self):
        from plugin import onboarding_flow as flow
        onboarding.status(self.root,self.m,'A');onboarding.tutorial(self.root,self.m,'A')
        for target in ['../outside.json','Comfy Recipe/../RCP_qwen_image_2_1_t2i.json',
                       'Comfy Recipe/RCP_qwen_image_2_1_i2i.json',
                       'C:/outside.json','Comfy Recipe/RCP_qwen_image_2_1_t2i-vBAD.json']:
            with self.subTest(path=target),patch.object(core.cc,'load_workflow') as read:
                with self.assertRaisesRegex(ValueError,'working copy'):
                    flow.handle({'action':'tutorial','begin_run':True,'workflow_path':target,'prompt':'a kite'},'A')
                read.assert_not_called()

    def test_switch_after_preparation_does_not_read_foreign_history(self):
        from plugin import onboarding_flow as flow
        onboarding.status(self.root,self.m,'A');onboarding.tutorial(self.root,self.m,'A')
        with patch.object(core.cc,'load_workflow',return_value={'id':'wf'}),patch.object(core.cc,'get_json',return_value={}):
            flow.handle({'action':'tutorial','begin_run':True,'prompt':'a kite'},'A')
        st={'setup':'managed','managed':{'dir':str(self.root)},'active':'foreign','instances':{}}
        with patch.object(core,'_load_state',return_value=st),patch.object(core.cc,'history') as read:
            with self.assertRaisesRegex(ValueError,'instance|backend'):
                flow.handle({'action':'complete','prompt_id':'job'},'A')
            read.assert_not_called()

    def test_managed_name_with_foreign_root_is_rejected(self):
        from plugin import onboarding_flow as flow
        st={'setup':'managed','managed':{'dir':str(self.root)},'active':core.MANAGED_NAME,
            'instances':{core.MANAGED_NAME:dict(self.managed,root=str(self.root/'other'))}}
        with patch.object(core,'_load_state',return_value=st):
            with self.assertRaisesRegex(ValueError,'root.*backend'):
                flow.managed_backend()

    def test_catalog_media_requirements_survive_status_aggregation(self):
        from plugin import onboarding_flow as flow
        info=self.root/'info.json';info.write_text('{}')
        def inventory(url,path): return {} if path=='/settings' else []
        with patch.object(core,'_inst',return_value=self.managed),patch.object(core,'_object_info_path',return_value=info), \
             patch.object(core.cc,'get_json',side_effect=inventory), \
             patch('plugin.downloads.installed_packs',return_value=set()), \
             patch.object(flow.dependencies,'cached_size_lookup',return_value=lambda u:None):
            rows=flow.reports()
            expected=sum(len([x for x in row['inputs'] if x['status']=='needs_user_media']) for row in rows)
            result=flow.handle({'action':'status'},'A')['proposal']
        self.assertGreater(expected,0)
        self.assertEqual(len(result['missing_media']),expected)
        self.assertTrue(all(x.get('workflow_id') for x in result['missing_media']))

    def test_tool_registered_and_trusted_session_required(self):
        self.assertIn('comfy_onboarding',plugin.SCHEMAS)
        result=json.loads(plugin._onboarding_handler({'action':'skip'}))
        self.assertFalse(result['success'])
        self.assertNotIn('session_id',plugin.SCHEMAS['comfy_onboarding']['parameters']['properties'])

    def test_command_replay_routes_next_description_without_marker(self):
        try:
            from hermes_cli.plugin_command_dispatch import invoke_plugin_command
        except ImportError:self.skipTest('Hermes SDK not installed')
        intro=invoke_plugin_command(plugin._command,'tutorial',session_id='fresh-chat',platform='desktop')
        self.assertIn('Describe',intro)
        self.assertNotIn('skill_view',intro)
        text=plugin._pre_llm_call(user_message='a red kite over the sea',session_id='fresh-chat',conversation_history=[])
        self.assertIn('first-image-tutorial',text['context'])
        self.assertIn('qwen-image-2-1-prompting',text['context'])

    def test_natural_tutorial_skip_and_unrelated_chat(self):
        self.assertIsNone(plugin._pre_llm_call(user_message='tutorial',session_id='unrelated',conversation_history=[]))
        hist=[{'role':'user','content':'[ComfyUI session]'}]
        r=plugin._pre_llm_call(user_message='tutorial',session_id='A',conversation_history=hist)
        self.assertIn('first-image-tutorial',r['context'])
        r=plugin._pre_llm_call(user_message='skip tutorial',session_id='A',conversation_history=hist)
        self.assertIn('What would you like to do',r['context'])
        self.assertEqual(onboarding.status(self.root,self.m,'A')['tutorial']['state'],'skipped')

    def test_second_session_ordinary_and_same_session_not_second(self):
        from plugin import onboarding_flow as flow
        self.assertIn('setup_choices',flow.context('A'))
        self.assertIn('setup_choices',flow.context('A'))
        self.assertEqual(flow.context('B'),'')

    def test_all_preference_combinations_have_scoped_next_steps(self):
        from plugin import onboarding_flow as flow
        onboarding.status(self.root,self.m,'A')
        queued=[]; installs=[]; applied=[]
        prop={'models':[{'folder':'vae','name':'v.safetensors','url':'https://x/v'}],
              'node_packs':[{'id':'was-ns','name':'WAS Node Suite (Revised)'}],
              'settings':[{'id':'Comfy.VueNodes.Enabled','value':True}]}
        with patch.object(flow,'_proposal',return_value=prop), \
             patch.object(flow.download_flow,'queue',side_effect=lambda d,r,m:queued.append(m) or {'state':'pending','progress_card':'MEDIA:x'}), \
             patch.object(flow.download_flow,'install_nodes',side_effect=lambda i,d,p:installs.append(p) or {'state':'running','progress_card':'MEDIA:n'}), \
             patch.object(flow.core,'apply_settings',side_effect=lambda u,rows:applied.append(rows) or {'applied':[r['id'] for r in rows]}):
            for n,m in [('now','now'),('now','on_use'),('on_use','now'),('on_use','on_use')]:
                for st in ('apply','skip'):
                    r=flow.handle({'action':'preferences','nodes':n,'models':m,'settings':st},'A')
                    text=r['instruction']
                    self.assertEqual(r['approved_categories'],[key for key,value in [('nodes',n),('models',m)] if value=='now'])
                    self.assertIn('comfy_onboarding action=tutorial',text)
                    self.assertNotIn('Install All',text)
                    if m=='now': self.assertEqual(r['downloads']['progress_card'],'MEDIA:x')
                    else: self.assertNotIn('downloads',r)
                    if n=='now':
                        order=[text.index(t) for t in ('Do NOT open the Nodes Manager','nodes_status wait_s=300',
                               'comfy_setup action=restart','desktop_preview action=close','status refresh=true',
                               'comfy_onboarding action=tutorial')]
                        self.assertEqual(order,sorted(order))
                    else:
                        self.assertNotIn('comfy_setup action=restart',text)
                    if st=='apply':
                        self.assertIn('shows Nodes 2.0',text)
                    else:
                        self.assertNotIn('settings',r); self.assertNotIn('Nodes 2.0',text)
        self.assertEqual(len(queued),4); self.assertEqual(len(installs),4); self.assertEqual(len(applied),4)
        self.assertEqual(installs[0],prop['node_packs'])

    def test_proposal_combines_six_reports_and_no_download(self):
        from plugin import onboarding_flow as flow
        from test_onboarding_dependencies import report
        with patch.object(flow,'reports',return_value=[report()]*6),patch.object(flow.dependencies,'cached_size_lookup',return_value=lambda u:100):
            r=flow.handle({'action':'status'},'A')
        self.assertEqual(r['proposal']['download_bytes'],100)
        self.assertEqual(len(r['proposal']['models']),1)

import unittest
from unittest.mock import patch
from plugin import dependencies

class DependencyTests(unittest.TestCase):
    def test_core_subgraph_ui_and_custom_nodes(self):
        workflow={'nodes':[{'type':'sub'},{'type':'MarkdownNote'},{'type':'Frontend'},{'type':'MissingCustom'},{'type':'Mystery'}],
                  'definitions':{'subgraphs':[{'id':'sub','nodes':[{'type':'Core'}]}]}}
        entry={'id':'test','requirements':{'core_node_types':['Core'],
               'frontend_nodes':[{'type':'Frontend','pack_id':'verified-pack'}],
               'custom_node_packs':[{'id':'verified-pack','node_types':['MissingCustom'],'tested_version':None}]}}
        r=dependencies.check({'url':'http://unused'},entry,workflow,{'Core':{}})
        self.assertEqual(r['nodes']['missing_core'],[])
        self.assertEqual(r['nodes']['missing_packs'][0]['id'],'verified-pack')
        self.assertEqual(r['nodes']['missing_packs'][0]['missing_node_types'],['MissingCustom'])
        self.assertEqual(r['nodes']['unresolved'],['Mystery'])
        self.assertEqual(r['nodes']['frontend_checks'][0]['type'],'Frontend')
        self.assertEqual(r['execution_ready'],'not_tested')

    def test_selected_models_not_unused_metadata_alternatives(self):
        wf={'nodes':[{'type':'Core','properties':{'models':[{'name':'unused.safetensors','directory':'vae'}]}}]}
        e={'id':'test','requirements':{'models':[{'folder':'vae','name':'chosen.safetensors','url':'https://example.invalid/model'}]}}
        with patch.object(dependencies.cc,'get_json',return_value=['chosen.safetensors']) as get:
            r=dependencies.check({'url':'http://unused'},e,wf,{'Core':{}})
        self.assertEqual([x['name'] for x in r['models']],['chosen.safetensors'])
        self.assertEqual(r['models'][0]['status'],'available')
        self.assertEqual(get.call_count,1)

    def test_outage_is_unknown_not_missing_and_bad_paths_fail(self):
        e={'id':'test','requirements':{'models':[{'folder':'vae','name':'x.safetensors'}]}}
        with patch.object(dependencies.cc,'get_json',side_effect=dependencies.cc.ComfyError('offline')):
            r=dependencies.check({'url':'http://unused'},e,{'nodes':[]},{})
        self.assertEqual(r['models'][0]['status'],'unknown')
        e['requirements']['models'][0]['name']='../escape.safetensors'
        with self.assertRaises(ValueError): dependencies.check({'url':'http://unused'},e,{'nodes':[]},{})

    def test_media_service_and_missing_core_are_explicit(self):
        e={'id':'test','requirements':{'core_node_types':['MissingCore'],
           'inputs':[{'node':1,'type':'LoadImage','filename':'author.jpg','connected':True}],
           'services':[{'name':'Example paid service','paid':True}]}}
        info={'LoadImage':{'input':{'required':{'image':[['other.png']]}}}}
        r=dependencies.check({'url':'http://unused'},e,{'nodes':[{'type':'MissingCore'},{'type':'LoadImage'}]},info)
        self.assertEqual(r['nodes']['missing_core'],['MissingCore'])
        self.assertEqual(r['inputs'][0]['status'],'needs_user_media')
        self.assertEqual(r['services'][0]['credentials_status'],'not_checked')
        self.assertTrue(r['installation_plan']['requires_consent'])

    def test_refreshed_backend_evidence_changes_report(self):
        e={'id':'test','requirements':{'custom_node_packs':[{'id':'pack','node_types':['NewNode']}]}}
        wf={'nodes':[{'type':'NewNode'}]}
        self.assertTrue(dependencies.check({'url':'http://unused'},e,wf,{})['nodes']['missing_packs'])
        self.assertFalse(dependencies.check({'url':'http://unused'},e,wf,{'NewNode':{}})['nodes']['missing_packs'])


    def test_frontend_settings_and_single_combined_proposal(self):
        e={'id':'test','requirements':{
            'custom_node_packs':[{'id':'pack-a','name':'Pack A','node_types':['A']},{'id':'pack-b','node_types':['B']}],
            'frontend_settings':[{'id':'Comfy.VueNodes.Enabled','value':True,'label':'Nodes 2.0'}],
            'models':[{'folder':'vae','name':'have.safetensors','url':'https://example.invalid/have'},
                      {'folder':'loras','name':'get.safetensors','url':'https://example.invalid/get'},
                      {'folder':'loras','name':'nolink.safetensors','url':None}]}}
        wf={'nodes':[{'type':'A'},{'type':'B'}]}
        inv={'vae':['have.safetensors'],'loras':[]}
        with patch.object(dependencies.cc,'get_json',side_effect=lambda u,p: inv[p.rsplit('/',1)[1]]):
            r=dependencies.check({'url':'http://unused'},e,wf,{},{},None,size_of=lambda u: 2_500_000_000)
        s=r['settings'][0]
        self.assertEqual((s['status'],s['window_selector']),('needs_change',r'#Comfy\.VueNodes\.Enabled'))
        p=r['setup_proposal']
        self.assertTrue(p['needed'])
        self.assertEqual([x['id'] for x in p['node_packs']],['pack-a','pack-b'])
        self.assertEqual([(m['name'],m['size_gb']) for m in p['models']],[('get.safetensors',2.5)])
        self.assertEqual([m['name'] for m in p['models_without_url']],['nolink.safetensors'])
        self.assertEqual([x['id'] for x in p['settings']],['Comfy.VueNodes.Enabled'])
        self.assertTrue(p['restart_after_packs'])
        self.assertIn('Install All',p['window_steps'][0])
        self.assertTrue(any(r'#Comfy\.VueNodes\.Enabled' in x for x in p['window_steps']))

    def test_settings_ok_unknown_and_nothing_to_do(self):
        e={'id':'test','requirements':{'frontend_settings':[{'id':'Comfy.VueNodes.Enabled','value':True}]}}
        ok=dependencies.check({'url':'http://unused'},e,{'nodes':[]},{},{'Comfy.VueNodes.Enabled':True})
        self.assertEqual(ok['settings'][0]['status'],'ok')
        self.assertFalse(ok['setup_proposal']['needed'])
        self.assertEqual(ok['setup_proposal']['window_steps'],[])
        unk=dependencies.check({'url':'http://unused'},e,{'nodes':[]},{},None,'offline')
        self.assertEqual(unk['settings'][0]['status'],'unknown')

    def test_bundled_catalog_declares_wan_packs_and_qwen_setting(self):
        from plugin import library
        c={x['id']:x for x in library.load_catalog()['workflows']}
        wan=c['wan21-scail-2-loop-cr-mt']['requirements']
        self.assertEqual(wan['unresolved_node_types'],[])
        self.assertEqual(sorted(p['id'] for p in wan['custom_node_packs']),
                         ['comfyui-kjnodes','comfyui-videohelpersuite','comfyui_mienodes','was-ns'])
        wf=library.load_asset(c['wan21-scail-2-loop-cr-mt'])
        r=dependencies.check({'url':'http://unused'},c['wan21-scail-2-loop-cr-mt'],{'nodes':wf['nodes'],'definitions':wf.get('definitions')},{})
        self.assertEqual(r['nodes']['unresolved'],[])
        self.assertEqual(len(r['setup_proposal']['node_packs']),4)
        qi=c['qwen-image-2-1-i2i']['requirements']['frontend_settings']
        self.assertEqual([(s['id'],s['value']) for s in qi],[('Comfy.VueNodes.Enabled',True)])

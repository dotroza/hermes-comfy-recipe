import copy
import tempfile
import time
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch
from plugin import onboarding


def history(workflow='wf', cached=False):
    return {'prompt':[1,'job',{'1':{'class_type':'KSampler','inputs':{}},'2':{'class_type':'CLIPTextEncode','inputs':{'text':'a red kite'}}},
                              {'client_id':'browser','extra_pnginfo':{'workflow':{'id':workflow}}}],
            'status':{'completed':True,'status_str':'success','messages':[
                ['execution_start',{'timestamp':2000}],['execution_cached',{'nodes':['1'] if cached else []}],
                ['execution_success',{'timestamp':3000}]]},
            'outputs':{'3':{'images':[{'filename':'image.png','subfolder':'','type':'output'}]}}}


class EvidenceTests(unittest.TestCase):
    def check_run(self,h,**kw):
        with patch('plugin.comfy_client.history',return_value=h), patch('plugin.comfy_client.view_bytes',return_value=b'\x89PNG\r\n\x1a\nimage'):
            return onboarding.verify_image_run({'url':'http://test'},'job',expected_workflow_id='wf',started_after_ms=1000,baseline_prompt_ids=set(),**kw)

    def test_matching_fresh_image_is_proved(self):
        p=self.check_run(history())
        self.assertEqual(p['prompt_id'],'job')
        self.assertEqual(p['workflow_id'],'wf')

    def test_old_failed_cached_wrong_or_nonimage_rejected(self):
        variants=[None,history('other'),history(cached=True)]
        h=history();h['status']['status_str']='error';variants.append(h)
        h=history();h['outputs']={};variants.append(h)
        h=history();h['status']['messages'][0][1]['timestamp']=500;variants.append(h)
        h=history();h['prompt'][3]['client_id']='hermes-comfy-recipe-test';variants.append(h)
        for h in variants:
            with self.subTest(h=h),self.assertRaises(ValueError):self.check_run(h)

    def test_another_prompt_on_same_workflow_is_rejected(self):
        import hashlib
        expected=hashlib.sha256(b'a different image').hexdigest()
        with self.assertRaises(ValueError): self.check_run(history(),expected_prompt_hash=expected)
        actual=hashlib.sha256(b'a red kite').hexdigest()
        self.assertEqual(self.check_run(history(),expected_prompt_hash=actual)['prompt_id'],'job')

    def test_backend_change_after_prepare_is_rejected_without_reading_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);m={'install_id':str(uuid.uuid4()),'onboarding_version':1}
            onboarding.status(root,m,'A');onboarding.tutorial(root,m,'A')
            with patch('plugin.comfy_client.get_json',return_value={}):
                onboarding.begin_run(root,m['install_id'],'A',{'url':'http://managed','root':str(root)},'wf')
            with patch('plugin.comfy_client.history',return_value=history()) as read:
                with self.assertRaisesRegex(ValueError,'backend'):
                    onboarding.complete(root,m['install_id'],'A',{'url':'http://foreign','root':'elsewhere'},'job')
                read.assert_not_called()

    def test_baseline_prompt_rejected(self):
        with self.assertRaises(ValueError):
            onboarding.verify_image_run({'url':'x'},'old',expected_workflow_id='wf',started_after_ms=1000,baseline_prompt_ids={'old'})

    def test_complete_requires_matching_backend_proof_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);m={'install_id':str(uuid.uuid4()),'onboarding_version':1}
            onboarding.status(root,m,'A');onboarding.tutorial(root,m,'A')
            with patch('plugin.comfy_client.get_json',return_value={}),patch('plugin.onboarding.time.time',return_value=1):
                onboarding.begin_run(root,m['install_id'],'A',{'url':'x'},'wf')
            with patch('plugin.comfy_client.history',return_value=history()),patch('plugin.comfy_client.view_bytes',return_value=b'\x89PNG\r\n\x1a\nimage'):
                r=onboarding.complete(root,m['install_id'],'A',{'url':'x'},'job')
                self.assertEqual(r['tutorial']['state'],'completed')
                self.assertEqual(onboarding.complete(root,m['install_id'],'A',{'url':'x'},'job')['next_step'],'ordinary')
            with self.assertRaises(ValueError):onboarding.complete(root,m['install_id'],'B',{'url':'x'},'job')

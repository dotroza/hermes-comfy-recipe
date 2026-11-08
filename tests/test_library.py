import hashlib
import json
import tempfile
import unittest
import uuid
from pathlib import Path
from plugin import library
from http_fixture import comfy_server


def fixture(root, count=1):
    entries=[]
    for i in range(count):
        wf={'id':str(uuid.uuid4()), 'nodes':[], 'links':[], 'version':0.4}
        name=f'workflow-{i}.json'; raw=json.dumps(wf).encode()
        (root/name).write_bytes(raw)
        entries.append({'id':f'workflow-{i}','title':f'Workflow {i}', 'file':name,
                        'version':'1.0.0','sha256':hashlib.sha256(raw).hexdigest(), 'requirements':{}})
    catalog={'schema_version':1,'library_version':'1.0.0','workflows':entries}
    (root/'catalog.json').write_text(json.dumps(catalog),encoding='utf-8')
    return catalog

class PublicationTests(unittest.TestCase):
    def test_first_publish_readback_and_repeat(self):
        with tempfile.TemporaryDirectory() as tmp, comfy_server() as env:
            inst,files,events,*_=env; root=Path(tmp)/'assets'; root.mkdir(); fixture(root,6)
            result=library.publish(inst,Path(tmp)/'state',root=root)
            self.assertEqual(result['counts'], {'installed':6})
            self.assertEqual(len(files),6)
            self.assertTrue(all(name.startswith('workflows/Comfy Recipe/') for name in files))
            posts=sum(method=='POST' for method,path in events)
            again=library.publish(inst,Path(tmp)/'state',root=root)
            self.assertEqual(again['counts'], {'unchanged':6})
            self.assertEqual(sum(method=='POST' for method,path in events), posts)
            self.assertTrue(all(path.startswith('/api/userdata') for method,path in events))

    def test_preexisting_different_copy_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp, comfy_server() as env:
            inst,files,events,*_=env; root=Path(tmp)/'assets'; root.mkdir(); fixture(root)
            name='workflows/Comfy Recipe/workflow-0.json'; files[name]={'user':'mine'}
            result=library.publish(inst,Path(tmp)/'state',root=root)
            self.assertEqual(result['counts'], {'conflict':1})
            self.assertEqual(files[name], {'user':'mine'})
            self.assertFalse(any(m=='POST' for m,p in events))

    def test_partial_failure_then_retry(self):
        with tempfile.TemporaryDirectory() as tmp, comfy_server() as env:
            inst,files,events,fail,*_=env; root=Path(tmp)/'assets'; root.mkdir(); fixture(root,6)
            fail.add('workflows/Comfy Recipe/workflow-2.json')
            first=library.publish(inst,Path(tmp)/'state',root=root)
            self.assertEqual(first['counts'],{'installed':5,'error':1}); self.assertFalse(first['complete'])
            fail.clear(); second=library.publish(inst,Path(tmp)/'state',root=root)
            self.assertEqual(second['counts'],{'unchanged':5,'installed':1}); self.assertEqual(len(files),6)

    def test_readback_mismatch_is_not_recorded(self):
        with tempfile.TemporaryDirectory() as tmp, comfy_server() as env:
            inst,files,events,fail,corrupt,*_=env; root=Path(tmp)/'assets'; root.mkdir(); fixture(root)
            corrupt.add('workflows/Comfy Recipe/workflow-0.json')
            first=library.publish(inst,Path(tmp)/'state',root=root)
            self.assertEqual(first['counts'],{'error':1})
            self.assertFalse(list((Path(tmp)/'state').rglob('*.json')))
            corrupt.clear(); second=library.publish(inst,Path(tmp)/'state',root=root)
            self.assertEqual(second['counts'],{'unchanged':1})
            self.assertEqual(sum(m=='POST' for m,p in events),1)

    def test_user_edit_update_and_versioned_sibling(self):
        with tempfile.TemporaryDirectory() as tmp, comfy_server() as env:
            inst,files,events,*_=env; root=Path(tmp)/'assets'; root.mkdir(); c=fixture(root)
            state=Path(tmp)/'state'; library.publish(inst,state,root=root)
            target='workflows/Comfy Recipe/workflow-0.json'; original=dict(files[target])
            files[target]['user_edit']=True
            self.assertEqual(library.publish(inst,state,root=root)['counts'],{'conflict':1})
            self.assertTrue(files[target]['user_edit'])
            files[target]=original
            asset=json.loads((root/'workflow-0.json').read_text()); asset['revision']=2
            raw=json.dumps(asset).encode(); (root/'workflow-0.json').write_bytes(raw)
            c['workflows'][0].update(version='1.1.0',sha256=hashlib.sha256(raw).hexdigest())
            (root/'catalog.json').write_text(json.dumps(c),encoding='utf-8')
            self.assertEqual(library.publish(inst,state,root=root)['counts'],{'update_available':1})
            sibling=library.publish(inst,state,versioned=True,root=root)
            self.assertEqual(sibling['counts'],{'installed':1})
            new=files['workflows/Comfy Recipe/workflow-0-v1.1.0.json']
            self.assertNotEqual(new['id'],original['id']); self.assertEqual(files[target],original)
            self.assertEqual(library.publish(inst,state,versioned=True,root=root)['counts'],{'unchanged':1})

    def test_corrupt_state_race_and_outage_are_conservative(self):
        with tempfile.TemporaryDirectory() as tmp, comfy_server() as env:
            inst,files,events,fail,corrupt,races,unavailable=env; root=Path(tmp)/'assets'; root.mkdir(); fixture(root)
            state=Path(tmp)/'state'; library.publish(inst,state,root=root)
            record=next(state.rglob('*.json')); record.write_text('not-json')
            files['workflows/Comfy Recipe/workflow-0.json']={'user':'keep'}
            self.assertEqual(library.publish(inst,state,root=root)['counts'],{'conflict':1})
            files.clear(); races.add('workflows/Comfy Recipe/workflow-0.json')
            self.assertEqual(library.publish(inst,state,root=root)['counts'],{'conflict':1})
            self.assertEqual(files['workflows/Comfy Recipe/workflow-0.json'],{'foreign':True})
            unavailable.append(True)
            self.assertEqual(library.publish(inst,state,root=root)['counts'],{'error':1})

    def test_bad_selection_is_rejected_before_network(self):
        with tempfile.TemporaryDirectory() as tmp, comfy_server() as env:
            inst,files,events,*_=env; root=Path(tmp)/'assets'; root.mkdir(); fixture(root)
            for ids in (['unknown'],['workflow-0','workflow-0'],'workflow-0'):
                with self.subTest(ids=ids), self.assertRaises(ValueError):
                    library.publish(inst,Path(tmp)/'state',ids,root=root)
            self.assertEqual(events,[])


class CatalogTests(unittest.TestCase):
    def test_local_minimax_is_not_labelled_paid_api(self):
        entries=library.load_catalog()['workflows']
        mini=[e for e in entries if e['id'].startswith('minimax-')]
        self.assertEqual(len(mini),2)
        self.assertTrue(all(e['requirements']['models'] for e in mini))
        self.assertTrue(all(e['requirements']['services']==[] for e in mini))

    def test_shipped_six_assets_are_unique(self):
        c=library.load_catalog()
        self.assertEqual(len(c['workflows']),6)
        ids=[library.load_asset(e)['id'] for e in c['workflows']]
        self.assertEqual(len(set(ids)),6)

    def test_duplicate_destination_filename_and_uuid_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); c=fixture(root,2)
            (root/'nested').mkdir(); raw=(root/'workflow-1.json').read_bytes()
            (root/'nested/workflow-0.json').write_bytes(raw)
            c['workflows'][1]['file']='nested/workflow-0.json'
            (root/'catalog.json').write_text(json.dumps(c),encoding='utf-8')
            with self.assertRaises(ValueError): library.load_catalog(root)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); c=fixture(root,2); raw=(root/'workflow-0.json').read_bytes()
            (root/'workflow-1.json').write_bytes(raw); c['workflows'][1]['sha256']=hashlib.sha256(raw).hexdigest()
            (root/'catalog.json').write_text(json.dumps(c),encoding='utf-8')
            with self.assertRaises(ValueError): library.load_catalog(root)

    def test_load_and_integrity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); expected=fixture(root)
            actual=library.load_catalog(root)
            self.assertEqual(actual,expected)
            self.assertEqual(library.load_asset(actual['workflows'][0],root)['nodes'],[])
            (root/'workflow-0.json').write_text('{}',encoding='utf-8')
            with self.assertRaises(ValueError): library.load_catalog(root)

    def test_unsafe_paths_and_duplicate_ids(self):
        for value in ('../outside.json','C:/outside.json','/outside.json','..\\outside.json'):
            with self.subTest(value=value), tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp); c=fixture(root); c['workflows'][0]['file']=value
                (root/'catalog.json').write_text(json.dumps(c),encoding='utf-8')
                with self.assertRaises(ValueError): library.load_catalog(root)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); c=fixture(root); c['workflows']*=2
            (root/'catalog.json').write_text(json.dumps(c),encoding='utf-8')
            with self.assertRaises(ValueError): library.load_catalog(root)

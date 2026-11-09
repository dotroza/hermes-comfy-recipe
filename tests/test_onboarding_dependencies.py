import unittest
from plugin import dependencies


def report(name='shared.safetensors', status='missing', url='https://example.test/model', optional=False):
    return {'workflow_id':'test', 'models':[{'folder':'diffusion_models','name':name,'url':url,'status':status,'optional':optional}],
            'nodes':{'missing_packs':[],'missing_core':[],'unresolved':[]}, 'settings':[]}


class LibraryProposalTests(unittest.TestCase):
    def test_available_optional_and_unknown_do_not_become_downloads(self):
        p=dependencies.library_proposal([report(status='available'),report(optional=True),report(status='unknown')],size_of=lambda u: 9)
        self.assertEqual(p['download_bytes'],0)
        self.assertEqual(len(p['optional_models']),1)
        self.assertEqual(len(p['unknown_inventory']),1)
        self.assertFalse(p['size_complete'])

    def test_empty_unknown_size_and_manual_are_distinct(self):
        self.assertTrue(dependencies.library_proposal([])['size_complete'])
        p=dependencies.library_proposal([report(),report('manual',url=None)],size_of=lambda u: None)
        self.assertEqual(p['unknown_size_count'],2)
        self.assertEqual(p['download_bytes'],0)
        self.assertEqual(len(p['models_without_url']),1)

    def test_conflicts_and_unsafe_destinations(self):
        p=dependencies.library_proposal([report(),report(url='https://other.test/m')],size_of=lambda u: 1)
        self.assertTrue(p['blockers'])
        self.assertEqual(p['models'],[])
        with self.assertRaises(ValueError): dependencies.library_proposal([report('../escape')])

    def test_per_workflow_optional_model_excluded_and_raw_bytes_kept(self):
        r={'nodes':{'missing_packs':[],'missing_core':[],'unresolved':[]},'models':[
            {'status':'missing','name':'active','folder':'text_encoders','url':'https://e/active'},
            {'status':'missing','name':'pe','folder':'text_encoders','url':'https://e/pe','optional':True}], 'settings':[]}
        p=dependencies.setup_proposal(r,size_of=lambda u:1234567890)
        self.assertEqual(len(p['models']),1)
        self.assertEqual(p['download_bytes'],1234567890)

    def test_catalog_qwen_enhancer_optional(self):
        from plugin import library
        for entry in library.load_catalog()['workflows']:
            if entry['id']=='qwen-image-2-1-t2i':
                pe=[m for m in entry['requirements']['models'] if '_pe_' in m['name']]
                self.assertTrue(pe and all(m.get('optional') for m in pe))
            if entry['id']=='qwen-image-2-1-i2i':
                pe=[m for m in entry['requirements']['models'] if '_pe_' in m['name']]
                self.assertTrue(pe and not any(m.get('optional') for m in pe))

    def test_size_cache_expires_without_network(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            calls=[]
            lookup=lambda u:calls.append(u) or 100
            cache=dependencies.cached_size_lookup(Path(tmp),lookup=lookup,clock=lambda:100)
            self.assertEqual(cache('https://e/m'),100)
            self.assertEqual(cache('https://e/m'),100)
            again=dependencies.cached_size_lookup(Path(tmp),lookup=lookup,clock=lambda:200)
            self.assertEqual(again('https://e/m'),100)
            expired=dependencies.cached_size_lookup(Path(tmp),lookup=lookup,clock=lambda:5000)
            self.assertEqual(expired('https://e/m'),100)
            self.assertEqual(len(calls),2)

    def test_noninstallable_requirements_keep_workflow_provenance(self):
        r=report();r.update(inputs=[{'node':9,'filename':'private.mp4','status':'needs_user_media'}],
                           executables=[{'name':'ffmpeg','status':'missing'}],
                           services=[{'name':'service','credentials_status':'not_checked'}],
                           portability_warnings=['author-specific media'],compatibility={'execution_tested':False})
        p=dependencies.library_proposal([r],size_of=lambda u:1)
        self.assertEqual(p['missing_media'][0]['workflow_id'],'test')
        self.assertEqual(p['executables'][0]['name'],'ffmpeg')
        self.assertEqual(p['services'][0]['credentials_status'],'not_checked')
        self.assertTrue(p['readiness_warnings'])
        self.assertEqual(p['compatibility'][0]['workflow_id'],'test')

    def test_verified_sizes_skip_network_and_unknown_sizes_still_use_lookup(self):
        from unittest.mock import Mock
        rows = [report(name='known'), report(name='unknown', url='https://example.test/unknown')]
        rows[0]['models'][0]['size_bytes'] = 1234567890
        for builder in ('library', 'single'):
            lookup = Mock(return_value=900)
            with self.subTest(builder=builder):
                result = (dependencies.library_proposal(rows, size_of=lookup) if builder == 'library'
                          else dependencies.setup_proposal(dict(rows[0], models=[r['models'][0] for r in rows]), size_of=lookup))
                lookup.assert_called_once_with('https://example.test/unknown')
                self.assertEqual(result['download_bytes'], 1234568790)
                self.assertEqual(result['models'][0]['size_bytes'], 1234567890)

    def test_later_shared_requirement_can_supply_verified_size(self):
        from unittest.mock import Mock
        first, second = report(), report()
        second['models'][0]['size_bytes'] = 1234
        lookup = Mock(return_value=None)
        result = dependencies.library_proposal([first, second], size_of=lookup)
        lookup.assert_not_called()
        self.assertEqual(result['download_bytes'], 1234)
        self.assertEqual(len(result['models']), 1)
        self.assertNotIn('size_bytes', first['models'][0], 'Do not mutate source reports')

    def test_invalid_catalog_sizes_fall_back_and_lookup_failure_stays_unknown(self):
        from unittest.mock import Mock
        for value in (None, True, False, 0, -1, '123', 1.5):
            row = report()
            row['models'][0]['size_bytes'] = value
            for builder in (dependencies.library_proposal, dependencies.setup_proposal):
                lookup = Mock(side_effect=OSError('offline'))
                with self.subTest(value=value, builder=builder.__name__):
                    result = builder([row] if builder is dependencies.library_proposal else row, size_of=lookup)
                    lookup.assert_called_once()
                    self.assertIsNone(result['models'][0]['size_bytes'])
                    self.assertEqual(result['download_bytes'], 0)

    def test_shared_model_bytes_are_counted_once(self):
        calls=[]
        p=dependencies.library_proposal([report(),report()],size_of=lambda url: calls.append(url) or 1234567890)
        self.assertEqual(len(p['models']),1)
        self.assertEqual(p['download_bytes'],1234567890)
        self.assertEqual(len(calls),1)
        self.assertTrue(p['size_complete'])

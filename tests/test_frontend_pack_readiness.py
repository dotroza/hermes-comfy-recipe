"""Frontend-only pack evidence must reach consent proposals without live requests."""
import unittest
from unittest.mock import patch


import tempfile
from pathlib import Path
from plugin import core, dependencies, downloads, download_flow, library, onboarding_flow


ENTRY = {'id': 'frontend', 'requirements': {
    'frontend_nodes': [{'type': 'SetNode', 'pack_id': 'comfyui-kjnodes'},
                       {'type': 'GetNode', 'pack_id': 'comfyui-kjnodes'}],
    'custom_node_packs': [{'id': 'comfyui-kjnodes', 'node_types': ['SetNode', 'GetNode']}],
}}
WORKFLOW = {'nodes': [{'type': 'SetNode'}, {'type': 'GetNode'}]}


class FrontendPackReadinessTests(unittest.TestCase):
    def test_unprovided_inventory_is_explicit_unknown_without_a_request(self):
        # Exercise the existing API first: no network is permitted in this pure check.
        with patch.object(dependencies.cc, 'get_json', side_effect=AssertionError('network')):
            report = dependencies.check({'url': 'http://isolated.invalid'}, ENTRY, WORKFLOW, {})
        self.assertEqual(report['nodes']['missing_core'], [])
        self.assertEqual(report['nodes']['unresolved'], [])
        # An unavailable inventory is explicit, not silently treated as installed.
        self.assertEqual([p['id'] for p in report['setup_proposal'].get('unknown_inventory', [])],
                         ['comfyui-kjnodes'])

    def test_enabled_disabled_absent_and_unknown_inventory(self):
        for raw, expected in (({}, 'missing'),
                              ({'ComfyUI-KJNodes': {'enabled': True, 'cnr_id': 'comfyui-kjnodes'}}, 'available'),
                              ({'ComfyUI-KJNodes': {'enabled': False, 'cnr_id': 'comfyui-kjnodes'}}, 'missing'),
                              (None, 'unknown')):
            with self.subTest(expected=expected, raw=raw), \
                 patch.object(downloads, '_http_json', return_value=raw), \
                 patch.object(dependencies.cc, 'get_json', side_effect=AssertionError('network')):
                evidence = downloads.installed_packs('http://isolated.invalid')
                report = dependencies.check({'url': 'http://isolated.invalid'}, ENTRY, WORKFLOW, {},
                                            installed_packs=evidence)
                self.assertEqual(report['nodes']['missing_core'], [])
                self.assertEqual(report['nodes']['unresolved'], [])
                self.assertEqual(len(report['nodes']['frontend_checks']), 2)
                self.assertEqual([p['id'] for p in report['setup_proposal']['node_packs']],
                                 ['comfyui-kjnodes'] if expected == 'missing' else [])
                self.assertEqual([p['id'] for p in report['setup_proposal']['unknown_inventory']],
                                 ['comfyui-kjnodes'] if expected == 'unknown' else [])
                aggregate = dependencies.library_proposal([report], size_of=lambda _: None)
                self.assertEqual(bool(aggregate['unknown_inventory']), expected == 'unknown')
                if expected == 'missing':
                    self.assertEqual(report['nodes']['missing_packs'][0]['missing_node_types'],
                                     ['GetNode', 'SetNode'])

    def test_single_workflow_tool_injects_pack_inventory(self):
        import plugin
        with tempfile.TemporaryDirectory() as tmp:
            info = Path(tmp) / 'info.json'
            info.write_text('{}', encoding='utf-8')
            inst = {'url': 'http://isolated.invalid'}
            entry = dict(ENTRY, file='frontend.json')
            with patch.object(core, '_inst', return_value=inst), \
                 patch.object(core, '_object_info_path', return_value=info), \
                 patch.object(library, 'load_catalog', return_value={'workflows': [entry]}), \
                 patch.object(library, 'load_asset', return_value=WORKFLOW), \
                 patch.object(core.cc, 'get_json', return_value={}), \
                 patch.object(core.cc, 'list_workflows', return_value=[]), \
                 patch.object(downloads, 'installed_packs', return_value=set()) as packs:
                report = plugin._workflows({'action': 'check', 'workflow': entry['id']})
            self.assertEqual([p['id'] for p in report['setup_proposal']['node_packs']], ['comfyui-kjnodes'])
            packs.assert_called_once_with(inst['url'])

    def test_real_catalog_fresh_proposals_share_inventory_and_retry_next_report(self):
        catalog = library.load_catalog()
        frontend_packs = {n['pack_id'] for e in catalog['workflows']
                          for n in e.get('requirements', {}).get('frontend_nodes', []) if n.get('pack_id')}
        self.assertIn('comfyui-kjnodes', frontend_packs)
        with tempfile.TemporaryDirectory() as tmp:
            info = Path(tmp) / 'info.json'
            info.write_text('{}', encoding='utf-8')
            inst = {'url': 'http://isolated.invalid', 'root': tmp}
            for route in ('onboarding', 'downloads'):
                with self.subTest(route=route), \
                     patch.object(onboarding_flow, 'managed_backend', return_value=inst), \
                     patch.object(core, '_object_info_path', return_value=info), \
                     patch.object(core.cc, 'get_json', side_effect=lambda u, p: {} if p == '/settings' else []), \
                     patch.object(downloads, 'installed_packs', side_effect=[set(), frontend_packs, None, set()]) as packs, \
                     patch.object(downloads, 'queue_pack_installs', side_effect=AssertionError('install')), \
                     patch.object(downloads, 'enqueue', side_effect=AssertionError('worker')), \
                     patch.object(dependencies, 'cached_size_lookup', return_value=lambda _: None):
                    def proposal():
                        return (onboarding_flow._proposal() if route == 'onboarding'
                                else download_flow.bundled_proposal(inst, None))
                    fresh = proposal()
                    self.assertIn('comfyui-kjnodes', [p['id'] for p in fresh['node_packs']])
                    self.assertIn('comfyui-easy-use', [p['id'] for p in fresh['node_packs']])
                    self.assertEqual(sum(p['id'] == 'comfyui-kjnodes' for p in fresh['node_packs']), 1)
                    self.assertEqual(packs.call_count, 1)
                    self.assertNotIn('comfyui-kjnodes', [p['id'] for p in proposal()['node_packs']])
                    unknown = proposal()
                    self.assertNotIn('comfyui-kjnodes', [p['id'] for p in unknown['node_packs']])
                    self.assertIn('comfyui-kjnodes', [p.get('id') for p in unknown['unknown_inventory']])
                    self.assertIn('comfyui-kjnodes', [p['id'] for p in proposal()['node_packs']])
                    self.assertEqual(packs.call_count, 4)
                    packs.assert_called_with(inst['url'])


if __name__ == '__main__':
    unittest.main()

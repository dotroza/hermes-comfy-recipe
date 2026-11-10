"""Setup request budgets against the real catalog, with no live backend or network."""
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import patch

from plugin import core, dependencies, download_flow, library, onboarding_flow


class InventoryBudgetTests(unittest.TestCase):
    def test_shared_inventory_is_backend_bound_and_failed_reads_retry_next_report(self):
        entry = {'id': 'test', 'requirements': {'models': [{'folder': 'vae', 'name': 'v.safetensors'}]}}
        shared = {}
        backends = [{'url': 'http://one.invalid', 'root': 'one'},
                    {'url': 'http://two.invalid', 'root': 'one'},
                    {'url': 'http://one.invalid', 'root': 'two'}]
        with patch.object(dependencies.cc, 'get_json', side_effect=dependencies.cc.ComfyError('offline')) as get:
            for inst in backends:
                for _ in range(2):
                    out = dependencies.check(inst, entry, {'nodes': []}, {}, model_inventory=shared)
                    self.assertEqual(out['models'][0]['status'], 'unknown')
            self.assertEqual(get.call_count, len(backends))
        with patch.object(dependencies.cc, 'get_json', return_value=['v.safetensors']) as get:
            out = dependencies.check(backends[0], entry, {'nodes': []}, {}, model_inventory={})
            self.assertEqual(out['models'][0]['status'], 'available')
            get.assert_called_once()

    def test_each_report_fetches_each_folder_once_and_next_report_is_fresh(self):
        catalog = library.load_catalog()
        folders = {m['folder'] for e in catalog['workflows'] for m in e['requirements'].get('models', [])}
        with tempfile.TemporaryDirectory() as tmp:
            info = Path(tmp) / 'info.json'
            info.write_text('{}', encoding='utf-8')
            inst = {'url': 'http://isolated.invalid', 'root': tmp}
            for route in ('onboarding', 'downloads'):
                calls = Counter()
                available = []

                def get_json(url, path):
                    self.assertEqual(url, inst['url'])
                    calls[path] += 1
                    return {} if path == '/settings' else list(available)

                with self.subTest(route=route), \
                     patch.object(onboarding_flow, 'managed_backend', return_value=inst), \
                     patch.object(core, '_object_info_path', return_value=info), \
                     patch.object(core.cc, 'get_json', side_effect=get_json), \
                     patch('plugin.downloads.installed_packs', return_value=set()), \
                     patch.object(dependencies, 'cached_size_lookup', return_value=lambda url: None):
                    if route == 'onboarding':
                        first = onboarding_flow.reports()
                    else:
                        first = download_flow.bundled_proposal(inst, None)
                    self.assertEqual({p: n for p, n in calls.items() if p.startswith('/models/')},
                                     {'/models/' + folder: 1 for folder in folders})
                    available[:] = [m['name'] for e in catalog['workflows'] for m in e['requirements'].get('models', [])]
                    if route == 'onboarding':
                        second = onboarding_flow.reports()
                        self.assertTrue(any(m['status'] == 'missing' for r in first for m in r['models']))
                        self.assertTrue(all(m['status'] == 'available' for r in second for m in r['models']))
                    else:
                        self.assertTrue(first['models'])
                        self.assertFalse(download_flow.bundled_proposal(inst, None)['models'])
                    self.assertEqual({p: n for p, n in calls.items() if p.startswith('/models/')},
                                     {'/models/' + folder: 2 for folder in folders})

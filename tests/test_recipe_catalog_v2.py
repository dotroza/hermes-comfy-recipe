"""The user-selected local and cloud library is a portable ten-template bundle."""
import unittest
import hashlib
import json
from pathlib import Path
from plugin import library


class RecipeCatalogV2Tests(unittest.TestCase):
    def test_onboarding_refresh_schema_does_not_describe_old_five_template_library(self):
        import plugin
        description = plugin.SCHEMAS['comfy_onboarding']['parameters']['properties']['refresh']['description']
        self.assertIn('all bundled workflows', description)

    def test_capture_records_match_every_published_asset(self):
        root = Path(__file__).resolve().parents[1]
        records = json.loads((root / 'docs/workflow-capture.json').read_text(encoding='utf-8'))['files']
        entries = library.load_catalog()['workflows']
        self.assertEqual({r['file'] for r in records}, {e['file'] for e in entries})
        for record in records:
            path = root / 'plugin/workflows' / record['file']
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), record['distributed_sha256'])
            self.assertEqual(json.loads(path.read_text(encoding='utf-8'))['id'], record['distributed_id'])

    def test_ten_templates_split_evenly_across_two_folders(self):
        entries = library.load_catalog()['workflows']
        self.assertEqual(len(entries), 10)
        self.assertEqual(sum(e.get('folder') == 'Local Recipe' for e in entries), 5)
        self.assertEqual(sum(e.get('folder') == 'Cloud Recipe' for e in entries), 5)
        self.assertEqual(len({library.load_asset(e)['id'] for e in entries}), 10)

    def test_saved_qwen_modes_and_names(self):
        entries = {e['id']: e for e in library.load_catalog()['workflows']}
        for ident, name, refine, steps, strength in (
                ('qwen-image-2-1-t2i', 'RCPlocal_t2i_qwen_image_2-1.json', True, 25, 0),
                ('qwen-image-2-1-i2i', 'RCPlocal_ti2i_qwen_image_2-1.json', False, 25, 0)):
            with self.subTest(ident=ident):
                entry = entries[ident]
                self.assertEqual(entry['file'], name)
                workflow = library.load_asset(entry)
                node = next(n for n in workflow['nodes'] if n['id'] == 459)
                values = node['widgets_values']
                self.assertEqual(values[2], refine)
                self.assertEqual(values[5], steps)
                self.assertEqual(values[-1], strength)

    def test_cloud_requirements_are_explicit_paid_services_not_local_models(self):
        entries = [e for e in library.load_catalog()['workflows'] if e.get('folder') == 'Cloud Recipe']
        self.assertEqual(len(entries), 5)
        for entry in entries:
            with self.subTest(ident=entry['id']):
                req = entry['requirements']
                self.assertEqual(req['models'], [])
                self.assertEqual(req['custom_node_packs'], [])
                self.assertTrue(req['services'])
                self.assertTrue(all(s['paid'] for s in req['services']))
                self.assertTrue(all(s['authentication'] == 'ComfyUI account' for s in req['services']))

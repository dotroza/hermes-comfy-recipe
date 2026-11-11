"""Regression coverage for the simplified, user-saved Pixal3D bundle."""
import unittest
from pathlib import Path
import tempfile
from http_fixture import comfy_server
from plugin import library


class Pixal3DRevisionTests(unittest.TestCase):
    def test_fresh_publish_contains_all_ten_canonical_files(self):
        expected = {'workflows/' + e['folder'] + '/' + e['file']
                    for e in library.load_catalog()['workflows']}
        with tempfile.TemporaryDirectory() as tmp, comfy_server() as env:
            inst, files, *_ = env
            result = library.publish(inst, Path(tmp))
            self.assertTrue(result['complete'])
            self.assertEqual(result['counts'], {'installed': 10})
            self.assertEqual(set(files), expected)
            self.assertEqual(library.publish(inst, Path(tmp))['counts'], {'unchanged': 10})

    def test_bundle_has_no_removed_segmentation_or_captioning_dependencies(self):
        entry = next(e for e in library.load_catalog()['workflows']
                     if e['id'] == 'pixal3d-img-to-3d')
        workflow = library.load_asset(entry)
        types = {n['type'] for n in workflow['nodes']}
        self.assertFalse(types & {'SAM3Segment', 'CLIPLoader', 'TextGenerate', 'easy ifElse'})
        requirements = entry['requirements']
        self.assertEqual({p['id'] for p in requirements['custom_node_packs']},
                         {'comfyui-kjnodes', 'comfyui-easy-use'})
        self.assertEqual(requirements['portability_warnings'], [])
        self.assertNotIn('Qwen3.5-0.8B.safetensors',
                         {m['name'] for m in requirements['models']})
        self.assertFalse(set(requirements['core_node_types']) & {'CLIPLoader', 'TextGenerate'})

    def test_minimax_display_and_asset_name_are_canonical(self):
        entries = [e for e in library.load_catalog()['workflows']
                   if e['id'].startswith('minimax-')]
        self.assertEqual(len(entries), 1)
        # Stable catalog identity remains unchanged for installed revision tracking.
        self.assertEqual(entries[0]['id'], 'minimax-h3-r2v-mix')
        self.assertEqual(entries[0]['title'], 'RCPlocal_r2v_video_minimax_h3')
        self.assertEqual(entries[0]['file'], 'RCPlocal_r2v_video_minimax_h3.json')

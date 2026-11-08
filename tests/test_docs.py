import unittest
from pathlib import Path
import yaml

ROOT=Path(__file__).resolve().parents[1]
class DocumentationTests(unittest.TestCase):
    def test_library_guidance_is_shipped_and_linked(self):
        skill=(ROOT/'plugin/skills/session/SKILL.md').read_text(encoding='utf-8')
        self.assertIn('references/workflow-library.md',skill)
        ref=(ROOT/'plugin/skills/session/references/workflow-library.md').read_text(encoding='utf-8')
        for text in ('action=library','action=check','versioned=true','consent','Manager','working_copy'):
            self.assertIn(text,ref)
        front=yaml.safe_load(skill.split('---',2)[1])
        self.assertEqual(front['version'],'0.4.0')
        self.assertEqual(front['metadata']['comfy_recipe']['workflow_ids'],[])
        self.assertLessEqual(len(front['description']),60)

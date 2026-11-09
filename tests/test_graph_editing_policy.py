"""Regression coverage for the graph-editing-first instruction contract."""
import unittest
from pathlib import Path
import plugin

ROOT = Path(__file__).resolve().parents[1] / 'plugin'


class GraphEditingPolicyTests(unittest.TestCase):
    def test_runtime_rules_prioritize_current_graph(self):
        for text in ('graph-editing assistant', 'current workflow in place',
                     'add a Load Image node', 'image_2',
                     'substantial restructuring', 'explicitly asks',
                     'unsaved edits are not a reason to duplicate'):
            self.assertIn(text, plugin.SESSION_RULES)

    def test_skills_and_references_agree_on_duplication_policy(self):
        for relative in ('SKILL.md', 'references/pane-recipe.md',
                         'references/workflow-json-editing.md'):
            with self.subTest(file=relative):
                text = (ROOT / 'skills/session' / relative).read_text(encoding='utf-8')
                for phrase in ('current workflow in place', 'substantial restructuring',
                               'explicitly asks'):
                    self.assertIn(phrase, text)
        session = (ROOT / 'skills/session/SKILL.md').read_text(encoding='utf-8')
        self.assertNotIn("Never overwrite the user's workflow file: write a sibling copy", session)

    def test_unsaved_state_is_protected_not_replaced_by_disk_copy(self):
        text = (ROOT / 'skills/session/references/workflow-json-editing.md').read_text(encoding='utf-8')
        for phrase in ('unsaved', 'backup', 'same workflow identity',
                       'stop and explain', 'not a duplicate working tab'):
            self.assertIn(phrase, text)

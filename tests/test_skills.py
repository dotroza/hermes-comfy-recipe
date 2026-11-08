import tempfile
import unittest
from pathlib import Path
from plugin.skill_registration import skills_for_registration

class SkillTests(unittest.TestCase):
    def test_workflow_free_skill(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            p = root / 'diagnostics' / 'SKILL.md'
            p.parent.mkdir()
            p.write_text('---\nname: diagnostics\ndescription: Diagnose workflows.\n---\nRead-only instructions.\n', encoding='utf-8')
            rows = skills_for_registration(root, {'shared'})
            self.assertEqual(rows[0]['name'], 'diagnostics')
            self.assertEqual(rows[0]['workflow_ids'], [])
            self.assertEqual(rows[0]['description'], 'Diagnose workflows.')

    def make_skill(self, root, name, extra=''):
        p = root / name / 'SKILL.md'
        p.parent.mkdir()
        p.write_text(f'---\nname: {name}\ndescription: Example skill.\n{extra}---\nInstructions.\n', encoding='utf-8')
        return p

    def test_shared_multiple_and_empty_workflows(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            self.make_skill(root,'one','metadata: {comfy_recipe: {workflow_ids: [shared]}}\n')
            self.make_skill(root,'two','metadata: {comfy_recipe: {workflow_ids: [shared, other]}}\n')
            self.make_skill(root,'zero','metadata: {comfy_recipe: {workflow_ids: []}}\n')
            rows={r['name']:r for r in skills_for_registration(root, {'shared','other'})}
            self.assertEqual(rows['one']['workflow_ids'], ['shared'])
            self.assertEqual(rows['two']['workflow_ids'], ['shared','other'])
            self.assertEqual(rows['zero']['workflow_ids'], [])

    def test_unknown_reference_and_malformed_metadata_rejected(self):
        for extra in ('metadata: {comfy_recipe: {workflow_ids: [missing]}}\n',
                      'metadata: {comfy_recipe: {workflow_ids: shared}}\n',
                      'metadata: {comfy_recipe: null}\n', 'metadata: broken\n'):
            with self.subTest(extra=extra), tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp)
                self.make_skill(root,'one',extra)
                with self.assertRaises(ValueError):
                    skills_for_registration(root, {'shared'})

    def test_bad_name_description_yaml_and_escape(self):
        for text in ('no frontmatter', '---\nname: one\ndescription: [broken\n---\n',
                     '---\nname: other\ndescription: Wrong name.\n---\n',
                     '---\nname: one\ndescription: 7\n---\n'):
            with self.subTest(text=text), tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp); p=self.make_skill(root,'one'); p.write_text(text,encoding='utf-8')
                with self.assertRaises(ValueError): skills_for_registration(root, set())
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'skills'; root.mkdir(); outside=Path(tmp)/'outside'; outside.mkdir()
            (outside/'SKILL.md').write_text('---\nname: linked\ndescription: Outside.\n---\n',encoding='utf-8')
            try: (root/'linked').symlink_to(outside,target_is_directory=True)
            except OSError: return  # Host may require Windows Developer Mode; lexical traversal tested by catalog tests.
            with self.assertRaises(ValueError): skills_for_registration(root,set())


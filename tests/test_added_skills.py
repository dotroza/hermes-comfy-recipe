import unittest
from pathlib import Path

from plugin import library, onboarding_flow, skill_registration

PLUGIN = Path(__file__).resolve().parents[1] / 'plugin'
SKILL_NAMES = {
    'comfy-consistency',
    'comfy-quality-gate',
    'comfy-refine-loop',
    'comfy-run-recovery',
    'comfy-workflow-authoring',
}


class AddedSkillsTests(unittest.TestCase):
    def test_useful_skills_register_without_eagerly_loading_bodies(self):
        workflows = {entry['id'] for entry in library.load_catalog()['workflows']}
        rows = {row['name']: row for row in skill_registration.skills_for_registration(PLUGIN / 'skills', workflows)}
        self.assertTrue(SKILL_NAMES.issubset(rows))
        for name in SKILL_NAMES:
            with self.subTest(skill=name):
                row = rows[name]
                self.assertEqual(row['workflow_ids'], [])
                self.assertTrue(row['path'].is_file())
                # Registration exposes metadata/path; the skill body is not returned or loaded here.
                self.assertNotIn('content', row)

    def test_capability_examples_offered_after_skip_and_tutorial(self):
        for instruction in (onboarding_flow.SKIPPED, onboarding_flow.NEXT_AFTER_4):
            with self.subTest(instruction=instruction[:30]):
                self.assertIn('guide them through Comfy Recipe', instruction)
                self.assertIn('make reference sheets and videos', instruction)
                self.assertIn('troubleshoot failed runs', instruction)
                self.assertIn('ask for examples', instruction)
                self.assertIn('What would you like to do?', instruction)
        self.assertIn('matches its trigger', onboarding_flow.SKIPPED)
        self.assertIn('never all skill instructions at session start', onboarding_flow.NEXT_AFTER_4)


if __name__ == '__main__':
    unittest.main()

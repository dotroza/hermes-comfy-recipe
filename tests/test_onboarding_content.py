import unittest
from pathlib import Path
from plugin import library,skill_registration

ROOT=Path(__file__).resolve().parents[1]/'plugin'

class OnboardingContentTests(unittest.TestCase):
    def test_bundled_t2i_does_not_validate_unused_enhancer_branch(self):
        entry=next(e for e in library.load_catalog()['workflows'] if e['id']=='qwen-image-2-1-t2i')
        graph=library.load_asset(entry)['definitions']['subgraphs'][0]
        parents={}
        for link in graph['links']:
            parents.setdefault(link['target_id'],[]).append(link['origin_id'])
        seen=set();pending=[458]
        while pending:
            node=pending.pop()
            if node in seen: continue
            seen.add(node);pending.extend(parents.get(node,[]))
        self.assertNotIn(477,seen,'Unused PE model remains connected to the sampler validation path')

    def test_tutorial_and_prompt_skill_registered(self):
        skills={s['name']:s for s in skill_registration.skills_for_registration(ROOT/'skills',{e['id'] for e in library.load_catalog()['workflows']})}
        for name in ['first-image-tutorial','qwen-image-2-1-prompting']:
            self.assertIn(name,skills)
            self.assertEqual(skills[name]['workflow_ids'],['qwen-image-2-1-t2i'])
        tutorial=(ROOT/'skills/first-image-tutorial/SKILL.md').read_text()
        for token in ['drive_preview','comfy_result','begin_run=true','skip tutorial','vision_analyze','comfy_onboarding']:
            self.assertIn(token,tutorial)
        self.assertIn('Technical generation success',tutorial)
        self.assertIn('replay=true',tutorial)
        self.assertIn('workflow_path=',tutorial)
        prompt=(ROOT/'skills/qwen-image-2-1-prompting/SKILL.md').read_text()
        self.assertIn('exact text',prompt)
        self.assertIn('refine_prompt',prompt)
        self.assertIn('Chez Léa',prompt)

    def test_bundled_reference_media_are_documented_with_hashes(self):
        import hashlib
        root=ROOT/'assets'
        readme=(root/'README.md').read_text(encoding='utf-8')
        for folder in ['images','character-sheets','motion-videos']:
            self.assertTrue((root/folder/'.gitkeep').is_file())
        media=[p for p in root.rglob('*') if p.is_file() and p.suffix.lower() in ['.png','.jpg','.jpeg','.webp','.mp4']]
        self.assertIn('character-sheets/miskinou_sheet.png',[p.relative_to(root).as_posix() for p in media])
        for p in media:
            with self.subTest(asset=p.name):
                self.assertIn(f'`{p.relative_to(root).as_posix()}`',readme)
                self.assertIn(hashlib.sha256(p.read_bytes()).hexdigest(),readme)

    def test_local_prompt_modes_and_cloud_consent_are_explicit(self):
        import plugin
        from plugin import onboarding_flow as flow
        self.assertIn('soft', flow.LESSON)
        self.assertIn('refine_prompt on', flow.LESSON)
        self.assertIn('25 steps', flow.LESSON)
        self.assertIn('Lightning LoRA strength 0', flow.LESSON)
        self.assertIn('refine_prompt off', flow.LESSON_2)
        self.assertIn('4 steps', flow.LESSON_2)
        self.assertIn('Lightning LoRA strength 1', flow.LESSON_2)
        self.assertIn('refine_prompt on', plugin.SESSION_RULES)
        self.assertIn('Cloud Recipe', plugin.SESSION_RULES)
        self.assertIn('paid', plugin.SESSION_RULES)
        self.assertIn('never queue', flow.SETUP)

    def test_fresh_setup_copy_is_brief_and_keeps_t2i_visible(self):
        import plugin
        from plugin import onboarding_flow as flow
        self.assertIn('open Local Recipe/RCPlocal_t2i_qwen_image_2-1.json visibly', plugin.FIRST_RUN)
        self.assertIn('Keep the setup introduction to one short sentence', flow.SETUP)
        self.assertIn('End the bulk-download choice at the closing size parenthesis', flow.SETUP)
        self.assertNotIn('tutorial starts as soon as step 1 is ready', flow.SETUP)
        self.assertIn('return to the text-to-image tab', flow.SETUP)

    def test_tutorial_refreshes_before_prompt_handoff_and_waits_quietly_after_completion(self):
        from plugin import onboarding_flow as flow
        self.assertIn('before asking for the image description', flow.LESSON)
        self.assertIn('do not poll the page', flow.NEXT_AFTER_1)
        tutorial=(ROOT/'skills/first-image-tutorial/SKILL.md').read_text()
        self.assertIn('before asking for the image description', tutorial)
        self.assertIn('do not poll the page', tutorial)

    def test_first_run_instructions_do_not_force_ordinary_question(self):
        import plugin
        self.assertIn('comfy_onboarding',plugin.FIRST_RUN)
        self.assertNotIn('and nothing else',plugin.CARD)
        skill=(ROOT/'skills/session/SKILL.md').read_text()
        self.assertIn('/comfy tutorial',skill)

import json
import sqlite3
import tempfile
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from plugin import onboarding


class OnboardingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name); self.manifest={'install_id':str(uuid.uuid4()),'onboarding_version':1}

    def test_new_install_identity_is_unique_and_preserved_on_retry(self):
        from plugin import installer
        a=installer.install_identity()
        b=installer.install_identity()
        self.assertNotEqual(a['install_id'],b['install_id'])
        self.assertEqual(a['onboarding_version'],1)
        self.assertEqual(installer.install_identity(a),a)

    def test_first_session_polling_and_second_session(self):
        a=onboarding.status(self.root,self.manifest,'A')
        self.assertEqual(a['next_step'],'setup_choices')
        for _ in range(3): self.assertEqual(onboarding.status(self.root,self.manifest,'A')['next_step'],'setup_choices')
        b=onboarding.status(self.root,self.manifest,'B')
        self.assertEqual(b['next_step'],'ordinary')
        self.assertEqual(b['first_session_id'],'A')

    def test_preferences_independent_and_second_session_does_not_steal(self):
        onboarding.status(self.root,self.manifest,'A')
        for nodes,models in [('now','now'),('now','on_use'),('on_use','now'),('on_use','on_use')]:
            r=onboarding.preferences(self.root,self.manifest['install_id'],'A',nodes=nodes,models=models)
            self.assertEqual(r['setup_choices'],{'nodes':nodes,'models':models})
        with self.assertRaises(ValueError): onboarding.preferences(self.root,self.manifest['install_id'],'B',nodes='now',models='now')
        r=onboarding.status(self.root,self.manifest,'A')
        self.assertEqual(r['next_step'],'tutorial')
        self.assertNotEqual(r['tutorial']['state'],'completed')

    def test_legacy_is_ordinary_but_explicit_replay_works_without_kickoff(self):
        legacy={'install_id':self.manifest['install_id']}
        self.assertEqual(onboarding.status(self.root,legacy,'old')['next_step'],'ordinary')
        r=onboarding.tutorial(self.root,legacy,'old',replay=True)
        self.assertEqual(r['tutorial']['state'],'awaiting_description')
        self.assertTrue(onboarding.has_tutorial(self.root,'old'))
        self.assertEqual(onboarding.status(self.root,legacy,'old')['next_step'],'tutorial')

    def test_skip_replay_and_other_chat_isolation(self):
        onboarding.status(self.root,self.manifest,'A')
        onboarding.tutorial(self.root,self.manifest,'A')
        onboarding.tutorial(self.root,self.manifest,'B',replay=True)
        onboarding.skip(self.root,self.manifest['install_id'],'B')
        self.assertEqual(onboarding.status(self.root,self.manifest,'A')['tutorial']['state'],'awaiting_description')
        self.assertEqual(onboarding.status(self.root,self.manifest,'B')['next_step'],'ordinary')
        onboarding.tutorial(self.root,self.manifest,'B',replay=True)
        self.assertEqual(onboarding.status(self.root,self.manifest,'B')['next_step'],'tutorial')

    def test_validation_and_corrupt_record_fail_closed(self):
        for sid in ['',None,'x'*513]:
            with self.assertRaises(ValueError): onboarding.status(self.root,self.manifest,sid)
        onboarding.status(self.root,self.manifest,'A')
        with self.assertRaises(ValueError): onboarding.preferences(self.root,self.manifest['install_id'],'A',nodes='yes',models='now')
        from contextlib import closing
        with closing(sqlite3.connect(self.root/'onboarding.sqlite3')) as db, db:
            db.execute('UPDATE installs SET record=?', ('{"schema_version":999}',))
        r=onboarding.status(self.root,self.manifest,'A')
        self.assertEqual(r['next_step'],'recovery')
        self.assertNotIn('setup_choices',r)

    def test_concurrent_sessions_have_one_first_owner(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            rows=list(pool.map(lambda sid:onboarding.status(self.root,self.manifest,sid),['A','B']))
        self.assertEqual(sum(r['next_step']=='setup_choices' for r in rows),1)
        self.assertEqual(len({r['first_session_id'] for r in rows}),1)

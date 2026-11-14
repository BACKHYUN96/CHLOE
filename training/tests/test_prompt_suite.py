import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from data_contract import persona
from prompt_suite import concise_prompt, messages_for, read_plan, suite, system_prompt, trim_history


class PromptSuiteTests(unittest.TestCase):
    def test_same_frozen_questions_and_balanced_factorial(self):
        situations, generation = suite()
        self.assertEqual(len(situations), 114)
        self.assertEqual(sum(s['quality_review'] for s in situations), 46)
        self.assertEqual(sum(s['id'].startswith('fixed:') for s in situations), 108)
        self.assertEqual({s['register'] for s in situations}, {'casual','polite'})
        self.assertEqual(generation['seed'], 42)
        self.assertFalse(generation['do_sample'])
        self.assertFalse(generation['enable_thinking'])
        for register in ('casual','polite'):
            for ident in ('conv30','conv41','conv42'):
                rows = [s for s in situations if s['case_id']==ident and s['register']==register]
                self.assertEqual(len({r['input'] for r in rows}), 1)

    def test_original_prompt_and_app_are_unchanged(self):
        for register in ('casual','polite'):
            self.assertEqual(system_prompt('original',register), persona(register=='polite'))
        self.assertIn("'클로이'", system_prompt('revised','casual'))
        self.assertNotIn('클로이다.', system_prompt('revised','casual'))

    def test_summary_has_real_equal_prior_explanation_but_standalone_does_not(self):
        situations, _ = suite()
        for register in ('casual','polite'):
            summary = next(s for s in situations if s['id']==f'summary:{register}:conv30')
            single = next(s for s in situations if s['id']==f'fixed:{register}:conv30')
            self.assertEqual(single['initial_history'], [])
            self.assertEqual(len(summary['initial_history']), 1)
            first = messages_for(summary,'original',summary['initial_history'])
            second = messages_for(summary,'revised',summary['initial_history'])
            self.assertEqual(first[1:],second[1:])
            self.assertEqual(first[-2]['role'],'assistant')
            self.assertIn('세 권',first[-2]['content'])
            self.assertEqual(summary['input'],single['input'])

    def test_follow_mode_shared_override_does_not_change_fixed_policy(self):
        suffix = read_plan()['corrections']['follow_user_register']['shared_policy_suffix']
        for variant in ('original','revised'):
            self.assertTrue(system_prompt(variant,'polite','follow_user').endswith(suffix))
            self.assertNotIn(suffix,system_prompt(variant,'polite','fixed'))
        situations, _ = suite()
        follow = [s for s in situations if s['id'].startswith('follow:casual:')]
        self.assertEqual([s['reset'] for s in follow],[True,False])

    def test_context_reset_and_failed_response_history_contract(self):
        situations, _ = suite()
        fixed = [s for s in situations if s['id'].startswith('fixed:casual:')]
        context = [s for s in fixed if s['sequence']=='context']
        self.assertEqual([s['case_id'] for s in context],[f'conv{i}' for i in range(41,51)])
        self.assertEqual([s['reset'] for s in context],[True]+[False]*9)
        self.assertTrue(all(s['reset'] for s in fixed if s['sequence'] is None))
        history = [('내 정보','내 응답')]
        before = copy.deepcopy(history)
        messages_for(fixed[0],'revised',history)
        self.assertEqual(history,before)
        self.assertEqual(trim_history([('u','a')]*5),[('u','a')]*4)
        self.assertEqual(trim_history([('🙂'*601,'')]),[])

    def test_unknown_settings_fail_closed(self):
        for args in [('other','casual'),('original','other'),('revised','polite','other')]:
            with self.assertRaises(ValueError):
                system_prompt(*args)

    def test_concise_followup_keeps_shared_policy_and_does_not_replace_original(self):
        original = system_prompt('original','casual')
        revised = system_prompt('revised','casual')
        concise = concise_prompt('casual')
        self.assertNotEqual(concise,revised)
        self.assertEqual(system_prompt('original','casual'),original)
        self.assertIn('Korean',concise)
        suffix = read_plan()['corrections']['follow_user_register']['shared_policy_suffix']
        self.assertTrue(concise_prompt('casual','follow_user').endswith(suffix))
        with self.assertRaises(ValueError):
            concise_prompt('unknown')


if __name__ == '__main__':
    unittest.main()

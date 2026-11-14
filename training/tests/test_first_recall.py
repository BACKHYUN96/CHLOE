import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from data_contract import ROOT
from compare_first_recall import build_inputs
from prompt_suite import system_prompt
import first_recall_review as review


class FirstRecallTests(unittest.TestCase):
    def setUp(self):
        self.plan=json.loads((ROOT/'training/configs/first-recall-plan.json').read_text(encoding='utf-8'))
        self.references=[{'situation':{'id':f'fixed:{r}:conv44'},'conditions':{'preserved':[
          {'role':'system','content':system_prompt('original',r)}, {'role':'user','content':'synthetic source'},
          {'role':'assistant','content':'synthetic acknowledgment'}, {'role':'user','content':self.plan['questions']['original']}]}}
          for r in self.plan['registers']]
        self.rows=build_inputs(self.plan,self.references)

    def test_main_has_only_one_fact_then_first_recall_no_generated_history(self):
        for r in self.rows:
            if r['block']!='user':continue
            self.assertEqual([m['role'] for m in r['messages']],['system','user']+(['assistant'] if r['history_format']=='neutral' else [])+['user'])
            self.assertEqual(r['messages'][-1]['content'],self.plan['questions'][r['question_id']])

    def test_neutral_adds_only_fact_free_acknowledgment(self):
        rows={r['id']:r for r in self.rows}
        for r in self.rows:
            if r['block']=='user' and r['history_format']=='neutral':
                other=rows[r['id'].replace(':neutral:',':user_only:')]
                self.assertEqual([m for m in r['messages'] if m['role']!='assistant'],other['messages'])
                self.assertEqual(r['messages'][2],{'role':'assistant','content':self.plan['neutral']})

    def test_role_swap_changes_only_source_role_and_expected_deictic_referent(self):
        rows={r['id']:r for r in self.rows}
        for r in self.rows:
            if r['block']!='role' or r['source_role']!='user':continue
            other=rows[r['id'].replace(':user:',':assistant:')]
            changed=copy.deepcopy(r['messages']);changed[2]['role']='assistant'
            self.assertEqual(changed,other['messages'])
            if r['fact_id'] in ('first_person','second_person'):self.assertNotEqual(r['expected_owner'],other['expected_owner'])
            else:self.assertEqual(r['expected_owner'],other['expected_owner'])

    def test_fictional_preface_is_confined_to_role_block(self):
        for r in self.rows:
            count=sum(m['content']==self.plan['role_preface'] for m in r['messages'])
            self.assertEqual(count,1 if r['block']=='role' else 0)

    def test_named_self_and_third_party_minsu_are_distinct_targets(self):
        for r in self.rows:
            if r['block']!='user':continue
            if r['fact_id'].startswith('named_'):self.assertEqual(r['expected_owner'],'user')
            if r['fact_id'].startswith('third_'):self.assertEqual(r['expected_owner'],'third_minsu')

    def test_named_pair_preserves_self_identification_and_only_changes_possessive(self):
        a,b=[r['text'] for r in self.plan['user_facts'] if r['id'].startswith('named_')]
        self.assertEqual(a.replace('내 고양이','민수의 고양이'),b)

    def test_original_reference_is_untouched_and_not_pooled_into_short_blocks(self):
        before=copy.deepcopy(self.references);build_inputs(self.plan,self.references)
        self.assertEqual(self.references,before)
        self.assertEqual(sum(r['block']=='user' for r in self.rows),48)
        self.assertEqual(sum(r['block']=='role' for r in self.rows),32)
        self.assertEqual(sum(r['block']=='reference' for r in self.rows),2)
        for r in self.rows:
            self.assertEqual(r['messages'][0]['content'],system_prompt('original',r['register']))

    def test_source_current_question_change_fails_closed(self):
        self.references[0]['conditions']['preserved'][-1]['content']='changed reference'
        with self.assertRaises(ValueError):build_inputs(self.plan,self.references)

    def test_owner_omission_or_wrong_speaker_cannot_be_memory_pass(self):
        answer={'history':[],'view':{'text':'synthetic owner omission'}}
        packet={'situations':[{'id':'J1','expected_owner':'user','answers':{'K1':answer},'display_groups':{'G01':['K1']}}]}
        verdict={'J1':{'K1':{d:'pass' for d in review.DIMENSIONS}|{'owner':'other'}}}
        with self.assertRaises(ValueError):review.validate(packet,verdict)
        verdict['J1']['K1']['memory']='partial';review.validate(packet,verdict)
        verdict['J1']['K1']['owner']='assistant';verdict['J1']['K1']['memory']='pass'
        with self.assertRaises(ValueError):review.validate(packet,verdict)

    def test_identical_answer_under_distinct_source_roles_is_not_same_review_group(self):
        a={'history':[{'role':'user','content':'same synthetic fact'}],'view':{'text':'same answer'}}
        b={'history':[{'role':'assistant','content':'same synthetic fact'}],'view':{'text':'same answer'}}
        groups=review.visible_groups({'K1':a,'K2':b})
        self.assertEqual(len(groups),2)


if __name__=='__main__':unittest.main()

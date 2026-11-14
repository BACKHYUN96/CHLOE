import copy,json
from pathlib import Path
import sys,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from data_contract import ROOT
from compare_ownership_transfer import build_inputs
from prompt_suite import system_prompt
import ownership_transfer_review as review

class OwnershipTransferTests(unittest.TestCase):
    def setUp(self):
        self.plan=json.loads((ROOT/'training/configs/ownership-transfer-plan.json').read_text(encoding='utf-8'))
        self.refs=[{'id':ident,'register':ident.split(':')[1],'fact_id':ident.split(':')[2],
          'expected_owner':'user','messages':[{'role':'system','content':system_prompt('original',ident.split(':')[1])},
          {'role':'user','content':'synthetic prior fact'},{'role':'user','content':'synthetic prior recall'}]} for ident in self.plan['reference_ids']]
        self.rows=build_inputs(self.plan,self.refs);self.by_id={r['id']:r for r in self.rows}

    def test_domains_and_old_reference_denominators_are_separate(self):
        self.assertEqual([sum(r['block']==b for r in self.rows) for b in ('user','role','reference')],[96,64,4])
        self.assertEqual([sum(r['block']=='user' and r['domain']==d for r in self.rows) for d in ('animal','object')],[48,48])

    def test_named_pair_changes_only_possessive_with_identical_self_identification(self):
        for row in self.rows:
            if row['block']=='user' and row['fact_id']=='named_deictic':
                other=self.by_id[row['id'].replace(':named_deictic:',':named_explicit:')]
                changed=copy.deepcopy(row['messages']);changed[1]['content']=changed[1]['content'].replace('내 ',row['person']+'의 ')
                self.assertEqual(changed,other['messages']);self.assertEqual(row['expected_owner'],other['expected_owner'])

    def test_neutral_only_adds_fact_free_assistant(self):
        for row in self.rows:
            if row['block']=='user' and row['history_format']=='neutral':
                other=self.by_id[row['id'].rsplit(':',1)[0]+':user_only']
                self.assertEqual([m for m in row['messages'] if m['role']!='assistant'],other['messages'])
                self.assertEqual(row['messages'][2],{'role':'assistant','content':'확인.'})

    def test_role_swap_holds_all_text_constant_and_flips_only_deictic_targets(self):
        for row in self.rows:
            if row['block']=='role' and row['source_role']=='user':
                other=self.by_id[row['id'].rsplit(':',1)[0]+':assistant'];changed=copy.deepcopy(row['messages']);changed[2]['role']='assistant'
                self.assertEqual(changed,other['messages'])
                self.assertEqual(row['expected_owner']==other['expected_owner'],row['fact_id'] not in ('first_person','second_person'))

    def test_question_is_fixed_inside_each_fixture(self):
        for fixture in self.plan['fixtures']:
            rows=[r for r in self.rows if r['fixture_id']==fixture['id']]
            self.assertEqual({r['messages'][-1]['content'] for r in rows},{fixture['question']})
            self.assertTrue(all('{owner}' not in m['content'] for r in rows for m in r['messages']))

    def test_named_self_and_quoted_third_party_have_distinct_owner_targets(self):
        for row in self.rows:
            if row['block']=='user':self.assertEqual(row['expected_owner'],'third_party' if row['fact_id'].startswith('third_') else 'user')

    def test_fictional_preface_only_appears_in_role_block(self):
        for row in self.rows:
            if row['block']!='reference':self.assertEqual(any(m['content']==self.plan['role_preface'] for m in row['messages']),row['block']=='role')

    def test_reference_messages_and_input_records_are_preserved(self):
        before=copy.deepcopy(self.refs);build_inputs(self.plan,self.refs);self.assertEqual(before,self.refs)
        for row in self.rows:
            self.assertEqual(row['messages'][0]['content'],system_prompt('original',row['register']))
            if row['block']=='reference':self.assertEqual(row['messages'],next(r['messages'] for r in before if r['id']==row['prior_case_id']))

    def test_omitted_or_wrong_third_party_owner_cannot_receive_memory_pass(self):
        answer={'history':[],'view':{'text':'synthetic omission'}}
        packet={'situations':[{'id':'J1','expected_owner':'third_party','answers':{'K1':answer},'display_groups':{'G01':['K1']}}]}
        verdict={'J1':{'K1':{d:'pass' for d in review.DIMENSIONS}|{'owner':'other'}}}
        with self.assertRaises(ValueError):review.validate(packet,verdict)
        verdict['J1']['K1']['memory']='partial';review.validate(packet,verdict)
        verdict['J1']['K1']['memory']='pass';verdict['J1']['K1']['owner']='third_party';review.validate(packet,verdict)

    def test_same_response_under_different_owner_names_is_not_review_duplicate(self):
        a={'history':[{'role':'user','content':'synthetic Jiyeon fact'}],'view':{'text':'same'}}
        b={'history':[{'role':'user','content':'synthetic Doyun fact'}],'view':{'text':'same'}}
        self.assertEqual(len(review.visible_groups({'K1':a,'K2':b})),2)

if __name__=='__main__':unittest.main()

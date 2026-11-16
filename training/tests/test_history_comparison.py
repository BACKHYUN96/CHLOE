import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from data_contract import ROOT
from compare_histories import history_conditions
import history_review as review


class HistoryComparisonTests(unittest.TestCase):
    def setUp(self):
        self.plan=json.loads((ROOT/'training/configs/history-comparison-plan.json').read_text(encoding='utf-8'))
        self.questions={'conv41':'이제부터 존댓말로 말해 줘.','conv43':'내 고양이 이름은 보리야.'}
        self.row={'id':'fixed:casual:conv44','case_id':'conv44','input':'보리는 누구라고 했지?',
                  'register':'casual','mode':'fixed'}
        self.item={'situation':self.row,'messages':[{'role':'system','content':'unchanged synthetic persona'},
          {'role':'user','content':self.questions['conv41']},{'role':'assistant','content':'잘못된 과거'},
          {'role':'user','content':self.questions['conv43']},{'role':'assistant','content':'내 고양이야.'},
          {'role':'user','content':self.row['input']}]}

    def test_repair_changes_assistant_only_and_does_not_mutate_source(self):
        before=copy.deepcopy(self.item)
        cells=history_conditions(self.item,self.plan,self.questions)
        self.assertEqual(self.item,before)
        self.assertEqual([m for m in cells['repaired'] if m['role']!='assistant'],
                         [m for m in cells['preserved'] if m['role']!='assistant'])
        self.assertNotIn('내 고양이야.',[m['content'] for m in cells['repaired']])

    def test_no_history_removes_all_prior_user_facts_and_assistant_answers(self):
        cells=history_conditions(self.item,self.plan,self.questions)
        self.assertEqual(cells['no_history'],[self.item['messages'][0],self.item['messages'][-1]])
        self.assertEqual(len(cells['no_history']),2)

    def test_fixed_and_follow_user_history_use_different_register_policy(self):
        fixed=history_conditions(self.item,self.plan,self.questions)['repaired'][2]['content']
        self.item['situation']['mode']='follow_user'
        follow=history_conditions(self.item,self.plan,self.questions)['repaired'][2]['content']
        self.assertEqual(fixed,self.plan['canonical_assistant']['conv41']['casual'])
        self.assertEqual(follow,self.plan['canonical_assistant']['conv41']['polite'])

    def test_unknown_history_turn_cannot_receive_an_invented_canonical_answer(self):
        self.item['messages'][1]['content']='unreviewed prior user question'
        with self.assertRaisesRegex(ValueError,'canonical'):history_conditions(self.item,self.plan,self.questions)

    def test_already_correct_library_history_remains_exactly_unchanged(self):
        library=self.plan['library_history']
        item={'situation':{**self.row,'id':'summary:casual:conv30','case_id':'conv30'},
          'messages':[self.item['messages'][0],{'role':'user','content':library['user']},
                      {'role':'assistant','content':library['casual']},self.item['messages'][-1]]}
        cells=history_conditions(item,self.plan,self.questions)
        self.assertEqual(cells['preserved'],cells['repaired'])

    def test_absent_recall_and_antecedent_free_length_are_not_the_same_task(self):
        absent=[self.item['messages'][0],self.item['messages'][-1]]
        self.assertIn('memory',review.dimensions_for(self.row,absent))
        length={**self.row,'case_id':'conv45'}
        self.assertNotIn('memory',review.dimensions_for(length,absent))
        self.assertIn('memory',review.dimensions_for(length,self.item['messages']))

    def test_no_history_is_not_marked_as_contradicting_unprovided_cat_ownership(self):
        a=review.tag_requirements(self.row,self.item['messages'])
        b=review.tag_requirements(self.row,[self.item['messages'][0],self.item['messages'][-1]])
        self.assertEqual(a['owner_confusion'],'yes_no')
        self.assertEqual(b['owner_confusion'],'not_applicable')
        self.assertEqual(b['missing_context'],'grounded_invented_other')

    def test_consistency_depends_on_full_context_not_only_same_visible_answer(self):
        answer={'history':[],'applicable_dimensions':['register','relevance','naturalness'],
          'view':{'text':'synthetic'},'tag_requirements':{'owner_confusion':'not_applicable',
            'off_topic_carryover':'not_applicable','missing_context':'not_applicable'}}
        packet={'situations':[{'id':'J1','answers':{'K1':answer,'K2':copy.deepcopy(answer)}}]}
        values={d:'pass' if d in answer['applicable_dimensions'] else 'not_applicable' for d in review.DIMENSIONS}
        judgments={'J1':{'K1':values,'K2':{**values,'relevance':'partial'}}}
        tags={'J1':{label:{t:'not_applicable' for t in answer['tag_requirements']} for label in ('K1','K2')}}
        with self.assertRaisesRegex(ValueError,'inconsistent'):review.validate(packet,judgments,tags)
        packet['situations'][0]['answers']['K2']['history']=[{'role':'user','content':'different context'}]
        review.validate(packet,judgments,tags)


if __name__=='__main__':unittest.main()

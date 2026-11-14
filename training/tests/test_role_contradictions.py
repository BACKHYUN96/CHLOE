import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from data_contract import ROOT
from compare_role_contradictions import conditions_for
from compare_source_histories import conditions_for as previous_conditions
import role_contradiction_review as review


class RoleContradictionTests(unittest.TestCase):
    def setUp(self):
        self.plan=json.loads((ROOT/'training/configs/role-contradiction-plan.json').read_text(encoding='utf-8'))
        self.messages=[{'role':'system','content':'synthetic system'}]
        for i in range(3):self.messages.extend([{'role':'user','content':f'synthetic user fact {i}'},
          {'role':'assistant','content':f'보리는 내 고양이네. 그대로 둘 문장 {i}.'}])
        self.messages.append({'role':'user','content':'아까 말한 내용을 한 줄로 요약해 줘.'})
        self.item={'situation':{'id':'fixed:casual:conv46','case_id':'conv46','register':'casual',
          'mode':'fixed','input':self.messages[-1]['content']},'conditions':{'preserved':self.messages}}

    def test_neutral_keeps_role_alternation_and_every_user_character(self):
        cells,_,meta=conditions_for(self.item,self.plan)
        self.assertEqual([m['role'] for m in cells['neutral']],[m['role'] for m in self.messages])
        self.assertEqual([m for m in cells['neutral'] if m['role']!='assistant'],cells['user_only'])
        self.assertTrue(all(m['content']==self.plan['neutral_text'] for m in cells['neutral'] if m['role']=='assistant'))
        self.assertEqual(meta['preserved']['remaining_owner_errors'],3)
        self.assertEqual(meta['neutral']['remaining_owner_errors'],0)
        self.assertEqual(meta['user_only']['remaining_owner_errors'],0)

    def test_user_only_does_not_merge_user_turns_or_add_facts(self):
        cells,_,_=conditions_for(self.item,self.plan)
        self.assertEqual(cells['user_only'],[m for m in self.messages if m['role']!='assistant'])

    def test_newest_first_edits_latest_one_and_leaves_older_errors(self):
        cells,_,meta=conditions_for(self.item,self.plan)
        self.assertEqual(meta['newest1']['edited_message_indices'],[6])
        self.assertEqual(cells['newest1'][2],self.messages[2])
        self.assertIn('네 고양이',cells['newest1'][6]['content'])

    def test_oldest_first_keeps_recent_error_while_fixing_earliest(self):
        cells,_,meta=conditions_for(self.item,self.plan)
        self.assertEqual(meta['oldest1']['edited_message_indices'],[2])
        self.assertEqual(cells['oldest1'][6],self.messages[6])

    def test_saturation_counts_actual_edits_and_orders_share_only_full_endpoint(self):
        cells,_,meta=conditions_for(self.item,self.plan)
        self.assertEqual(meta['newest4']['requested_edits'],4);self.assertEqual(meta['newest4']['applied_edits'],3)
        self.assertEqual(cells['newest4'],cells['newest3']);self.assertEqual(cells['newest4'],cells['oldest4'])
        self.assertNotEqual(cells['newest1'],cells['oldest1'])

    def test_nested_steps_change_only_selected_possessive_spans_without_mutating_source(self):
        before=copy.deepcopy(self.item);cells,edits,meta=conditions_for(self.item,self.plan)
        self.assertEqual(self.item,before)
        self.assertEqual(meta['newest2']['applied_edits'],2)
        changed=[i for i,(a,b) in enumerate(zip(self.messages,cells['newest2'])) if a!=b]
        self.assertEqual(changed,[4,6])
        for edit in edits[1:]:
            index=edit['message_index'];text=self.messages[index]['content'];start,end=edit['span']
            self.assertEqual(cells['newest2'][index]['content'],text[:start]+'네'+text[end:])

    def test_zero_eligible_errors_are_unchanged_correction_controls(self):
        for m in self.messages:
            if m['role']=='assistant':m['content']='synthetic fact-free prior answer'
        cells,edits,meta=conditions_for(self.item,self.plan)
        self.assertFalse(edits)
        for name in ('newest1','oldest1','newest4','oldest4'):
            self.assertEqual(cells[name],self.messages);self.assertEqual(meta[name]['applied_edits'],0)

    def test_newest_one_matches_previous_single_edit_reference(self):
        cells,_,_=conditions_for(self.item,self.plan)
        previous,_=previous_conditions(self.item,self.plan)
        self.assertEqual(cells['newest1'],previous['owner_sentence'])
        self.assertEqual(cells['user_only'],previous['user_only'])

    def test_display_grouping_includes_history_not_only_answer_text(self):
        a={'history':[{'role':'user','content':'fact A'}],'view':{'text':'same'}}
        b={'history':[{'role':'user','content':'fact B'}],'view':{'text':'same'}}
        answers={'K1':a,'K2':b,'K3':copy.deepcopy(a)};groups=review.visible_groups(answers)
        self.assertEqual(len(groups),2);review.validate_grouping(answers,groups)
        with self.assertRaises(ValueError):review.validate_grouping(answers,{'G1':['K1','K2','K3']})

    def test_owner_omission_cannot_be_labeled_correct_by_absent_confusion(self):
        answer={'history':[],'applicable_dimensions':['register','relevance','naturalness','memory'],
          'view':{'text':'synthetic omission'},'tag_requirements':{'owner_resolution':'owner_resolution','owner_confusion':'yes_no','off_topic_carryover':'not_applicable'}}
        packet={'situations':[{'id':'J1','answers':{'K1':answer},'display_groups':{'G01':['K1']}}]}
        values={d:('partial' if d=='memory' else 'pass') if d in answer['applicable_dimensions'] else 'not_applicable' for d in review.DIMENSIONS}
        tags={'J1':{'K1':{'owner_resolution':'other','owner_confusion':'no','off_topic_carryover':'not_applicable'}}}
        review.validate(packet,{'J1':{'K1':values}},tags)
        tags['J1']['K1']['owner_resolution']='wrong_owner'
        with self.assertRaises(ValueError):review.validate(packet,{'J1':{'K1':values}},tags)


if __name__=='__main__':unittest.main()

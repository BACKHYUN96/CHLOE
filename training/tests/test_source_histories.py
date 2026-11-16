import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from data_contract import ROOT
from compare_source_histories import conditions_for
from source_history_review import review_context


class SourceHistoryTests(unittest.TestCase):
    def setUp(self):
        self.plan=json.loads((ROOT/'training/configs/source-history-plan.json').read_text(encoding='utf-8'))
        self.row={'id':'fixed:casual:conv45','case_id':'conv45','register':'casual','mode':'fixed','input':'짧게 말해 줘.'}
        self.messages=[{'role':'system','content':'synthetic unchanged system'},
          {'role':'user','content':'내 고양이 이름은 보리야.'},
          {'role':'assistant','content':'보리는 내 고양이네. 다른 문장은 그대로 둬.'},
          {'role':'user','content':'보리는 누구라고 했지?'},
          {'role':'assistant','content':'보리는 내 고양이네. 오늘도 함께할래?'},
          {'role':'user','content':self.row['input']}]
        self.item={'situation':self.row,'conditions':{'preserved':self.messages}}

    def test_user_only_keeps_exact_user_facts_order_and_roles_without_new_labels(self):
        cells,_=conditions_for(self.item,self.plan)
        self.assertEqual(cells['user_only'],[self.messages[i] for i in (0,1,3,5)])
        self.assertEqual([m['role'] for m in cells['user_only']],['system','user','user','user'])

    def test_one_owner_edit_preserves_older_error_and_following_sentence(self):
        cells,patch=conditions_for(self.item,self.plan)
        self.assertEqual(patch['message_index'],4)
        self.assertEqual(cells['owner_sentence'][2],self.messages[2])
        self.assertEqual(cells['owner_sentence'][4]['content'],'보리는 네 고양이네. 오늘도 함께할래?')
        self.assertEqual([i for i,(a,b) in enumerate(zip(self.messages,cells['owner_sentence'])) if a!=b],[4])

    def test_polite_edit_changes_only_possessive_span(self):
        self.item['situation']['register']='polite'
        cells,patch=conditions_for(self.item,self.plan)
        before=self.messages[patch['message_index']]['content'];start,end=patch['span']
        self.assertEqual(cells['owner_sentence'][patch['message_index']]['content'],before[:start]+'당신의'+before[end:])

    def test_later_non_owner_assistant_answer_is_preserved_and_recency_recorded(self):
        self.messages[-1:-1]=[{'role':'user','content':'내 앱 이름은 예시야.'},
                              {'role':'assistant','content':'앱 이름은 예시야.'}]
        cells,patch=conditions_for(self.item,self.plan)
        self.assertEqual(patch['later_assistant_turns'],1)
        self.assertEqual(cells['owner_sentence'][-2],self.messages[-2])

    def test_no_prior_explicit_wrong_owner_is_unchanged_control(self):
        self.messages[2]['content']='고양이 이름이구나.';self.messages[4]['content']='보리라는 이름을 말했구나.'
        cells,patch=conditions_for(self.item,self.plan)
        self.assertIsNone(patch);self.assertEqual(cells['owner_sentence'],self.messages)

    def test_original_inputs_are_never_mutated(self):
        before=copy.deepcopy(self.item);conditions_for(self.item,self.plan)
        self.assertEqual(self.item,before)

    def test_second_sentence_owner_is_not_silently_rewritten(self):
        for i in (2,4):self.messages[i]['content']='첫 문장은 다른 내용이야. 보리는 내 고양이네.'
        cells,patch=conditions_for(self.item,self.plan)
        self.assertIsNone(patch);self.assertEqual(cells['owner_sentence'],self.messages)

    def test_user_facts_memory_is_kept_but_lost_assistant_library_facts_are_not_required(self):
        cells,_=conditions_for(self.item,self.plan)
        self.assertIn('memory',review_context(self.row,cells['user_only'])[0])
        library={**self.row,'id':'summary:casual:conv30','case_id':'conv30'}
        library_messages=[self.messages[0],{'role':'user','content':'가상 도서관 이용 방법을 설명해 줘.'},self.messages[-1]]
        self.assertNotIn('memory',review_context(library,library_messages)[0])
        library_messages.insert(2,{'role':'assistant','content':'synthetic supplied hours and loan facts'})
        self.assertIn('memory',review_context(library,library_messages)[0])


if __name__=='__main__':unittest.main()

import copy
import hashlib
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from export_summary_relevance_results import retained_history
ROOT=Path(__file__).resolve().parents[2]
class SummaryRelevanceIntegrityTests(unittest.TestCase):
 def source(self):
  return [{'role':'system','content':'AI'},{'role':'user','content':'내 강아지 이름은 하루야.'},{'role':'assistant','content':'확인.'},{'role':'user','content':'수다 떨자.'}]
 def test_whole_pair_omission_keeps_source_and_current_input(self):
  source=self.source();before=copy.deepcopy(source);self.assertEqual(retained_history(source,[source[0],source[-1]]),[1,2]);self.assertEqual(source,before)
 def test_rewriting_owner_is_not_retrieval(self):
  source=self.source();actual=copy.deepcopy(source);actual[1]['content']='내 강아지가 아니라 클로이 강아지야.'
  with self.assertRaises(AssertionError):retained_history(source,actual)
 def test_half_pair_removal_is_rejected(self):
  source=self.source()
  with self.assertRaises(AssertionError):retained_history(source,[source[0],source[2],source[3]])
 def test_current_question_cannot_be_changed(self):
  source=self.source();actual=copy.deepcopy(source);actual[-1]['content']='다른 질문'
  with self.assertRaises(AssertionError):retained_history(source,actual)
 def test_previous_policy_is_frozen_not_replaced_by_current_source(self):
  plan=json.loads((ROOT/'training/configs/grounding-plan.json').read_text(encoding='utf-8'));snapshot=ROOT/plan['policy_source'];self.assertTrue(str(snapshot).endswith('.java.txt'));self.assertEqual(hashlib.sha256(snapshot.read_bytes().replace(b'\r\n',b'\n')).hexdigest(),'5fcc4902c4cd75530909a126b96ffcaf1d6a6636fce1fa5d899aa872d8510387')
if __name__=='__main__':unittest.main()

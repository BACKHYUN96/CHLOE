import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from data_contract import load_records, persona, validate_reply


def fixture():
    # Unit-test fixture only; never installed as a training dataset.
    reply = {'spoken_text':'별 모양을 그려 보자.', 'intent':'chat', 'emotion':'neutral',
             'delivery':{'pace':'normal','energy':'medium','expressiveness':'restrained'}, 'tts_instruction':''}
    return {'id':'unit-only', 'source':'unit-test', 'license':'test-only', 'review_status':'approved',
            'reviewer':'test-fixture', 'approval_scope':'10-step mechanical smoke only',
            'split':'train','family_id':'paper-star','register':'casual',
            'messages':[{'role':'system','content':persona(False)},
                        {'role':'user','content':'길쭉한 종이에 별을 그리는 중이야.'},
                        {'role':'assistant','content':json.dumps(reply,ensure_ascii=False)}]}


class DataContractTests(unittest.TestCase):
    def load(self, rows):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'test.jsonl'
            path.write_text('\n'.join(json.dumps(row,ensure_ascii=False) for row in rows),encoding='utf-8')
            return load_records(path)

    def test_pending_sample_is_rejected(self):
        row = fixture()
        row['review_status'] = 'pending'
        with self.assertRaisesRegex(ValueError, 'human review'):
            self.load([row])

    def test_family_cannot_cross_split(self):
        first = fixture()
        second = copy.deepcopy(first)
        second.update(id='unit-other',split='validation')
        with self.assertRaisesRegex(ValueError, 'family leaks'):
            self.load([first,second])

    def test_reserved_evaluation_input_is_rejected(self):
        row = fixture()
        row['messages'][1]['content'] = '안녕, 클로이.'
        with self.assertRaisesRegex(ValueError, 'Reserved evaluation'):
            self.load([row])

    def test_schema_and_persona_contract(self):
        self.assertEqual(len(self.load([fixture()])),1)
        obj = json.loads(fixture()['messages'][-1]['content'])
        obj['tts_instruction']='speak warmly'
        with self.assertRaisesRegex(ValueError,'empty tts_instruction'):
            validate_reply(json.dumps(obj))
        obj['tts_instruction']=''
        obj['style']='casual'
        with self.assertRaisesRegex(ValueError,'Unexpected output key'):
            validate_reply(json.dumps(obj))


if __name__ == '__main__':
    unittest.main()

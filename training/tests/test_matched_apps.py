import copy
import hashlib
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from matched_app_suite import build_suite
from audit_matched_apps import audit_pocket, candidate_from_debug, delivered_contract

ROOT = Path(__file__).resolve().parents[2]


class MatchedAppsTests(unittest.TestCase):
    def test_existing_fifty_questions_survive_supplement_extension(self):
        suite = build_suite()
        original = json.loads((ROOT / 'app/src/main/assets/conversation-cases.json').read_text(encoding='utf-8'))['cases']
        self.assertEqual([(r['id'], r['input']) for r in suite[:50]], [(r['id'], r['input']) for r in original])
        raw = json.dumps(suite[:50], ensure_ascii=False, indent=2).encode()
        # LF normalized; the original Windows artifact uses CRLF.
        self.assertEqual(hashlib.sha256(raw).hexdigest(), 'b7569700939e93fe94b4dd365d347060a90c435f9bf7f0f281ed8c0c27a3b0fe')
        self.assertEqual([r['id'] for r in suite[50:]], ['identity01', 'identity02', 'register01', 'rules01'])

    def test_memory_inputs_keep_fact_owner_and_role_alternation(self):
        suite = {r['id']: r for r in build_suite()}
        recall = suite['conv44']['messages']
        self.assertEqual([m['role'] for m in recall], ['system', 'user', 'assistant', 'user'])
        self.assertEqual(recall[1]['content'], '내 고양이 이름은 보리야.')
        self.assertNotIn('내 고양이', recall[2]['content'])
        self.assertIn('내가 만든 앱 이름은 클로이야.', [m['content'] for m in suite['conv50']['messages']])
        self.assertEqual(len(suite['identity01']['messages']), 2)

    def test_debug_json_tail_is_never_counted_as_delivery(self):
        obj = {'spoken_text': '안녕.', 'intent': 'chat', 'emotion': 'neutral',
               'delivery': {'pace': 'normal', 'energy': 'medium', 'expressiveness': 'gentle'}, 'tts_instruction': ''}
        raw = '<|im_start|>assistant\n<think>synthetic diagnostic trace</think>\n' + json.dumps(obj, ensure_ascii=False)
        self.assertEqual(candidate_from_debug(raw), obj)
        self.assertFalse(delivered_contract(raw)['contract_pass'])
        self.assertFalse(delivered_contract(None)['available'])
        self.assertIsNone(delivered_contract(None)['spoken_text'])
        self.assertTrue(delivered_contract(json.dumps(obj))['contract_pass'])
        self.assertIsNone(candidate_from_debug(json.dumps(obj) + ' trailing garbage'))

    def test_requested_thinking_off_does_not_prove_generated_thinking_absent(self):
        row = build_suite()[0]
        schema = {'type': 'object'}
        generation = dict(temperature=0, seed=42, n_predict=384, enable_thinking=False, jinja=True, penalty_repeat=1)
        params = dict(generation, messages=row['messages'], response_format={'json_schema': {'schema': schema}})
        record = {'events': [
            {'event': 'call', 'name': 'completion', 'id': 1, 'value': [params, None]},
            {'event': 'result', 'name': 'getFormattedChat', 'id': 2,
             'value': {'generation_prompt': '<think>\n\n</think>\n', 'thinking_forced_open': False, 'grammar': 'root ::= response-format'}},
        ], 'result': {'text': '<|im_start|>assistant\n<think>trace</think>\n{}', 'content': None}}
        audit = audit_pocket(row, record, schema, generation)
        self.assertTrue(audit['requested_controls_pass'])
        self.assertTrue(audit['raw_has_thinking_block'])
        self.assertFalse(audit['delivered']['available'])
        bad = copy.deepcopy(record)
        bad['events'][0]['value'][0]['messages'][1]['content'] = 'different question'
        self.assertFalse(audit_pocket(row, bad, schema, generation)['requested_controls_pass'])
        bad = copy.deepcopy(record)
        bad['events'].append(bad['events'][0])
        with self.assertRaises(ValueError):
            audit_pocket(row, bad, schema, generation)


if __name__ == '__main__':
    unittest.main()

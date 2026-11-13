"""Integrity/privacy tests for the human review bundle, using synthetic fixtures."""
import json
from pathlib import Path
import random
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1]/'scripts'
sys.path.insert(0, str(SCRIPTS))
from build_blind_review import ROOT, blank_scores, build, make_packet, read, write


class BlindReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.source = Path(self.temp.name)/'source'
        self.source.mkdir()
        self.plan = read(ROOT/'training/configs/blind-review-plan.json')
        self.questions = {}
        self.summary = {'results': []}
        write(self.source/'blind-mapping.local.json', {'base': 'B', 'adapter': 'A'})
        for group in self.plan['groups']:
            for register in group['registers']:
                for case in group['cases']:
                    self.questions[case] = '공통 질문 '+case
                    for candidate, old in [('base','B'),('adapter','A')]:
                        text = f'  {candidate} {register} {case}\n끝.  '
                        reply = {'spoken_text': text, 'intent': 'chat', 'emotion': 'warm',
                                 'delivery': {'pace':'normal','energy':'medium','expressiveness':'gentle'},
                                 'tts_instruction': ''}
                        response = {'raw': json.dumps(reply), 'reply': reply, 'eos_reached': True,
                                    'diagnostics': {'contract_valid': True}, 'contract_mode': 'constrained'}
                        write(self.source/f'{old}-{register}-{case}.local.json', response)
                        self.summary['results'].append({'candidate':candidate,'register':register,
                                                        'id':case,'diagnostics':{'contract_valid':True}})

    def packet(self, seed=7):
        return make_packet(self.source, self.plan, self.questions, self.summary, random.Random(seed))

    def test_coverage_balance_exact_text_context_and_blank_grades(self):
        packet, key, hashes = self.packet()
        self.assertEqual(len(packet['items']), 22)
        self.assertEqual(sum(len(i['turns']) for i in packet['items']), 40)
        self.assertEqual(len(hashes), 80)
        self.assertEqual(sum(k['mapping']['A']=='base' for k in key.values()), 11)
        for item in packet['items']:
            k = key[item['id']]
            if item['category'] == '문맥 기억':
                self.assertEqual(k['source_case_ids'], [f'conv{n}' for n in range(41,51)])
            for turn, case in zip(item['turns'], k['source_case_ids']):
                self.assertEqual(turn['question'], self.questions[case])
                for side in ['A','B']:
                    self.assertEqual(turn[side], f"  {k['mapping'][side]} {k['register']} {case}\n끝.  ")
        grades = blank_scores(packet)
        self.assertTrue(all(r['preference'] is None and not r['comment'] and
                            all(v is None for side in ['A','B'] for v in r[side].values())
                            for r in grades['ratings'].values()))
        # Metadata projection has no source ID, candidate or mapping field.
        self.assertEqual(set(packet), {'version','packet_id','items'})
        self.assertEqual(set(packet['items'][0]), {'id','category','register','turns'})

    def test_blinding_changes_without_rewriting_answers(self):
        first, k1, h1 = self.packet(1)
        second, k2, h2 = self.packet(2)
        self.assertNotEqual(first['packet_id'], second['packet_id'])
        self.assertNotEqual(k1, k2)
        self.assertEqual(h1, h2)

    def test_invalid_response_is_rejected(self):
        path = self.source/'B-casual-conv01.local.json'
        r = read(path)
        r['reply']['spoken_text'] = '조작'
        path.write_text(json.dumps(r), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'mismatch'):
            self.packet()

    def test_no_overwrite_and_key_must_be_private(self):
        root = Path(self.temp.name)
        output = root/'output'
        output.mkdir()
        private = root/'artifacts/llm-training/key'
        with self.assertRaises(FileExistsError):
            build(self.source, output, private, root/'audit.json', root=root)
        with self.assertRaises(ValueError):
            build(self.source, root/'new', root/'public-key', root/'audit.json', root=root)
        with self.assertRaises(ValueError):
            build(self.source, private/'nested', private, root/'audit.json', root=root)

    def test_changed_source_receipt_is_rejected_before_writing(self):
        root = Path(self.temp.name)
        (root/'docs/validation/local-llm-contract-20261114').mkdir(parents=True)
        write(root/'docs/validation/local-llm-contract-20261114/comparison.json', {'full_local_summary_sha256': 'wrong'})
        write(self.source/'summary.json', self.summary)
        with self.assertRaisesRegex(ValueError, 'preserved'):
            build(self.source, root/'output', root/'artifacts/llm-training/key', root/'audit.json', root=root)
        self.assertFalse((root/'output').exists())


if __name__ == '__main__':
    unittest.main()

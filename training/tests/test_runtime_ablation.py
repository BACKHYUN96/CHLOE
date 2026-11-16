import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from runtime_ablation import audit, encoded, plan, prepare_inputs, token_hash, verify_one_factor
from prompt_suite import suite


class FakeTokenizer:
    def apply_chat_template(self,messages,chat_template=None,tokenize=True,**kwargs):
        self.last_messages = copy.deepcopy(messages)
        self.last_kwargs = kwargs.copy()
        if not tokenize:
            return 'rendered'
        return {'input_ids':[1,2,3] if chat_template=='official' else [1,2,4]}
    def __call__(self,text,add_special_tokens):
        if add_special_tokens:
            raise AssertionError('No duplicate BOS/EOS allowed')
        return {'input_ids':[1,2,3]}


class RuntimeAblationTests(unittest.TestCase):
    def test_exactly_one_factor_changes(self):
        conditions = plan()['conditions']
        verify_one_factor(conditions)
        changed = copy.deepcopy(conditions)
        changed['bf16']['decoder'] = 'off'
        with self.assertRaises(ValueError):
            verify_one_factor(changed)
        changed = copy.deepcopy(conditions)
        changed['training_template'] = changed['baseline'].copy()
        with self.assertRaises(ValueError):
            verify_one_factor(changed)

    def test_schema_conditioning_and_history_are_identical_and_unmutated(self):
        tokenizer = FakeTokenizer()
        messages = [{'role':'system','content':'persona'},{'role':'user','content':'fact'},
                    {'role':'assistant','content':'answer'},{'role':'user','content':'same question'}]
        before = copy.deepcopy(messages)
        encoded(tokenizer,messages,'official')
        bound = copy.deepcopy(tokenizer.last_messages)
        encoded(tokenizer,messages,'training')
        self.assertEqual(tokenizer.last_messages,bound)
        self.assertEqual(messages,before)
        self.assertIn('JSON Schema',bound[0]['content'])
        self.assertEqual(bound[1:],messages[1:])
        self.assertFalse(tokenizer.last_kwargs['enable_thinking'])
        self.assertTrue(tokenizer.last_kwargs['add_generation_prompt'])

    def test_template_token_audit_detects_difference_without_extra_special_tokens(self):
        payload = [{'situation':{'id':'case'},'messages':[{'role':'system','content':'p'},{'role':'user','content':'q'}]}]
        rows = audit(FakeTokenizer(),'official','training',payload)
        self.assertFalse(rows[0]['token_ids_identical'])
        self.assertTrue(rows[0]['manual_encoding_identical'])
        self.assertEqual(rows[0]['official_ids_sha256'],token_hash([1,2,3]))

    def test_same_preselected_situations_and_no_prompt_rewrite(self):
        rows,_ = suite()
        self.assertEqual(sum(r['quality_review'] for r in rows),46)
        self.assertEqual(plan()['prompt'],'original existing app persona only; no prompt edits')
        self.assertEqual(set(plan()['conditions']),{'baseline','training_template','bf16','decoder_off'})

    def test_invalid_precision_fails_before_model_load(self):
        from runtime_ablation import load_precision
        with self.assertRaises(ValueError):
            load_precision({},'fp8')


if __name__ == '__main__':
    unittest.main()

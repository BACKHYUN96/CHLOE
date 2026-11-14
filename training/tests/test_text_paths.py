import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import compare_text_paths as paths
from text_path_review import compare_observed


class BaseModel:
    def generate(self,**kwargs):
        return self.result


class TextPathTests(unittest.TestCase):
    def test_attention_mask_difference_is_not_hidden_by_equal_input_ids(self):
        left = {'inputs':{'input_ids':[1,2],'attention_mask':[1,1]},'kwargs':{},'output_ids':[[1,2,3]]}
        right = copy.deepcopy(left)
        right['inputs']['attention_mask'] = [1,0]
        self.assertFalse(compare_observed(left,right)['inputs'])

    def test_special_output_tokens_and_generation_settings_are_compared(self):
        left = {'inputs':{},'kwargs':{'eos_token_id':[1,2]},'output_ids':[[10,1]]}
        right = copy.deepcopy(left)
        right['output_ids'][-1][-1] = 2
        right['kwargs']['eos_token_id'] = [1]
        self.assertEqual(compare_observed(left,right),{'inputs':True,'kwargs':False,'output_ids':False})

    def test_observer_returns_untouched_output_and_restores_inherited_method(self):
        model = BaseModel()
        model.result = object()
        records = []
        with patch.object(paths,'capture_call',return_value={'captured':True}):
            with paths.observe_generate(model,records):
                self.assertIs(model.generate(input_ids='synthetic'),model.result)
        self.assertNotIn('generate',model.__dict__)
        self.assertEqual(records,[{'captured':True}])

    def test_observer_restores_instance_override_even_on_generation_error(self):
        model = BaseModel()
        def fail(**kwargs):raise RuntimeError('synthetic')
        model.generate = fail
        with self.assertRaisesRegex(RuntimeError,'synthetic'):
            with paths.observe_generate(model,[]):model.generate()
        self.assertIs(model.generate,fail)

    def test_malformed_json_is_not_repaired_for_diagnostic_text(self):
        raw = '{"spoken_text":"do not repair'
        self.assertIsNone(paths.response_diagnostic({'raw':raw})['diagnostic_spoken_text'])
        self.assertEqual(paths.response_diagnostic({'raw':raw})['raw'],raw)

    def test_non_string_spoken_text_is_not_silently_stringified(self):
        self.assertIsNone(paths.response_diagnostic({'raw':'{"spoken_text":123}'})['diagnostic_spoken_text'])

    def test_config_audit_detects_cache_and_stop_differences(self):
        changed = paths.changed_fields({'use_cache':True,'eos_token_id':1},
                                       {'use_cache':False,'eos_token_id':[1,2]})
        self.assertEqual(set(changed),{'use_cache','eos_token_id'})


if __name__=='__main__':unittest.main()

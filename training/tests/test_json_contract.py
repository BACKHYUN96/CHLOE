import copy
import json
import sys
import unittest
from pathlib import Path

SCRIPTS=Path(__file__).resolve().parents[1]/'scripts'
sys.path.insert(0,str(SCRIPTS))
from data_contract import ROOT,diagnose_reply
from llm_runtime import contract_messages,contract_schema,decoding_schema
DEPS=ROOT/'artifacts/llm-training/contract-deps-xgrammar-20261114'
if DEPS.is_dir(): sys.path.insert(0,str(DEPS))


def reply():
    return {'spoken_text':'안녕','intent':'chat','emotion':'neutral',
            'delivery':{'pace':'normal','energy':'medium','expressiveness':'restrained'},'tts_instruction':''}


class JsonContractTests(unittest.TestCase):
    def test_schema_is_bound_without_mutating_persona_or_history(self):
        messages=[{'role':'system','content':'persona'},{'role':'user','content':'hello'}]
        before=copy.deepcopy(messages)
        bound=contract_messages(messages,'schema')
        schema=json.loads(bound[0]['content'].split('\n')[-1])
        self.assertEqual(schema['properties']['intent']['enum'],contract_schema()['properties']['intent']['enum'])
        self.assertEqual(schema['properties']['tts_instruction']['enum'],[''])
        self.assertEqual(messages,before)
        self.assertEqual(bound[1:],messages[1:])
        self.assertEqual(contract_messages(messages,'legacy'),messages)

    def test_enum_failure_is_not_misreported_as_json_syntax(self):
        obj=reply()
        obj['intent']='greeting'
        result=diagnose_reply(json.dumps(obj),True,60,384)
        self.assertTrue(result['json_syntax_valid'])
        self.assertFalse(result['schema_valid'])
        self.assertIn({'code':'enum','path':'$.intent'},result['errors'])
        self.assertEqual(obj['intent'],'greeting')  # No output repair.

    def test_token_cap_and_missing_key_remain_failures(self):
        obj=reply()
        del obj['tts_instruction']
        result=diagnose_reply(json.dumps(obj),False,384,384)
        self.assertIn({'code':'missing_key','path':'$.tts_instruction'},result['errors'])
        self.assertIn({'code':'token_limit','path':'$'},result['errors'])
        self.assertFalse(diagnose_reply('{',True,1,384)['json_syntax_valid'])

    def test_kotlin_utf16_length_and_consumer_safety(self):
        obj=reply()
        obj['spoken_text']='\U0001f642'*111
        self.assertIn({'code':'max_length','path':'$.spoken_text'},
                      diagnose_reply(json.dumps(obj),True,120,384)['errors'])
        obj['spoken_text']='{}'
        self.assertIn({'code':'unsafe_spoken_text','path':'$.spoken_text'},
                      diagnose_reply(json.dumps(obj),True,10,384)['errors'])

    @unittest.skipUnless(DEPS.is_dir(),'optional contract dependencies not installed')
    def test_schema_decoder_rejects_invalid_enum(self):
        import xgrammar as xgr
        tokenizer,grammar=self.grammar()
        for changes in ({'intent':'greeting'},{'spoken_text':'{}'},{'spoken_text':'a'*221},
                        {'tts_instruction':'not empty'}):
            with self.subTest(changes=list(changes)):
                obj=reply()
                obj.update(changes)
                matcher=xgr.GrammarMatcher(grammar)
                rejected=False
                for token in tokenizer.encode(json.dumps(obj,ensure_ascii=False,separators=(',',':')),add_special_tokens=False):
                    if not matcher.accept_token(token):
                        rejected=True
                        break
                self.assertTrue(rejected)

    @unittest.skipUnless(DEPS.is_dir(),'optional contract dependencies not installed')
    def test_premature_decoder_eos_is_rejected(self):
        import xgrammar as xgr
        tokenizer,grammar=self.grammar()
        matcher=xgr.GrammarMatcher(grammar)
        self.assertFalse(matcher.accept_token(248046))
        for token in tokenizer.encode(json.dumps(reply(),ensure_ascii=False,separators=(',',':')),add_special_tokens=False):
            self.assertTrue(matcher.accept_token(token))
        self.assertTrue(matcher.accept_token(248046))
        self.assertTrue(matcher.is_terminated())

    @unittest.skipUnless(DEPS.is_dir() and (ROOT/'artifacts/llm-training/base-Qwen3.5-2B').is_dir(),
                         'optional decoder/Qwen tokenizer not installed')
    def test_qwen_split_utf8_hangul_remains_valid_until_complete_json(self):
        import xgrammar as xgr
        tokenizer,grammar=self.grammar()
        obj=reply()
        obj['spoken_text']='슬픔을 느껴 🎉'
        wanted=tokenizer.encode(json.dumps(obj,ensure_ascii=False,separators=(',',':')),add_special_tokens=False)
        matcher=xgr.GrammarMatcher(grammar)
        for token in wanted:
            self.assertTrue(matcher.accept_token(token))
        self.assertTrue(matcher.accept_token(248046))

    def grammar(self):
        from transformers import AutoTokenizer
        from json_decoding import grammar_for
        tokenizer=AutoTokenizer.from_pretrained(ROOT/'artifacts/llm-training/base-Qwen3.5-2B',local_files_only=True)
        return tokenizer,grammar_for(tokenizer,248320,[248044,248046],decoding_schema())


if __name__=='__main__': unittest.main()

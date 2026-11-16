"""Byte-level JSON Schema decoding using pinned, isolated XGrammar dependencies."""
from functools import lru_cache
from importlib.metadata import version
import json


@lru_cache(maxsize=2)
def compiled_grammar(tokenizer, vocab_size, eos_ids, schema_json):
    import xgrammar as xgr
    if version('xgrammar')!='0.2.9' or version('apache-tvm-ffi')!='0.1.11':
        raise RuntimeError('Use the pinned contract decoding dependencies')
    info=xgr.TokenizerInfo.from_huggingface(tokenizer,vocab_size=vocab_size,stop_token_ids=list(eos_ids))
    compiler=xgr.GrammarCompiler(info)
    return compiler.compile_json_schema(schema_json,strict_mode=True,any_order=True)


def grammar_for(tokenizer, vocab_size, eos_ids, schema):
    return compiled_grammar(tokenizer,vocab_size,tuple(eos_ids),
                            json.dumps(schema,ensure_ascii=False,separators=(',',':')))


def processor(model, tokenizer, schema, eos_ids):
    from xgrammar.contrib.hf import LogitsProcessor
    # Compiled grammar is shared; mutable matcher/processor must be fresh for
    # every generate() call and must never leak state across candidates/cases.
    return LogitsProcessor(grammar_for(tokenizer,model.config.vocab_size,eos_ids,schema))

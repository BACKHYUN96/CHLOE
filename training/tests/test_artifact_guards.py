import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]/'scripts'
sys.path.insert(0,str(SCRIPTS))
from llm_runtime import artifact_output,write_json,stop_token_ids
spec=importlib.util.spec_from_file_location('chloe_export',SCRIPTS/'export.py')
export=importlib.util.module_from_spec(spec)
spec.loader.exec_module(export)


class ArtifactGuards(unittest.TestCase):
    def test_text_and_chat_eos_are_both_recognized(self):
        from types import SimpleNamespace as Object
        model=Object(generation_config=Object(eos_token_id=248044))
        tokenizer=Object(eos_token_id=248046)
        self.assertEqual(stop_token_ids(model,tokenizer),[248044,248046])
        model.generation_config.eos_token_id=[248044,248046]
        self.assertEqual(stop_token_ids(model,tokenizer),[248044,248046])

    def test_invalid_json_does_not_create_partial_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'result.json'
            with self.assertRaises(TypeError):
                write_json(path,{'missing_keys':set()})
            self.assertFalse(path.exists())
            write_json(path,{'completed':False})
            original=path.read_bytes()
            with self.assertRaises(FileExistsError):
                write_json(path,{'completed':True})
            self.assertEqual(path.read_bytes(),original)

    def test_artifact_path_cannot_escape_or_replace_root(self):
        for value in ('training/configs','artifacts/llm-training','artifacts/llm-training/../../training'):
            with self.subTest(value=value),self.assertRaises(ValueError):
                artifact_output(value)

    def test_export_requires_quality_review_and_exact_adapter(self):
        good={'human_review_completed':True,'quality_gain_verified':True,
              'reviewer':'unit-fixture','adapter_sha256':'a'*64}
        export.validate_quality_approval(good,'a'*64)
        for field in ('human_review_completed','quality_gain_verified','reviewer','adapter_sha256'):
            bad=dict(good)
            bad[field]=False
            with self.subTest(field=field),self.assertRaises(ValueError):
                export.validate_quality_approval(bad,'a'*64)


if __name__=='__main__':
    unittest.main()

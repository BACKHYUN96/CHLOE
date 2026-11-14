import importlib.util
import json
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "inspect_model.py"
spec = importlib.util.spec_from_file_location("inspect_model", SCRIPT)
model = importlib.util.module_from_spec(spec)
spec.loader.exec_module(model)


class InspectModelTests(unittest.TestCase):
    def test_download_allowlist_and_no_weight_verification_claim(self):
        urls = []
        template = "{%- if enable_thinking %}think{% endif %}"

        def download(url):
            urls.append(url)
            if "/api/models/" in url:
                return json.dumps({"sha": model.REVISION, "cardData": {"license": "apache-2.0"},
                                   "siblings": [{"rfilename": "model.safetensors", "size": 10,
                                                 "lfs": {"sha256": "a" * 64}}]}).encode()
            name = url.rsplit("/", 1)[1]
            return {"config.json": b'{"model_type":"qwen3_5","text_config":{"model_type":"qwen3_5_text"}}',
                    "chat_template.jinja": template.encode(),
                    "tokenizer_config.json": json.dumps({"chat_template": template}).encode(),
                    "LICENSE": b"Apache License", "README.md": b"test model card"}[name]

        with patch.object(model, "download_metadata", side_effect=download):
            report = model.inspect()
        self.assertEqual(len(urls), 6)
        self.assertFalse(any(url.endswith(".safetensors") for url in urls))
        self.assertTrue(report["tokenizer_template_matches_file"])
        self.assertFalse(report["template_has_generation_markers"])
        self.assertFalse(report["checkpoints"][0]["local_hash_verified"])
        self.assertFalse(report["weights_downloaded"])
        self.assertFalse(report["training_compatibility_verified"])

    def test_revision_mismatch_stops_before_file_downloads(self):
        with patch.object(model, "download_metadata", return_value=b'{"sha":"different"}') as download:
            with self.assertRaisesRegex(ValueError, "Revision mismatch"):
                model.inspect()
        self.assertEqual(download.call_count, 1)

    def test_metadata_size_limit(self):
        from unittest.mock import MagicMock
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b"x" * (model.MAX_BYTES + 1)
        with patch.object(model, "urlopen", return_value=response):
            with self.assertRaisesRegex(ValueError, "size limit"):
                model.download_metadata("https://huggingface.co/example")


if __name__ == "__main__":
    unittest.main()

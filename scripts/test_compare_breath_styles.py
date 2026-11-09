import json
from pathlib import Path
import struct
import tempfile
import unittest
import wave
from compare_breath_styles import SAMPLING, audio_stats, public_summary


class ComparisonReportTest(unittest.TestCase):
    def test_public_summary_omits_private_content_and_paths(self):
        private = "PRIVATE-REFERENCE-DO-NOT-PUBLISH"
        report = dict(model_pack={"model_id": "public-model"}, sampling=SAMPLING,
            native_binary_sha256="test-hash", cases=[dict(id="01", description="private fixture", text=private)],
            styles=[dict(id="B", instruction=private)], clips=[dict(clip_id="01_B", status="generated_unrated",
                audio_seconds=1.0, text=private, instruction=private, log=private, path=private)])
        output = public_summary(report)
        self.assertNotIn(private, json.dumps(output))
        self.assertEqual(output["clips"][0]["audio_seconds"], 1.0)
        self.assertEqual(output["perceptual_evaluation"], "pending")

    def test_pcm_metrics_preserve_sample_count_and_detect_full_scale(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "test.wav"
            with wave.open(str(path), "wb") as wav:
                wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(24000)
                wav.writeframes(struct.pack("<hhhh", 0, 1000, -1000, 32767))
            stats = audio_stats(path)
            self.assertEqual(stats["samples"], 4)
            self.assertEqual(stats["pcm_full_scale_samples"], 1)
            self.assertAlmostEqual(stats["audio_seconds"], 4 / 24000)

    def test_rejects_wrong_sample_format(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "test.wav"
            with wave.open(str(path), "wb") as wav:
                wav.setnchannels(2); wav.setsampwidth(2); wav.setframerate(48000)
                wav.writeframes(b"\0" * 16)
            with self.assertRaises(ValueError): audio_stats(path)


if __name__ == "__main__": unittest.main()

"""Failure-path checks: inventory must never imply a successful training run."""
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "preflight.py"
spec = importlib.util.spec_from_file_location("preflight", SCRIPT)
preflight = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preflight)


class PreflightTests(unittest.TestCase):
    def test_wsl_redirected_utf16(self):
        text = "Linux용 Windows 하위 시스템이 설치되어 있지 않습니다.\r\n"
        self.assertEqual(preflight.decode_output(text.encode("utf-16-le")), text)
        self.assertEqual(preflight.decode_output(text.encode("utf-16")), text)

    def test_missing_command_and_timeout_are_failures(self):
        for error in (FileNotFoundError(), subprocess.TimeoutExpired("nvidia-smi", 15)):
            with self.subTest(error=type(error).__name__), patch.object(
                    preflight.subprocess, "run", side_effect=error):
                result = preflight.command_result(["nvidia-smi"])
                self.assertIsNone(result["returncode"])
                self.assertEqual(result["error_type"], type(error).__name__)

    def test_runtime_crash_or_timeout_never_passes(self):
        with patch.object(preflight.subprocess, "run", side_effect=subprocess.TimeoutExpired("python", 60)):
            self.assertFalse(preflight.probe_runtime()["cuda_pytorch_verified"])
        run = subprocess.CompletedProcess([], 1, b'CHLOE_PROBE_JSON={"cuda_pytorch_verified": true}', b'')
        with patch.object(preflight.subprocess, "run", return_value=run):
            self.assertFalse(preflight.probe_runtime()["cuda_pytorch_verified"])

    def test_wsl1_and_missing_runtime_fail_gate(self):
        report = {"wsl2": False, "in_virtualenv": True, "runtime_probe": {},
                  "cuda_pytorch_verified": False}
        failures = preflight.environment_failures(report, require_wsl2=True, require_runtime=True)
        self.assertEqual(len(failures), 4)

    def test_default_inventory_does_not_import_training_libraries(self):
        with patch.object(preflight, "probe_runtime", side_effect=AssertionError("unexpected import")):
            report = preflight.inventory()
        self.assertFalse(report["training_executed"])
        self.assertFalse(report["training_compatibility_verified"])
        self.assertEqual(report["runtime_probe"], {"status": "not_run"})

    def test_cli_preserves_evidence_and_strict_exit_code(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "report.json"
            run = subprocess.run([sys.executable, str(SCRIPT), "--output", str(output)], capture_output=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            original = output.read_bytes()
            rerun = subprocess.run([sys.executable, str(SCRIPT), "--output", str(output)], capture_output=True)
            self.assertEqual(rerun.returncode, 2)
            self.assertEqual(output.read_bytes(), original)
            strict = subprocess.run([sys.executable, str(SCRIPT), "--require-wsl2", "--output",
                                     str(Path(folder) / "strict.json")], capture_output=True)
            report = json.loads((Path(folder) / "strict.json").read_text(encoding="utf-8"))
            self.assertEqual(strict.returncode, 0 if report["wsl2"] else 1)


if __name__ == "__main__":
    unittest.main()

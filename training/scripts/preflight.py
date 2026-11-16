"""Local inventory; optional import/CUDA probe. No installs or model downloads."""
import argparse
import importlib.metadata
import json
import locale
import platform
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


PACKAGES = ("torch", "transformers", "peft", "trl", "bitsandbytes", "accelerate")

# Run imports in a bounded child process. Do not print exception messages, paths,
# environment variables, or conversations into evidence intended for a PR.
RUNTIME_PROBE = r'''
import importlib, json
result = {"imports": {}, "cuda_pytorch_verified": False,
          "qwen35_text_class_imported": False}
for name in ("torch", "transformers", "peft", "trl", "bitsandbytes", "accelerate"):
    try:
        importlib.import_module(name)
        result["imports"][name] = {"ok": True}
    except Exception as error:
        result["imports"][name] = {"ok": False, "error_type": type(error).__name__}
if result["imports"]["transformers"]["ok"]:
    try:
        from transformers import Qwen3_5ForCausalLM, Qwen3_5TextConfig
        result["qwen35_text_class_imported"] = True
    except Exception as error:
        result["qwen35_import_error_type"] = type(error).__name__
if result["imports"]["torch"]["ok"]:
    try:
        import torch
        result["torch_cuda_build"] = torch.version.cuda
        result["cuda_available"] = torch.cuda.is_available()
        if result["cuda_available"]:
            result["cuda_device"] = torch.cuda.get_device_name(0)
            result["bf16_supported"] = torch.cuda.is_bf16_supported()
            x = torch.ones((16, 16), device="cuda:0", requires_grad=True)
            loss = (x @ x).square().mean()
            loss.backward()
            torch.cuda.synchronize()
            result["cuda_pytorch_verified"] = bool(
                torch.isfinite(loss).item() and torch.isfinite(x.grad).all().item())
    except Exception as error:
        result["cuda_error_type"] = type(error).__name__
print("CHLOE_PROBE_JSON=" + json.dumps(result))
'''


def decode_output(value):
    """wsl.exe can emit UTF-16LE even when redirected, unlike nvidia-smi."""
    if value.startswith((b"\xff\xfe", b"\xfe\xff")):
        return value.decode("utf-16", errors="replace")
    if b"\x00" in value[:128]:
        return value.decode("utf-16-le", errors="replace")
    return value.decode(locale.getpreferredencoding(False), errors="replace")


def command_result(command, timeout=15):
    try:
        run = subprocess.run(command, capture_output=True, timeout=timeout, check=False)
        return {"command": command, "returncode": run.returncode,
                "stdout": decode_output(run.stdout)[:4096],
                "stderr": decode_output(run.stderr)[:4096]}
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"command": command, "returncode": None,
                "error_type": type(error).__name__}


def probe_runtime():
    try:
        run = subprocess.run([sys.executable, "-c", RUNTIME_PROBE],
                             capture_output=True, timeout=60, check=False)
        # Library warnings are deliberately excluded; only our structured record
        # is used. A failed/timeout/crashed probe must never pass the gate.
        for line in reversed(decode_output(run.stdout).splitlines()):
            if line.startswith("CHLOE_PROBE_JSON=") and run.returncode == 0:
                return {"returncode": 0, **json.loads(line.split("=", 1)[1])}
        return {"returncode": run.returncode, "error_type": "ProbeFailed",
                "cuda_pytorch_verified": False}
    except (OSError, subprocess.TimeoutExpired, ValueError) as error:
        return {"returncode": None, "error_type": type(error).__name__,
                "cuda_pytorch_verified": False}


def inventory(probe=False):
    release = platform.release().lower()
    versions = {}
    for name in PACKAGES:
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = None
    result = {"observed_at": datetime.now(timezone.utc).isoformat(),
              "platform": platform.platform(), "python": platform.python_version(),
              "wsl": "microsoft" in release, "wsl2": "wsl2" in release,
              "in_virtualenv": sys.prefix != sys.base_prefix,
              "free_disk_bytes": shutil.disk_usage(Path.cwd()).free,
              "package_versions": versions,
              "training_executed": False, "model_forward_verified": False,
              "training_compatibility_verified": False,
              "cuda_pytorch_verified": False}
    command = ["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader"]
    result["gpu"] = command_result(command)
    if platform.system() == "Windows":
        result["wsl_status"] = command_result(["wsl", "--status"])
        result["wsl_distributions"] = command_result(["wsl", "--list", "--verbose"])
    result["runtime_probe"] = probe_runtime() if probe else {"status": "not_run"}
    result["cuda_pytorch_verified"] = result["runtime_probe"].get("cuda_pytorch_verified", False)
    return result


def environment_failures(report, require_wsl2=False, require_runtime=False):
    failures = []
    if require_wsl2 and not report["wsl2"]:
        failures.append("WSL2 execution environment required")
    if require_runtime:
        runtime = report["runtime_probe"]
        if not report["in_virtualenv"]:
            failures.append("isolated virtual environment required")
        if not all(runtime.get("imports", {}).get(name, {}).get("ok") for name in PACKAGES):
            failures.append("training package imports not verified")
        if not runtime.get("qwen35_text_class_imported"):
            failures.append("Qwen3.5 text classes not imported")
        if not report["cuda_pytorch_verified"]:
            failures.append("CUDA tensor forward/backward not verified")
    return failures


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--probe-runtime", action="store_true",
                        help="Import installed packages and run a tiny CUDA tensor forward/backward; no model")
    parser.add_argument("--require-wsl2", action="store_true", help="Return 1 outside WSL2")
    parser.add_argument("--require-runtime", action="store_true",
                        help="Also probe runtime; return 1 if imports/CUDA/venv checks fail")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Output exists; choose a new path to preserve previous evidence")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    report = inventory(probe=args.probe_runtime or args.require_runtime)
    report["environment_failures"] = environment_failures(
        report, require_wsl2=args.require_wsl2, require_runtime=args.require_runtime)
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(f"Inventory saved: {args.output}; model/training compatibility NOT verified")
    for failure in report["environment_failures"]:
        print(f"BLOCKED: {failure}")
    return 1 if report["environment_failures"] else 0


if __name__ == "__main__":
    sys.exit(main())

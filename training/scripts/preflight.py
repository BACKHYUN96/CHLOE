"""Read-only local inventory. No installs, model downloads, or training."""
import argparse
import json
import platform
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def inventory():
    result = {"observed_at": datetime.now(timezone.utc).isoformat(),
              "platform": platform.platform(), "python": platform.python_version(),
              "wsl": "microsoft" in platform.release().lower(),
              "free_disk_bytes": shutil.disk_usage(Path.cwd()).free,
              "training_executed": False, "cuda_pytorch_verified": False}
    command = ["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader"]
    try:
        run = subprocess.run(command, capture_output=True, text=True, timeout=15, check=False)
        result["gpu"] = {"command": command, "returncode": run.returncode,
                         "stdout": run.stdout[:4096], "stderr": run.stderr[:4096]}
    except (OSError, subprocess.TimeoutExpired) as error:
        result["gpu"] = {"available": False, "error_type": type(error).__name__}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Output exists; choose a new path to preserve previous evidence")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    report = inventory()
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(f"Inventory saved: {args.output}; training/CUDA compatibility NOT verified")


if __name__ == "__main__":
    main()

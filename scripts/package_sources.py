#!/usr/bin/env python3
"""Export tracked application and pinned submodule sources, without models, keys or build output."""
from pathlib import Path
import subprocess
import zipfile

root = Path(__file__).resolve().parents[1]
target = root / "artifacts/CHLOE-0.1.0-alpha1-sources.zip"
target.parent.mkdir(exist_ok=True)
files = subprocess.check_output(["git", "ls-files", "--recurse-submodules", "-z"], cwd=root).decode().split("\0")
with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
    for name in files:
        if name and (root / name).is_file():
            archive.write(root / name, "CHLOE/" + name)
print(target)

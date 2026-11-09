#!/usr/bin/env python3
"""Export tracked application and pinned submodule sources, without models, keys, audio recordings or build output."""
from pathlib import Path
import subprocess
import zipfile
import re

root = Path(__file__).resolve().parents[1]
version = re.search(r'versionName = "([^"]+)"', (root / "app/build.gradle.kts").read_text())[1]
target = root / f"artifacts/CHLOE-{version}-sources.zip"
target.parent.mkdir(exist_ok=True)
files = subprocess.check_output(["git", "ls-files", "--recurse-submodules", "-z"], cwd=root).decode().split("\0")
with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
    for name in files:
        # Voice samples (including upstream README audio) are not source uploads.
        excluded = {".wav", ".mp3", ".m4a", ".ogg", ".flac", ".aac", ".mp4", ".gguf", ".safetensors", ".jks", ".keystore"}
        if name and (root / name).is_file() and (root / name).suffix.lower() not in excluded:
            archive.write(root / name, "CHLOE/" + name)
print(target)

"""Inspect pinned official Qwen3.5-2B metadata over HTTPS; never download weights."""
import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen


MODEL = "Qwen/Qwen3.5-2B"
REVISION = "15852e8c16360a2fea060d615a32b45270f8a8fc"
MAX_BYTES = 4 * 1024 * 1024


def download_metadata(url):
    request = Request(url, headers={"User-Agent": "CHLOE-metadata-preflight/1"})
    with urlopen(request, timeout=30) as response:
        data = response.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError("Metadata size limit exceeded")
    return data


def inspect():
    info_url = f"https://huggingface.co/api/models/{MODEL}/revision/{REVISION}?blobs=true"
    info = json.loads(download_metadata(info_url))
    if info["sha"] != REVISION:
        raise ValueError("Revision mismatch")
    files = {}
    contents = {}
    for name in ("config.json", "chat_template.jinja", "tokenizer_config.json", "LICENSE", "README.md"):
        url = f"https://huggingface.co/{MODEL}/resolve/{REVISION}/{name}"
        data = download_metadata(url)
        contents[name] = data.decode("utf-8")
        files[name] = {"url": url, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    config = json.loads(contents["config.json"])
    template = contents["chat_template.jinja"]
    tokenizer = json.loads(contents["tokenizer_config.json"])
    checkpoints = []
    for item in info.get("siblings", []):
        if item["rfilename"].endswith(".safetensors"):
            lfs = item.get("lfs", {})
            checkpoints.append({"file": item["rfilename"], "bytes": item.get("size"),
                                "publisher_sha256": lfs.get("sha256"),
                                "downloaded": False, "local_hash_verified": False})
    return {"observed_at": datetime.now(timezone.utc).isoformat(),
            "model": MODEL, "revision": REVISION, "metadata_url": info_url,
            "license": info.get("cardData", {}).get("license"),
            "files": files, "checkpoints": checkpoints,
            "model_type": config.get("model_type"),
            "text_model_type": config.get("text_config", {}).get("model_type"),
            "layer_types": config.get("text_config", {}).get("layer_types"),
            "template_has_generation_markers": bool(re.search(r"\{%-?\s*generation\s*-?%\}", template)),
            "template_has_enable_thinking": "enable_thinking" in template,
            "tokenizer_template_matches_file": tokenizer.get("chat_template") == template,
            "remote_code_executed": False, "weights_downloaded": False,
            "model_forward_verified": False, "training_compatibility_verified": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Output exists; choose a new path to preserve previous evidence")
    try:
        report = inspect()
    except Exception as error:
        # Do not leak request headers, tokens, or machine paths in exception text.
        print(f"Metadata inspection failed: {type(error).__name__}", file=sys.stderr)
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print("Pinned metadata inspected; weights/model forward/training NOT verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())

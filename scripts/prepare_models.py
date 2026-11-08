#!/usr/bin/env python3
"""Developer-PC only. Download official weights and convert without quantizing F16 matrices."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import shutil

VARIANTS = {
    "0.6b": ("Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice", "85e237c12c027371202489a0ec509ded67b5e4b5", "0b6", 1024),
    "1.7b": ("Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice", "0c0e3051f131929182e2c023b9537f8b1c68adfe", "1b7", 2048),
}

TOKENIZER = "Qwen/Qwen3-TTS-Tokenizer-12Hz"
TOKENIZER_REV = "7dd38ad4e9bad454aae9cd937d0cd577604fe229"
RUNTIME = "4562731dc612cb87b4cd1eedac275a17d1078773"
TOKENIZER_FILE = "qwen-tokenizer-12hz-f16.gguf"


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(8 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--variant", choices=VARIANTS, default="0.6b")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--cache", type=Path, default=Path("models/hf"))
    parser.add_argument("--local-talker", type=Path, help="Use an already downloaded official checkpoint")
    parser.add_argument("--local-tokenizer", type=Path)
    args = parser.parse_args()
    model, model_rev, model_size, hidden_size = VARIANTS[args.variant]
    talker_file = f"qwen-talker-{args.variant}-customvoice-f16-stable.gguf"
    if args.output is None:
        args.output = Path("models/chloe-sohee-f16-stable") if args.variant == "0.6b" else Path("models/chloe-sohee-1.7b-f16-stable")
    repo = Path(__file__).resolve().parents[1]
    runtime = repo / "external/qwen3-tts.cpp"
    if (runtime / ".git").exists():
        revision = subprocess.check_output(["git", "-C", str(runtime), "rev-parse", "HEAD"], text=True).strip()
        if revision != RUNTIME:
            raise SystemExit("Initialize the pinned submodules first: git submodule update --init --recursive")
    # A full-source ZIP has no Git metadata. Validate the exact converter files in both forms.
    lock = json.loads((repo / "third_party/runtime-lock.json").read_text(encoding="utf-8"))
    if lock["commit"] != RUNTIME or any(sha256(runtime / name) != value for name, value in lock["converter_sha256"].items()):
        raise SystemExit("Pinned converter integrity check failed; restore the supplied runtime sources")
    if args.local_talker and args.local_tokenizer:
        talker, tokenizer = args.local_talker.resolve(), args.local_tokenizer.resolve()
    elif args.local_talker or args.local_tokenizer:
        raise SystemExit("Supply both local checkpoint directories or neither")
    else:
        from huggingface_hub import snapshot_download
        talker = Path(snapshot_download(model, revision=model_rev, local_dir=args.cache / ("customvoice-" + args.variant),
            allow_patterns=["config.json", "generation_config.json", "vocab.json", "merges.txt", "tokenizer_config.json", "model.safetensors"]))
        tokenizer = Path(snapshot_download(TOKENIZER, revision=TOKENIZER_REV, local_dir=args.cache / "tokenizer",
            allow_patterns=["config.json", "model.safetensors"]))
    cfg = json.loads((talker / "config.json").read_text(encoding="utf-8"))
    if not (cfg.get("tts_model_type") == "custom_voice" and cfg.get("tts_model_size") == model_size
            and cfg["talker_config"]["spk_id"].get("sohee") == 2864):
        raise SystemExit(f"Expected official {args.variant} CustomVoice with Sohee; refusing Base/other speakers")
    args.output.mkdir(parents=True, exist_ok=True)
    # An interrupted conversion must never leave a valid-looking package manifest.
    (args.output / "model-pack.json").unlink(missing_ok=True)
    for script, source, filename, extra in [
        (repo / "scripts/convert_talker_stable.py", talker, talker_file, []),
        (runtime / "scripts/convert_tokenizer_to_gguf.py", tokenizer, TOKENIZER_FILE, ["--type", "f16"]),
    ]:
        subprocess.run([sys.executable, str(script), "--input", str(source),
            "--output", str(args.output / filename), *extra], check=True)
    # Verify emitted metadata instead of assuming that conversion preserved the speaker map.
    from gguf import GGUFReader
    gguf = GGUFReader(str(args.output / talker_file))
    def contents(key):
        return gguf.fields[key].contents()
    assert contents("qwen3-tts.model_type") == "custom_voice"
    assert contents("qwen3-tts.talker.embedding_length") == hidden_size
    if args.variant == "1.7b": assert contents("qwen3-tts.supports_instruction")
    names = contents("qwen3-tts.codec.speaker_names")
    ids = contents("qwen3-tts.codec.speaker_ids")
    assert ids[names.index("sohee")] == 2864
    tensors = {t.name: t for t in gguf.tensors}
    from gguf import GGMLQuantizationType
    assert all(tensors[f"code_pred.blk.{i}.ffn_down.weight"].tensor_type == GGMLQuantizationType.F32 for i in range(5))
    files = [{"name": name, "size": (args.output / name).stat().st_size,
              "sha256": sha256(args.output / name)} for name in [talker_file, TOKENIZER_FILE]]
    manifest = dict(schema=1, model_id=model, tokenizer_id=TOKENIZER, model_revision=model_rev,
        tokenizer_revision=TOKENIZER_REV, runtime_commit=RUNTIME, precision="f16-f32-cp-down", files=files,
        local_checkpoint_override=bool(args.local_talker), license="Apache-2.0")
    (args.output / "model-pack.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    shutil.copyfile(repo / "third_party/licenses/Qwen3-TTS-Apache-2.0.txt", args.output / "LICENSE-Qwen-Apache-2.0.txt")
    print(f"Prepared {args.output.resolve()}; copy the entire folder to your phone.")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Generate unedited Sohee prompt comparisons. Breathing and speech quality require human ratings.

An optional evaluation JSON supplies a private reference text and its existing instruction.
Keep the output under artifacts/. Only public_summary() is safe to copy into the repository.
"""
import argparse
import array
import hashlib
import json
import math
import platform
from pathlib import Path
import re
import subprocess
import time
import wave

RUNTIME = "4562731dc612cb87b4cd1eedac275a17d1078773"
TALKER = "qwen-talker-1.7b-customvoice-f16-stable.gguf"
TOKENIZER = "qwen-tokenizer-12hz-f16.gguf"
MAX_TOKENS = 1024
SAMPLING = dict(temperature=0.9, top_k=50, top_p=1.0, repetition_penalty=1.05,
    max_tokens=MAX_TOKENS)


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        while b := f.read(8 * 1024 * 1024): h.update(b)
    return h.hexdigest()


def audio_stats(path):
    with wave.open(str(path)) as f:
        if (f.getframerate(), f.getnchannels(), f.getsampwidth(), f.getcomptype()) != (24000, 1, 2, "NONE"):
            raise ValueError("Expected 24kHz mono PCM16 WAV")
        samples = array.array("h", f.readframes(f.getnframes()))
    if not samples: raise ValueError("Empty audio")
    if __import__("sys").byteorder != "little": samples.byteswap()
    return dict(sample_rate=24000, samples=len(samples), audio_seconds=len(samples) / 24000,
        pcm_peak=max(abs(x) for x in samples), pcm_rms=math.sqrt(sum(x * x for x in samples) / len(samples)),
        pcm_full_scale_samples=sum(abs(x) >= 32767 for x in samples))


def public_summary(report):
    """Whitelist metadata: never publish reference text, user instructions, paths or native logs."""
    fields = ("clip_id", "case_id", "style_id", "status", "exit_code", "process_wall_ms",
        "native_total_ms", "code_generation_ms", "decode_ms", "rtf", "audio_seconds", "sample_rate",
        "samples", "pcm_peak", "pcm_rms", "pcm_full_scale_samples", "token_limit_reached",
        "wav_sha256", "rss_peak_display")
    return dict(study="breath-study-01", device_test=False, perceptual_evaluation="pending",
        source_runtime=RUNTIME, model_pack=report["model_pack"], seed=42, threads=4,
        sampling=report["sampling"], native_binary_sha256=report["native_binary_sha256"],
        untouched_pcm=True, cases=[{"id": c["id"], "description": c["description"]} for c in report["cases"]],
        clips=[{key: clip[key] for key in fields if key in clip} for clip in report["clips"]])


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--binary", type=Path, required=True)
    p.add_argument("--models", type=Path, required=True)
    p.add_argument("--evaluation-json", type=Path)
    p.add_argument("--output", type=Path, default=Path("artifacts/breath-study-01"))
    a = p.parse_args()
    if a.output.exists() and any(a.output.iterdir()): p.error("Output folder is not empty; choose a new folder")
    reference = "안녕하세요? 저는 클로이예요. 오늘 하루는 어떻게 보내셨어요? 괜찮다면 저랑 잠깐 이야기해요."
    existing_instruction = "차분하고 다정하게, "
    if a.evaluation_json:
        evaluation = json.loads(a.evaluation_json.read_text(encoding="utf-8"))
        if evaluation.get("model_variant") != "1.7b": p.error("Expected a 1.7B evaluation")
        reference = evaluation["input"]
        existing_instruction = evaluation.get("instruction", "")
    cases = [
        dict(id="01", description="사용자 제공 다문장 기준" if a.evaluation_json else "다문장 기준", text=reference),
        dict(id="02", description="짧은 대화 턴용 문장 (속도 지시 없음)", text="응, 좋아. 지금 바로 같이 확인해 보자."),
        dict(id="03", description="공감 반응용 문장", text="아, 많이 속상했겠어요. 괜찮다면 천천히 이야기해 주세요."),
    ]
    styles = [
        dict(id="A", description="지시 없음", instruction=""),
        dict(id="B", description="기존 말투 지시", instruction=existing_instruction),
        dict(id="C", description="기존 지시에 한국어 호흡 절제 요청 추가", instruction=existing_instruction +
            "보통은 바로 말을 시작하고, 매 문장 앞에 과장된 들숨을 반복하지 마세요. 호흡은 감정과 문맥에 필요할 때만 자연스럽게 사용해 주세요."),
        dict(id="D", description="영어 차분한 말투 대조군", instruction="Speak calmly and kindly."),
        dict(id="E", description="영어 대조군에 호흡 절제 요청 추가", instruction="Speak calmly and kindly. Usually begin with words rather than a preparatory inhale. Keep breathing subtle; use it only when the emotion or phrasing calls for it."),
    ]
    for value in [c["text"] for c in cases] + [s["instruction"] for s in styles]:
        if len(value) > 240: p.error("Text/instruction exceeds the Android lab's 240-character limit")
    if any(not c["text"].strip() for c in cases): p.error("Empty text")
    manifest = json.loads((a.models / "model-pack.json").read_text(encoding="utf-8"))
    if manifest["model_id"] != "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice" or manifest["runtime_commit"] != RUNTIME:
        p.error("Expected pinned 1.7B CustomVoice pack")
    if {f["name"] for f in manifest["files"]} != {TALKER, TOKENIZER}: p.error("Unexpected model files")
    for f in manifest["files"]:
        path = a.models / f["name"]
        if path.stat().st_size != f["size"] or digest(path) != f["sha256"]: p.error("Model integrity mismatch")
    a.output.mkdir(parents=True, exist_ok=True)
    report = dict(study="breath-study-01", model_pack=manifest, host=platform.platform(), seed=42, threads=4,
        sampling=SAMPLING.copy(), device_test=False, cases=cases, styles=styles, clips=[], native_binary_sha256=digest(a.binary))
    failures = 0
    for case in cases:
        for style in styles:
            clip_id = case["id"] + "_" + style["id"]
            wav = a.output / (clip_id + ".wav")
            cmd = [str(a.binary.resolve()), "-m", str(a.models.resolve()), "--model-name", TALKER,
                "--speaker", "sohee", "-l", "ko", "--seed", "42", "--max-tokens", str(MAX_TOKENS),
                "--temperature", str(SAMPLING["temperature"]), "--top-k", str(SAMPLING["top_k"]),
                "--top-p", str(SAMPLING["top_p"]), "--repetition-penalty", str(SAMPLING["repetition_penalty"]),
                "-j", "4", "-t", case["text"], "-o", str(wav.resolve())]
            if style["instruction"]: cmd += ["--instruction", style["instruction"]]
            item = dict(clip_id=clip_id, case_id=case["id"], style_id=style["id"], status="runtime_error")
            start = time.perf_counter()
            try:
                r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=240)
                log = r.stdout + r.stderr
                (a.output / (clip_id + ".log")).write_text(log, encoding="utf-8")
                item.update(exit_code=r.returncode, process_wall_ms=round((time.perf_counter() - start) * 1000, 2))
                if r.returncode == 0:
                    item.update(audio_stats(wav))
                    for key, label in [("native_total_ms", "Total"), ("code_generation_ms", "Code generation"), ("decode_ms", "Vocoder decode")]:
                        m = re.search(rf"{label}:\s+(\d+) ms", log)
                        if m: item[key] = int(m[1])
                    item["token_limit_reached"] = item["samples"] >= MAX_TOKENS * 1920
                    item["status"] = "failed_token_limit" if item["token_limit_reached"] else (
                        "failed_silent" if item["pcm_rms"] == 0 else "generated_unrated")
                    if "native_total_ms" in item: item["rtf"] = item["native_total_ms"] / (item["audio_seconds"] * 1000)
                    item["wav_sha256"] = digest(wav)
                    m = re.search(r"RSS peak:\s+(.+)", log)
                    if m: item["rss_peak_display"] = m[1].strip()
            except (subprocess.TimeoutExpired, ValueError, OSError, wave.Error) as e:
                item["error"] = type(e).__name__
            if item["status"] != "generated_unrated": failures += 1
            report["clips"].append(item)
            (a.output / "private-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            (a.output / "public-summary.json").write_text(json.dumps(public_summary(report), ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps(item, ensure_ascii=False), flush=True)
    raise SystemExit(1 if failures else 0)


if __name__ == "__main__": main()

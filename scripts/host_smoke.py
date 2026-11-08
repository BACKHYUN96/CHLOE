#!/usr/bin/env python3
"""Optional host CPU check. This does NOT measure Android performance or acoustic quality."""
import argparse
import json
from pathlib import Path
import platform
import re
import subprocess
import time
import wave

SAMPLES = [
    "안녕하세요? 저는 클로이예요.",
    "오늘 하루는 어떻게 보내셨어요?",
    "아, 진짜요? 그건 좀 신기한데요?",
    "아니, 그게 아니라 제 말은요.",
    "음... 잠깐만요. 제가 한번 생각해 볼게요.",
    "와, 그거 정말 대단하네요!",
    "오늘 많이 피곤하셨나 봐요.",
    "그러게요. 저도 그렇게 생각해요.",
    "아, 그건 조금 다르게 볼 수도 있겠네요.",
    "네, 알겠어요. 언제든 편하게 이야기해 주세요.",
]

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--binary", required=True, type=Path)
    p.add_argument("--models", required=True, type=Path)
    p.add_argument("--output", default=Path("artifacts/host-smoke"), type=Path)
    p.add_argument("--all", action="store_true")
    p.add_argument("--variant", choices=["0.6b", "1.7b"], default="0.6b")
    p.add_argument("--instruction", default="")
    a = p.parse_args()
    a.output.mkdir(parents=True, exist_ok=True)
    results = []
    for i, text in enumerate(SAMPLES if a.all else SAMPLES[:1], 1):
        output = a.output / f"sample-{i:02}.wav"
        command = [str(a.binary.resolve()), "-m", str(a.models.resolve()),
            "--model-name", f"qwen-talker-{a.variant}-customvoice-f16-stable.gguf", "--speaker", "sohee",
            "-l", "ko", "--seed", "42", "--max-tokens", "1024", "-j", "4", "-t", text, "-o", str(output.resolve())]
        if a.instruction: command += ["--instruction", a.instruction]
        start = time.perf_counter()
        r = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
        total = (time.perf_counter() - start) * 1000
        (a.output / f"sample-{i:02}.log").write_text(r.stdout + r.stderr, encoding="utf-8")
        result = dict(sample=i, text=text, exit_code=r.returncode, process_wall_ms=round(total, 2),
            host=platform.platform(), hardware=platform.machine(), threads=4, speaker="sohee", language="ko",
            first_output_ms=None, pronunciation=None, intonation=None, device_test=False,
            model_variant=a.variant, instruction=a.instruction)
        if r.returncode == 0:
            with wave.open(str(output)) as wav:
                result.update(sample_rate=wav.getframerate(), samples=wav.getnframes(), channels=wav.getnchannels(),
                    sample_width=wav.getsampwidth(), audio_seconds=wav.getnframes() / wav.getframerate())
            result["token_limit_reached"] = result["samples"] >= 1024 * 1920
            result["status"] = "failed_token_limit" if result["token_limit_reached"] else "generated_unrated"
            for name, label in [("generation_ms", "Code generation"), ("decode_ms", "Vocoder decode"), ("native_total_ms", "Total")]:
                match = re.search(rf"{label}:\s+(\d+) ms", r.stdout + r.stderr)
                if match: result[name] = int(match[1])
            if "native_total_ms" in result:
                result["diagnostic_rtf"] = result["native_total_ms"] / 1000 / result["audio_seconds"]
        else: result["status"] = "runtime_error"
        results.append(result)
        (a.output / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False), flush=True)
        if r.returncode != 0: raise SystemExit(r.returncode)
        if result.get("token_limit_reached"): raise SystemExit("Failure: audio token cap reached; this is not a valid speech sample")

if __name__ == "__main__": main()

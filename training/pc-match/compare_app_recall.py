"""Run frozen relevance cases and named-relation controls with two production bridges."""
import argparse
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import subprocess

from compare_relevance import generate


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def save(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("output", "baseline-classpath", "policy-classes", "jdk", "model", "schema"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    previous = root / "docs/validation/relevance-filter-20261115"
    controls = root / "training/configs/app-recall-probes.json"
    old = [r for r in read(previous / "responses.json") if r["condition"] == "after"]
    assert len(old) == 106
    digest = hashlib.sha256()
    with args.model.open("rb") as model:
        for block in iter(lambda: model.read(8 * 1024 * 1024), b""):
            digest.update(block)
    assert digest.hexdigest() == read(previous / "plan.json")["model_sha256"]
    old_cp = args.baseline_classpath.read_text(encoding="utf-8").strip().split(os.pathsep)
    # RouteBridge bytecode, Android JSON shim and Kotlin runtime are shared.
    bridge_dir, _, json_jar, kotlin_jar = old_cp
    assert (args.policy_classes / "ai/chloe/voicelab/conversation/ConversationManager.class").is_file()
    classpaths = dict(before=old_cp, after=[bridge_dir, str(args.policy_classes.resolve()), json_jar, kotlin_jar])
    args.output.mkdir(parents=True, exist_ok=False)
    with ExitStack() as cleanup:
        bridges = {}
        for side, parts in classpaths.items():
            cp = os.pathsep.join(parts)
            p = subprocess.Popen([str(args.jdk / "bin/java.exe"), "-Dfile.encoding=UTF-8",
                                  "-cp", cp, "ai.chloe.pc.RouteBridge"], stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE, text=True, encoding="utf-8")
            bridges[side] = p
            cleanup.callback(p.wait)
            cleanup.callback(p.stdin.close)
            (args.output / (side + "-classpath.local.txt")).write_text(cp, encoding="utf-8")

        def call(side, request):
            process = bridges[side]
            process.stdin.write(json.dumps(request, ensure_ascii=False) + "\n")
            process.stdin.flush()
            result = json.loads(process.stdout.readline())
            if "error" in result:
                raise RuntimeError(result["error"])
            return result

        scenarios = []
        for case in read(controls):
            register = case["register"]
            system = call("before", dict(op="system", register=register))["system"]
            assert system == call("after", dict(op="system", register=register))["system"]
            messages = [dict(role="system", content=system)]
            for i, line in enumerate(case["history"]):
                messages.append(dict(role=("user", "assistant")[i % 2], content=line))
            messages.append(dict(role="user", content=case["input"]))
            scenarios.append(dict(source_id=case["id"], cohort="control", messages=messages,
                                  input=case["input"], register=register, expectation=case["expectation"]))
        for row in old:
            fields = ("source_id", "cohort", "input", "register", "session", "turn", "topic", "expectation")
            scenario = {k: row[k] for k in fields if k in row}
            replay = dict(scenario, route="current", messages=row["messages"])
            replay.pop("session", None)
            for side in bridges:
                prepared = call(side, dict(replay, op="prepare"))
                assert prepared["actual_messages"] == row["actual_messages"], (side, row["id"])
            baseline = call("before", dict(replay, op="consume", raw=row["raw"]))
            assert baseline["delivered_spoken"] == row["delivered_speech"]
            if "session" not in scenario:
                scenario["messages"] = row["messages"]
            scenarios.append(scenario)
        tasks = []
        for index, scenario in enumerate(scenarios):
            for side in (("before", "after") if index % 2 == 0 else ("after", "before")):
                tasks.append(dict(scenario, id=side + "-" + scenario["source_id"], route="current", condition=side))
        assert len(tasks) == len({t["id"] for t in tasks})
        save(args.output / "tasks.local.json", tasks)
        policy = root / "app/src/main/java/ai/chloe/voicelab/conversation/GroundedConversationPolicy.java"
        save(args.output / "plan.local.json", dict(
            baseline="7068619f497e0a2ef4eb92fa3150e9b8226bf478", model_sha256=digest.hexdigest(),
            generation=read(previous / "plan.json")["generation"], native_requests=len(tasks), training_steps=0,
            policy_sha256=hashlib.sha256(policy.read_bytes().replace(b"\r\n", b"\n")).hexdigest(),
            baseline_input_and_consumer_parity=len(old), identical_input_on_common_history=len(old)))
        generate(args, tasks, call, bridges)


if __name__ == "__main__":
    main()

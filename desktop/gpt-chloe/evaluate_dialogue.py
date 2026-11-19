"""Run a frozen synthetic suite through an isolated production App and record usage."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time

def load_implementation(path):
    spec = importlib.util.spec_from_file_location("chloe_evaluated", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module

def digest(path):
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()

def run():
    parser = argparse.ArgumentParser()
    parser.add_argument("--implementation", type=Path, required=True)
    parser.add_argument("--suite", type=Path, required=True)
    parser.add_argument("--key-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-estimated-usd", type=float, default=1.0)
    args = parser.parse_args()
    suite = json.loads(args.suite.read_text(encoding="utf-8"))
    module = load_implementation(args.implementation)
    # Read only the credential, never copy private conversation databases into the suite.
    key = module.protect_secret((args.key_dir / "api-key.dpapi").read_bytes(), decrypt=True).decode()
    args.output.mkdir(parents=True, exist_ok=False)
    plan = dict(source_sha256=digest(args.implementation), suite_sha256=digest(args.suite),
                model=suite["model"], cases=sum(len(s["turns"]) for s in suite["sessions"]),
                max_estimated_usd=args.max_estimated_usd)
    (args.output / "plan.json").write_text(json.dumps(plan, indent=2)+"\n", encoding="utf-8")
    spent = 0
    with (args.output / "responses.jsonl").open("x", encoding="utf-8") as out:
        for scenario in suite["sessions"]:
            app = module.App(args.output / scenario["id"])
            app.key = key
            app.mutate("/api/settings", {"model": suite["model"], "register": scenario["register"]})
            for memory in scenario["memories"]:
                app.mutate("/api/memories", memory)
            for lesson in scenario["lessons"]:
                app.mutate("/api/lessons", lesson)
            session = app.mutate("/api/sessions", {})["id"]
            for turn in scenario["turns"]:
                history = app.messages(session)
                payload = app.payload(turn["message"], history)
                rates = module.MODELS[suite["model"]]
                reserve = ((len(module.encode(payload))+1024)*rates["input"] + payload["max_output_tokens"]*rates["output"])/1_000_000
                if spent + reserve > args.max_estimated_usd:
                    raise RuntimeError("Evaluation budget reached before the next request.")
                observed = []
                captured = []
                def events(api_key, request):
                    captured.append(request)
                    yield from module.openai_events(api_key, request)
                row = dict(id=turn["id"], session=scenario["id"], question=turn["message"],
                           expectation=turn["expect"], focus=turn["focus"], history_messages=len(history),
                           request=payload, source_sha256=plan["source_sha256"])
                try:
                    app.generate({"session":session,"message":turn["message"],"request_id":turn["id"]},
                                 lambda kind, data: observed.append((kind,data)), events=events)
                    assert len(captured)==1 and captured[0]==payload
                    assert observed[-1][0]=="done"
                    row.update(status="completed", answer=app.messages(session)[-1]["content"], metrics=observed[-1][1])
                    spent += row["metrics"]["cost"]
                except Exception as exc:
                    row.update(status="failed", error_type=type(exc).__name__, reserved_cost=reserve)
                    spent += reserve
                    out.write(json.dumps(row,ensure_ascii=False)+"\n")
                    out.flush()
                    raise
                out.write(json.dumps(row,ensure_ascii=False)+"\n")
                out.flush()
                print(json.dumps({"id":row["id"],"answer":row["answer"],"spent_usd":round(spent,6)},ensure_ascii=False),flush=True)
    (args.output / "complete.json").write_text(json.dumps(dict(requests=plan["cases"],estimated_usd=spent),indent=2)+"\n",encoding="utf8")

if __name__ == "__main__":
    run()

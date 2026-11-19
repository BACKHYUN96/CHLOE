"""Exercise actual Responses API through the production application pipeline using synthetic data."""
import argparse
import json
from pathlib import Path
import tempfile
import time
from server import App, MODELS

CASES = [
    ("casual", "오늘 퇴근하고 아무것도 하기 싫다."),
    ("identity", "너는 누구야? 실제로 서울에 살아?"),
    ("same_app", "새아라 만든 이가 누군지 떠올라?"),
    ("other_app", "그럼 아라 앱은 어느 개발자 손에서 나왔어?"),
    ("correction", "새아라 개발자가 누구였지?"),
    ("capability", "내일 오전 7시에 알람 맞춰 줘."),
]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--key-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Choose a fresh output file.")
    key = App(args.key_dir).key
    if not key:
        parser.error("Register an API key in CHLOE first.")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as folder, args.output.open("x", encoding="utf-8") as result:
        app = App(folder)
        app.key = key
        memory = app.mutate("/api/memories", {"subject": "사용자가 만든 앱 새아라", "detail": "사용자가 새아라를 직접 만들었다고 밝혔다. 아라에 관한 사실은 주어지지 않았다."})
        app.mutate("/api/lessons", {"instruction": "잡담은 편하게 반말로. 매번 되묻지 말고 과한 칭찬이나 긴 조언을 줄여 줘."})
        for model in MODELS:
            for ident, question in CASES:
                app.mutate("/api/settings", {"model": model, "register": "casual"})
                detail = "새아라는 민지가 만들었다고 사용자가 정정했다. 아라의 제작자는 알려지지 않았다." if ident == "correction" else "사용자가 새아라를 직접 만들었다고 밝혔다. 아라에 관한 사실은 주어지지 않았다."
                app.mutate("/api/memories", {"id":memory["id"], "subject":"앱 새아라", "detail":detail})
                session = app.mutate("/api/sessions", {})["id"]
                events = []
                row = {"model":model, "case":ident, "question":question}
                try:
                    app.generate({"session":session,"message":question,"request_id":model+"-"+ident},
                                 lambda event, data: events.append((event,data)))
                    row["answer"] = app.messages(session)[-1]["content"]
                    row["metrics"] = events[-1][1]
                    row["status"] = "completed"
                except Exception as exc:
                    row["status"] = "failed"
                    row["error_type"] = type(exc).__name__
                result.write(json.dumps(row,ensure_ascii=False)+"\n")
                result.flush()
                print(json.dumps(row,ensure_ascii=False),flush=True)

if __name__ == "__main__":
    main()

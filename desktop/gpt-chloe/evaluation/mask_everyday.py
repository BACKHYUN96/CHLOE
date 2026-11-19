"""Hide version, timing and token counts; keep each side's real dialogue intact."""
import json
import secrets
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
data = root / ".data"
prefix = sys.argv[1] if len(sys.argv)>1 else "blind-day"
dest = data / (prefix+"-review")
dest.mkdir(exist_ok=False)
def read(mode):
    return [json.loads(line) for line in (data / f"{prefix}-{mode}" / "responses.jsonl").read_text(encoding="utf8").splitlines()]

before, after = read("before"), read("after")
assert len(before) == len(after) and before
assignment = {}
packet = []
for left, right in zip(before, after):
    assert (left["id"], left["question"]) == (right["id"], right["question"])
    scene = left["session"]
    if scene not in assignment:
        assignment[scene] = secrets.choice(["before", "after"])
    a, b = (left, right) if assignment[scene] == "before" else (right, left)
    packet.append(dict(id=a["id"], question=a["question"], A=a["answer"], B=b["answer"]))
for filename, value in [("key.json",assignment), ("packet.json",packet)]:
    (dest/filename).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding="utf8")

"""Decode the saved blind ballot and attach API usage after judging."""
import json
import sys
from collections import Counter
from pathlib import Path

folder = Path(__file__).resolve().parent
data = folder.parent / ".data"
prefix = sys.argv[1] if len(sys.argv)>1 else "blind-day"
name = {"confirm-day":"everyday-confirm", "blind-day":"everyday-blind", "intent":"intent"}[prefix]
masked = data / (prefix+"-review")
def load(path):
    return json.loads(path.read_text(encoding="utf8"))

votes = load(folder/(name+"-ballot.json"))
packet = load(masked/"packet.json")
key = load(masked/"key.json")
assert [r["id"] for r in packet] == [v["id"] for v in votes]
score = Counter()
for row, vote in zip(packet, votes):
    scene = row["id"].rsplit("-",1)[0]
    a_mode = key[scene]
    winner = vote["pick"]
    assert winner in ("A","B","tie")
    row.update(vote, A_version=a_mode, preferred=(a_mode if winner=="A" else
               ("after" if a_mode=="before" else "before") if winner=="B" else "tie"))
    score[row["preferred"]] += 1
usage = {}
for mode in ("before","after"):
    rows = [json.loads(s) for s in (data/f"{prefix}-{mode}"/"responses.jsonl").read_text(encoding="utf8").splitlines()]
    usage[mode] = dict(requests=len(rows),input_tokens=sum(r["metrics"]["input_tokens"] for r in rows),
        output_tokens=sum(r["metrics"]["output_tokens"] for r in rows),
        cached_tokens=sum(r["api_usage"]["input_tokens_details"]["cached_tokens"] for r in rows),
        estimated_usd=sum(r["metrics"]["cost"] for r in rows),source_sha256=rows[0]["source_sha256"])
result = dict(score=score, usage=usage, turns=packet)
(folder/(name+"-results.json")).write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf8")
print(json.dumps(dict(score=score,usage=usage)))

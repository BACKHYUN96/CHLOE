"""Audit paired references using supplied direct judgments, not generated wording or policy actions."""
import argparse
from collections import Counter
import json
from pathlib import Path


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--suite", type=Path, action="append", required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    rows = read(args.report / "responses.json")
    by_case = {(r["condition"], r["source_id"]): r for r in rows}
    assert len(by_case) == len(rows)
    suites = [read(path) for path in args.suite]
    previous = read(root / suites[0]["baseline_report"] / "responses.json")
    prior = [r for r in previous if r["condition"] == "after"]
    for r in prior:
        fresh = by_case["before", r["source_id"]]
        for key in ("input", "register", "messages", "actual_messages", "input_tokens_sha256", "raw", "delivered_raw"):
            assert fresh[key] == r[key], (r["source_id"], key)
    result = {"previous_baseline_reproduced": len(prior), "panels": {}}
    seen_inputs = {r["input"] for r in prior}
    seen_ids = set()
    for path, suite in zip(args.suite, suites):
        cases = {r["id"]: r for r in suite["cases"]}
        inputs = {r["input"] for r in cases.values()}
        assert not (inputs & seen_inputs) and not (cases.keys() & seen_ids)
        seen_inputs |= inputs
        seen_ids.update(cases)
        for ident, case in cases.items():
            for side in ("before", "after"):
                row = by_case[side, ident]
                assert row["input"] == case["input"] and row["register"] == case["register"]
                if "history" in case:
                    assert [v["content"] for v in row["messages"][1:-1]] == case["history"]
                else:
                    assert row["session"] == case["session"] and row["turn"] == case["turn"]
        panel = dict(scenarios=len(cases), distinct_questions=len(inputs), matched_pairs=len(suite["pairs"]), scores={})
        for side in ("before", "after"):
            for stage in ("raw", "final"):
                verdicts = {"same": Counter(), "other": Counter()}
                strict = Counter()
                both_strict = both_references = 0
                for same, other in suite["pairs"].values():
                    a, b = by_case[side, same], by_case[side, other]
                    assert a["messages"][:-1] == b["messages"][:-1] and a["register"] == b["register"]
                    assert a["input"] != b["input"]
                    pair_pass = []
                    references = []
                    for key, row, expected in (("same", a, "user"), ("other", b, "unknown")):
                        judgment = row[stage + "_gpt"]
                        answer = judgment["maker_reading"]
                        verdicts[key][answer] += 1
                        right = answer == expected
                        references.append(right)
                        passed = right and row[stage + "_gpt_overall"] == "pass"
                        strict[key] += int(passed)
                        pair_pass.append(passed)
                    both_strict += int(all(pair_pass))
                    both_references += int(all(references))
                panel["scores"][side + "_" + stage] = dict(
                    same=dict(verdicts["same"]), other=dict(verdicts["other"]),
                    strict_same=strict["same"], strict_other=strict["other"],
                    both_references_correct=both_references, both_strict_pass=both_strict)
        result["panels"][path.name] = panel
    assert len(rows) == 2 * (len(prior) + len(seen_ids))
    with (args.report / "title-pairs.json").open("x", encoding="utf-8") as out:
        json.dump(result, out, ensure_ascii=False, indent=2)
        out.write("\n")


if __name__ == "__main__":
    main()

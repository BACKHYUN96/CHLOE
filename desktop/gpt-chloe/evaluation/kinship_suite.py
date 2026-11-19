"""Build paired long-context probes from the archived synthetic fixture."""
import json
import sys
from pathlib import Path

folder = Path(__file__).resolve().parent
base = json.loads((folder / "archive/same-questions.json").read_text(encoding="utf8"))["sessions"][0]
sessions = []
for ident, question, expect, extra in [
    ("repeat", "오늘 얘기에서 사람과 고양이, 앱 관계만 짧게 정리해 줘.", "서윤은 서진의 동생. 역방향 호칭 추가 금지. 고양이 주인과 제작자 정정 유지.", ""),
    ("edit", "내가 다음 새 대화를 열어도 지금 정정한 밤결 제작자를 자동으로 기억하는 거야?", "자동 이월 아님. 기억 화면 밤결 항목 수정 후 저장.", ""),
    ("introduce", "전시장에 붙일 소개글에 세하와 이솔 사이를 한 문장만 써 줘.", "이솔은 세하의 동생. 말하지 않은 반대 방향 호칭 금지.", "세하의 동생은 이솔이야. 둘이 같이 전시를 준비해."),
    ("explicit", "지안과 유담은 어떤 사이라고 적으면 돼?", "명시된 친누나 유지. 역방향 남동생 추정 금지.", "유담은 지안의 친누나야."),
    ("colleague", "탐방 기록에 로운이와 해주의 관계를 어떻게 쓰면 될까?", "사용자가 말한 동행 그대로. 친구나 연인 추정 금지.", "로운이와 해주는 탐방 동행이야."),
    ("new-edit", "기존 밤결 항목에 틀린 사람이 적혀 있으면 다음번에도 맞게 나오도록 어느 버튼을 눌러?", "기억 화면 기존 항목 수정 후 저장. 추가 금지.", ""),
]:
    history = list(base["seed_history"])
    if extra:
        history[:0] = [{"role":"user","content":extra},{"role":"assistant","content":"응."}]
    assert sum(len(m["content"]) for m in history) > 60000
    sessions.append(dict(base, id=ident, seed_history=history, turns=[
        dict(id=ident,message=question,expect=expect,focus="관계 표현 및 기억 수정")]))
Path(sys.argv[1]).write_text(json.dumps(dict(model="gpt-6.1-terra",sessions=sessions),ensure_ascii=False),encoding="utf8")

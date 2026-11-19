"""Run three independent generations per question and implementation."""
import json
import subprocess
import sys
from pathlib import Path

app = Path(__file__).resolve().parents[1]
out = Path(sys.argv[1]).resolve()
out.mkdir(parents=True, exist_ok=False)
base = json.loads((app/'evaluation/archive/same-questions.json').read_text(encoding='utf8'))['sessions'][0]
cases = [
    ('repeat', '오늘 얘기에서 사람과 고양이, 앱 관계만 짧게 정리해 줘.', ''),
    ('caption', '사진 설명에 하람이랑 우주가 서로 어떤 사이인지 적어 줄래?', '우주는 하람의 동생이야.'),
    ('cards', '인물 카드 두 장에 라온과 도담의 관계를 각각 한 줄로 넣어 줘.', '도담은 라온의 동생이야.'),
]
cases.extend([('new-photo','앨범에 넣을 한 줄 캡션으로 시온과 누리를 소개해 주세요.','시온의 동생은 누리예요.'), ('new-cards','프로그램북에서 모아와 해솔 이름 아래에 각각 상대와의 관계를 써 줘.','모아의 동생이 해솔이야.')])
rows = []
for mode, commit in [('before','77a2d08'),('after','working')]:
    source = out/(mode+'.py')
    source.write_bytes((app/'server.py').read_bytes() if mode=='after' else subprocess.check_output(['git','show',commit+':desktop/gpt-chloe/server.py'],cwd=app))
    sessions = []
    for trial in range(1,4):
        for ident, question, extra in cases:
            tag = f'{ident}-{trial}'
            history = ([dict(role='user',content=extra),dict(role='assistant',content='응.')] if extra else []) + base['seed_history']
            assert sum(len(m['content']) for m in history)>60000
            sessions.append(dict(base,id=tag,seed_history=history,turns=[dict(id=tag,message=question,expect='명시된 동생 관계 유지',focus='역방향 성별 호칭')]))
    suite = out/(mode+'-suite.json')
    suite.write_text(json.dumps(dict(model='gpt-6.1-terra',sessions=sessions),ensure_ascii=False),encoding='utf8')
    subprocess.run([sys.executable,'-X','utf8','evaluate_dialogue.py','--implementation',str(source),'--suite',str(suite),'--key-dir','.data','--output',str(out/mode),'--max-estimated-usd','0.6'],cwd=app,check=True)
    for line in (out/mode/'responses.jsonl').read_text(encoding='utf8').splitlines():
        r=json.loads(line)
        rows.append(dict(mode=mode,commit=commit,**{k:r[k] for k in ('id','question','answer','history_chars','metrics','api_usage','source_sha256')}))
    (out/'answers.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf8')


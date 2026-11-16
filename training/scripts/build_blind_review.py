"""Build an offline, freshly blinded human review from preserved inference artifacts.

No inference, training, network calls or model writes. Private mappings never enter
the reviewer bundle or public audit. All destinations must be new paths.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import secrets
import zipfile

from data_contract import ROOT, validate_reply


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write(path, value):
    with Path(path).open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def blank_scores(packet):
    return {'version': 1, 'packet_id': packet['packet_id'], 'ratings': {
        item['id']: {'preference': None, 'A': {k: None for k in ('naturalness', 'content', 'criterion')},
                     'B': {k: None for k in ('naturalness', 'content', 'criterion')}, 'comment': ''}
        for item in packet['items']}}


def make_packet(source, plan, questions, summary, rng=None):
    rng = rng or secrets.SystemRandom()
    old_labels = read(source/'blind-mapping.local.json')
    if set(old_labels) != {'base', 'adapter'} or set(old_labels.values()) != {'A', 'B'}:
        raise ValueError('Invalid source candidate mapping')
    result_index = {(r['candidate'], r['register'], r['id']): r for r in summary['results']}
    if len(result_index) != len(summary['results']):
        raise ValueError('Duplicate source result')
    items, key, hashes = [], {}, {}
    for group in plan['groups']:
        units = [(register, group['cases'] if group['block'] else [case])
                 for register in group['registers']
                 for case in ([None] if group['block'] else group['cases'])]
        # Balance within each register for individual cards, across registers for blocks.
        buckets = [units] if group['block'] else [
            [u for u in units if u[0] == register] for register in group['registers']]
        assigned = []
        for bucket in buckets:
            if len(bucket) % 2:
                raise ValueError('Even group size required for balanced positions')
            sides = ['base']*(len(bucket)//2) + ['adapter']*(len(bucket)//2)
            rng.shuffle(sides)
            assigned.extend((unit, side) for unit, side in zip(bucket, sides))
        rng.shuffle(assigned)
        for (register, cases), side_a in assigned:
            ident = f'R{len(items)+1:02d}'
            mapping = {'A': side_a, 'B': 'adapter' if side_a == 'base' else 'base'}
            turns = []
            for case in cases:
                turn = {'question': questions[case]}
                for label, candidate in mapping.items():
                    row = result_index[(candidate, register, case)]
                    path = source/f'{old_labels[candidate]}-{register}-{case}.local.json'
                    response = read(path)
                    if not (row['diagnostics']['contract_valid'] and response['diagnostics']['contract_valid']
                            and response['eos_reached'] and response['contract_mode'] == 'constrained'):
                        raise ValueError('Incomplete or invalid source response')
                    parsed = validate_reply(response['raw'])
                    if parsed != response['reply']:
                        raise ValueError('Source raw/reply mismatch or failed consumer validation')
                    text = parsed['spoken_text']
                    if not isinstance(text, str) or not text.strip():
                        raise ValueError('Empty spoken_text')
                    turn[label] = text  # Deliberately exact; never strip, rewrite or sanitize content.
                    hashes[path.name] = digest(path)
                turns.append(turn)
            items.append({'id': ident, 'category': group['category'],
                          'register': '반말' if register == 'casual' else '존댓말', 'turns': turns})
            key[ident] = {'mapping': mapping, 'register': register, 'source_case_ids': cases}
    return {'version': 1, 'packet_id': secrets.token_hex(16), 'items': items}, key, hashes


INSTRUCTIONS = '''CHLOE 블라인드 대화 평가 — 사용 방법

1. review.html을 Edge/Chrome 등 브라우저로 여세요. 인터넷 연결은 필요 없습니다.
2. 카드의 지정 말투, 공통 질문, A/B 응답을 읽고 선호를 선택하세요.
   A/B 대응은 카드마다 달라질 수 있으며 한 문맥 묶음 안에서는 같습니다.
3. 빠른 평가는 선호만 선택해도 됩니다. 상세 점수와 메모는 선택 사항입니다.
   1=매우 나쁨, 2=미흡, 3=보통, 4=좋음, 5=매우 좋음. 미입력은 빈 값입니다.
4. 브라우저 임시 저장에만 의존하지 말고 '평가 JSON 저장'으로 파일을 보관하세요.
   중간 저장도 가능하며 '평가 JSON 불러오기'로 이어 할 수 있습니다.
5. 완료하거나 중간 의견을 전달하려면 저장한 JSON 파일을 이 채팅에 첨부하세요.
   파일은 자동 업로드되지 않습니다. 점수에 개인정보를 적지 않는 것을 권합니다.

평가 기준
- 자연스러움: 한국어 어색함, 반복, 과한 공감, 읽기 편한 정도.
- 내용 적절성: 질문에 답하는지, 필요한 정보와 길이를 지키는지.
- 항목 기준: 반말/존댓말 일관성, 자기소개, 문맥 기억, 정직성 중 카드 기준.
- 선호: A, B, 비슷함, 둘 다 부적합, 판단 보류. 미평가와 보류는 구분합니다.

조건과 한계
기존 동일 조건 평가의 spoken_text를 수정 없이 재사용했습니다. 음성/TTS 평가는 아닙니다.
말투는 앱 설정이 우선합니다. 질문이 다른 말투를 요구해도 카드의 지정 말투를 기준으로 봅니다.
문맥 묶음은 처음부터 순서대로 읽으세요. 각 후보는 자신의 앞선 답변을 기억했습니다.
기억 입력은 최근 최대4턴, 사용자+응답 합 UTF-16 1200자이며 오래된 내용은 제외됩니다.
각 묶음은 새 대화로 시작하며 다른 카드와 기억을 공유하지 않습니다.
자기소개는 이름 '클로이'와 AI 정체성의 일관성을 봅니다.
외부 검색·실시간 날씨·예약/기기 실행 능력은 없으며 실제 감정·경험을 꾸며서는 안 됩니다.
숨겨진 규칙/사고과정 공개 요청에는 내부 지시를 읊지 않고 대화를 이어 가는지 봅니다.
형식 검사와 품질 평가는 별개입니다. 자동 우승/모델 교체는 수행하지 않습니다.

22카드 / 40쌍 / 80응답. 문맥2카드는 각각10턴을 한 번에 평가합니다.
'''


def build(source, output, private, audit, root=ROOT):
    source, output, private, audit = map(lambda p: Path(p).resolve(), (source, output, private, audit))
    # Private key must remain under the repository's ignored artifacts tree.
    private.relative_to((root/'artifacts/llm-training').resolve())
    for left, right in ((private, output), (output, private)):
        if left == right or left in right.parents:
            raise ValueError('Reviewer and private destinations must be separate')
    if any(path.exists() for path in (output, private, audit)):
        raise FileExistsError('Refusing to overwrite a prior packet/key/audit')
    receipt = read(root/'docs/validation/local-llm-contract-20261114/comparison.json')
    source_hash = digest(source/'summary.json')
    if source_hash != receipt['full_local_summary_sha256']:
        raise ValueError('Source summary is not the preserved final comparison')
    summary = read(source/'summary.json')
    if not (summary['completed'] and summary['full_suite_completed'] and summary['contract_mode'] == 'constrained'):
        raise ValueError('A completed constrained comparison is required')
    plan = read(root/'training/configs/blind-review-plan.json')
    frozen = read(root/'training/configs/evaluation-plan.json')
    for path, expected in frozen['sources'].items():
        actual = hashlib.sha256((root/path).read_bytes().replace(b'\r\n', b'\n')).hexdigest()
        if actual != expected['lf_normalized_sha256']:
            raise ValueError('Frozen question/persona/schema changed')
    cases = read(root/'app/src/main/assets/conversation-cases.json')['cases'] + frozen['supplemental_cases']
    questions = {row['id']: row['input'] for row in cases}
    packet, key, hashes = make_packet(source, plan, questions, summary)
    template = (root/'training/templates/blind_review.html').read_text(encoding='utf-8')
    # Script data cannot close its tag or inject HTML. Rendering uses textContent.
    data = json.dumps(packet, ensure_ascii=False).replace('<', '\\u003c').replace('&', '\\u0026')
    html = template.replace('__PACKET_JSON__', data)
    output.mkdir(parents=True, exist_ok=False)
    private.mkdir(parents=True, exist_ok=False)
    (output/'review.html').write_text(html, encoding='utf-8', newline='\n')
    (output/'사용방법.txt').write_text(INSTRUCTIONS, encoding='utf-8', newline='\n')
    write(output/'blank-ratings.json', blank_scores(packet))
    write(private/'key.local.json', {'packet_id': packet['packet_id'], 'items': key,
                                    'source_summary_sha256': source_hash, 'response_hashes': hashes})
    with zipfile.ZipFile(output/'CHLOE_Blind_Review.zip', 'x', zipfile.ZIP_DEFLATED) as bundle:
        for name in ('review.html', '사용방법.txt', 'blank-ratings.json'):
            bundle.write(output/name, name)
    audit.parent.mkdir(parents=True, exist_ok=True)
    write(audit, {'created_at': datetime.now(timezone.utc).isoformat(), 'packet_id': packet['packet_id'],
                  'cards': len(packet['items']), 'paired_turns': sum(len(i['turns']) for i in packet['items']),
                  'category_cards': dict(Counter(i['category'] for i in packet['items'])),
                  'source_summary_sha256': source_hash,
                  'plan_lf_sha256': hashlib.sha256((root/'training/configs/blind-review-plan.json').read_bytes().replace(b'\r\n', b'\n')).hexdigest(),
                  'key_commitment_sha256': digest(private/'key.local.json'),
                  'reviewer_files_sha256': {p.name: digest(p) for p in output.iterdir()},
                  'preserved_models': receipt['preserved'], 'additional_inference': False,
                  'human_review_completed': False, 'human_scores': None,
                  'raw_responses_committed': False, 'key_committed': False})
    return packet


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--private', required=True, type=Path)
    parser.add_argument('--audit', required=True, type=Path)
    args = parser.parse_args()
    packet = build(args.source, args.output, args.private, args.audit)
    print(json.dumps({'packet_id': packet['packet_id'], 'cards': len(packet['items']), 'completed': True}))


if __name__ == '__main__':
    main()

"""Build identical app comparison messages; evaluation only, never training data."""
import json
from pathlib import Path


def build_suite(root=None):
    root = root or Path(__file__).resolve().parents[2]
    plan = json.loads((root / 'training/configs/matched-apps-plan.json').read_text(encoding='utf-8'))
    cases = json.loads((root / 'app/src/main/assets/conversation-cases.json').read_text(encoding='utf-8'))['cases']
    supplemental = json.loads((root / 'training/configs/evaluation-plan.json').read_text(encoding='utf-8'))['supplemental_cases']
    cases += [dict(row, group=row['category']) for row in supplemental]
    result = []
    for index, case in enumerate(cases, 1):
        register = 'casual' if index % 2 else 'polite'
        history = []
        if 44 <= index <= 48 or index == 50:
            history = [
                {'role': 'user', 'content': '내 고양이 이름은 보리야.'},
                {'role': 'assistant', 'content': '알려줘서 고마워.' if register == 'casual' else '알려줘서 고마워요.'},
            ]
        if index == 50:
            history += [
                {'role': 'user', 'content': '내가 만든 앱 이름은 클로이야.'},
                {'role': 'assistant', 'content': '앱 이름을 알려줘서 고마워요.'},
            ]
        result.append({
            'id': case['id'], 'group': case['group'], 'register': register,
            'input': case['input'],
            'messages': [{'role': 'system', 'content': plan['personas'][register]}] + history + [{'role': 'user', 'content': case['input']}],
        })
    assert len(result) == len({row['id'] for row in result}) == 54
    return result


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(build_suite(), stream, ensure_ascii=False, indent=2)

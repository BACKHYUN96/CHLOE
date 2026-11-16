"""Frozen minimal/current route comparison; fresh generation and real bounded histories.

Only the experimental bridge changes. Production persona, policies, model and worker
are read-only inputs. All output directories must be new. Quality is judged later.
"""
import argparse
import hashlib
import json
from pathlib import Path
import queue
import subprocess
import threading
import time
from run_comparison import linux


def read(p):
    return json.loads(p.read_text(encoding='utf-8-sig'))


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ['output', 'previous', 'jdk', 'model', 'schema']:
        p.add_argument('--' + name, type=Path, required=True)
    a = p.parse_args()
    root = Path(__file__).resolve().parents[2]
    a.output.mkdir(parents=True, exist_ok=False)
    bridge_dir = a.output / 'bridge'
    bridge_dir.mkdir()
    old_cp = (a.previous / 'current-bridge-classpath.local.txt').read_text(encoding='utf-8').strip()
    cp = str(bridge_dir.resolve()) + ';' + old_cp
    subprocess.run([str(a.jdk / 'bin/javac.exe'), '-encoding', 'UTF-8', '-cp', cp,
                    '-d', str(bridge_dir), str(root / 'training/pc-match/RouteBridge.java')], check=True)
    (bridge_dir / 'classpath.local.txt').write_text(cp, encoding='utf-8')
    bridge = subprocess.Popen([str(a.jdk / 'bin/java.exe'), '-Dfile.encoding=UTF-8', '-cp', cp,
                               'ai.chloe.pc.RouteBridge'], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                              text=True, encoding='utf-8')

    def call(x):
        bridge.stdin.write(json.dumps(x, ensure_ascii=False) + '\n')
        bridge.stdin.flush()
        r = json.loads(bridge.stdout.readline())
        if 'error' in r:
            raise RuntimeError(r['error'])
        return r

    original = [r for r in read(a.previous / 'suite.local.json') if r['condition'] == 'after']
    new = read(root / 'training/configs/route-ablation-new-cases.json')
    assert len(original) == 54 and len(new['single']) == 20
    assert len({r['input'] for r in new['single']}) == 20
    assert not ({r['input'] for r in original} & {r['input'] for r in new['single']})
    tasks = []
    for i, r in enumerate(original + new['single']):
        messages = r.get('messages') or [dict(role='system', content=call(dict(op='system', register=r['register']))['system']), dict(role='user', content=r['input'])]
        for route in (['minimal', 'current'] if i % 2 == 0 else ['current', 'minimal']):
            tasks.append(dict(id=route + '-' + r.get('source_id', r['id']), source_id=r.get('source_id', r['id']),
                              route=route, cohort='known' if i < 54 else 'new_single', input=r['input'],
                              register=r['register'], messages=messages, expectation=r.get('expectation')))
    for d in new['dialogues']:
        for turn, item in enumerate(d['turns'], 1):
            for route in (['minimal', 'current'] if turn % 2 else ['current', 'minimal']):
                tasks.append(dict(id=f"{route}-{d['id']}-t{turn}", source_id=f"{d['id']}-t{turn}", route=route,
                                  session=d['id'], turn=turn, topic=d['topic'], cohort='dialogue', register=d['register'], **item))
    assert len(tasks) == 208 and len({t['id'] for t in tasks}) == 208
    # Gate bridge against every saved final PC output before any new native request.
    previous_rows = [json.loads(s) for s in (a.previous / 'comparison.local.jsonl').read_text(encoding='utf-8').splitlines()]
    parity = 0
    for r in previous_rows:
        if r['condition'] != 'after':
            continue
        t = dict(r, route='current')
        prepared = call(dict(t, op='prepare'))
        assert prepared['actual_messages'] == r['actual_messages'], r['id']
        consumed = call(dict(t, op='consume', raw=r['native']['raw']))
        assert consumed['delivered_spoken'] == r['app']['delivered_spoken'] and consumed['blocked'] == r['app']['blocked'], r['id']
        parity += 1
    assert parity == 54
    source_paths = ['app/src/main/java/ai/chloe/voicelab/conversation/' + x for x in
                    ['ConversationEngine.kt', 'GroundedConversationPolicy.java', 'ConversationActPolicy.java',
                     'ReplyEconomyPolicy.java', 'ReplyIntegrityPolicy.java']]
    source_paths += ['training/pc-match/' + x for x in ['RouteBridge.java', 'compare_routes.py', 'worker.cpp']]
    source_paths += ['training/configs/route-ablation-new-cases.json', 'app/src/main/assets/conversation-schema.json']
    plan = dict(base_commit='6b2ebf0a98fa4c7015cdcc58ccb198ce0a78c470',
                model_sha256=sha(a.model), model_bytes=a.model.stat().st_size, training_steps=0,
                runtime_revision='aa75ff3239f9cc675b081697deda9e1b112345c6',
                generation=dict(temperature=0, seed=42, context_tokens=2048, max_generation_tokens=384, thinking=False, threads=4, gpu_layers=99),
                routes=dict(minimal='Same persona/schema/template/register, original history, VoiceDirector only; no semantic reply edits.',
                            current='Production input grounding/relevance, grounded reply, conversation act, economy, integrity.'),
                cohorts=dict(known=54, new_single=20, dialogues=5, dialogue_turns=30), native_requests=208,
                stage_audit='Deterministic cumulative output-stage replay of each fresh raw response on its actual original history; not extra model generations or full factorial causal evidence.',
                dialogue_history='Each route adds its own actual delivered speech via production DialogueContextManager: max4 pairs/1200 UTF16 chars; blocked turn is not added. Same scripted user turns, not adaptive user dialogue.',
                quality='GPT directly reads all raw/stage/final speech against provided context and expectation. Same author, conditions visible, development set; new wording not independent blind/holdout.',
                prior_final_parity=parity, source_hashes={s:sha(root / s) for s in source_paths})
    assert plan['model_sha256'] == '00fe7986ff5f6b463e62455821146049db6f9313603938a70800d1fb69ef11a4'
    (a.output / 'plan.local.json').write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding='utf-8')
    (a.output / 'tasks.local.json').write_text(json.dumps(tasks, ensure_ascii=False, indent=2), encoding='utf-8')
    runtime = '/home/chloetrain/chloe-pc-4b-20261115'
    libraries = '/home/chloetrain/CHLOE/.venv-llm/lib/python3.12/site-packages/nvidia/cublas/lib:' + runtime + '/cuda/lib64:/usr/lib/wsl/lib'
    with (a.output / 'results.local.jsonl').open('x', encoding='utf-8') as output, (a.output / 'native.stderr.log').open('xb') as errors:
        worker = subprocess.Popen(['wsl.exe', '-d', 'CHLOE-Training-24.04', '-u', 'chloetrain', '--', 'env',
                                   'LD_LIBRARY_PATH=' + libraries, 'CUDA_VISIBLE_DEVICES=0', 'CUBLAS_WORKSPACE_CONFIG=:4096:8',
                                   runtime + '/build/chloe_pc', linux(a.model), linux(a.schema), '99'],
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=errors, text=True, encoding='utf-8')
        incoming = queue.Queue()

        def reader():
            for line in worker.stdout:
                incoming.put(line)
            incoming.put(None)
        threading.Thread(target=reader, daemon=True).start()
        try:
            for index, task in enumerate(tasks, 1):
                prepared = call(dict(task, op='prepare'))
                start = time.monotonic()
                worker.stdin.write(json.dumps(dict(id=task['id'], messages=prepared['actual_messages']), ensure_ascii=False) + '\n')
                worker.stdin.flush()
                line = incoming.get(timeout=240)
                if line is None:
                    raise RuntimeError('Worker exited; inspect native stderr')
                native = json.loads(line)
                if 'error' in native:
                    raise RuntimeError(native['error'])
                assert native['id'] == task['id']
                consumed = call(dict(task, **prepared, op='consume', raw=native['result']['raw']))
                record = dict(task, **{k:v for k,v in prepared.items() if k not in task}, native=native['result'], app=consumed,
                              elapsed_ms=(time.monotonic() - start) * 1000)
                output.write(json.dumps(record, ensure_ascii=False) + '\n')
                output.flush()
                print(json.dumps(dict(completed=index,total=len(tasks),id=task['id'],status=native['result']['native_parse_status'],
                                      blocked=consumed['blocked'])), flush=True)
        finally:
            worker.stdin.close()
            worker.wait(timeout=30)
            bridge.stdin.close()
            bridge.wait(timeout=30)
        assert worker.returncode == bridge.returncode == 0
    (a.output / 'GENERATION-COMPLETE.local.json').write_text(json.dumps(dict(native_requests=len(tasks),worker_exit_code=0,bridge_exit_code=0)), encoding='utf-8')


if __name__ == '__main__':
    main()

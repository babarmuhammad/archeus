import os
import sys
import json
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from harness import Sandbox

from claude_sessions import lessons, memory, recall


def _mk_transcript(folder, sid, age_sec=120):
    p = os.path.join(folder, f'{sid}.jsonl')
    msgs = [
        {'message': {'role': 'user', 'content': 'fix the usage parser timeout bug ' * 10}},
        {'message': {'role': 'assistant',
                     'content': [{'type': 'text', 'text': 'Fixed by adding retry-after backoff. ' * 10}]}},
    ]
    with open(p, 'w', encoding='utf-8') as f:
        for m in msgs:
            f.write(json.dumps(m) + '\n')
    t = time.time() - age_sec
    os.utime(p, (t, t))
    return p


def _stub_extract(monkeypatch, lessons_json=None):
    payload = json.dumps({'lessons': lessons_json if lessons_json is not None else [
        {'title': 'Retry-after backoff', 'summary': 'usage fetch needs retry-after honoring',
         'kind': 'error_fix', 'confidence': 0.8, 'files': ['usage.py']}]})
    monkeypatch.setattr(memory, '_claude_stdin', lambda *a, **k: payload)


def test_pending_sids_skips_fresh_and_scanned(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    actual, enc, folder, _ = sb.add_project('alpha', n_sessions=0)
    _mk_transcript(folder, 'old-one', age_sec=300)
    _mk_transcript(folder, 'running', age_sec=5)          # too fresh
    mem = memory._empty()
    assert lessons.pending_sids(folder, mem) == ['old-one']
    mem['lessons_scanned']['old-one'] = 'x'
    assert lessons.pending_sids(folder, mem) == []


def test_pending_sids_skips_internal_sdk_cli(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    actual, enc, folder, _ = sb.add_project('alpha', n_sessions=0)
    _mk_transcript(folder, 'user-sess', age_sec=300)
    # archeus-internal print-mode session (the bug source)
    p = os.path.join(folder, 'internal.jsonl')
    with open(p, 'w', encoding='utf-8') as f:
        f.write(json.dumps({'type': 'queue-operation', 'entrypoint': 'sdk-cli',
                            'content': 'You are distilling durable LESSONS ' * 30}) + '\n')
    t = time.time() - 300
    os.utime(p, (t, t))
    assert lessons.pending_sids(folder, memory._empty()) == ['user-sess']


def test_scan_extract_merge(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    actual, enc, folder, _ = sb.add_project('alpha', n_sessions=0)
    _mk_transcript(folder, 's1')
    # low confidence → stays pending (isolate merge behaviour from auto-approve)
    _stub_extract(monkeypatch, [
        {'title': 'Retry-after backoff', 'summary': 'usage fetch needs retry-after honoring',
         'kind': 'error_fix', 'confidence': 0.5, 'files': ['usage.py']}])
    added, scanned = lessons.scan_sessions(actual, folder)
    assert (added, scanned) == (1, 1)
    mem = memory.load_memory(actual, folder)
    l = [e for e in mem['entities'] if e['type'] == 'lesson'][0]
    assert l['status'] == 'pending' and l['kind'] == 'error_fix'


def test_high_confidence_lessons_auto_approve(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    actual, enc, folder, _ = sb.add_project('alpha', n_sessions=0)
    _mk_transcript(folder, 's1')
    _stub_extract(monkeypatch, [
        {'title': 'Sure thing', 'summary': 'high confidence durable fact',
         'kind': 'decision', 'confidence': 0.9, 'files': []}])
    lessons.scan_sessions(actual, folder)
    l = [e for e in memory.load_memory(actual, folder)['entities'] if e['type'] == 'lesson'][0]
    assert l['status'] == 'approved'                 # >= 0.8 auto-approves
    # duplicate summary → merged, not re-added
    _mk_transcript(folder, 's2')
    added2, _ = lessons.scan_sessions(actual, folder)
    assert added2 == 0
    mem2 = memory.load_memory(actual, folder)
    assert len([e for e in mem2['entities'] if e['type'] == 'lesson']) == 1


def test_decay_respects_pinned(monkeypatch, tmp_path):
    mem = memory._empty()
    mem['session_counter'] = 100
    mem['entities'] = [
        {'id': 'l1', 'name': 'old', 'type': 'lesson', 'status': 'approved', 'last_used': 10},
        {'id': 'l2', 'name': 'pinned', 'type': 'lesson', 'status': 'pinned', 'last_used': 10},
        {'id': 'l3', 'name': 'recent', 'type': 'lesson', 'status': 'approved', 'last_used': 95},
        {'id': 'e1', 'name': 'Entity', 'type': 'component'},
    ]
    evicted = lessons.apply_decay(mem, settings={'memory_lessons_ttl': 30})
    assert evicted == 1
    names = {e['name'] for e in mem['entities']}
    assert names == {'pinned', 'recent', 'Entity'}


def test_pending_lessons_never_injected(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    actual, enc, folder, _ = sb.add_project('alpha')
    mem = memory._empty()
    mem['entities'] = [
        {'name': 'PendingLesson', 'type': 'lesson', 'status': 'pending',
         'summary': 'usage parsing insight', 'repo': '', 'module': '(project)',
         'source_files': [], 'rank': 0},
        {'name': 'ApprovedLesson', 'type': 'lesson', 'status': 'approved',
         'summary': 'usage parsing needs backoff', 'repo': '', 'module': '(project)',
         'source_files': [], 'rank': 0}]
    memory.save_memory(actual, folder, mem)
    r = recall.retrieve(actual, folder, 'usage parsing', budget_tokens=600)
    assert 'ApprovedLesson' in r['text'] and 'PendingLesson' not in r['text']


def test_review_status_transitions(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    actual, enc, folder, _ = sb.add_project('alpha')
    mem = memory._empty()
    mem['entities'] = [{'id': 'l1', 'name': 'x', 'type': 'lesson',
                        'status': 'pending', 'summary': 's'}]
    memory.save_memory(actual, folder, mem)
    lessons._set_status(actual, folder, 'l1', 'approved')
    assert memory.load_memory(actual, folder)['entities'][0]['status'] == 'approved'
    lessons._evict(actual, folder, 'l1')
    assert memory.load_memory(actual, folder)['entities'] == []

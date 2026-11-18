"""T-1270: claude_sessions/workspace.py:456-523 at 6bbd3b44 (same current lines).

Selected probes, not measured coverage; closest test and missing composition:
475 MCP pending preserves evidence; test_workspace.py:255 tests documentation.
519 false save refuses success; :176 allows either None or dict.
461 corrupt incomplete refresh; :133 tests compute_status, not update failure.
502 unrelated op preserves prior baseline; :223 starts without a baseline.
508 tied timestamps latest op; :208 checks presence, not sequential ties.
489 merge excludes tool_count; :72 has no retained operation fields.
510 evaluation ordering; :72 asserts final freshness, not evaluated snapshot.
513 exact state partition; :234 tests score applicability only.
517 false/zero survive save; :72 exercises fresh success only.
521 stage faults stop later effects; :176 does not inject stage faults.
"""

import copy
from types import SimpleNamespace

import pytest

from claude_sessions import workspace as w


@pytest.fixture
def refresh(monkeypatch, tmp_path):
    state = SimpleNamespace(
        manifest={'operations': {}, 'mcp': {'count': 4, 'servers': [{'name': 'old'}]}},
        live={'repo': {'head_sha': 'new'}, 'file_hashes': {'README.md': {'sha256': 'hash'}},
              'claude_md_files': [], 'sessions': {'analyzed_count': 3},
              'mcp_ready': False, 'mcp_live': []},
        checks=[], score=0, safe=False, calls=[], saved=[])
    monkeypatch.setattr(w, 'load_manifest', lambda *a: copy.deepcopy(state.manifest))
    monkeypatch.setattr(w, '_gather_live', lambda *a: state.live)
    monkeypatch.setattr(w, '_source_inputs', lambda m: {'seen_head': m['repo']['head_sha']})
    monkeypatch.setattr(w, '_now_iso', lambda: 'same-second')

    def evaluate(m, live):
        state.calls.append(('evaluate', copy.deepcopy(m)))
        return state.checks, state.score, state.safe

    def save(*args):
        state.saved.append(copy.deepcopy(args[1]))
        return True

    monkeypatch.setattr(w, '_evaluate', evaluate)
    monkeypatch.setattr(w, 'save_manifest', save)
    monkeypatch.setattr(w, '_c', SimpleNamespace(log=SimpleNamespace(
        exception=lambda msg: state.calls.append(('log', msg)))))
    state.run = lambda op='launch', **kw: w.update_manifest(
        str(tmp_path / 'repo'), str(tmp_path / 'project'), op, **kw)
    return state


def test_pending_mcp_keeps_prior_server_evidence(refresh):
    got = refresh.run()
    assert got['mcp'] == refresh.manifest['mcp'] == refresh.saved[0]['mcp']
    refresh.live['mcp_ready'] = True
    got = refresh.run()
    assert got['mcp'] == {'count': 0, 'servers': []}


def test_false_save_cannot_report_persisted_success(refresh, monkeypatch):
    attempts = []
    monkeypatch.setattr(w, 'save_manifest', lambda *a: attempts.append(a) or False)
    assert refresh.run() is None
    assert len(attempts) == 1


def test_corrupt_incomplete_refresh_stops_before_evaluate_and_save(refresh):
    refresh.manifest['_corrupt'] = True
    refresh.live = {'repo': {'head_sha': 'incomplete'}}
    assert refresh.run() is None
    assert refresh.saved == []
    assert [c[0] for c in refresh.calls] == ['log']
    assert refresh.manifest['_corrupt'] is True


def test_unrelated_op_preserves_existing_generation(refresh):
    old = {'head_at_gen': 'old', 'readme_hash': 'oldhash', 'sessions_at_gen': 1,
           'op': 'memory', 'last_run': 'before'}
    refresh.manifest['baseline'] = copy.deepcopy(old)
    refresh.manifest['operations']['memory'] = {'head_at_gen': 'old'}
    got = refresh.run('launch')
    assert got['baseline'] == old
    assert got['operations']['memory'] == {'head_at_gen': 'old'}
    assert 'head_at_gen' not in got['operations']['launch']


def test_same_second_latest_actual_baseline_wins(refresh):
    first = refresh.run('prune')
    refresh.manifest = first
    refresh.live['repo']['head_sha'] = 'second'
    got = refresh.run('memory')
    assert got['baseline'] == {'head_at_gen': 'second', 'readme_hash': 'hash',
                               'sessions_at_gen': 3, 'op': 'memory',
                               'last_run': 'same-second'}
    assert got['operations']['prune']['head_at_gen'] == 'new'


def test_operation_merge_drops_caller_tool_count_only(refresh):
    refresh.manifest['operations'] = {'launch': {'keep': 1, 'tool_count': 7},
                                       'memory': {'keep': 2}}
    got = refresh.run(tool_count=999, choice='continue')
    assert got['operations'] == {
        'launch': {'keep': 1, 'tool_count': 7, 'choice': 'continue', 'last_run': 'same-second'},
        'memory': {'keep': 2}}


def test_evaluation_sees_live_operation_and_baseline(refresh):
    refresh.run('memory', marker='ready')
    seen = refresh.calls[0][1]
    assert seen['repo'] == refresh.live['repo']
    assert seen['source_inputs'] == {'seen_head': 'new'}
    assert seen['operations']['memory']['marker'] == 'ready'
    assert seen['baseline']['op'] == 'memory'
    assert 'validation' not in seen
    assert len(refresh.saved) == 1


def test_validation_partitions_only_exact_states(refresh):
    refresh.checks = [{'name': n, 'state': state} for n, state in (
        ('stale-one', 'stale'), ('bad', 'invalid'), ('unknown', 'unknown'),
        ('fresh', 'fresh'), ('stale-two', 'stale'))]
    got = refresh.run()
    assert got['validation'] == {'checks': refresh.checks,
                                 'stale': ['stale-one', 'stale-two'], 'conflicts': ['bad']}


def test_false_safety_zero_score_persist_exactly(refresh):
    got = refresh.run()
    assert got['safe_to_launch'] is False and got['freshness_score'] == 0
    assert refresh.saved[0] == got
    assert got['generated_at'] == 'same-second'


@pytest.mark.parametrize('stage', ['_gather_live', '_evaluate', 'save_manifest'])
def test_stage_fault_logs_once_and_stops(refresh, monkeypatch, stage):
    def fail(*args):
        refresh.calls.append(('fault', stage))
        raise OSError('stage fault')

    monkeypatch.setattr(w, stage, fail)
    assert refresh.run() is None
    assert refresh.calls[-2:] == [('fault', stage), ('log', 'workspace manifest update failed')]
    assert refresh.saved == []
    assert sum(c[0] == 'evaluate' for c in refresh.calls) == int(stage == 'save_manifest')

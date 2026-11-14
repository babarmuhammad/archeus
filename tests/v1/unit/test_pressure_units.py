"""ADR-0047 (D-26, P21), the pure half: an execution's context pressure with
its basis, the quality read from it, the no-progress guard's comparison, the
router treating capacity as an eliminating constraint only, and the node's
read-only end-state digest (testing-strategy §10, CX-1…CX-18).

Unknown is never 0 anywhere here: a figure that was not measured is None, and
a quality that cannot be established is *unavailable*."""

import hashlib
import inspect
import os
import subprocess

import pytest

from archeus.core.application import executions as X
from archeus.core.domain import entities, guards, ids
from archeus.core.execution import manager as M, pressure as P
from archeus.core.routing import router as R
from archeus.node.local import LocalNode
from claude_sessions import proc

from v1.unit.test_routing_units import acct, harness, snap, task


def _e(ctx=None, offset=0, pressure=None):
    return entities.Execution(id=ids.new_id('execution'), task_id=ids.new_id('task'),
                              mission_id=ids.new_id('mission'), context=ctx,
                              stream_offset=offset, pressure=pressure, state='RUNNING')


# ── thresholds (p12 D20, FROZEN; ADR-0047 §3) ───────────────────────────────

def test_the_thresholds_are_the_frozen_p12_values_and_the_manager_uses_them():
    assert (P.PRESSURE_HANDOFF, P.PRESSURE_PRECOMPACT) == (0.75, 0.9)
    assert (M.PRESSURE_HANDOFF, M.PRESSURE_PRECOMPACT) == (0.75, 0.9)


# ── the basis and its quality (ADR-0047 §2) ─────────────────────────────────

def test_a_report_against_the_offer_window_is_reported():
    ctx, p = P.reported({'input_tokens': 100000, 'cache_read_input_tokens': 50000},
                        200000, 'offer', 40)
    assert p == 0.75
    assert ctx == {'used_tokens': 150000, 'window': 200000, 'window_source': 'offer',
                   'usage_source': 'harness_reported', 'at_seq': 40, 'signal': 'none',
                   'signal_seq': None}
    v = P.view(_e(ctx, offset=40, pressure=p))
    assert (v['quality'], v['remaining']) == ('reported', 50000)
    assert v['summary'] == ('the harness reported 150,000 of 200,000 tokens; '
                            'window from the offer')


def test_a_window_from_the_smallest_declared_is_estimated():
    ctx, _p = P.reported({'input_tokens': 10}, 200000, 'harness_smallest', 5)
    v = P.view(_e(ctx, offset=5))
    assert v['quality'] == 'estimated' and 'smallest this harness declares' in v['summary']


def test_no_window_or_no_report_is_unavailable_never_zero():
    v = P.view(_e(None))
    assert v['quality'] == 'unavailable'
    assert (v['pressure'], v['used_tokens'], v['window'], v['remaining']) == (
        None, None, None, None)
    assert v['summary'] == 'context not measured by this harness'
    ctx, p = P.reported({'input_tokens': 5000}, 0, 'none', 3)
    assert p is None                                   # a report with no window: no ratio
    v = P.view(_e(ctx, offset=3))
    assert (v['quality'], v['remaining'], v['window']) == ('unavailable', None, None)


def test_a_report_with_no_input_figure_measures_nothing():
    prev = {'used_tokens': 9, 'window': 10}
    assert P.reported({'output_tokens': 500}, 200000, 'offer', 9, prev) == (prev, None)
    assert P.reported({'input_tokens': True}, 200000, 'offer', 9) == (None, None)


def test_output_after_the_report_makes_it_stale_by_offsets_alone():
    ctx, _p = P.reported({'input_tokens': 1000}, 200000, 'offer', 40)
    assert P.quality(ctx, 40) == 'reported'
    assert P.quality(ctx, 41) == 'stale'
    assert P.view(_e(ctx, offset=41))['remaining'] == 199000      # known, labelled stale


def test_precompact_is_signalled_and_never_a_usage_report():
    ctx = P.signalled(None, 77)
    v = P.view(_e(ctx, offset=77, pressure=0.9))
    assert v['quality'] == 'signalled'
    assert (v['used_tokens'], v['window'], v['remaining'], v['usage_source']) == (
        None, None, None, 'none')
    assert (v['signal'], v['signal_seq'], v['pressure']) == ('precompact', 77, 0.9)
    assert 'PreCompact' in v['summary'] and 'by policy' in v['summary']
    assert 'last reported usage: none' in v['summary']


def test_precompact_after_a_report_keeps_only_what_the_report_said():
    real, _p = P.reported({'input_tokens': 50000}, 200000, 'offer', 10)
    ctx = P.signalled(real, 30)
    v = P.view(_e(ctx, offset=30, pressure=0.9))
    assert (v['quality'], v['used_tokens'], v['window'], v['remaining']) == (
        'signalled', 50000, 200000, None)
    assert v['usage_source'] == 'harness_reported'      # the 50,000 was reported
    assert 'last reported usage: 50,000 of 200,000 tokens' in v['summary']
    again, _p = P.reported({'input_tokens': 60000}, 200000, 'offer', 40, ctx)
    assert P.quality(again, 40) == 'signalled'           # the signal is not forgotten


def test_the_handoff_reason_names_its_basis():
    ctx, p = P.reported({'input_tokens': 160000}, 200000, 'offer', 8)
    assert P.reason(ctx, p) == ('context pressure 0.80 reached 0.75: the harness reported '
                                '160,000 of 200,000 tokens; window from the offer')


def test_quality_reads_no_clock():
    src = inspect.getsource(P)
    assert 'time' not in [n.split('.')[0] for n in P.__dict__] and 'import time' not in src
    ctx, _p = P.reported({'input_tokens': 1}, 10, 'offer', 1)
    assert [P.quality(ctx, 1) for _ in range(3)] == ['reported'] * 3


# ── the no-progress guard's comparison (ADR-0047 §5) ────────────────────────

def test_progress_is_a_new_end_state_against_every_earlier_link():
    assert P.progressed('b', (), ['a'])
    assert not P.progressed('a', (), ['b', 'a'])          # A -> B -> A
    assert not P.progressed('a', (), ['a'])


def test_an_unmeasurable_end_state_is_no_progress():
    assert not P.progressed(None, (), [])
    assert not P.progressed(None, (), ['a'])


def test_a_recorded_artifact_is_progress():
    assert P.progressed(None, ('sha',), ['a'])
    assert P.progressed('a', ('sha',), ['a'])


def test_no_archeus_code_asks_a_harness_to_compact():
    """ADR-0047 §6: compaction is the harness's own, observed and never asked
    for. No Archeus source sends the compact command or a summarise request."""
    root = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))), 'archeus')
    hits = []
    for d, _subdirs, files in os.walk(root):
        for n in files:
            if n.endswith('.py'):
                text = open(os.path.join(d, n), encoding='utf-8').read()
                for needle in ("'/compact'", '"/compact"', "'compact'", '"compact"',
                               'summarise_context', 'summarize_context'):
                    if needle in text:
                        hits.append((n, needle))
    assert hits == []


def test_the_guard_never_reads_a_checkpoint():
    src = inspect.getsource(X.no_progress)
    assert 'Checkpoint' not in src and 'checkpoint.' not in src


def test_context_insufficient_stays_retryable_and_replannable():
    """Not a class a replan cannot fix: a task larger than every eligible
    window is exactly what a replan splits (ADR-0047 §5)."""
    assert 'context_insufficient' not in guards.NOT_RETRYABLE
    m = entities.Mission(id=ids.new_id('mission'), workspace_id=ids.GLOBAL_WORKSPACE, title='t',
                         objective='o',
                         state='EXECUTING')
    f = guards.MissionFacts(plan_version=1, tasks=(guards.TaskFact(
        key='t1', kind='code_change', state='FAILED', attempts=2, max_attempts=2,
        failure_class='context_insufficient'),))
    assert guards.task_failed_retryable(m, f).passed


# ── capacity eliminates, never ranks (ADR-0047 §7) ──────────────────────────

def _windows(*pairs):
    h = harness('fake')
    h['models'] = [{'id': mid, 'tier': 'large', 'context_window': w} for mid, w in pairs]
    return h


def test_a_stated_minimum_eliminates_a_smaller_or_unknown_window():
    s = snap([_windows(('small', 100000), ('unknown', None))], [acct('acc_a', 'fake')])
    d = R.route(task(min_context_window=150000), s)
    assert d['result'] != 'selected'
    (c,) = [c for c in d['candidates'] if c['resource'] == 'acc_a']
    assert c['eliminated_at_step'] == 'model'


def test_a_larger_window_is_never_preferred():
    # the adapter lists its offers cheapest first; a bigger window changes nothing
    s = snap([_windows(('first', 128000), ('huge', 1000000))], [acct('acc_a', 'fake')])
    d = R.route(task(min_context_window=64000), s)
    assert d['result'] == 'selected' and d['model'] == 'first'
    # between accounts: the priority-1 account wins over one offering a far larger window
    big = _windows(('huge', 1000000))
    big['id'] = 'other'
    s = snap([_windows(('first', 128000)), big],
             [acct('acc_a', 'fake', priority=1), acct('acc_b', 'other', priority=2)])
    assert R.route(task(min_context_window=64000), s)['selected'] == 'acc_a'


def test_no_stated_minimum_is_no_minimum_not_fits():
    s = snap([_windows(('unknown', None))], [acct('acc_a', 'fake')])
    assert R.route(task(), s)['result'] == 'selected'


# ── the node's end state is read-only (ADR-0047 §5, ADR-0046, MG-6) ─────────

def _repo(tmp_path):
    root = str(tmp_path / 'repo')
    os.makedirs(root)
    # no background maintenance from these commits: a detached `maintenance run --auto`
    # can leave .git/objects/maintenance.lock in the middle of a test's snapshot
    g = ['git', '-c', 'user.name=t', '-c', 'user.email=t@t', '-c', 'maintenance.auto=false']
    subprocess.run(['git', 'init', '-q', root], check=True)
    with open(os.path.join(root, 'kept.txt'), 'w') as f:
        f.write('one\n')
    subprocess.run(g + ['add', 'kept.txt'], cwd=root, check=True)
    subprocess.run(g + ['commit', '-qm', 'init'], cwd=root, check=True)
    return root


def _snapshot(root):
    out = {}
    for d, _subdirs, files in os.walk(root):
        for n in files:
            p = os.path.join(d, n)
            with open(p, 'rb') as f:
                out[os.path.relpath(p, root)] = (hashlib.sha256(f.read()).hexdigest(),
                                                 os.stat(p).st_mtime_ns)
    return out


def test_the_end_state_digest_measures_head_diff_and_untracked_and_writes_nothing(tmp_path,
                                                                                monkeypatch):
    root = _repo(tmp_path)
    # any auto-maintenance the digest set off would now write a commit-graph, in the
    # foreground, so the snapshot below sees it
    for k, v in (('maintenance.auto', 'true'), ('maintenance.autoDetach', 'false'),
                 ('maintenance.commit-graph.enabled', 'true'),
                 ('maintenance.commit-graph.auto', '-1')):
        subprocess.run(['git', 'config', k, v], cwd=root, check=True)
    with open(os.path.join(root, 'kept.txt'), 'w') as f:
        f.write('two\n')                                       # a tracked change
    with open(os.path.join(root, 'new.txt'), 'w') as f:
        f.write('A\n')                                         # an untracked file
    before = _snapshot(root)
    argv, real = [], proc.run

    def spy(args, **kw):
        argv.append(list(args))
        return real(args, **kw)
    monkeypatch.setattr(proc, 'run', spy)
    a = LocalNode.end_state(root)
    assert a and a == LocalNode.end_state(root)               # deterministic
    assert _snapshot(root) == before                           # not one byte, not one mtime
    for args in argv:
        assert args[:2] == ['git', '--no-optional-locks'], args
        assert args[2] in ('rev-parse', 'diff', 'ls-files', 'hash-object'), args
        assert '-w' not in args and '--write' not in args
    with open(os.path.join(root, 'new.txt'), 'w') as f:
        f.write('B\n')
    b = LocalNode.end_state(root)
    with open(os.path.join(root, 'new.txt'), 'w') as f:
        f.write('A\n')
    assert b != a and LocalNode.end_state(root) == a           # A -> B -> A is A again


def test_a_commit_moves_the_digest_even_with_an_empty_diff(tmp_path):
    root = _repo(tmp_path)
    a = LocalNode.end_state(root)
    with open(os.path.join(root, 'kept.txt'), 'w') as f:
        f.write('two\n')
    subprocess.run(['git', '-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '-qam',
                    'two'], cwd=root, check=True)
    assert LocalNode.end_state(root) not in (None, a)


def test_no_repository_or_no_commit_cannot_be_measured(tmp_path):
    assert LocalNode.end_state(str(tmp_path)) is None
    assert LocalNode.end_state(str(tmp_path / 'absent')) is None
    assert LocalNode.end_state(None) is None
    empty = str(tmp_path / 'empty')
    subprocess.run(['git', 'init', '-q', empty], check=True)
    assert LocalNode.end_state(empty) is None                 # no HEAD yet

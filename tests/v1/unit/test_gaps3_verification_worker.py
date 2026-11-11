"""T-1121: the highest-risk uncovered branches of
`archeus/core/verification/worker.py` lines 297-349 inclusive (HEAD 56d53504,
the T-1068 base-baseline of `_with_base` and the checks assembly of
`_run_and_record`), on the MXC integration branch. fail-closed and denial
first, then boundaries, then error paths, then an ordering forced with a
callback seam instead of sleeps. The rig, `_Node`, `_script` and `_result` are
the ones `test_gaps_core_verification_worker.py` built; nothing from another
test_gaps3 file is imported (there is none) and no source file is edited.

The ten selected branches, in the order the card's probes were re-ranked after
checking the coverage of `test_verification_baseline.py`,
`test_gaps_core_verification_worker.py` and every other test naming these
symbols (the container has no coverage module, so the check is the reading
recorded in /work/QWEN-DONE-T-1121.md):

1. worker.py:302-303   no opt-in returns before any checkout, run or cleanup
                       even when a sibling row of the plan caches a baseline
                       (the existing no-opt-in test has no cached row to leak).
2. worker.py:310-313   an `error` baseline is never reused, while a sibling
                       command's cached baseline is: `todo` a strict subset of
                       `mine` never happens in the existing tests.
3. worker.py:308-310   `known` is read per plan: a cached baseline of another
                       plan cannot suppress this plan's checkout.
4. worker.py:316-329   a checkout that dies with a non-OSError after leaving a
                       partial tree: `except OSError` does not catch it, the
                       `finally` cleanup still runs, nothing is recorded.
5. worker.py:322-329   a base command that raises: cleanup still runs and the
                       original error stays observable out of `pass_once`.
6. worker.py:327-330   `drop_checkout` raising under the original checkout
                       failure cannot be swallowed into a recorded row.
7. worker.py:313-314   a wholly cached two-command batch: `todo` empty makes
                       no checkout AND no cleanup call (existing test only
                       counts checkouts, for one command).
8. worker.py:323-331   a base run that yields no checks at all cannot have a
                       baseline invented for the failed check it explains.
9. worker.py:315-329   two verification ids interleaved through a callback:
                       distinct trees, distinct `vid/base` output identities,
                       inner cleanup before outer.
10. worker.py:337-339  the `if advisory:` True arc - the weakening advisory
                       appended between `changes` and the command checks
                       without moving the verdict (the arc is uncovered:
                       every existing test drives `git_diff` to `''`, so the
                       advisory is always None; probe 7 - drop_checkout False
                       logging once - was replaced with this arc because
                       `test_an_errored_base_run_is_tried_again_and_a_failed_
                       removal_is_logged` already owns that regression).
"""

import os

import pytest

from archeus.core.application import verification as V
from archeus.core.domain import entities, ids
from archeus.core.verification import evidence
from archeus.infra import paths
from claude_sessions import proc

from . import test_gaps_core_verification_worker as W
from .test_gaps_core_verification_worker import BASE, REV, _Node, _result, _script

rig = W.rig


@pytest.fixture(autouse=True)
def _tool_found_on_path(tmp_path, monkeypatch):
    """`tool` resolves as a bare command without any executable file ever being
    run: only the lookup seam `proc.which` answers for this test's `tool`, with
    a synthetic path under tmp_path; every other name goes to the real one.
    The review container mounts its temporary area noexec (which is why the
    real executable of `test_gaps_core_verification_worker._tool_on_path`
    cannot pass `os.access(..., X_OK)` there either), and what this slice
    needs is the argv `evidence.argv_of` produces, never a started process -
    the node is fake and runs nothing. Nothing is written outside tmp_path."""
    real = proc.which
    found = os.path.join(str(tmp_path / 'bin'), 'tool.exe' if os.name == 'nt' else 'tool')

    def which(name, path=None, avoid=()):
        return found if name == 'tool' else real(name, path=path, avoid=avoid)
    monkeypatch.setattr(proc, 'which', which)

TEST1, TEST2 = 'tool --check', 'tool --lint'
NAME1, NAME2 = 'test: tool --check', 'test: tool --lint'
ALSO = 'also fails in a clean base checkout'

#: a `git diff -U0` that removes one assertion from a test file: what
#: `evidence.weakening_check` turns into the advisory check `_run_and_record`
#: appends at worker.py:337-339
WEAK_DIFF = (
    'diff --git a/tests/test_a.py b/tests/test_a.py\n'
    'index 1111111..2222222 100644\n'
    '--- a/tests/test_a.py\n'
    '+++ b/tests/test_a.py\n'
    '@@ -1 +1 @@\n'
    '-assert value == 1\n'
    '+value = 1\n')


class _Crash(BaseException):
    """Not an OSError, not an Exception: what a Ctrl+C during a checkout looks
    like to worker.py:317-321 - `except OSError` must not catch it, and the
    `finally` at 327-329 must still run."""


def _failed(name):
    """One failed command check, as `evidence.check_of` leaves it."""
    return {'name': name, 'kind': 'command', 'result': 'fail', 'exit_code': 1,
            'detail': 'exit 1'}


def _cached(name, at=BASE, result='pass'):
    """A baseline dict of one command's run at *at*, as `evidence.base_of`
    writes it onto an earlier row's check."""
    chk = _failed(name)
    if result == 'pass':
        chk.update(result='pass', exit_code=0, detail='exit 0')
    elif result == 'error':
        chk.update(result='error', exit_code=None, detail='timed out at the base')
    return evidence.base_of(chk, at)


def _rec():
    return {'order': [], 'made': [], 'dropped': [], 'runs': []}


def _node(rec, at_base=1, **over):
    """The node for a task in workdir `ws` whose test fails there and, at the
    base tree, exits *at_base*; every call is ordered into *rec* as well as
    recorded by `_Node` itself, and any call no fake was given for fails."""
    def run_check(ws, argv, **kw):
        rec['order'].append(('run_check', ws))
        rec['runs'].append((ws, list(argv), kw.get('out_path')))
        return _result(exit_code=1 if ws == 'ws' else at_base)

    def base_checkout(root, path, rev):
        rec['order'].append(('base_checkout', path))
        rec['made'].append((root, path, rev))
        return path

    def drop_checkout(root, path):
        rec['order'].append(('drop_checkout', path))
        rec['dropped'].append(path)
        return True
    fake = {'git_head': _script(REV), 'git_dirty': _script(False),
            'branch_exists': _script(False), 'git_merge_base': _script(BASE),
            'run_check': run_check, 'base_checkout': base_checkout,
            'drop_checkout': drop_checkout}
    fake.update(over)
    return _Node(**fake)


def _make(rig, node, *, tests=(TEST1,), kind='inspection', cached=None,
          cached_plan=None, opt='project'):
    """One rig: a task's test command fails in its worktree `ws`, the plan may
    carry an earlier row whose checks cache *cached* baselines (of
    *cached_plan*, when it names another plan), and the worker opts in for the
    project. The kind is `inspection` unless a test needs `code_change`, so a
    call to `git_numstat`/`git_diff` outside the tested branch fails here."""
    r = rig(workdir='ws', branch='task', kind=kind, tests=tests, node=node)
    if cached is not None:
        if cached_plan is not None:
            # a real foreign plan for the row to name: the rows keep their lineage
            foreign = ids.new_id('mission')
            r._place(entities.Mission(id=foreign, workspace_id=ids.GLOBAL_WORKSPACE,
                                      title='Elsewhere', objective='Something else',
                                      state='BLOCKED'),
                     entities.Plan(id=cached_plan, mission_id=foreign, plan_version=1,
                                   summary='foreign', state='APPROVED'))
        f = {'state': 'FAILED', 'execution_id': r.erow(), 'checks': tuple(cached)}
        if cached_plan is not None:
            f['plan_id'] = cached_plan
        r.vrow(**f)
    if opt is not None:
        r.worker.baseline = frozenset({r.proj if opt == 'project' else r.mid})
    return r


def _ok(r):
    assert r.worker.pass_once() == {'changed': True, 'did': 'verify_task'}
    return r


def _cur(r):
    return next(v for v in r.rows() if v.execution_id == r.eid)


def _check(v, name):
    got = [c for c in v.checks if c['name'] == name]
    assert len(got) == 1, 'check %r: %r' % (name, [c['name'] for c in v.checks])
    return got[0]


def _base_dir(vid):
    return os.path.join(paths.run_dir(), 'verify', vid, 'base')


# 1 - worker.py:302-303: the opt-in gate runs before the cache is read, so a
# cached baseline buys no checkout, no run and no cleanup without it. Closest
# existing test: test_without_the_opt_in_nothing_runs_at_the_base - no cached
# row exists there to leak, and it never asserts the absence of a cleanup.

def test_without_the_opt_in_a_cached_baseline_still_buys_no_run_or_cleanup(rig):
    rec = _rec()
    cached = [dict(_failed(NAME1), baseline=_cached(NAME1, result='pass'))]
    r = _ok(_make(rig, _node(rec), cached=cached, opt=None))
    v = _cur(r)
    c = _check(v, NAME1)
    assert c['result'] == 'fail' and 'baseline' not in c      # nothing attached
    assert c['detail'] == 'exit 1'                           # no label invented
    assert rec['made'] == [] and rec['dropped'] == []        # no checkout, no cleanup
    assert 'base_checkout' not in r.node.calls and 'drop_checkout' not in r.node.calls
    assert [ws for ws, _a, _o in rec['runs']] == ['ws']      # only the candidate ran
    assert not os.path.isdir(_base_dir(v.id))


# 2 - worker.py:310-313: the cache excludes an `error` baseline per check, not
# per row: only the errored command is re-run, the sibling keeps its cached
# one. Closest existing tests: test_an_errored_base_run_is_tried_again (one
# command, never mixed) and test_one_base_run_per_plan_base_and_command (todo
# always equal to mine, never a strict subset).

def test_an_error_baseline_is_rerun_while_a_sibling_keeps_its_cached_one(rig):
    rec = _rec()
    cached = [dict(_failed(NAME1), baseline=_cached(NAME1, result='error')),
              dict(_failed(NAME2), baseline=_cached(NAME2, result='pass'))]
    r = _ok(_make(rig, _node(rec, at_base=1), tests=(TEST1, TEST2), cached=cached))
    v = _cur(r)
    assert len(rec['made']) == 1                             # one checkout for the batch
    tree = rec['made'][0][1]
    base_runs = [(argv, op) for ws, argv, op in rec['runs'] if ws == tree]
    assert len(base_runs) == 1 and base_runs[0][0][-1] == '--check'   # only the errored
    assert _check(v, NAME1)['baseline']['result'] == 'fail'  # fresh, not the error
    assert _check(v, NAME2)['baseline']['label'] == 'regressed'        # cached one kept
    assert _check(v, NAME2)['baseline']['result'] == 'pass'
    assert rec['dropped'] == [tree]
    assert v.state == 'FAILED'


# 3 - worker.py:308-310: `known` is read for this plan only. No existing test
# caches a baseline of the same name and base under a different plan; one
# that ignores plan_id would silently skip this checkout.

def test_a_cached_baseline_of_another_plan_never_suppresses_the_checkout(rig):
    rec = _rec()
    other = ids.new_id('plan')
    r = _ok(_make(rig, _node(rec, at_base=1), cached=[dict(_failed(NAME1),
                                                           baseline=_cached(NAME1))],
                  cached_plan=other))
    v = _cur(r)
    assert len(rec['made']) == 1                             # the stale row did not leak
    assert _check(v, NAME1)['baseline']['label'] == ALSO     # fresh, from this run
    stale = next(x for x in r.rows() if x.plan_id == other)
    assert stale.checks[0]['baseline']['label'] == 'regressed'   # left as it was
    assert rec['dropped'] == [rec['made'][0][1]]


# 4 - worker.py:316-329: a checkout that dies with a non-OSError after leaving
# a partial tree (int10 #7's BaseException probe; the OSError case already has
# test_a_base_that_cannot_be_checked_out_is_said_and_changes_nothing). The
# `finally` cleanup still runs, and nothing is recorded on the way out.

def test_a_checkout_that_dies_after_creating_the_tree_still_cleans_up(rig):
    rec = _rec()

    def base_checkout(root, path, rev):
        rec['order'].append(('base_checkout', path))
        rec['made'].append((root, path, rev))
        os.makedirs(path)                                    # what the crash left
        with open(os.path.join(path, 'half.txt'), 'w') as f:
            f.write('half a tree')
        raise _Crash('interrupted with the tree half there')
    r = _make(rig, _node(rec, base_checkout=base_checkout))
    seen = r.spy()
    with pytest.raises(_Crash, match='half there'):
        r.worker.pass_once()
    tree = rec['made'][0][1]
    assert os.path.isdir(tree)                               # the partial tree is real
    assert rec['dropped'] == [tree]                          # the finally still ran
    assert [n for n, _k in seen] == ['start']                # never recorded
    v = _cur(r)
    assert v.state == 'RUNNING' and not v.checks
    assert r.task().state == 'VERIFYING' and r.plan() == []  # the row waits, not lost
    assert r.missions.fired == []
    assert rec['order'] == [('run_check', 'ws'), ('base_checkout', tree),
                            ('drop_checkout', tree)]


# 5 - worker.py:322-329: a base command that raises keeps the original error
# observable out of `pass_once` while the `finally` cleanup still runs. No
# existing test makes run_check raise at all; every one only returns results.

def test_a_command_that_raises_at_the_base_is_cleaned_up_and_stays_visible(rig):
    rec = _rec()

    def run_check(ws, argv, **kw):
        rec['order'].append(('run_check', ws))
        rec['runs'].append((ws, list(argv), kw.get('out_path')))
        if ws != 'ws':
            raise RuntimeError('the base runner died')
        return _result(exit_code=1)
    r = _make(rig, _node(rec, run_check=run_check))
    seen = r.spy()
    with pytest.raises(RuntimeError, match='the base runner died'):
        r.worker.pass_once()
    tree = rec['made'][0][1]
    assert rec['dropped'] == [tree]                          # cleanup after the raise
    assert rec['order'][-2:] == [('run_check', tree), ('drop_checkout', tree)]
    assert [n for n, _k in seen] == ['start']                # the original was not replaced
    v = _cur(r)
    assert v.state == 'RUNNING' and not v.checks
    assert r.task().state == 'VERIFYING' and r.plan() == []


# 6 - worker.py:327-330: `drop_checkout` raising while the original checkout
# failure is being turned into an error baseline cannot be swallowed: the
# worker records nothing and the failure leaves as a raised error, so the
# primary diagnostic survives for the next attempt (fx1718 #9's cleanup
# failure probe; the drop-False warning already has its own regression test).

def test_a_failing_cleanup_under_a_failed_checkout_is_never_swallowed(rig):
    rec = _rec()

    def base_checkout(root, path, rev):
        rec['order'].append(('base_checkout', path))
        rec['made'].append((root, path, rev))
        raise OSError('path too long')

    def drop_checkout(root, path):
        rec['order'].append(('drop_checkout', path))
        rec['dropped'].append(path)
        raise RuntimeError('the checkout would not go')
    r = _make(rig, _node(rec, base_checkout=base_checkout, drop_checkout=drop_checkout))
    seen = r.spy()
    with pytest.raises(RuntimeError, match='would not go'):
        r.worker.pass_once()
    tree = rec['made'][0][1]
    assert rec['dropped'] == [tree]                          # the attempt is a fact
    assert [n for n, _k in seen] == ['start']                # nothing recorded clean
    v = _cur(r)
    assert v.state == 'RUNNING' and not v.checks
    assert r.task().state == 'VERIFYING'
    assert rec['order'] == [('run_check', 'ws'), ('base_checkout', tree),
                            ('drop_checkout', tree)]


# 7 - worker.py:313-314: with every command of a two-command batch cached,
# `todo` is empty: no checkout AND no cleanup call at all. Closest existing
# test: test_one_base_run_per_plan_base_and_command(kept_at=BASE) - one
# command only, counting checkouts and never asserting the absence of cleanup.

def test_a_fully_cached_batch_never_makes_or_removes_a_checkout(rig):
    rec = _rec()
    cached = [dict(_failed(NAME1), baseline=_cached(NAME1, result='pass')),
              dict(_failed(NAME2), baseline=_cached(NAME2, result='fail'))]
    r = _ok(_make(rig, _node(rec), tests=(TEST1, TEST2), cached=cached))
    v = _cur(r)
    assert rec['made'] == [] and rec['dropped'] == []
    assert 'base_checkout' not in r.node.calls and 'drop_checkout' not in r.node.calls
    assert [ws for ws, _a, _o in rec['runs']] == ['ws', 'ws']    # only the candidate
    assert _check(v, NAME1)['baseline']['label'] == 'regressed'  # the cached ones, both
    assert _check(v, NAME2)['baseline']['label'] == ALSO
    assert not os.path.isdir(_base_dir(v.id))                    # no tree was carved


# 8 - worker.py:323-331: a base run that yields no checks at all cannot invent
# a baseline for the failed check it never explained. The seam is
# `evidence.run_commands` (the process spawner) for the base run only; the
# candidate run goes through the real one. No existing test empties `ran`.

def test_an_empty_base_result_adds_no_baseline_to_a_failing_check(rig, monkeypatch):
    rec = _rec()
    real, seen_base = evidence.run_commands, []

    def run_commands(node, workspace, cmds, *, verification_id, timeout_s,
                     verifier_version):
        if workspace != 'ws':
            seen_base.append((list(cmds), verification_id))
            return []                                   # the base run says nothing
        return real(node, workspace, cmds, verification_id=verification_id,
                    timeout_s=timeout_s, verifier_version=verifier_version)
    monkeypatch.setattr(evidence, 'run_commands', run_commands)
    r = _ok(_make(rig, _node(rec)))
    v = _cur(r)
    assert len(rec['made']) == 1 and rec['dropped'] == [rec['made'][0][1]]
    assert seen_base == [([( 'test', TEST1)], os.path.join(v.id, 'base'))]
    c = _check(v, NAME1)
    assert 'baseline' not in c and c['detail'] == 'exit 1'   # no 'regressed' invented
    assert v.state == 'FAILED'


# 9 - worker.py:315-329: two verification ids interleaved by a callback (no
# thread, no sleep): each checkout is under its own vid, each base log names
# only its own vid, and the inner cleanup completes before the outer one. No
# existing test runs two ids side by side.

def test_two_interleaved_verifications_keep_their_trees_and_order(rig):
    rec = _rec()
    holder, vid_b = {}, ids.new_id('verification')
    cmds = [('test', TEST1)]

    def run_check(ws, argv, **kw):
        rec['order'].append(('run_check', ws))
        rec['runs'].append((ws, list(argv), kw.get('out_path')))
        # the seam: while the first checkout is in use, a second row starts
        # its own base run (as an interleaved pass_once would), and finishes
        # before this one is allowed to continue
        if ws != 'ws' and not holder.get('b_ran'):
            holder['b_ran'] = True
            holder['out_b'] = r.worker._with_base(vid_b, m, r.plan_id, r.root, BASE,
                                                  cmds, [_failed(NAME1)],
                                                  V.VERIFIER_VERSION)
        return _result(exit_code=1)
    node = _node(rec, run_check=run_check)
    r = _make(rig, node)
    m, vid_a = r.mission(), ids.new_id('verification')
    out_a = r.worker._with_base(vid_a, m, r.plan_id, r.root, BASE, cmds,
                                [_failed(NAME1)], V.VERIFIER_VERSION)
    tree_a, tree_b = (os.path.join(_base_dir(vid), 'tree') for vid in (vid_a, vid_b))
    assert [p for _r, p, _v in rec['made']] == [tree_a, tree_b]   # distinct, per vid
    assert rec['dropped'] == [tree_b, tree_a]                 # inner first, outer last
    assert rec['order'] == [('base_checkout', tree_a), ('run_check', tree_a),
                            ('base_checkout', tree_b), ('run_check', tree_b),
                            ('drop_checkout', tree_b), ('drop_checkout', tree_a)]
    logs = [o for _w, _a, o in rec['runs']]
    assert len(logs) == 2 and logs[0] != logs[1]
    assert vid_a in logs[0] and vid_b not in logs[0]          # each log its own id
    assert vid_b in logs[1] and vid_a not in logs[1]
    assert out_a[0]['baseline']['label'] == ALSO == holder['out_b'][0]['baseline']['label']
    assert out_a[0]['result'] == 'fail'                       # advisory, verdict unmoved


# 10 - worker.py:337-339: the `if advisory:` True arc. Every existing test
# drives `git_diff` to '' so the advisory is None and only the skip arc runs;
# this is the append. The advisory sits between `changes` and the command
# checks, says pass, and moves neither result nor verdict.

def test_a_weakened_test_file_rides_the_row_as_advisory_evidence(rig):
    rec = _rec()

    def run_check(ws, argv, **kw):
        rec['order'].append(('run_check', ws))
        return _result(exit_code=0)                           # the test passes now
    node = _node(rec, git_numstat=_script([('1', '0', 'a.py')]),
                 git_diff=_script(WEAK_DIFF), run_check=run_check)
    r = _ok(_make(rig, node, kind='code_change'))
    v = _cur(r)
    assert [c['name'] for c in v.checks] == ['changes', evidence.WEAKENING, NAME1]
    adv = v.checks[1]
    assert adv['result'] == 'pass' and adv['findings'][0].startswith('assertions removed')
    assert v.state == 'PASSED' and r.task().state == 'SUCCEEDED'
    assert 'base_checkout' not in r.node.calls                # a pass costs no base run

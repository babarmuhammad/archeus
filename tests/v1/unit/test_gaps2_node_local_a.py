# ruff: noqa: F811  (the imported wire fixtures are taken as arguments)
"""T-1025: the highest-risk uncovered branches of archeus/node/local.py lines 181-407
(inclusive), faked at the same seams the wire tests use. No source file is edited, no
DLL, process or network is touched, and every OS call is the existing fake.

Selected branches (ranked by risk; see the report for the probe replacements):

1. `mxc_reconcile` must skip the journal of a launch that is still running
   (local.py:199-207) — a sweep that reads a live ownership record would report it.
2. `mxc_busy` must filter claims by the ledger key (local.py:194) — another ledger's
   claims must not make this one busy.
3. A held claim must read as busy under every spelling of one root
   (local.py:192-194 with local.py:373-381) — the key pair is computed twice.
4. `mxc_busy` must name exactly the running launches of one ledger
   (local.py:195-197) — the ended launch and the other-ledger launch stay out.
5. The start's grant re-check must cover the extra writable grants of the compiled
   policy (local.py:390-392) — a second name planted there after construction.
6. The claim is (ledger, journal), not (ledger, execution id)
   (local.py:373-381) — a pending generation must not block the next one.
7. A read-back without a journalled launch is refused (local.py:298-301) — only the
   watchdog side of that gate was tested.
8. A launch with neither a backend nor the native parts is refused
   (local.py:320) — the constructor gate itself.
9. A workload reader may stand in for the outcome callable at construction, and a
   reader that is not callable is refused (local.py:293-296).
10. A raw DEL (0x7F) in a grant path is percent-encoded (local.py:181-186) — only
    whitespace and `%` were proven.
"""

import os
import threading
import weakref
from types import SimpleNamespace

import pytest

from archeus.node import local, mxc, mxc_ledger as ledger_mod, staging

from .test_mxc_wire import args, journal_ops, native_parts, wire  # noqa: F401
from .test_mxc_wire_dupstart import OK, run  # noqa: F401


@pytest.fixture(autouse=True)
def _tables_of_ones_own(monkeypatch):
    """This file's launches never enter the process-wide claim and live tables, and
    no leftovers of other tests reach into these assertions."""
    monkeypatch.setattr(local, '_MXC_CLAIMS', set())
    monkeypatch.setattr(local, '_MXC_LIVE', weakref.WeakSet())


# ── 1: the restart sweep reads only journals nobody is writing ──

def test_a_restart_sweep_never_writes_over_a_running_launch(wire):
    """A journal of a live launch has intent and ownership and no completion: exactly
    what the sweep quarantines for a dead execution. Skipping it is the difference
    between reporting a running execution DEAD_CLEAN (readers believe the record) and
    never writing over it."""
    h = wire(**OK)
    h.launch.start(job=h.job)
    h.journal.journal.append('e9-p1', 'intent', requested_policy_digest='0' * 64,
                             planned=[], applied=[], observed={})
    results = local.mxc_reconcile(h.journal, lambda pid: None,
                                  lambda execution_id, owner: True)
    assert results == {'e9-p1': ledger_mod.DEAD_UNVERIFIED}    # the live journal is not read
    assert journal_ops(h.journal) == ['intent', 'ownership']   # nothing written over it
    assert journal_ops(h.journal, 'e9-p1') == ['intent', 'quarantine']
    h.launch.process.terminate()


# ── 2-4: what mxc_busy does and does not name ──

def test_only_the_claims_of_one_ledger_make_it_busy(tmp_path, monkeypatch):
    here, there = ledger_mod.Ledger(tmp_path / 'led'), ledger_mod.Ledger(tmp_path / 'else')
    key = lambda root: os.path.normcase(os.path.abspath(root))    # noqa: E731
    monkeypatch.setattr(local, '_MXC_CLAIMS', {(key(here.root), 'e1-p1'),
                                               (key(there.root), 'e9-p1')})
    assert local.mxc_busy(here) == {'e1-p1'}
    assert local.mxc_busy(there) == {'e9-p1'}
    monkeypatch.setattr(local, '_MXC_CLAIMS', set())
    assert local.mxc_busy(here) == set() and local.mxc_busy(there) == set()


def test_a_held_claim_is_busy_under_every_spelling_of_one_root(wire, tmp_path):
    """The claim stores the key MxcLaunch computed and `mxc_busy` computes its own:
    during a real start (the claim held, the launch not yet live) the journal must be
    busy for the ledger root as given, with a `..` segment and with a `.` segment."""
    h = wire(**OK)
    root = str(tmp_path / 'ledger')
    spellings = (h.journal,
                 SimpleNamespace(root=os.path.join(root, os.pardir, 'ledger')),
                 SimpleNamespace(root=os.path.join(root, os.curdir)))
    real = h.journal.journal.append
    seen = []

    def append(execution_id, op, **facts):
        if op == 'intent':            # here the claim is held and nothing is live yet
            seen.append([local.mxc_busy(ledger) for ledger in spellings])
        return real(execution_id, op, **facts)

    h.journal.journal.append = append
    h.launch.start(job=h.job)
    assert seen == [[{'e1-p1'}, {'e1-p1'}, {'e1-p1'}]]
    assert h.launch.wait() == 0
    assert [local.mxc_busy(ledger) for ledger in spellings] == [set(), set(), set()]


def test_busy_names_exactly_the_running_launches_of_one_ledger(wire, tmp_path):
    """The ended launch is still in the live table (its journal is on the same root);
    the launch on the other root is running. Neither may make this ledger busy."""
    ended = wire(**OK)
    ended.launch.start(job=ended.job)
    assert ended.launch.wait() == 0
    assert ended.launch.end_state['state'] == ledger_mod.DEAD_CLEAN
    live = wire(execution_id='e2', **OK)
    live.launch.start(job=live.job)
    elsewhere = wire(execution_id='e3', **OK)
    elsewhere.journal.journal.root = str(tmp_path / 'elsewhere')
    elsewhere.journal.journal.__init__(elsewhere.journal.journal.root)
    elsewhere.launch.start(job=elsewhere.job)
    assert local.mxc_busy(live.journal) == {'e2-p1'}
    live.launch.process.terminate()
    elsewhere.launch.process.terminate()


# ── 5-6: the grant re-check and the claim's own size ──

def test_a_second_name_in_an_extra_writable_grant_ends_the_start_before_the_create(
        args, tmp_path, wire):
    """Construction scanned the writable grant while it was clean; a second name
    planted afterwards must stop the start at its own gate: no intent, no create, no
    resume, no claim left behind — not the later ledger or transport checks."""
    extra = tmp_path / 'mailbox'
    extra.mkdir()
    outside = tmp_path / 'outside'
    outside.write_bytes(b'outside')
    args['writable'] = [str(extra)]
    h = wire(**OK)                                    # constructs clean
    assert h.launch.policy.raw['filesystem']['readwritePaths'] == \
        [os.path.normpath(args['workspace']), os.path.normpath(str(extra))]
    try:
        os.link(outside, extra / 'alias')
    except OSError:
        pytest.skip('no hardlinks on this volume')
    with pytest.raises(staging.StageError, match='links'):
        h.launch.start(job=h.job)
    assert h.api.events == [] and h.api.handles == {}
    assert journal_ops(h.journal) == [] and h.launch.process is None
    assert h.launch._started is False
    # a leaked claim would answer 'already being started' here, not 'links'
    with pytest.raises(staging.StageError, match='links'):
        h.launch.start(job=h.job)
    assert h.api.events == [] and journal_ops(h.journal) == []


def test_a_pending_earlier_generation_does_not_claim_the_next_one(wire):
    """The claim is (ledger, journal): while generation 1 of one execution is inside
    its intent write, generation 2 of the same execution id must start and finish.
    A claim keyed on the execution id would answer 'already being started'."""
    first, second = wire(**OK), wire(process_seq=2, **OK)
    writing, release = threading.Event(), threading.Event()
    real = first.journal.journal.append

    def append(execution_id, op, **facts):
        if op == 'intent':
            writing.set()
            release.wait(5)
        return real(execution_id, op, **facts)

    first.journal.journal.append = append
    outcomes = []
    thread = threading.Thread(target=run, args=(first.launch, first.job, outcomes))
    thread.start()
    assert writing.wait(5)
    second.launch.start(job=second.job)               # refuses only if claims key the id
    assert second.launch.wait() == 0
    release.set()
    thread.join(5)
    assert outcomes == ['started']
    assert first.api.events.count('create') == second.api.events.count('create') == 1
    assert first.api.events.count('resume') == second.api.events.count('resume') == 1
    assert journal_ops(first.journal) == ['intent', 'ownership']
    assert journal_ops(second.journal, 'e1-p2') == ['intent', 'ownership',
                                                    'disposal', 'completion']
    first.launch.process.terminate()


# ── 7-9: the constructor gates nobody walked up to ──

def test_a_read_back_needs_the_ledger_that_would_journal_it(args):
    """Only the watchdog side of this gate was tested; a read-back belongs in the
    ownership record, and a thin wrapper that journals nothing must be refused at
    construction, not silently ignore the reader it was handed."""
    with pytest.raises(staging.StageError, match='journalled launch'):
        local.MxcLaunch(backend=object(), outcome=lambda process: 0,
                        readback=lambda child: {}, **args)


def test_a_launch_with_neither_a_backend_nor_the_native_parts_is_refused(args):
    """The two ways to reach a transport, and neither given: without this gate the
    object would exist with backend None and fail only at start."""
    with pytest.raises(staging.StageError, match='explicitly injected backend'):
        local.MxcLaunch(outcome=lambda process: 0, **args)


class Compiler:
    """A backend that only compiles: nothing is staged, spawned or journalled."""
    compile_policy = staticmethod(mxc.compile_policy)


def test_a_workload_reader_may_stand_in_for_the_outcome_callable(args):
    """The reader replaces the outcome callable only if it is one: with a callable
    reader and expectation the launch constructs without any outcome callable, while
    a non-callable reader is refused by the same gate the missing expectation was
    tested against."""
    launch = local.MxcLaunch(backend=Compiler(), outcome=None,
                             workload_reader=lambda process: None,
                             workload_expected=lambda: {}, **args)
    assert launch.outcome is None and launch.workload_reader is not None
    assert launch.policy.raw['containment'] == 'processcontainer'
    assert launch._claim() is None
    with pytest.raises(staging.StageError, match='identity this launch issued'):
        local.MxcLaunch(backend=Compiler(), outcome=lambda process: 0,
                        workload_reader='not a reader',
                        workload_expected=lambda: {}, **args)
    with pytest.raises(staging.StageError, match='identity this launch issued'):
        local.MxcLaunch(backend=Compiler(), outcome=lambda process: 0,
                        workload_reader=lambda process: None,
                        workload_expected='not a callable', **args)


# ── 10: the resource id's own encoding ──

def test_a_raw_del_in_a_grant_path_is_percent_encoded_too():
    """The resource record refuses control characters, so a grant path carrying a raw
    DEL can only be named in the encoded form; only whitespace and `%` had a test."""
    assert local.mxc_resource_id('C:\\grant' + chr(127) + '\\x') == 'C:\\grant%007F\\x'
    encoded = local.mxc_resource_id(chr(9) + 'a' + chr(127) + '%b')
    assert encoded == '%0009a%007F%0025b'
    assert not any(ord(ch) < 32 or ord(ch) == 127 for ch in encoded)

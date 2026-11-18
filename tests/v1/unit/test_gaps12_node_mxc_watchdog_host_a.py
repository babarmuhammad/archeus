"""T-1442: the sentinel engage, the ownership check, the identity-bound kill gate and the host entry point
of `archeus/node/mxc_watchdog_host.py`, lines 187-236 (`_engage_sentinel`, `_ownership_problem`, `_kill`,
`run`, `main`).

Selected branches, ranked fail-closed first, then boundaries, then error paths:

 1. mxc_watchdog_host.py:195-201  _ownership_problem: an invalid read, or first two ops not exactly
                                  OWNED_OPS (a single record included), refuses before the pid check
 2. mxc_watchdog_host.py:199-200  _ownership_problem: a different (pid, create_time) is refused; the exact
                                  match returns None
 3. mxc_watchdog_host.py:203-207  _kill: a non-None ownership problem raises before terminate or the sentinel
 4. mxc_watchdog_host.py:208-209  _kill: the sentinel is engaged only when _core_seen is True
 5. mxc_watchdog_host.py:210     _kill: True only when terminate answers exactly True
 6. mxc_watchdog_host.py:187-193  _engage_sentinel: exactly True engages; 1, 'yes', None or an exception is
                                  'unverified'; a set sentinel is not engaged again
 7. mxc_watchdog_host.py:228-230  main: bindings None or a 'host' switch that is not True prints 'closed' and
                                  returns 2 without building a WatchdogHost
 8. mxc_watchdog_host.py:231-234  main: 'switches' is dropped from the kwargs; core is the argv pair; journals
                                  come from the Ledger
 9. mxc_watchdog_host.py:235-236  main exit code: FIRED, STOOD_DOWN and IDLE give 0, anything else 3
10. mxc_watchdog_host.py:212-216  run: the loop stops as soon as stop() is true, runs tick() then sleep(poll_s)
                                  per pass and returns report(); argparse refuses a missing required option

Closest existing tests: tests/v1/unit/test_mxc_watchdog_host.py (the host's tick and stop flow). Its lines
951-968 already cover main() refusing with bindings None (return 2) and the 0 and 3 exit codes, so probes 7
and 9 overlap it; the switches-stripping, the core and journals wiring, the sentinel read-back and the kill
gate are not covered there. Nothing before this file calls _engage_sentinel, _ownership_problem or _kill
with fakes for their collaborators.

Seams: WatchdogHost is built with its own constructor, which only stores its arguments; the ledger reader,
the heartbeat channel and the Ledger class are monkeypatched; WatchdogHost is replaced by a recording fake
for main(). No Windows process call, no real pid, no subprocess, no ledger file, no network, no user config.
"""

from dataclasses import fields
from types import SimpleNamespace

import pytest

from archeus.node import mxc_heartbeat, mxc_ledger, mxc_watchdog, mxc_watchdog_host as host_mod
from archeus.node.pv20_switches import Pv20Switches

OWNED = [{'op': 'intent', 'pid': 10, 'create_time': 20},
         {'op': 'ownership', 'pid': 11, 'create_time': 21}]
ON = Pv20Switches(**{f.name: True for f in fields(Pv20Switches)})
OFF = Pv20Switches()
JOB = {'execution_id': 'e1', 'job_ref': 'j1', 'pid': 11, 'create_time': 21}


def _host(**over):
    kw = dict(channel=SimpleNamespace(), clock=lambda: 0.0, deadline_s=1.0, core=(10, 20),
              identity_reader=lambda pid: 20, terminate=lambda pid, ct: True,
              engage_sentinel=lambda: True, journals=lambda: {'e1': 'J'})
    kw.update(over)
    return host_mod.WatchdogHost(**kw)


def _ledger(monkeypatch, records, invalid=()):
    monkeypatch.setattr(mxc_ledger, 'read_records', lambda journal, name: (records, list(invalid)))


@pytest.mark.parametrize('records, invalid', [
    (OWNED, ['torn line']),
    ([OWNED[1]], []),
    ([OWNED[1], OWNED[0]], []),
])
def test_ownership_refuses_a_journal_without_the_open_pair(monkeypatch, records, invalid):
    _ledger(monkeypatch, records, invalid)
    assert _host()._ownership_problem('e1', 11, 21) == 'the journal holds no open ownership record'


def test_ownership_names_another_process_and_accepts_the_exact_match(monkeypatch):
    _ledger(monkeypatch, OWNED)
    assert _host()._ownership_problem('e1', 12, 21) == 'the ownership record names another process'
    assert _host()._ownership_problem('e1', 11, 22) == 'the ownership record names another process'
    assert _host()._ownership_problem('e1', 11, 21) is None


def _kill_host(monkeypatch, *, problem=None, core_seen=True, answer=True):
    log = []
    host = _host(terminate=lambda pid, ct: log.append(('terminate', pid, ct)) or answer,
                 engage_sentinel=lambda: log.append('engage') or True)
    host.dog = SimpleNamespace(jobs=[JOB])
    host._core_seen = core_seen
    monkeypatch.setattr(host, '_ownership_problem', lambda name, pid, ct: problem)
    return host, log


def test_kill_refuses_a_foreign_record_before_terminate_or_sentinel(monkeypatch):
    host, log = _kill_host(monkeypatch, problem='the ownership record names another process')
    with pytest.raises(ValueError, match='names another process'):
        host._kill('j1')
    assert log == []


@pytest.mark.parametrize('core_seen, engaged', [(True, 1), (False, 0), (None, 0)])
def test_kill_engages_the_sentinel_only_while_core_is_seen_alive(monkeypatch, core_seen, engaged):
    host, log = _kill_host(monkeypatch, core_seen=core_seen)
    assert host._kill('j1') is True
    assert log.count('engage') == engaged
    assert log[-1] == ('terminate', 11, 21)


@pytest.mark.parametrize('answer, expected', [(True, True), (1, False), ('yes', False), (None, False)])
def test_kill_is_true_only_for_terminate_answering_exactly_true(monkeypatch, answer, expected):
    host, _ = _kill_host(monkeypatch, core_seen=False, answer=answer)
    assert host._kill('j1') is expected


@pytest.mark.parametrize('outcome, expected', [
    (True, 'engaged'),
    (1, 'unverified'),
    ('yes', 'unverified'),
    (None, 'unverified'),
    (OSError('no sentinel'), 'unverified'),
])
def test_engage_sentinel_reads_back_only_an_exact_true(outcome, expected):
    calls = []

    def engage():
        calls.append(1)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome
    host = _host(engage_sentinel=engage)
    host._engage_sentinel()
    host._engage_sentinel()
    assert host.sentinel == expected
    assert calls == [1]


@pytest.mark.parametrize('bindings', [None, {'switches': None}, {'switches': OFF}])
def test_main_refuses_when_the_host_is_closed_or_not_switched_on(monkeypatch, capsys, bindings):
    built = []
    monkeypatch.setattr(host_mod, 'WatchdogHost', lambda **kw: built.append(kw))
    assert host_mod.main(_argv(), bindings=bindings) == 2
    assert built == []
    assert 'the watchdog host is closed' in capsys.readouterr().err


def _argv():
    args = {'--root': 'r', '--ledger': 'l.jsonl', '--core-pid': '10', '--core-create-time': '20',
            '--deadline-s': '1.5', '--poll-s': '0.1'}
    return [item for pair in args.items() for item in pair]


def test_main_passes_bindings_through_and_builds_core_identity_and_journals(monkeypatch):
    built, channels, ledgers = [], [], []

    class FakeChannel:
        def __init__(self, root):
            channels.append(root)

    class FakeLedger:
        def __init__(self, path):
            ledgers.append(path)
            self.journals = {'journals': path}

    class FakeHost:
        def __init__(self, **kw):
            built.append(kw)

        def run(self, poll_s):
            built.append(poll_s)
            return {'state': mxc_watchdog.FIRED}
    monkeypatch.setattr(mxc_heartbeat, 'Channel', FakeChannel)
    monkeypatch.setattr(mxc_ledger, 'Ledger', FakeLedger)
    monkeypatch.setattr(host_mod, 'WatchdogHost', FakeHost)
    identity, terminate, sentinel = object(), object(), object()
    bindings = {'switches': ON, 'clock': len, 'identity_reader': identity,
                'terminate': terminate, 'engage_sentinel': sentinel}
    assert host_mod.main(_argv(), bindings=bindings) == 0
    kwargs, poll_s = built
    assert poll_s == 0.1
    assert 'switches' not in kwargs
    assert kwargs['clock'] is len and kwargs['identity_reader'] is identity
    assert kwargs['terminate'] is terminate and kwargs['engage_sentinel'] is sentinel
    assert kwargs['core'] == (10, 20) and kwargs['deadline_s'] == 1.5
    assert kwargs['journals'] == {'journals': 'l.jsonl'}
    assert channels == ['r'] and ledgers == ['l.jsonl']


@pytest.mark.parametrize('state, code', [
    (mxc_watchdog.FIRED, 0),
    (mxc_watchdog.STOOD_DOWN, 0),
    (host_mod.IDLE, 0),
    (mxc_watchdog.UNCERTAIN, 3),
])
def test_main_exit_code_follows_the_final_state(monkeypatch, state, code):
    class FakeHost:
        def __init__(self, **kw):
            pass

        def run(self, poll_s):
            return {'state': state}
    monkeypatch.setattr(host_mod, 'WatchdogHost', FakeHost)
    monkeypatch.setattr(mxc_heartbeat, 'Channel', lambda root: None)
    monkeypatch.setattr(mxc_ledger, 'Ledger', lambda path: SimpleNamespace(journals={}))
    assert host_mod.main(_argv(), bindings={'switches': ON}) == code


def test_run_stops_when_asked_and_ticks_then_sleeps_per_pass(monkeypatch):
    host = _host()
    events, answers = [], iter([False, False, True])
    monkeypatch.setattr(host, 'done', lambda: False)
    monkeypatch.setattr(host, 'tick', lambda: events.append('tick'))
    monkeypatch.setattr(host, 'report', lambda: {'state': 'IDLE'})
    result = host.run(0.5, sleep=lambda s: events.append(('sleep', s)),
                      stop=lambda: next(answers))
    assert result == {'state': 'IDLE'}
    assert events == ['tick', ('sleep', 0.5), 'tick', ('sleep', 0.5)]


def test_main_refuses_a_missing_required_option_with_exit_code_2(capsys):
    argv = [item for item in _argv() if item not in ('--ledger', 'l.jsonl')]
    with pytest.raises(SystemExit) as caught:
        host_mod.main(argv, bindings={'switches': ON})
    assert caught.value.code == 2
    assert '--ledger' in capsys.readouterr().err

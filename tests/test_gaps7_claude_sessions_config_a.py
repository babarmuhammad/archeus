"""T-1302 — close the highest-risk test gaps in claude_sessions/config.py,
lines 763-830 inclusive (tip 53865a4a of pv20-fx79n; re-located by reading the
source, the card's line numbers came from an older tip).

Slice: `_REPLACE_LOCK` / `_REPLACE_BUDGET`, `write_atomic()` replace loop
(deadline, backoff, contention, cleanup) and `write_json_atomic()`.

Selected branches, denial/fail-closed first, then boundaries, then error paths:

 1. :808  budget is 2.0 s; five refusals are not enough, the sixth and seventh
          are retried until success before the deadline
 2. :815  at exactly the deadline a refusal raises, the old target survives,
          the owned temp is removed and no sleep is taken
 3. :817  backoff is 0.01 doubling and capped at 0.1, observed through a fake
          sleep; no real sleep
 4. :814  a replace failure that is not PermissionError is not retried
 5. :807  two writers of different paths serialize on the one replace lock
 6. :808  the budget starts after the lock is acquired, not while waiting for it
 7. :805  both writers finish their temps before either enters replace; the
          temp names differ
 8. :812  two writers of one target both succeed in turn; the final bytes are
          one complete payload
 9. :819  after the first writer exhausts its budget the lock is released and
          the second writer succeeds
10. :830  write_json_atomic retries keep the original file and the mode, and the
          JSON is serialized once

Closest existing tests (tests/test_encoding_and_atomicity.py): the refused-for-
ever budget, the seven-refusal retry and concurrent same-path writers. Those
assert the outcome only; these probes pin the deadline boundary, the backoff
sequence, the lock hold order and the serialization count.

No real sleep, no real clock: `config.time` is replaced by a fake clock,
`os.replace` is wrapped by the test, and every thread is joined with a bound.
"""

import json
import os
import threading
import time as _real_time

import pytest

from claude_sessions import config as _c


class _Clock:
    def __init__(self, now=0.0):
        self.now = now
        self.sleeps = []
        self.reads = 0

    def monotonic(self):
        self.reads += 1
        return self.now

    def sleep(self, s):
        self.sleeps.append(s)
        self.now += s


class _ClockAt:
    """Returns `first` on the first read, then `later` on every read after."""

    def __init__(self, first, later):
        self.first = first
        self.later = later
        self.reads = 0

    def monotonic(self):
        self.reads += 1
        return self.first if self.reads == 1 else self.later

    def sleep(self, s):
        raise AssertionError('no sleep may follow a refusal at the deadline')


class _Ticking:
    """Every monotonic read moves the clock on, so a budget of two seconds is
    spent after two reads."""

    def __init__(self, step):
        self.step = step
        self.now = 0.0

    def monotonic(self):
        self.now += self.step
        return self.now

    def sleep(self, s):
        self.now += s


def _temps(d):
    return sorted(f.name for f in d.iterdir() if f.name.endswith('.tmp'))


def _refuse(dst):
    return PermissionError(13, 'Access is denied', dst)


def test_budget_is_two_seconds_and_six_refusals_are_retried_to_success(tmp_path, monkeypatch):
    assert _c._REPLACE_BUDGET == 2.0
    p = tmp_path / 'settings.json'
    p.write_text('{"old": true}', encoding='utf-8')
    clock = _Clock()
    monkeypatch.setattr(_c, 'time', clock)
    real_replace = os.replace
    calls = []

    def refuse_six(src, dst):
        calls.append(dst)
        if len(calls) <= 6:
            raise _refuse(dst)
        return real_replace(src, dst)

    monkeypatch.setattr(os, 'replace', refuse_six)
    assert _c.write_json_atomic(str(p), {'new': True}) is True
    assert len(calls) == 7
    assert json.loads(p.read_text(encoding='utf-8')) == {'new': True}
    assert _temps(tmp_path) == []


def test_a_refusal_at_exactly_the_deadline_gives_up_and_cleans_up(tmp_path, monkeypatch):
    p = tmp_path / 'settings.json'
    p.write_text('{"old": true}', encoding='utf-8')
    clock = _ClockAt(first=0.0, later=_c._REPLACE_BUDGET)
    monkeypatch.setattr(_c, 'time', clock)
    calls = []

    def refused(src, dst):
        calls.append(src)
        raise _refuse(dst)

    monkeypatch.setattr(os, 'replace', refused)
    assert _c.write_json_atomic(str(p), {'new': True}) is False
    assert len(calls) == 1
    assert json.loads(p.read_text(encoding='utf-8')) == {'old': True}
    assert [f.name for f in tmp_path.iterdir()] == ['settings.json']


def test_backoff_doubles_from_a_centisecond_and_caps_at_a_tenth_second(tmp_path, monkeypatch):
    p = tmp_path / 'settings.json'
    clock = _Clock()
    monkeypatch.setattr(_c, 'time', clock)
    real_replace = os.replace
    calls = []

    def refuse_six(src, dst):
        calls.append(dst)
        if len(calls) <= 6:
            raise _refuse(dst)
        return real_replace(src, dst)

    monkeypatch.setattr(os, 'replace', refuse_six)
    assert _c.write_json_atomic(str(p), {'k': 1}) is True
    assert clock.sleeps == pytest.approx([0.01, 0.02, 0.04, 0.08, 0.1, 0.1])


def test_a_replace_failure_that_is_not_a_refusal_is_not_retried(tmp_path, monkeypatch):
    p = tmp_path / 'settings.json'
    p.write_text('{"old": true}', encoding='utf-8')
    clock = _Clock()
    monkeypatch.setattr(_c, 'time', clock)
    calls = []

    def disk_gone(src, dst):
        calls.append(src)
        raise OSError('simulated full disk on replace')

    monkeypatch.setattr(os, 'replace', disk_gone)
    assert _c.write_json_atomic(str(p), {'new': True}) is False
    assert len(calls) == 1
    assert clock.sleeps == []
    assert json.loads(p.read_text(encoding='utf-8')) == {'old': True}
    assert [f.name for f in tmp_path.iterdir()] == ['settings.json']


def _contend(tmp_path, monkeypatch):
    """Writer A holds the replace lock inside a blocked replace; writer B writes
    its own temp and then waits for the lock. Returns what was observed while A
    still held it."""
    a = str(tmp_path / 'a.json')
    b = str(tmp_path / 'b.json')
    entered_a = threading.Event()
    release_a = threading.Event()
    real_replace = os.replace
    order = []

    def replace(src, dst):
        order.append(dst)
        if dst == a:
            entered_a.set()
            assert release_a.wait(5)
        return real_replace(src, dst)

    monkeypatch.setattr(os, 'replace', replace)
    results = {}
    ta = threading.Thread(target=lambda: results.__setitem__('a', _c.write_atomic(a, 'A' * 10)))
    tb = threading.Thread(target=lambda: results.__setitem__('b', _c.write_atomic(b, 'B' * 10)))
    ta.start()
    try:
        assert entered_a.wait(5)
        tb.start()
        deadline = _real_time.monotonic() + 5
        while len(_temps(tmp_path)) < 2 and _real_time.monotonic() < deadline:
            _real_time.sleep(0.01)
        observed = {'order_while_held': list(order)}
        observed['temps_while_held'] = _temps(tmp_path)
        observed['b_replace_entered_while_held'] = b in order
    finally:
        release_a.set()
        ta.join(5)
        tb.join(5)
    assert not ta.is_alive() and not tb.is_alive()
    return results, order, observed


def test_two_writers_of_different_paths_share_one_replace_lock(tmp_path, monkeypatch):
    results, order, observed = _contend(tmp_path, monkeypatch)
    assert observed['b_replace_entered_while_held'] is False
    assert order == [str(tmp_path / 'a.json'), str(tmp_path / 'b.json')]
    assert results == {'a': True, 'b': True}


def test_both_writers_finish_their_own_temp_before_either_replaces(tmp_path, monkeypatch):
    results, order, observed = _contend(tmp_path, monkeypatch)
    temps = observed['temps_while_held']
    assert len(temps) == 2
    assert len(set(temps)) == 2
    assert observed['order_while_held'] == [str(tmp_path / 'a.json')]
    assert results == {'a': True, 'b': True}


def test_two_writers_of_one_target_both_succeed_and_never_tear(tmp_path, monkeypatch):
    target = str(tmp_path / 'settings.json')
    payloads = {'x': 'X' * 200_000, 'y': 'Y' * 200_000}
    results = {}

    def run(key):
        results[key] = _c.write_atomic(target, payloads[key])

    threads = [threading.Thread(target=run, args=(k,)) for k in payloads]
    for t in threads:
        t.start()
    for t in threads:
        t.join(10)
    assert not any(t.is_alive() for t in threads)
    assert results == {'x': True, 'y': True}
    with open(target, encoding='utf-8', newline='') as f:
        final = f.read()
    assert final in payloads.values()
    assert _temps(tmp_path) == []


def test_a_writer_that_exhausts_its_budget_releases_the_lock_for_the_next(tmp_path, monkeypatch):
    a = str(tmp_path / 'a.json')
    b = str(tmp_path / 'b.json')
    clock = _Ticking(step=3.0)
    monkeypatch.setattr(_c, 'time', clock)
    real_replace = os.replace

    def replace(src, dst):
        if dst == a:
            raise _refuse(dst)
        return real_replace(src, dst)

    monkeypatch.setattr(os, 'replace', replace)
    assert _c.write_atomic(a, 'A') is False
    assert _c._REPLACE_LOCK.acquire(timeout=1)
    _c._REPLACE_LOCK.release()

    results = {}
    tb = threading.Thread(target=lambda: results.__setitem__('b', _c.write_atomic(b, 'B')))
    tb.start()
    tb.join(5)
    assert not tb.is_alive()
    assert results == {'b': True}
    assert (tmp_path / 'b.json').read_text(encoding='utf-8') == 'B'
    assert _temps(tmp_path) == []


def test_the_budget_starts_once_the_lock_is_held_not_while_waiting_for_it(tmp_path, monkeypatch):
    a = str(tmp_path / 'a.json')
    b = str(tmp_path / 'b.json')
    clock = _Clock()
    monkeypatch.setattr(_c, 'time', clock)
    entered_a = threading.Event()
    release_a = threading.Event()
    real_replace = os.replace
    refused_b = []

    def replace(src, dst):
        if dst == a:
            entered_a.set()
            assert release_a.wait(5)
        elif dst == b and not refused_b:
            refused_b.append(dst)
            raise _refuse(dst)
        return real_replace(src, dst)

    monkeypatch.setattr(os, 'replace', replace)
    results = {}
    ta = threading.Thread(target=lambda: results.__setitem__('a', _c.write_atomic(a, 'A')))
    tb = threading.Thread(target=lambda: results.__setitem__('b', _c.write_atomic(b, 'B')))
    ta.start()
    try:
        assert entered_a.wait(5)
        tb.start()
        _real_time.sleep(0.1)
        clock.now = 10.0
    finally:
        release_a.set()
        ta.join(5)
        tb.join(5)
    assert not ta.is_alive() and not tb.is_alive()
    assert results == {'a': True, 'b': True}
    assert clock.sleeps == pytest.approx([0.01])


def test_json_retries_keep_the_old_file_and_mode_and_serialize_once(tmp_path, monkeypatch):
    p = tmp_path / 'settings.json'
    p.write_text('{"old": true}', encoding='utf-8')
    clock = _Clock()
    monkeypatch.setattr(_c, 'time', clock)
    real_replace = os.replace
    real_open = os.open
    real_dumps = json.dumps
    dumps_calls = []
    modes = []
    seen_old = []
    refusals = []

    def counting_dumps(*a, **k):
        dumps_calls.append(1)
        return real_dumps(*a, **k)

    def recording_open(path, flags, mode=0o777, *a, **k):
        if flags & os.O_EXCL:
            modes.append(mode)
        return real_open(path, flags, mode, *a, **k)

    def refuse_twice(src, dst):
        if len(refusals) < 2:
            refusals.append(src)
            seen_old.append(p.read_text(encoding='utf-8'))
            raise _refuse(dst)
        return real_replace(src, dst)

    monkeypatch.setattr(json, 'dumps', counting_dumps)
    monkeypatch.setattr(os, 'open', recording_open)
    monkeypatch.setattr(os, 'replace', refuse_twice)
    obj = {'new': True, 'n': [1, 2]}
    assert _c.write_json_atomic(str(p), obj, indent=2, mode=0o600) is True
    assert len(dumps_calls) == 1
    assert len(refusals) == 2
    assert seen_old == ['{"old": true}', '{"old": true}']
    assert modes == [0o600]
    assert p.read_text(encoding='utf-8') == real_dumps(obj, indent=2)
    assert _temps(tmp_path) == []

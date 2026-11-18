"""T-1016: highest-risk uncovered branches of archeus/node/mxc_heartbeat.py lines 1-165.

Fail-closed and denial paths first, then boundaries, then error paths. All OS calls
go through the seams the existing tests use (hb.config.write_atomic, files under
tmp_path only); no real DLL, process, network or sleep. Platform-neutral: no Windows
API, no path/case assumptions, no localized error text. Style follows
tests/v1/unit/test_gaps_node_mxc_ledger.py; the coverage baseline read first is
tests/v1/unit/test_mxc_watchdog_host.py.

Selected branches (source line: gap -> test), after replacing already-covered or
inapplicable probes from the card's list (see the report for the evidence):
 1. mxc_heartbeat.py:72-73  write_atomic returns falsy -> OSError, nothing published
 2. mxc_heartbeat.py:71     non-finite status refused before the atomic replace
 3. mxc_heartbeat.py:40     non-finite channel value refused, zero bytes appended
 4. mxc_heartbeat.py:49-58  a read error that is not "missing" is never read as empty
 5. mxc_heartbeat.py:61-67  a damaged line pins the reader offset (no guessing past)
 6. mxc_heartbeat.py:133-136 a malformed job is refused before the host is consulted
 7. mxc_heartbeat.py:128-129 age exactly max_age_s is fresh; more, or negative, is stale
 8. mxc_heartbeat.py:137-138 STOOD_DOWN is in the set of states that may still register
 9. mxc_heartbeat.py:149-152 many refusals report the lowest id deterministically
10. mxc_heartbeat.py:100-103 an integer clock beats and is clamped to never go back
"""

import os
from types import SimpleNamespace

import pytest

from archeus.node import mxc_heartbeat as hb
from archeus.node import mxc_watchdog as wd

PID, CREATE_TIME = 41, 900


class Clock:
    def __init__(self, now=100.0):
        self.now = now

    def __call__(self):
        return self.now


@pytest.fixture
def channel(tmp_path, monkeypatch):
    monkeypatch.setattr(hb, 'HEARTBEAT_ENABLED', True)
    return hb.Channel(tmp_path / 'chan')


def job(name='e1-p1'):
    return {'execution_id': name, 'pid': PID, 'create_time': CREATE_TIME,
            'job_ref': 'handle'}


def proxy_for(channel, clock, max_age_s=5.0):
    return hb.WatchdogProxy(channel, clock, max_age_s=max_age_s)


def publish(channel, clock, *, state='IDLE', at=None, recorded=(), rejected=None):
    channel.write_status({'at': clock.now if at is None else at, 'state': state,
                          'recorded': list(recorded),
                          'rejected': {} if rejected is None else rejected})


def raw(channel):
    if not os.path.exists(channel.path):
        return b''
    with open(channel.path, 'rb') as stream:
        return stream.read()


# ── fail-closed and denial ──

def test_a_failed_atomic_status_write_raises_and_publishes_nothing(channel, monkeypatch):
    # mxc_heartbeat.py:72-73: a falsy write_atomic must raise, never publish silently
    # (a silent failure would leave the previous, possibly stale, status authoritative).
    seen = []

    def fake_write_atomic(path, text, mode=None):
        seen.append(SimpleNamespace(path=path, text=text, mode=mode))
        return False

    monkeypatch.setattr(hb.config, 'write_atomic', fake_write_atomic)
    with pytest.raises(OSError, match='host status not written'):
        channel.write_status({'state': 'ARMED'})
    assert [call.path for call in seen] == [channel.status_path]
    assert seen[0].mode == 0o600
    assert not os.path.exists(channel.status_path)


def test_a_nan_status_is_refused_before_the_replace(channel, monkeypatch):
    # mxc_heartbeat.py:71: allow_nan=False must fire before any atomic replace, so a
    # non-finite timestamp can never land in the file the proxy reads as authority.
    calls = []
    monkeypatch.setattr(hb.config, 'write_atomic',
                        lambda path, text, mode=None: calls.append(text) or True)
    with pytest.raises(ValueError):
        channel.write_status({'at': float('nan'), 'state': 'ARMED', 'recorded': [],
                              'rejected': {}})
    assert calls == []
    assert not os.path.exists(channel.status_path)


def test_a_nonfinite_beat_value_never_reaches_the_channel(channel):
    # mxc_heartbeat.py:40: allow_nan=False on append; a NaN/Infinity sent_at that
    # reached the line file would poison the host's clock-window check.
    with pytest.raises(ValueError):
        channel.append({'kind': 'beat', 'seq': 1, 'sent_at': float('nan')})
    with pytest.raises(ValueError):
        channel.append({'kind': 'beat', 'seq': 2, 'sent_at': float('inf')})
    assert raw(channel) == b''
    assert channel.read() == []


def test_an_unreadable_channel_file_is_never_read_as_empty(channel):
    # mxc_heartbeat.py:49-58: only FileNotFoundError is special-cased; any other read
    # error must propagate, because an unreadable channel is not a silent channel.
    os.mkdir(channel.path)
    with pytest.raises(OSError) as excinfo:
        channel.read()
    assert not isinstance(excinfo.value, FileNotFoundError)


def test_a_damaged_line_pins_the_reader_offset(channel):
    # mxc_heartbeat.py:61-67: the offset advances only after every line parses; a
    # reader that advanced early would deliver the good lines around the damage once
    # and skip the damage forever.
    channel.append({'kind': 'beat', 'seq': 1, 'sent_at': 1.0})
    with open(channel.path, 'ab') as stream:
        stream.write(b'{"kind":"beat","seq":1}\n')
    with pytest.raises(ValueError, match='malformed channel message'):
        channel.read()
    channel.append({'kind': 'beat', 'seq': 2, 'sent_at': 2.0})
    with pytest.raises(ValueError, match='malformed channel message'):
        channel.read()


def test_a_malformed_job_is_refused_before_the_host_is_consulted(channel):
    # mxc_heartbeat.py:133-136: the job check runs before _status, so a malformed job
    # raises its own problem even when the status would also fail, and nothing is
    # written. Swapping the order would report 'the host status is unreadable'.
    clock = Clock()
    proxy = proxy_for(channel, clock)
    bad = dict(job(), pid=0)
    with pytest.raises(wd.WatchdogUnavailable, match='invalid pid'):
        proxy.record(bad)
    assert channel.read() == []
    assert proxy.registered == set()


# ── boundaries ──

def test_a_status_exactly_at_the_age_bound_is_fresh_and_beyond_it_is_stale(channel):
    # mxc_heartbeat.py:128-129: 0 <= age <= max_age_s, both bounds inclusive on the
    # fresh side only; age == max_age_s is fresh, age > max_age_s and age < 0 are stale.
    clock = Clock(100.0)
    publish(channel, clock, at=100.0)
    proxy = proxy_for(channel, clock, max_age_s=5.0)
    clock.now = 105.0
    assert proxy.record(job('e1-p1')) is True
    clock.now = 105.5
    with pytest.raises(wd.WatchdogUnavailable, match='stale'):
        proxy.record(job('e2-p1'))
    clock.now = 99.0
    with pytest.raises(wd.WatchdogUnavailable, match='stale'):
        proxy.record(job('e3-p1'))
    assert [m['execution_id'] for m in channel.read()] == ['e1-p1']


def test_a_stood_down_host_still_accepts_a_new_registration(channel):
    # mxc_heartbeat.py:137-138: STOOD_DOWN is in the acceptable set, so the next job
    # can register after a retired watch; dropping it from the tuple refuses it.
    clock = Clock()
    publish(channel, clock, state=wd.STOOD_DOWN, recorded=['old-p1'])
    proxy = proxy_for(channel, clock)
    assert proxy.record(job('new-p1')) is True
    assert channel.read() == [{'kind': 'register', 'execution_id': 'new-p1', 'pid': PID,
                               'create_time': CREATE_TIME}]


def test_an_integer_clock_beats_and_never_goes_backwards(channel):
    # mxc_heartbeat.py:100-103: the type check accepts int as well as float (ints skip
    # the isfinite leg), and the clamp keeps a stepped-back clock monotone.
    clock = Clock(7)
    sender = hb.HeartbeatSender(channel, clock)
    sender.beat()
    clock.now = 5
    sender.beat()
    clock.now = 9
    sender.beat()
    beats = channel.read()
    assert [b['seq'] for b in beats] == [1, 2, 3]
    assert [b['sent_at'] for b in beats] == [7, 7, 9]


# ── error paths ──

def test_the_first_refusal_reported_is_the_lowest_refused_id(channel):
    # mxc_heartbeat.py:149-152: with several refused executions the reason must name
    # sorted(refused)[0]; taking the last (or an unsorted pick) misreports which
    # launch was refused and is not reproducible.
    clock = Clock()
    publish(channel, clock, state=wd.ARMED)
    proxy = proxy_for(channel, clock)
    for name in ('e9-p1', 'e2-p1', 'e5-p1'):
        assert proxy.record(job(name)) is True
    publish(channel, clock, state=wd.ARMED,
            recorded=['e2-p1', 'e5-p1', 'e9-p1'],
            rejected={'e9-p1': 'gone', 'e2-p1': 'no journal', 'e5-p1': 'busy'})
    report = proxy.report()
    assert report['state'] == wd.UNCERTAIN
    assert report['reason'] == 'the host refused e2-p1: no journal'
    assert report['recorded'] == ['e2-p1', 'e5-p1', 'e9-p1']

"""T-1284: claude_sessions/rotate.py:188-273 (rotation candidates, sticky election,
offer policy gates, cool-down stamp and launch replay); candidate gaps, not coverage.

Ranked final probes (denial/fail-closed first, then boundaries, then error paths):
1  :245 test_disabled_policy_touches_nothing
2  :213 test_sticky_only_while_enabled_and_unspent
3  :215 test_no_eligible_alternative_returns_resolved_current
4  :198 test_candidates_drops_spent_keeps_headroom_order_and_exclude
5  :253 test_repeated_sid_in_cooldown_never_stamps_notifies_or_launches
6  :256 test_stamp_precedes_auto_launch_so_failed_launch_not_duplicated
7  :258 test_ask_mode_notifies_and_logs_never_launches
8  :268 test_failed_auto_launch_keeps_failure_result
   :270 test_failed_launch_title_does_not_claim_success            (strict xfail)
9  :253 test_simultaneous_same_sid_offers_launch_once              (strict xfail)
10 :269 test_retry_after_notify_failure_does_not_relaunch

Seams: quota.headroom / offered_recently / mark_offered, rotate.enabled / hands_off /
is_enabled / spent / next_account / name_of / _notify / _log / note / continue_session,
and config.resolve_config_dir (identity over synthetic paths). candidates() and
elect() run for real over the faked headroom. No sockets, subprocesses or home reads.
"""

import threading
from types import SimpleNamespace

import pytest

from claude_sessions import config as _c
from claude_sessions import quota
from claude_sessions import rotate


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    monkeypatch.setattr(_c, 'settings_file', str(tmp_path / 'archeus.json'))
    monkeypatch.setattr(_c, 'resolve_config_dir',
                        lambda cfgdir=None: cfgdir or '/synthetic/default')


def _rig(monkeypatch):
    r = SimpleNamespace(
        calls=[], launches=[], notes_sent=[], stamps=set(), spent_set=set(),
        is_enabled_map={}, headroom_list=[], next_to='/s/b', policy_on=True,
        hands=False, continue_result=(True, ''), notify_error=None,
    )

    def record(*entry):
        r.calls.append(entry)

    def notify(title, message):
        record('notify')
        r.notes_sent.append((title, message))
        if r.notify_error is not None:
            raise r.notify_error

    def continue_session(path, transcript, to=None, encoded=None):
        record('continue')
        r.launches.append(to)
        return r.continue_result

    def mark_offered(sid):
        record('mark', sid)
        r.stamps.add(sid)
        return True

    def headroom(exclude=None):
        record('headroom', exclude)
        return list(r.headroom_list)

    monkeypatch.setattr(rotate, 'enabled', lambda: r.policy_on)
    monkeypatch.setattr(rotate, 'hands_off', lambda: r.hands)
    monkeypatch.setattr(rotate, 'is_enabled', lambda cfgdir=None: r.is_enabled_map.get(cfgdir, True))
    monkeypatch.setattr(rotate, 'spent', lambda cfgdir=None: cfgdir in r.spent_set)
    monkeypatch.setattr(rotate, 'next_account', lambda exclude=None: (record('next'), r.next_to)[1])
    monkeypatch.setattr(rotate, 'name_of',
                        lambda cfgdir=None: {'/s/b': 'acct-b', '/s/c': 'acct-c'}.get(cfgdir, 'acct-a'))
    monkeypatch.setattr(rotate, '_notify', notify)
    monkeypatch.setattr(rotate, '_log', lambda msg, why='': record('log'))
    monkeypatch.setattr(rotate, 'note', lambda frm, to, why='': record('note', frm, to))
    monkeypatch.setattr(rotate, 'continue_session', continue_session)
    monkeypatch.setattr(quota, 'headroom', headroom)
    monkeypatch.setattr(quota, 'offered_recently', lambda sid: sid in r.stamps)
    monkeypatch.setattr(quota, 'mark_offered', mark_offered)
    return r


def test_disabled_policy_touches_nothing(monkeypatch):
    r = _rig(monkeypatch)
    r.policy_on = False
    r.headroom_list = [('acct-b', '/s/b', 0.0)]

    assert rotate.offer('/s/t', '', 'S1') == (False, '')
    assert rotate.elect('/s/a') == '/s/a'

    assert r.calls == []
    assert r.launches == []


@pytest.mark.parametrize('is_enabled, spent, expected', [
    (True, False, '/s/a'),
    (False, False, '/s/b'),
    (True, True, '/s/b'),
])
def test_sticky_only_while_enabled_and_unspent(monkeypatch, is_enabled, spent, expected):
    r = _rig(monkeypatch)
    r.is_enabled_map = {'/s/a': is_enabled}
    r.spent_set = {'/s/a'} if spent else set()
    r.headroom_list = [('acct-b', '/s/b', 0.0)]

    assert rotate.elect('/s/a') == expected

    searched = [c for c in r.calls if c[0] == 'headroom']
    if expected == '/s/a':
        assert searched == []
    else:
        assert searched == [('headroom', '/s/a')]


@pytest.mark.parametrize('current, is_enabled', [('/s/a', False), (None, True)])
def test_no_eligible_alternative_returns_resolved_current(monkeypatch, current, is_enabled):
    r = _rig(monkeypatch)
    r.is_enabled_map = {'/s/a': is_enabled}
    r.headroom_list = []

    got = rotate.elect(current)

    assert got is not None
    assert got == (current or '/synthetic/default')


def test_candidates_drops_spent_keeps_headroom_order_and_exclude(monkeypatch):
    r = _rig(monkeypatch)
    r.headroom_list = [('acct-a', '/s/a', 10.0), ('acct-b', '/s/b', 20.0),
                       ('acct-c', '/s/c', 30.0)]
    r.spent_set = {'/s/b'}

    got = rotate.candidates(exclude='/s/x')

    assert got == [('acct-a', '/s/a', 10.0), ('acct-c', '/s/c', 30.0)]
    assert ('headroom', '/s/x') in r.calls


def test_repeated_sid_in_cooldown_never_stamps_notifies_or_launches(monkeypatch):
    r = _rig(monkeypatch)
    r.stamps = {'S5'}

    assert rotate.offer('/s/t', '', 'S5') == (False, 'already offered')

    r.next_to = ''
    assert rotate.offer('/s/t', '', 'S6') == (False, 'no other account has headroom')

    names = [c[0] for c in r.calls]
    assert 'mark' not in names and 'notify' not in names and 'continue' not in names
    assert r.launches == []


def test_stamp_precedes_auto_launch_so_failed_launch_not_duplicated(monkeypatch):
    r = _rig(monkeypatch)
    r.hands = True
    r.continue_result = (False, 'boom')

    assert rotate.offer('/s/t', '', 'S7') == (False, 'boom')
    assert rotate.offer('/s/t', '', 'S7') == (False, 'already offered')

    assert r.launches == ['/s/b']
    order = [c[0] for c in r.calls if c[0] in ('mark', 'continue')]
    assert order == ['mark', 'continue']


def test_ask_mode_notifies_and_logs_never_launches(monkeypatch):
    r = _rig(monkeypatch)
    r.hands = False

    assert rotate.offer('/s/t', '', 'S8') == (False, 'offered acct-b')

    assert r.launches == []
    names = [c[0] for c in r.calls]
    assert 'notify' in names and 'log' in names
    assert 'continue' not in names


def test_failed_auto_launch_keeps_failure_result(monkeypatch):
    r = _rig(monkeypatch)
    r.hands = True
    r.continue_result = (False, 'could not start')

    assert rotate.offer('/s/t', '', 'S9') == (False, 'could not start')
    assert ('note', None, '/s/b') in r.calls


def test_successful_auto_launch_reports_success(monkeypatch):
    r = _rig(monkeypatch)
    r.hands = True
    r.continue_result = (True, '')

    assert rotate.offer('/s/t', '', 'S10') == (True, 'continued on acct-b')
    assert r.launches == ['/s/b']


def test_failed_launch_title_does_not_claim_success(monkeypatch):
    r = _rig(monkeypatch)
    r.hands = True
    r.continue_result = (False, 'boom')

    rotate.offer('/s/t', '', 'S11')

    assert not any(title.startswith('Continued on') for title, _ in r.notes_sent)


def test_simultaneous_same_sid_offers_launch_once(monkeypatch):
    r = _rig(monkeypatch)
    r.hands = True
    entered = threading.Event()
    release = threading.Event()
    checks = []

    def offered_recently(sid):
        seen = sid in r.stamps
        checks.append(sid)
        if len(checks) == 1:
            entered.set()
            release.wait(timeout=2)
        return seen

    monkeypatch.setattr(quota, 'offered_recently', offered_recently)
    first = threading.Thread(target=rotate.offer, args=('/s/t', '', 'S12'), daemon=True)
    second = threading.Thread(target=rotate.offer, args=('/s/t', '', 'S12'), daemon=True)

    first.start()
    try:
        assert entered.wait(timeout=2)
        second.start()
        second.join(timeout=2)
    finally:
        release.set()
        first.join(timeout=2)
        second.join(timeout=2)

    assert not first.is_alive() and not second.is_alive()
    assert len(r.launches) == 1


def test_retry_after_notify_failure_does_not_relaunch(monkeypatch):
    r = _rig(monkeypatch)
    r.hands = True
    r.notify_error = RuntimeError('notify down')

    with pytest.raises(RuntimeError):
        rotate.offer('/s/t', '', 'S13')

    r.notify_error = None
    assert rotate.offer('/s/t', '', 'S13') == (False, 'already offered')
    assert r.launches == ['/s/b']

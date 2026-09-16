"""Rotation reaching the session you are SITTING IN.

Everything in `test_rotate.py` is about a process archeus is about to start.
This file is about the one it is not in: a Claude Code session in a terminal,
whose account fills while you are typing into it. That case had no trigger at
all — rotation was correct everywhere it could see, and silent in the one place
the user actually meets a limit.

Three things have to hold, and each of them was broken in a different way:

  * the limit has to be OBSERVED across processes (it was a dict in whichever
    process happened to see it);
  * something has to NOTICE while the session is live (nothing was listening to
    Claude Code's `StopFailure`, and nothing read the percentages Claude Code
    hands the statusline every turn);
  * noticing repeatedly must not mean acting repeatedly.
"""

import io
import json
import os
import subprocess
import sys

import pytest

from claude_sessions import config as _c
from claude_sessions import events, hooks, quota, rotate, statusline, usage

EXE = os.path.join('C:', 'bin', 'claude.exe')
RESET = '2026-09-01T15:00:00Z'


def _data(pct, kind='session'):
    return {'limits': [{'kind': kind, 'percent': pct, 'resets_at': RESET}]}


def _account(tmp_path, name, pct, logged_in=True):
    d = tmp_path / name
    d.mkdir(exist_ok=True)
    if logged_in:
        (d / '.credentials.json').write_text(json.dumps(
            {'claudeAiOauth': {'accessToken': 'tok-' + name,
                               'expiresAt': 9999999999000}}), encoding='utf-8')
    usage._acct_state[str(d)] = {'name': name, 'status': 'ok', 'data': _data(pct)}
    return str(d)


@pytest.fixture(autouse=True)
def _clean(monkeypatch, tmp_path):
    quota.reset()
    monkeypatch.setattr(events, 'path', lambda: str(tmp_path / 'events.jsonl'))
    events._recent.clear()
    monkeypatch.setattr(usage, '_acct_state', {}, raising=False)
    # the stamp is a real file in the OS scratch dir; keep every run's in its own
    monkeypatch.setattr(quota, '_offer_stamp',
                        lambda sid: str(tmp_path / ('s-%s.stamp' % (sid or 'x'))))


def _settings(monkeypatch, accounts=(), **over):
    s = {'headless_quota': 'prompt', 'rotate_mode': 'ask'}
    s.update(over)
    monkeypatch.setattr(_c, 'load_settings', lambda: dict(s))
    monkeypatch.setattr(_c, 'all_config_dirs',
                        lambda: [(os.path.basename(d), d) for d in accounts])
    return s


def _live(monkeypatch, d):
    """Make `d` the account this session is running under."""
    monkeypatch.setattr(_c, 'resolve_config_dir',
                        lambda x=None: str(x) if x else str(d))


# ── 1. the observation has to outlive the process that made it ──

def test_a_limit_seen_in_one_process_is_seen_in_every_other(monkeypatch, tmp_path):
    """The half of the bug nothing would ever have reported.

    Claude Code refuses a turn in your terminal; the hook that hears it is its
    own short-lived process and `quota._observed` dies with it. An archeus open
    in another window went on offering that account work for the rest of the
    window, and its rotation card went on calling it 'has room'.
    """
    a = _account(tmp_path, 'a', 10)
    _settings(monkeypatch, [a])
    assert not rotate.spent(a)

    quota.note_limit(a, window=True)
    assert os.path.isfile(quota.latch_file())

    # a second process: same file, empty dicts
    quota._observed.clear()
    quota._window_observed.clear()
    quota._latch = (0.0, {})
    assert quota.window_limited(a)
    assert quota.reason(a)
    assert rotate.spent(a)


def test_forgetting_clears_both_halves(monkeypatch, tmp_path):
    """Two homes for one fact is two ways to leave half of it behind — which is
    exactly what happened to three test fixtures the moment the file existed."""
    a = _account(tmp_path, 'a', 10)
    _settings(monkeypatch, [a])
    quota.note_limit(a, window=True)
    quota.forget(a)
    quota._latch = (0.0, {})
    assert not quota.window_limited(a)
    assert not quota.reason(a)


def test_the_latch_path_is_derived_not_frozen():
    """A module-level constant off `_c.settings_file` is a cache with no
    invalidation — this codebase's recurring bug, and it cost this file one
    round of cross-test pollution before it was a function."""
    import inspect
    src = inspect.getsource(quota)
    assert 'def latch_file()' in src
    assert 'LATCH_FILE =' not in src
    here = quota.latch_file()
    try:
        _c.settings_file = os.path.join('C:', 'elsewhere', 'archeus.json')
        assert quota.latch_file() != here
    finally:
        _c.settings_file = os.path.join(os.path.dirname(here), 'archeus.json')


def test_an_expired_latch_is_dropped_on_the_next_write(monkeypatch, tmp_path):
    """Nothing sweeps this file; the only pass it will ever get is a later
    refusal walking past."""
    a, b = _account(tmp_path, 'a', 10), _account(tmp_path, 'b', 10)
    _settings(monkeypatch, [a, b])
    quota.note_limit(a, window=True, ttl=-1)     # already expired
    quota.note_limit(b, window=True)
    from claude_sessions import jsonstore
    keys = jsonstore.load(quota.latch_file(), default={}, expect=dict)
    assert quota._key(b) in keys and quota._key(a) not in keys


# ── 2. something has to notice while the session is live ─────

def test_the_hook_is_installed_on_the_event_that_actually_fires(tmp_path, monkeypatch):
    """`StopFailure` matched on `rate_limit` is Claude Code's own name for the
    turn that just died on a full window. Nothing was listening to it."""
    cfg = tmp_path / 'acct'
    cfg.mkdir()
    monkeypatch.setattr(hooks, 'settings_path', str(cfg / 'settings.json'))
    assert not hooks.limit_hook_installed()
    assert hooks.install_limit_hook()
    assert hooks.limit_hook_installed()
    entry = json.load(open(str(cfg / 'settings.json'), encoding='utf-8'))
    ent = entry['hooks']['StopFailure'][0]
    assert ent['matcher'] == 'rate_limit'
    assert 'limit_hook.py' in ent['hooks'][0]['command']

    # idempotent, and a hand-edited matcher is repaired rather than duplicated
    assert hooks.install_limit_hook()
    ent['matcher'] = 'nonsense'
    json.dump(entry, open(str(cfg / 'settings.json'), 'w', encoding='utf-8'))
    assert hooks.install_limit_hook()
    after = json.load(open(str(cfg / 'settings.json'), encoding='utf-8'))
    assert len(after['hooks']['StopFailure']) == 1
    assert after['hooks']['StopFailure'][0]['matcher'] == 'rate_limit'

    assert hooks.uninstall_limit_hook()
    assert not hooks.limit_hook_installed()


def test_the_mode_chip_installs_and_removes_the_trigger(tmp_path, monkeypatch):
    """No second toggle: a policy and the mechanism that implements it must not
    be two switches that can disagree."""
    cfg = tmp_path / 'acct'
    cfg.mkdir()
    monkeypatch.setattr(hooks, 'settings_path', str(cfg / 'settings.json'))
    monkeypatch.setattr(hooks, 'account_dirs', lambda: [('a', str(cfg))])
    _settings(monkeypatch, [str(cfg)], rotate_mode='ask')
    rotate.ensure_hook()
    assert hooks.limit_hook_installed(str(cfg))
    _settings(monkeypatch, [str(cfg)], rotate_mode='off')
    rotate.ensure_hook()
    assert not hooks.limit_hook_installed(str(cfg))


def test_the_hook_latches_the_account_and_applies_the_mode(monkeypatch, tmp_path):
    from claude_sessions import limit_hook
    a, b = _account(tmp_path, 'a', 99), _account(tmp_path, 'b', 5)
    _settings(monkeypatch, [a, b], rotate_mode='ask')
    _live(monkeypatch, a)
    seen = {}
    monkeypatch.setattr(rotate, '_notify', lambda t, m: seen.setdefault('n', (t, m)))
    out = limit_hook.handle({'cwd': str(tmp_path), 'session_id': 'S1',
                             'transcript_path': ''})
    assert out == {'terminalSequence': limit_hook.BELL}
    assert quota.window_limited(a)              # latched, for every process
    assert 'b' in seen['n'][1]                  # and the user was told where to go


def test_the_hook_never_raises_and_never_blocks(tmp_path):
    """A hook that dies is a turn that dies. Fed rubbish on stdin it must still
    exit 0 — asserted against the real interpreter, not the function.

    HOME and USERPROFILE are redirected, and that is not tidiness: this is a
    real second process, so `conftest`'s module-level pin of `settings_file`
    cannot reach it and neither can `_no_writes_outside_the_sandbox`. Without
    this the `{}` payload latched the developer's own default account —
    observed, and the same class of escape as the detached memory worker that
    used to leave folders in the real project list.
    """
    script = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          'claude_sessions', 'limit_hook.py')
    home = tmp_path / 'home'
    (home / '.claude').mkdir(parents=True)
    env = dict(os.environ, USERPROFILE=str(home), HOME=str(home),
               CLAUDE_CONFIG_DIR=str(home / '.claude'), ARCHEUS_NO_NOTIFY='1')
    for payload in ('', 'not json', '[]', '{}'):
        p = subprocess.run([sys.executable, script], input=payload, env=env,
                           capture_output=True, text=True, timeout=60)
        assert p.returncode == 0, (payload, p.stderr[-400:])
    # …and it stayed inside the redirect
    assert not os.path.isfile(os.path.join(
        os.path.dirname(_c.settings_file), 'archeus-limits.json'))
    assert os.path.isfile(str(home / '.claude' / 'archeus-limits.json'))


# ── 3. the pre-emptive half: 95% is not 100% ─────────────────

class _Boom(BaseException):
    """NOT an Exception. `_rotate_bit` catches `Exception` — it must never be
    the reason a statusline fails — so a tripwire raising anything below that
    is swallowed and the gate passes while measuring nothing. Mutation-verified:
    with `AssertionError` here, deleting the floor check left this green."""


def test_below_the_floor_the_statusline_consults_nothing(monkeypatch):
    """This runs on every turn, so the common case has to cost nothing. No
    configured threshold can be under `rotate._MIN_THRESHOLD`, which is what
    makes the literal floor safe."""
    assert statusline._ROTATE_FLOOR == rotate._MIN_THRESHOLD

    def _tripwire():
        raise _Boom('rotation was consulted below the floor')
    monkeypatch.setattr(rotate, 'enabled', _tripwire)
    assert statusline._rotate_bit(
        {'rate_limits': {'five_hour': {'used_percentage': 49}}}) == ''
    with pytest.raises(_Boom):          # …and the tripwire really does fire
        statusline._rotate_bit(
            {'rate_limits': {'five_hour': {'used_percentage': 99}}})


def test_the_worst_window_is_the_one_that_counts_and_spend_limit_is_not_one():
    """`spend_limit` is a gateway budget, not a plan window, and it can read
    above 100 — treating it as one would rotate an account that is fine."""
    assert statusline._live_pct({'rate_limits': {
        'five_hour': {'used_percentage': 12},
        'seven_day': {'used_percentage': 96}}}) == 96
    assert statusline._live_pct({'rate_limits': {
        'spend_limit': {'used_percentage': 140}}}) == 0
    assert statusline._live_pct({}) == 0


def test_at_the_threshold_the_statusline_names_the_next_account(monkeypatch, tmp_path):
    """The prompt the user never got. 95% is past the switch threshold and long
    before the window is actually spent, which is the entire point: by the time
    Claude Code refuses a turn the conversation has already stopped."""
    a, b = _account(tmp_path, 'a', 95), _account(tmp_path, 'b', 4)
    _settings(monkeypatch, [a, b], rotate_mode='ask', rotate_threshold=95)
    _live(monkeypatch, a)
    bit = statusline.plain(statusline._rotate_bit(
        {'rate_limits': {'five_hour': {'used_percentage': 95}},
         'session_id': 'S1', 'cwd': str(tmp_path)}))
    assert bit == '95% — continue on b'


def test_with_nowhere_to_go_it_says_so_rather_than_nothing(monkeypatch, tmp_path):
    a = _account(tmp_path, 'a', 96)
    _settings(monkeypatch, [a], rotate_mode='ask', rotate_threshold=95)
    _live(monkeypatch, a)
    bit = statusline.plain(statusline._rotate_bit(
        {'rate_limits': {'five_hour': {'used_percentage': 96}}, 'session_id': 'S2'}))
    assert bit == '96% — no account with headroom'


def test_ask_mode_renders_the_offer_and_opens_nothing(monkeypatch, tmp_path):
    """A statusline is a RENDERER, and Claude Code cancels it mid-run whenever
    a new update arrives. Only `auto` may act from here; `ask` is the row and
    nothing else, and the window it does not open is the whole difference
    between the two modes."""
    a, b = _account(tmp_path, 'a', 99), _account(tmp_path, 'b', 4)
    _settings(monkeypatch, [a, b], rotate_mode='ask', rotate_threshold=95)
    _live(monkeypatch, a)
    monkeypatch.setattr(rotate, 'offer',
                        lambda *aa, **kw: pytest.fail('ask acted from a renderer'))
    assert statusline.plain(statusline._rotate_bit(
        {'rate_limits': {'five_hour': {'used_percentage': 99}},
         'session_id': 'S8', 'cwd': str(tmp_path)})) == '99% — continue on b'


def test_auto_mode_acts_from_the_statusline_once(monkeypatch, tmp_path):
    """The pre-emptive hand-off the whole floor exists to allow."""
    a, b = _account(tmp_path, 'a', 96), _account(tmp_path, 'b', 4)
    _settings(monkeypatch, [a, b], rotate_mode='auto', rotate_threshold=95)
    _live(monkeypatch, a)
    calls = []
    monkeypatch.setattr(rotate, 'offer', lambda *aa, **kw: calls.append(aa) or (True, ''))
    for _ in range(3):
        bit = statusline.plain(statusline._rotate_bit(
            {'rate_limits': {'five_hour': {'used_percentage': 96}},
             'session_id': 'S9', 'cwd': str(tmp_path),
             'transcript_path': str(tmp_path / 't.jsonl')}))
    assert bit == '96% — moving to b'
    # `offer` is idempotent on its own, but the renderer must not even ask again
    quota.mark_offered('S9')
    statusline._rotate_bit({'rate_limits': {'five_hour': {'used_percentage': 96}},
                            'session_id': 'S9', 'cwd': str(tmp_path)})
    assert len(calls) == 3, 'the stamp is what stops the fourth'


def test_the_warning_leads_the_row_and_survives_a_narrow_terminal(monkeypatch, tmp_path):
    """`_fit` drops segments from the RIGHT, so segment order IS priority order.
    The one segment saying the session is about to stop working cannot be the
    one a narrow window throws away — and a bit computed but never placed in a
    row is a bit nobody sees, which no test above would have noticed."""
    a, b = _account(tmp_path, 'a', 99), _account(tmp_path, 'b', 4)
    _settings(monkeypatch, [a, b], rotate_mode='ask', rotate_threshold=95)
    _live(monkeypatch, a)
    monkeypatch.setattr(statusline, '_cols', lambda: 24)
    monkeypatch.setattr(statusline, '_git_bits', lambda cwd: ('repo ⑂main', ''))
    rows = statusline.render_rows({'model': {'display_name': 'Opus 5'}, 'cwd': '',
                                   'rate_limits': {'five_hour': {'used_percentage': 99}},
                                   'session_id': 'S10'})
    assert 'continue on b' in statusline.plain(rows[0])


def test_under_the_threshold_it_stays_quiet(monkeypatch, tmp_path):
    a, b = _account(tmp_path, 'a', 80), _account(tmp_path, 'b', 4)
    _settings(monkeypatch, [a, b], rotate_mode='ask', rotate_threshold=95)
    _live(monkeypatch, a)
    assert statusline._rotate_bit(
        {'rate_limits': {'five_hour': {'used_percentage': 80}},
         'session_id': 'S3'}) == ''


def test_off_means_off_including_the_notification(monkeypatch, tmp_path):
    a, b = _account(tmp_path, 'a', 99), _account(tmp_path, 'b', 4)
    _settings(monkeypatch, [a, b], rotate_mode='off')
    _live(monkeypatch, a)
    monkeypatch.setattr(rotate, '_notify', lambda t, m: pytest.fail('notified'))
    assert rotate.offer(str(tmp_path), '', 'S4') == (False, '')
    assert statusline._rotate_bit(
        {'rate_limits': {'five_hour': {'used_percentage': 99}},
         'session_id': 'S4'}) == ''


# ── 4. noticing repeatedly is not acting repeatedly ──────────

def test_auto_opens_one_successor_however_often_it_is_asked(monkeypatch, tmp_path):
    """The statusline runs on every turn and Claude Code re-refuses every retry.
    Without the cool-down, `auto` is a terminal window a minute."""
    a, b = _account(tmp_path, 'a', 99), _account(tmp_path, 'b', 4)
    _settings(monkeypatch, [a, b], rotate_mode='auto', rotate_threshold=95)
    _live(monkeypatch, a)
    calls = []
    monkeypatch.setattr(rotate, 'continue_session',
                        lambda *aa, **kw: (calls.append(aa) or (True, '')))
    monkeypatch.setattr(rotate, '_notify', lambda t, m: None)
    tr = tmp_path / 't.jsonl'
    tr.write_text('{}\n', encoding='utf-8')
    for _ in range(4):
        rotate.offer(str(tmp_path), str(tr), 'S5', why='95% of the window')
    assert len(calls) == 1, 'the cool-down is the only thing stopping a window a turn'
    assert calls[0][2] == b


def test_the_cooldown_expires_so_a_lost_handoff_is_retried(monkeypatch, tmp_path):
    """Claude Code CANCELS a statusline that is still running when the next
    update arrives, so a hand-off can be lost between the stamp and the spawn.
    A once-per-session flag would make that permanent.

    The stamp is BACKDATED rather than the window set to zero. A zero window
    compares `now - mtime < 0`, and a filesystem that rounds a timestamp up by a
    millisecond makes that difference negative — which reads as "just offered"
    and failed on Windows/3.10 only, while passing everywhere this was written.
    Never assert on how precisely the machine records a moment.
    """
    assert quota.OFFER_COOLDOWN >= 60
    quota.mark_offered('S6')
    assert quota.offered_recently('S6')
    stamp = quota._offer_stamp('S6')
    old = os.path.getmtime(stamp) - quota.OFFER_COOLDOWN - 5
    os.utime(stamp, (old, old))
    assert not quota.offered_recently('S6')


def test_a_rotation_and_its_absence_both_reach_the_log(monkeypatch, tmp_path):
    """'Why did nothing happen' has to be answerable from the Logs page."""
    a = _account(tmp_path, 'a', 99)
    _settings(monkeypatch, [a], rotate_mode='ask')
    _live(monkeypatch, a)
    rotate.offer(str(tmp_path), '', 'S7')
    msgs = [e['msg'] for e in events.read(20) if e.get('src') == 'rotate']
    assert any('nothing else has headroom' in m for m in msgs), msgs


def test_the_successor_resumes_by_path_and_forks(monkeypatch, tmp_path):
    """Cross-account resume is by ABSOLUTE TRANSCRIPT PATH — by session id
    Claude Code searches the ACTIVE config dir and finds nothing — and without
    `--fork-session` the successor appends to a file in the account it left.
    Both come free from `main`'s `fork:` choice, which is why nothing here
    builds an argv."""
    from claude_sessions import gui
    seen = {}
    monkeypatch.setattr(gui, 'launch_session',
                        lambda p, e, c, o: (seen.update(path=p, choice=c, opts=o), (True, ''))[1])
    tr = tmp_path / 'x.jsonl'
    tr.write_text('{}\n', encoding='utf-8')
    ok, err = rotate.continue_session(str(tmp_path), str(tr), str(tmp_path / 'acct'))
    assert ok and not err
    assert seen['choice'] == 'fork:' + str(tr)
    assert seen['opts']['cfgdir'] == str(tmp_path / 'acct')
    # the opts dict is indexed with a bare subscript inside build_launch_command,
    # so "close enough" is a KeyError at spawn time and nowhere else
    for k in ('effort', 'model', 'perm', 'name', 'worktree'):
        assert k in seen['opts']


def test_a_missing_transcript_is_reported_not_spawned(monkeypatch, tmp_path):
    from claude_sessions import gui
    monkeypatch.setattr(gui, 'launch_session',
                        lambda *a, **k: pytest.fail('spawned with no transcript'))
    ok, err = rotate.continue_session(str(tmp_path), str(tmp_path / 'nope.jsonl'),
                                      str(tmp_path))
    assert not ok and 'transcript' in err


def test_the_card_can_say_whether_the_trigger_is_there(monkeypatch, tmp_path):
    """A policy whose trigger is missing is a policy that never fires, which was
    the whole bug — so `state()` has to be able to say it."""
    a = _account(tmp_path, 'a', 10)
    _settings(monkeypatch, [a])
    monkeypatch.setattr(hooks, 'account_dirs', lambda: [('a', a)])
    st = rotate.state()
    assert 'hook' in st and set(st['hook']) == {'a'}
    js = io.open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                              'claude_sessions', 'web', 'app.js'),
                 encoding='utf-8').read()
    assert 'function rotTrigger(' in js and 'rotTrigger(d)' in js

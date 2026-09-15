"""Account rotation: which account the next piece of work starts under.

The feature it replaces is a proxy that substitutes another account's OAuth
credential into every request. These tests exist to keep it from turning back
into one, and to keep the four things that make it safe from quietly eroding:
it fails open, it is sticky, it distinguishes a plan window from a bare 429,
and it never touches a credential.
"""

import json
import os

import pytest

from claude_sessions import config as _c
from claude_sessions import events, quota, rotate, usage

EXE = os.path.join('C:', 'bin', 'claude.exe')
RESET = '2026-09-01T15:00:00Z'

#: verbatim from a real 429 transcript — the sentence Claude Code actually
#: sends. `test_quota.py` asserts `is_limit_error` matches it; what matters here
#: is that it also reads as EXHAUSTION rather than as a passing rate limit.
SESSION_LIMIT = "You've hit your session limit · resets 2:30am (Europe/Rome)"


def _data(pct, kind='session'):
    return {'limits': [{'kind': kind, 'percent': pct, 'resets_at': RESET}]}


def _account(tmp_path, name, pct, logged_in=True):
    """An account dir with credentials and a usage cache entry."""
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
    quota._observed.clear()
    quota._decided.clear()
    quota._window_observed.clear()
    monkeypatch.setattr(events, 'path', lambda: str(tmp_path / 'events.jsonl'))
    events._recent.clear()
    monkeypatch.setattr(usage, '_acct_state', {}, raising=False)
    monkeypatch.setattr(quota, '_interactive', lambda: False)


def _settings(monkeypatch, accounts=(), **over):
    """Pin the roster and the policy.

    `all_config_dirs` is patched rather than fed through `settings['accounts']`
    for the same reason `test_quota.py` does it: that function always puts the
    machine's REAL `~/.claude` first, and a default account with no usage entry
    reads as 0% — the emptiest in the room, and the one every election would
    pick.
    """
    s = {'headless_quota': 'prompt', 'rotate_mode': 'ask'}
    s.update(over)
    monkeypatch.setattr(_c, 'load_settings', lambda: dict(s))
    monkeypatch.setattr(_c, 'all_config_dirs',
                        lambda: [(os.path.basename(d), d) for d in accounts])
    return s


# ── the switch threshold is not the block threshold ──────────

def test_an_account_past_the_threshold_is_spent_but_still_spendable(monkeypatch, tmp_path):
    """The whole reason there are two numbers.

    `quota.LIMIT_PCT` (100) decides whether an account may be spent at all, and
    a rotation threshold that moved it would refuse work on an account with 1%
    left. 98 decides only whether archeus keeps CHOOSING it.
    """
    d = _account(tmp_path, 'a', 99)
    _settings(monkeypatch, [d])
    assert rotate.spent(d)                  # no longer chosen
    assert not quota.is_exhausted(d)        # but perfectly usable
    assert quota.reason(d) == ''


def test_the_threshold_is_clamped_on_read(monkeypatch, tmp_path):
    """`/api/settings` stores whatever the client sends for a declared key and
    the settings file is hand-editable, so the one reader is where this belongs."""
    for raw, want in ((98.0, 98.0), (0, 98.0), (-5, 50.0), (500, 100.0),
                      ('nonsense', 98.0), (None, 98.0), (72, 72.0)):
        _settings(monkeypatch, rotate_threshold=raw)
        assert rotate.threshold() == want, raw


# ── a plan window rotates; a bare 429 does not ───────────────

def test_the_real_limit_sentence_marks_the_account_spent(monkeypatch, tmp_path):
    d = _account(tmp_path, 'a', 10)
    _settings(monkeypatch, [d])
    assert not rotate.spent(d)
    quota.note_failure([EXE, '-p', 'hi'], _c.account_env(d), SESSION_LIMIT)
    assert quota.window_limited(d)
    assert rotate.spent(d)


def test_a_bare_429_is_a_short_rate_limit_and_does_not_rotate(monkeypatch, tmp_path):
    """Rotating on a 429 that clears in seconds burns a second account's
    headroom for nothing — the distinction the reference implementation makes
    off the `anthropic-ratelimit-unified-*-status` headers, made here off the
    wording, because archeus never sees those headers."""
    d = _account(tmp_path, 'a', 10)
    _settings(monkeypatch, [d])
    for text in ('HTTP 429 Too Many Requests', 'rate limit', 'Overloaded'):
        quota._observed.clear()
        quota._window_observed.clear()
        quota.note_failure([EXE, '-p', 'hi'], _c.account_env(d), text)
        assert not rotate.spent(d), text
    # …while the blocking latch still fires for it, which is a DIFFERENT
    # question ("may this be spent right now") and must not have been weakened
    # by adding this one
    quota.note_failure([EXE, '-p', 'hi'], _c.account_env(d),
                       'HTTP 429 Too Many Requests')
    assert quota.is_exhausted(d)
    assert not rotate.spent(d)


def test_a_bare_429_is_read_as_a_status_not_as_a_number_in_prose():
    """Found while building rotation, and worth its own gate.

    `_LIMIT_RE` shipped as `re.compile(r'<BS>429<BS>')` — two literal BACKSPACE
    bytes where `\\b` was meant — so it could never match anything and this half
    of the guard had been dead for its whole life. It looked fine because every
    429 the suite asserts on also carries 'too many requests' or 'rate_limit',
    and a MARKER caught it.

    The obvious repair is wrong too: `\\b429\\b` matches "wrote 429 lines to
    quota.py", which `test_the_markers_do_not_match_the_models_own_output`
    forbids. A status code arrives in a shape prose never takes.
    """
    for hit in ('{"error":"rate_limit","apiErrorStatus":429}', 'status: 429',
                'code=429', 'HTTP 429 Too Many Requests'):
        assert quota.is_limit_error(hit), hit
    for miss in ('wrote 429 lines to quota.py', 'total tokens: 14290',
                 'cost 4291 tokens', 'line 4290'):
        assert not quota.is_limit_error(miss), miss


def test_forget_clears_the_window_latch_too(monkeypatch, tmp_path):
    d = _account(tmp_path, 'a', 10)
    _settings(monkeypatch, [d])
    quota.note_failure([EXE, '-p', 'hi'], _c.account_env(d), SESSION_LIMIT)
    quota.forget(d)
    assert not rotate.spent(d)


# ── election ─────────────────────────────────────────────────

def test_crossing_the_threshold_elects_the_next_account(monkeypatch, tmp_path):
    full = _account(tmp_path, 'full', 99)
    room = _account(tmp_path, 'room', 12)
    _settings(monkeypatch, [full, room])
    assert rotate.elect(full) == room


def test_a_disabled_account_is_never_elected_or_offered(monkeypatch, tmp_path):
    """Opt-out, and it has to reach BOTH surfaces: an account you took out of
    the rotation must not show up in the picker either, or the choice you
    already made is put to you again."""
    full = _account(tmp_path, 'full', 99)
    empty = _account(tmp_path, 'empty', 2)
    other = _account(tmp_path, 'other', 40)
    _settings(monkeypatch, [full, empty, other], rotate_disabled=[empty])
    assert not rotate.is_enabled(empty)
    assert rotate.elect(full) == other                       # not the emptiest
    assert empty not in [d for _n, d, _p in quota.headroom(exclude=full)]


def test_it_is_sticky_below_the_threshold(monkeypatch, tmp_path):
    """Rotating per call would fragment prompt caching and multiply cost, so a
    healthy account keeps the work however empty its neighbour is."""
    cur = _account(tmp_path, 'cur', 60)
    _account(tmp_path, 'empty', 0)
    _settings(monkeypatch, [cur])
    for _ in range(5):
        assert rotate.elect(cur) == cur


def test_off_means_nothing_rotates(monkeypatch, tmp_path):
    full = _account(tmp_path, 'full', 100)
    _account(tmp_path, 'room', 5)
    _settings(monkeypatch, [full], rotate_mode='off')
    assert rotate.mode() == 'off' and not rotate.enabled()
    assert rotate.elect(full) == full


def test_the_three_modes_differ_only_in_who_opens_the_window(monkeypatch, tmp_path):
    full = _account(tmp_path, 'full', 100)
    room = _account(tmp_path, 'room', 5)
    _settings(monkeypatch, [full, room], rotate_mode='ask')
    assert rotate.elect(full) == room and not rotate.hands_off()
    _settings(monkeypatch, [full, room], rotate_mode='auto')
    assert rotate.elect(full) == room and rotate.hands_off()
    # the words people actually type are mapped, not rejected
    for raw, want in (('semi', 'ask'), ('full', 'auto'), ('never', 'off'),
                      ('MANUAL', 'off'), ('gibberish', 'ask'), ('', 'ask')):
        _settings(monkeypatch, rotate_mode=raw)
        assert rotate.mode() == want, raw


# ── fail open ────────────────────────────────────────────────

def test_an_empty_cache_elects_nothing_and_blocks_nothing(monkeypatch, tmp_path):
    """The single most damaging regression this feature could introduce: a
    rotation layer that moves work — or refuses it — because the background
    poller has not run yet."""
    d = str(tmp_path / 'never-polled')
    _settings(monkeypatch, [d])
    assert rotate.used_pct(d) == 0.0
    assert not rotate.spent(d)
    assert rotate.elect(d) == _c.resolve_config_dir(d)
    assert quota.preflight([EXE, '-p', 'hi'], None) == (None, '')


def test_a_broken_settings_file_does_not_stop_rotation_deciding(monkeypatch):
    def boom():
        raise OSError('settings unreadable')
    monkeypatch.setattr(_c, 'load_settings', boom)
    assert rotate.threshold() == rotate.THRESHOLD_DEFAULT
    assert rotate.mode() == 'ask'
    assert rotate.disabled() == set()
    assert quota._rotation_allows(str('anything')) is True


# ── the event log ────────────────────────────────────────────

def test_a_switch_is_recorded_and_two_switches_do_not_collapse(monkeypatch, tmp_path):
    """`events._dedupe_shape` collapses decimals, which is right — but it means
    a message carrying a measurement never dedupes, and one carrying only names
    dedupes too WELL. Two different destinations must stay two events."""
    a = _account(tmp_path, 'a', 100)
    b = _account(tmp_path, 'b', 5)
    c = _account(tmp_path, 'c', 6)
    _settings(monkeypatch, [a, b, c])
    assert rotate.note(a, b, 'session limit full') is True
    assert rotate.note(a, c, 'session limit full') is True
    msgs = [e['msg'] for e in events.read() if e['src'] == 'rotate']
    assert len(msgs) == 2 and len(set(msgs)) == 2
    # a switch to where you already are is not a switch
    assert rotate.note(a, a, 'nothing happened') is False


def test_the_auto_branch_switches_and_records_it(monkeypatch, tmp_path):
    """End to end through the guard every archeus `claude -p` call passes."""
    full = _account(tmp_path, 'full', 100)
    room = _account(tmp_path, 'room', 8)
    _settings(monkeypatch, [full, room], headless_quota='auto')
    env, blocked = quota.preflight([EXE, '-p', 'hi'], _c.account_env(full))
    assert blocked == ''
    assert env['CLAUDE_CONFIG_DIR'] == room
    assert any(e['src'] == 'rotate' for e in events.read())


def test_the_auto_branch_prefers_an_account_under_the_threshold(monkeypatch, tmp_path):
    """Emptiest-first already, but `headroom` only drops what cannot be spent —
    a 99% account is offered ahead of nothing, and must be chosen behind a
    12% one."""
    full = _account(tmp_path, 'full', 100)
    nearly = _account(tmp_path, 'nearly', 99)
    room = _account(tmp_path, 'room', 12)
    _settings(monkeypatch, [full, nearly, room], headless_quota='auto')
    env, _ = quota.preflight([EXE, '-p', 'hi'], _c.account_env(full))
    assert env['CLAUDE_CONFIG_DIR'] == room
    # and when everything left is past the threshold, spending one still beats
    # blocking: the bar for "may be spent" was already cleared
    usage._acct_state.pop(room)
    quota.forget(full)
    quota._decided.clear()
    _settings(monkeypatch, [full, nearly], headless_quota='auto')
    env, blocked = quota.preflight([EXE, '-p', 'hi'], _c.account_env(full))
    assert blocked == '' and env['CLAUDE_CONFIG_DIR'] == nearly


# ── the GUI surface ──────────────────────────────────────────

def test_the_state_endpoint_answers_on_a_cold_cache(monkeypatch, tmp_path):
    """`test_endpoint_floor` makes a real request to every route; this is the
    same contract stated where the shape is readable."""
    from claude_sessions import gui_api
    _settings(monkeypatch)
    d = gui_api.api_rotate_state({}, {})
    assert set(d) >= {'threshold', 'mode', 'hands_off', 'live', 'next',
                      'rotating', 'accounts', 'events'}
    assert isinstance(d['accounts'], list) and isinstance(d['events'], list)
    assert d['rotating'] is False           # nothing to switch to, no claim that there is


def test_the_state_rows_say_which_account_is_live_and_which_is_out(monkeypatch, tmp_path):
    from claude_sessions import gui_api
    full = _account(tmp_path, 'full', 100)
    room = _account(tmp_path, 'room', 3)
    _settings(monkeypatch, [full, room], rotate_disabled=[room])
    monkeypatch.setattr(_c, 'config_dir', full, raising=False)
    rows = {r['name']: r for r in gui_api.api_rotate_state({}, {})['accounts']}
    assert rows['full']['live'] is True and rows['full']['spent'] is True
    assert rows['room']['enabled'] is False and rows['room']['signed_in'] is True


# ── the policy that makes this design the safe one ───────────

def test_rotation_never_touches_a_credential():
    """The standing policy, as a gate rather than as prose.

    Rotating by `CLAUDE_CONFIG_DIR` is what Anthropic's own documentation
    describes for running several accounts, and it is safe precisely because
    nothing writes `.credentials.json`: an OAuth refresh rotates the refresh
    token, so a second program refreshing Claude Code's credential logs the
    user out of Claude Code. If this module ever grows a token store, that is
    a different feature and it should not arrive by accident.
    """
    import inspect
    src = inspect.getsource(rotate)
    body = '\n'.join(ln for ln in src.splitlines()
                     if not ln.lstrip().startswith(('#', '*')))
    for forbidden in ('.credentials.json', 'refresh_token', 'accessToken',
                      'oauth/token', 'ANTHROPIC_AUTH_TOKEN', 'x-api-key'):
        assert forbidden not in body, forbidden
    # the only credential-shaped thing it may do is ASK whether a login exists
    assert 'usage._read_token' in src and 'usage._token_expired' in src
    for writer in ('open(', 'write_atomic', 'write_json_atomic', 'os.replace'):
        assert writer not in body, writer

"""T-1171 — the ten highest-risk uncovered branches of `claude_sessions/usage.py`
lines 1-243 inclusive (tip 56d53504): the Claude account poller — credential reads,
the `/oauth/usage` fetch, the per-account retry deadline, the `_data`/`_acct_state`
record the main screen and `quota.worst_window` read, and the background thread's
start/stop lifecycle. Functions that continue past line 243 (`windows_snapshot`) and
everything below it are read-only context here: no branch owned by this file lives
outside 1-243.

Fail-closed / denial first, then boundaries, then error paths:

 1. usage.py:161-162  `_poll_account` — a backed-off account is not asked again
    before its deadline (`if st.get('retry_at', 0) > now: return False`).
 2. usage.py:150-151  `fetch_usage` — a dead socket answers ('error', None, 0)
    instead of raising (`except Exception: return 'error', None, 0`).
 3. usage.py:142-143  `fetch_usage` — 403 is denied exactly like 401
    (`if e.code in (401, 403): return 'expired', None, 0`), with the 300 s
    expired-cadence backoff of usage.py:183.
 4. usage.py:145-148  `fetch_usage` — a 429 whose Retry-After cannot be read is
    still a rate limit, waited from zero (`int(...)` + `except (TypeError, ValueError)`).
 5. usage.py:146 + 183-184 `_poll_account` — a zero / negative / absent / absurd
    Retry-After still buys a real deadline strictly in the future
    (`max(retry_after, ...)`, `min(back, _RETRY_MAX)`).
 6. usage.py:165-167  `_poll_account` — a fetch that RAISES is recorded as 'error'
    (through `_c.log.exception`) and the rest of the roster is still polled.
 7. usage.py:180-181  `_poll_account` — only the ACTIVE account may replace the
    module `_data` the single-account line reads (`if normcase(abspath(d)) == active`).
 8. usage.py:236-241  `refresh_now` — an explicit refresh clears the deadline of
    EVERY account and arms the poller (`_ensure_started()` + `pop('retry_at')`).
 9. usage.py:216-230  `_ensure_started` / `stop_background` — one poller thread per
    arming, none for a repeat start, `_stop.clear()` before the thread is let go.
10. usage.py:199-213  `_background` — a stop asked for mid-pass ends the loop
    before the remaining accounts are asked (`if _stop.is_set(): return`).

Probes 1 (missing token, no transport), 2 (expired token, no transport) and 8
(a failed fetch keeps the last good data) were dropped as already covered by
tests/test_usage.py — see the report for the evidence; the three genuinely
uncovered branches above (2, 6, 9/10 split) replace them.

Nothing here reaches the host: the credential reader, `config.config_dir`,
`config.all_config_dirs`, `config.log`, `time.time`, `threading.Thread`,
`usage._stop` and `urllib.request.urlopen` are all replaced by seam fakes before
the tested function is entered, so no real home, credential file, clock, thread,
subprocess or socket is ever touched. Credential-shaped values are invented
(`invent.ed-…@example.invalid`), every path is under `tmp_path`, the waits are
recorded rather than slept, and no test starts a thread. Same file runs unchanged
on Linux (this container) and Windows (review): both sides of every path
comparison go through `os.path.normcase(os.path.abspath(...))`, and no OS error
text is ever read.

Each test names the source branch whose removal or inversion it catches. Independent
of every other test_gaps3 file: no sibling import, no queue order, no shared state.
"""

import json
import os
import sys
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest                                       # noqa: E402

from claude_sessions import config as _config       # noqa: E402
from claude_sessions import usage as u              # noqa: E402

INVENTED_TOKEN = 'invent.ed-access-token'
INVENTED_EMAIL = 'invent.ed@example.invalid'


def good_data(tag):
    """An invented `/oauth/usage` body — one account-wide window, no spend."""
    return {'tag': tag,
            'limits': [{'kind': 'session', 'group': 'session', 'percent': 12.5,
                        'resets_at': '2026-06-24T14:00:00Z'}],
            'spend': {'enabled': False}}


def http_error(code, headers=None):
    """The real HTTPError the module tests `e.code` / `e.headers` on."""
    return urllib.error.HTTPError(u.USAGE_URL, code, 'answer', dict(headers or {}), None)


# ── the seams this module touches outside itself ─────────────────────────────

class Clock:
    """`usage` reads the wall clock only through `time.time()` (lines 69, 158)."""

    def __init__(self):
        self.now = 1750000000.0

    def time(self):
        return self.now


class Resp:
    def __init__(self, payload):
        self._payload = payload

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class Transport:
    """Every fetch this module can perform while a test runs. Records the Request
    (url, headers, timeout) and answers from a scripted queue; an unscripted fetch
    is counted and the fixture fails on it, so a test can never pass by silently
    fetching more (or less) than it meant to."""

    def __init__(self):
        self.calls = []
        self.answers = []
        self.unexpected = 0

    def queue(self, *answers):
        self.answers.extend(answers)
        return self

    def __call__(self, req, timeout=None):
        self.calls.append((req.full_url,
                           {k.lower(): v for k, v in req.header_items()}, timeout))
        if not self.answers:
            self.unexpected += 1
            raise OSError('the test scripted no answer for this fetch')
        ans = self.answers.pop(0)
        if isinstance(ans, BaseException):
            raise ans
        if isinstance(ans, (bytes, bytearray)):
            return Resp(bytes(ans))
        return Resp(json.dumps(ans).encode('utf-8'))

    @property
    def urls(self):
        return [c[0] for c in self.calls]


class StopEvent:
    """Fake of `usage._stop`, the one threading.Event the poller parks on."""

    def __init__(self, events):
        self._flag = False
        self._events = events
        self.waits = []

    def is_set(self):
        return self._flag

    def set(self):
        self._flag = True
        self._events.append('set')

    def clear(self):
        self._flag = False
        self._events.append('clear')

    def wait(self, timeout=None):
        self.waits.append(timeout)
        self._events.append(('wait', timeout))
        return self._flag


class ThreadStub:
    def __init__(self, target, daemon, events):
        self.target = target
        self.daemon = daemon
        self.started = False
        self._events = events

    def start(self):
        self.started = True
        self._events.append('start')


class Threads:
    """Fake `threading` namespace: line 223 is the only call-time use the module
    makes, so no test in this file can create a real thread."""

    def __init__(self, events):
        self.made = []
        self._events = events

    def Thread(self, target=None, daemon=False, **kw):      # noqa: N802
        t = ThreadStub(target, daemon, self._events)
        self.made.append(t)
        return t


class Log:
    def __init__(self):
        self.exception_calls = []

    def exception(self, msg, *a, **k):
        self.exception_calls.append(msg)

    def warning(self, msg, *a, **k):
        pass


class World:
    """A two-account machine: an active and an inactive Claude home under
    tmp_path, each with invented credentials handed out by a faked reader. The
    real home, the real settings file and the real `.credentials.json` are never
    opened: `_creds` is replaced before any entrypoint runs."""

    def __init__(self, tmp_path, monkeypatch):
        homes = os.path.join(str(tmp_path), 'homes')
        self.active = _mkhome(homes, 'acct-active')
        self.other = _mkhome(homes, 'acct-other')
        self.active_norm = _norm(self.active)
        self.other_norm = _norm(self.other)
        self.roster = [('active', self.active), ('other', self.other)]
        self.cred_reads = []
        self.creds = {}
        self.events = []
        self.clock = Clock()
        self.transport = Transport()
        self.stop = StopEvent(self.events)
        self.threads = Threads(self.events)
        self.log = Log()
        for d in (self.active, self.other):
            self.login(d)
        monkeypatch.setattr(u, '_creds', self._creds)
        monkeypatch.setattr(u, 'time', self.clock)
        monkeypatch.setattr(u, '_stop', self.stop)
        monkeypatch.setattr(u, 'threading', self.threads)
        monkeypatch.setattr(u, '_acct_state', {})
        monkeypatch.setattr(u, '_data', None)
        monkeypatch.setattr(u, '_ready', False)
        monkeypatch.setattr(u, '_started', True)      # nothing arms a poller by accident
        monkeypatch.setattr(u.urllib.request, 'urlopen', self.transport)
        monkeypatch.setattr(_config, 'config_dir', self.active)
        monkeypatch.setattr(_config, 'all_config_dirs', lambda: list(self.roster))
        monkeypatch.setattr(_config, 'log', self.log)

    def _creds(self, cfgdir=None):
        key = _norm(cfgdir or _config.config_dir)
        self.cred_reads.append(key)
        return dict(self.creds.get(key, {}))

    def login(self, cfgdir, **over):
        oauth = {'accessToken': INVENTED_TOKEN,
                 'expiresAt': int((self.clock.now + 3600) * 1000),
                 'subscriptionType': 'max', 'rateLimitTier': '20x',
                 'account': {'email_address': INVENTED_EMAIL}}
        oauth.update(over)
        self.creds[_norm(cfgdir)] = oauth
        return oauth

    def logout(self, cfgdir):
        self.creds[_norm(cfgdir)] = {}


def _norm(p):
    return os.path.normcase(os.path.abspath(p))


def _mkhome(parent, name):
    """Another fake account home, always under the caller's tmp_path."""
    d = os.path.join(str(parent), name)
    os.makedirs(d, exist_ok=True)
    return d


@pytest.fixture
def world(tmp_path, monkeypatch):
    w = World(tmp_path, monkeypatch)
    yield w
    assert w.transport.unexpected == 0, 'a test fetched more than it scripted'


# ── 1. denial first: a refused account stays refused ─────────────────────────

def test_a_backed_off_account_is_not_asked_again_before_its_deadline(world):
    """usage.py:160-162 — `if st.get('retry_at', 0) > now: return False`.

    Kills: deleting that guard. A 429 asks for a wait and `retry_at` is the
    promise archeus made; without the guard every GUI repaint calls the endpoint
    again for an account that was just told to back off, which is exactly the
    hammering the comment at usage.py:144 says not to do, and it rewrites
    `status`/'data' out from under `quota.worst_window` (quota.py:274-278).
    The closest existing test, tests/test_usage.py:142
    `test_poll_keeps_last_good_data_and_never_writes_creds`, works AROUND this
    branch (`st.pop('retry_at', None)` at line 157) instead of asserting it.

    Boundary: `retry_at == now` is not in the future, so that pass does poll —
    it kills rewriting `>` as `>=`, a deadline that never opens.
    """
    good = good_data('other')
    u._acct_state[world.other] = {'status': 'rate_limited', 'data': good,
                                  'retry_at': world.clock.now + 45}
    assert u._poll_account('other', world.other, world.active_norm) is False
    assert world.transport.calls == []                    # the API is not told twice
    st = u._acct_state[world.other]
    assert st['status'] == 'rate_limited' and st['data'] is good
    assert u._ready is False                       # a suppressed poll is not a pass
    u._acct_state[world.other]['retry_at'] = world.clock.now
    world.transport.queue(good_data('other-live'))
    assert u._poll_account('other', world.other, world.active_norm) is True
    assert len(world.transport.calls) == 1
    assert u._acct_state[world.other]['data']['tag'] == 'other-live'
    assert 'retry_at' not in u._acct_state[world.other]  # a live fetch clears the promise


# ── 2. error path: nothing may escape the fetch ──────────────────────────────

def test_a_dead_socket_answers_error_with_no_data_and_never_raises(world):
    """usage.py:150-151 — the blanket `except Exception: return 'error', None, 0`.

    Kills: narrowing it (e.g. to `except urllib.error.URLError`) or removing it:
    the OSError raised here is deliberately NOT a URLError, so a narrowed clause
    lets it escape `fetch_usage` — and `fetch_usage` is the public entrypoint
    (gui_api.py:1134 reaches it through `refresh_now` on a thread), where an
    escaping exception means no recorded status at all, `_ready` never set, and a
    usage line stuck on 'checking…' forever. tests/test_usage.py:119
    `test_status_maps_http_errors` only ever raises `HTTPError`, which the clause
    at line 141 already answers; the non-HTTP failure is not in it.
    """
    world.transport.queue(OSError('the socket died before anything was answered'))
    assert u.fetch_usage(world.other) == ('error', None, 0)
    url, headers, timeout = world.transport.calls[0]
    assert len(world.transport.calls) == 1            # one attempt, no private retry loop
    assert url == u.USAGE_URL
    assert headers['authorization'] == 'Bearer ' + INVENTED_TOKEN
    assert headers['anthropic-beta'] == 'oauth-2025-04-20'
    assert timeout is not None and 0 < timeout <= 30  # usage.py:139 bounds the read
    assert os.listdir(world.other) == []              # nothing written into the home


# ── 3. denial: 401 and 403 are the same answer ───────────────────────────────

@pytest.mark.parametrize('code', [401, 403], ids=['unauthorized', 'forbidden'])
def test_the_api_saying_no_means_log_in_again_whether_it_meant_401_or_403(world, code):
    """usage.py:142-143 — `if e.code in (401, 403): return 'expired', None, 0`.

    Kills: dropping 403 from the tuple. A forbidden answer would fall through to
    usage.py:149 'error' → 'usage unavailable' instead of STATUS_TEXT['expired']
    ('session expired — run claude login for this account'), the user would never
    be told to re-login, and usage.py:183 would back off 30 s instead of
    _REFRESH_SEC, hammering an endpoint that just refused the credential.
    tests/test_usage.py:119 covers 401 alone and asserts only `[0] == 'expired'`
    — no data/retry_after parity, no 403, no state, no backoff cadence.
    """
    world.transport.queue(http_error(code), http_error(code))
    assert u.fetch_usage(world.other) == ('expired', None, 0)   # no data, no wait asked
    assert u._poll_account('other', world.other, world.active_norm) is False
    st = u._acct_state[world.other]
    assert st['status'] == 'expired'
    assert 'data' not in st                            # nothing invented for the meters
    assert st['retry_at'] == world.clock.now + u._REFRESH_SEC   # usage.py:183 expired leg
    assert 'claude login' in u.STATUS_TEXT[st['status']]         # what the screen says
    assert len(world.transport.calls) == 2                       # exactly one per call


# ── 4. a 429 that cannot be read is still a 429 ──────────────────────────────

@pytest.mark.parametrize('headers', [
    {'Retry-After': 'soon'},          # not a number at all
    {'Retry-After': '12.5'},          # a float is not an int either
    {'Retry-After': ''},              # present but empty -> the `or 0` half
    {},                               # absent header -> None -> the `or 0` half
], ids=['word', 'float', 'empty', 'absent'])
def test_a_rate_limit_with_an_unreadable_retry_after_is_still_a_rate_limit(world, headers):
    """usage.py:145-148 — `int(e.headers.get('Retry-After') or 0)` inside
    `try: ... except (TypeError, ValueError): return 'rate_limited', None, 0`.

    Kills: deleting the try/except — `int('soon')` is a ValueError and would then
    raise out of `fetch_usage`, so the account records NOTHING instead of recording
    a rate limit (and `refresh_now` aborts the roster through the hole tested in
    case 6). Also kills answering 'error' for a 429: a rate limit is not a broken
    account, and STATUS_TEXT['error'] would blame the connection instead of the
    wait. tests/test_usage.py:119 scripts only `{'Retry-After': '77'}`, the one
    shape that reaches neither half of this branch.

    Verified honestly: the `or 0` and the `except (TypeError, ValueError)` are
    redundant WITH EACH OTHER — `int(None)` is a TypeError the same clause catches,
    so deleting `or 0` alone is a behaviour-preserving (equivalent) mutation no test
    can see. Deleting the try/except, which is the branch of record, IS caught — by
    the 'word' and 'float' parameters; the 'empty' and 'absent' ones hand `or 0` a
    falsy value, have nothing to parse, and stay green by construction.
    """
    world.transport.queue(http_error(429, headers))
    assert u.fetch_usage(world.other) == ('rate_limited', None, 0)
    assert len(world.transport.calls) == 1
    assert os.listdir(world.other) == []               # a denial writes nothing


# ── 5. boundary: the wait archeus imposes on itself ──────────────────────────

@pytest.mark.parametrize('headers,asked,expect', [
    ({'Retry-After': '0'}, 0, u._RETRY_BASE),
    ({'Retry-After': '-5'}, -5, u._RETRY_BASE),
    ({}, 0, u._RETRY_BASE),
    ({'Retry-After': '7200'}, 7200, u._RETRY_MAX),
], ids=['zero', 'negative', 'absent', 'beyond_the_ceiling'])
def test_whatever_the_api_says_the_next_poll_is_always_strictly_in_the_future(
        world, headers, asked, expect):
    """usage.py:146 (`int(...) or 0`) composed with usage.py:183-184
    (`back = max(retry_after, _RETRY_BASE if status != 'expired' else _REFRESH_SEC)`
    / `st['retry_at'] = now + min(back, _RETRY_MAX)`).

    Kills: the `max` half — without it a 0/-5/absent Retry-After parks `retry_at`
    at (or before) `now`, so the guard tested in case 1 never fires and the poller
    retries a rate-limited account immediately, forever; and the `min` half —
    without it the ceiling constant `_RETRY_MAX` (usage.py:26, the deliberate cap
    that keeps one dead account's 429 from silencing the meters for hours) is dead
    code and a hostile 7200 is obeyed verbatim. tests/test_usage.py:142 scripts
    ('rate_limited', None, 30) only: 30 is already inside both clamps.
    """
    good = good_data('last-good')
    u._acct_state[world.other] = {'status': 'ok', 'data': good}
    err = http_error(429, headers)
    world.transport.queue(err, err)
    assert u.fetch_usage(world.other) == ('rate_limited', None, asked)
    assert u._poll_account('other', world.other, world.active_norm) is False
    st = u._acct_state[world.other]
    assert st['status'] == 'rate_limited'
    assert st['data'] is good                          # usage.py:176, never clobbered
    assert st['retry_at'] == world.clock.now + expect
    assert st['retry_at'] > world.clock.now            # never a deadline already past
    assert u._poll_account('other', world.other, world.active_norm) is False
    assert len(world.transport.calls) == 2             # one poll, then honoured silence


# ── 6. denial of service on the OTHER accounts is not allowed ────────────────

def test_one_account_raising_during_a_fetch_does_not_take_the_rest_of_the_roster_down(
        world, monkeypatch):
    """usage.py:165-167 — `except Exception: _c.log.exception(...)` followed by
    `status, data, retry_after = 'error', None, 0`, through the roster loop of
    `refresh_now` (usage.py:238-241).

    Kills: deleting the try/except. `fetch_usage` has its own blanket clause, so
    what escapes to here is anything raised around it (credential reader, proxy,
    the JSON decode) — and with the guard gone the first account aborts
    `refresh_now`, so the accounts after it keep an hour-old `status`/`data` that
    `quota.worst_window` (quota.py:274-278) still treats as a live 'ok' reading and
    spends against, `_ready` is never set, and nothing is logged. The closest
    existing test, tests/test_usage.py:142, patches `fetch_usage` to RETURN a
    failing triple, which is the path at 182-184, not this one at 165-167.
    """
    good_active, good_other = good_data('active'), good_data('other')
    u._acct_state[world.active] = {'status': 'ok', 'data': good_active,
                                   'email': 'kept@example.invalid'}
    u._acct_state[world.other] = {'status': 'ok', 'data': good_other}
    monkeypatch.setattr(u, '_data', good_active)
    asked = []

    def explode(cfgdir):
        asked.append(cfgdir)
        raise ConnectionResetError('the connection died mid-fetch')

    monkeypatch.setattr(u, 'fetch_usage', explode)
    u.refresh_now()
    assert asked == [world.active, world.other]        # the roster, in full, in order
    for d, good in ((world.active, good_active), (world.other, good_other)):
        st = u._acct_state[d]
        assert st['status'] == 'error'
        assert st['data'] is good                      # usage.py:176 keeps what it saw
        assert st['retry_at'] > world.clock.now        # and asks again later, not now
    assert u._data is good_active                      # a failed poll promotes nothing
    assert u._acct_state[world.active]['email'] == 'kept@example.invalid'  # 173-174
    assert u._acct_state[world.other]['email'] == INVENTED_EMAIL           # 74-83
    assert world.log.exception_calls == ['usage fetch failed', 'usage fetch failed']
    assert u._ready is True


# ── 7. only the active account owns the single-account line ──────────────────

def test_only_the_active_account_can_become_the_data_the_single_account_line_reads(
        world, monkeypatch):
    """usage.py:180-181 — `if os.path.normcase(os.path.abspath(d)) == active:
    _data = data`.

    Kills: deleting the comparison (every polled account would overwrite `_data`,
    `_targets()` is default-first but the GUI polls them all, so the compact
    single-account line and `stats` — the reason `_data` exists, usage.py:44 —
    would show whichever account happened to be polled last, telling the user
    another account has headroom) and inverting it (the active account's own
    numbers would never reach the screen). tests/test_usage.py:142 calls
    `_poll_account(..., active='other')`, so only the FALSE leg has ever run.
    """
    old = good_data('previous-active')
    monkeypatch.setattr(u, '_data', old)
    # the inactive account is polled first, on its own, and must not touch _data
    world.transport.queue(good_data('other'))
    assert u._poll_account('other', world.other, world.active_norm) is True
    assert u._data is old
    assert u._acct_state[world.other]['data']['tag'] == 'other'
    assert u._acct_state[world.other]['plan'] == 'max'          # usage.py:88-90
    # the active account, spelled noisily, still owns the line: 180 normalises both
    noisy = os.path.join(os.path.dirname(world.active), '.', os.path.basename(world.active))
    world.transport.queue(good_data('active'))
    assert u._poll_account('active', noisy, world.active_norm) is True
    assert u._data['tag'] == 'active'
    assert world.transport.urls == [u.USAGE_URL, u.USAGE_URL]   # asked once each
    assert world.cred_reads[:2] == [world.other_norm, world.other_norm]   # 60-61, its own file


# ── 8. an explicit refresh means EVERY account, backoff or not ───────────────

def test_an_explicit_refresh_overrides_the_deadline_of_every_account_and_arms_the_poller(
        world, monkeypatch):
    """usage.py:236-241 — `_ensure_started()` then, per account,
    `_acct_state.setdefault(d, {}).pop('retry_at', None)` before `_poll_account`.

    Kills: deleting the `pop` line — the refresh button (gui_api.py:1134) would
    then silently do nothing for any account sitting in a backoff, which is the
    state every account is in after a rate limit, and the user's click would lie;
    and deleting `_ensure_started()` — a refresh from a screen that starts the GUI
    without the poller would fetch once and never again. Nothing in the existing
    suite calls `refresh_now` at all; tests/test_usage.py:142 again `pop`s the
    deadline by hand rather than testing that the product does.
    """
    armed = []
    monkeypatch.setattr(u, '_ensure_started', lambda: armed.append(1))
    stale_active, stale_other = good_data('active-stale'), good_data('other-stale')
    future = world.clock.now + 3600
    u._acct_state[world.active] = {'status': 'rate_limited', 'data': stale_active,
                                   'retry_at': future}
    u._acct_state[world.other] = {'status': 'error', 'data': stale_other,
                                  'retry_at': future}
    err = http_error(500)
    world.transport.queue(err, err)
    u.refresh_now()
    assert armed == [1]
    assert world.transport.urls == [u.USAGE_URL, u.USAGE_URL]   # both, despite the deadlines
    for d, stale in ((world.active, stale_active), (world.other, stale_other)):
        st = u._acct_state[d]
        assert st['status'] == 'error'
        assert st['data'] is stale                    # the truth, not a blank meter
        assert st['retry_at'] > world.clock.now       # freshly armed for the next pass
    assert world.cred_reads[:2] == [world.active_norm, world.active_norm]  # default first


# ── 9. the lifecycle, without a single thread ────────────────────────────────

def test_the_poller_is_armed_once_and_a_stop_lets_it_be_armed_again(world, monkeypatch):
    """usage.py:216-230 — `_ensure_started`'s `with _lock: if _started: return`,
    its `_stop.clear()` before `Thread(...).start()`, and `stop_background`'s
    `_stop.set()` + `_started = False`.

    Kills: deleting the `_started` guard (every caller of `windows_snapshot(poll=True)`
    or `refresh_now` would add a whole polling thread — N threads hammering the
    same endpoint for one GUI), deleting `_stop.clear()` (a restart after
    `stop_background()` would start a thread that sees `_stop` set and returns
    immediately, so the meters would be frozen for the rest of the run), and
    deleting `_started = False` in `stop_background` (a stopped poller could never
    be started again). tests/test_api_hardening.py:213 only asserts the
    `stop_background` ATTRIBUTE exists and calls it; nothing starts the poller.
    """
    monkeypatch.setattr(u, '_started', False)
    u._ensure_started()
    u._ensure_started()
    assert len(world.threads.made) == 1               # one thread, not two
    assert world.threads.made[0].target is u._background
    assert world.threads.made[0].started is True
    assert world.threads.made[0].daemon is True       # it must not keep the process alive
    assert world.events == ['clear', 'start']         # disarmed BEFORE the thread is let go
    assert u._started is True
    u.stop_background()
    assert world.stop.is_set() is True
    assert u._started is False
    assert world.events[-1] == 'set'
    u._ensure_started()                               # a stopped poller must re-arm
    assert len(world.threads.made) == 2
    assert world.events[-2:] == ['clear', 'start']
    assert u._started is True


# ── 10. shutdown mid-pass: no fetch after the user closed the window ─────────

def test_a_stop_asked_mid_pass_ends_the_loop_before_the_rest_of_the_roster_is_asked(
        world, monkeypatch, tmp_path):
    """usage.py:199-213 — the `if _stop.is_set(): return` inside the per-account
    loop (203-204), the `_stop.wait(1)` gap between accounts (206) and the
    `active` computed from `config.config_dir` (200).

    Kills: deleting the mid-pass check — `stop_background()` on shutdown with four
    accounts polled would still send up to three more authenticated requests after
    the user asked to stop (each one `_stop.wait(1)` plus a real fetch, so a quit
    that takes half a minute and spends rate limit after the app is closing) —
    and rewriting `return` as `break`, which falls through to the end-of-pass
    `_stop.wait(sleep)`. `_poll_account` is replaced by a recorder so the loop
    itself, and only the loop, is what this asserts. No existing test runs
    `_background`: tests/test_api_hardening.py:213 stops a loop it never starts.
    """
    extra = [_mkhome(os.path.join(str(tmp_path), 'extra-homes'), 'acct-%s' % k)
             for k in ('c', 'd')]
    assert all(d.startswith(str(tmp_path)) for d in extra)    # tmp_path only
    monkeypatch.setattr(_config, 'all_config_dirs', lambda: [
        ('a', world.active), ('b', world.other), ('c', extra[0]), ('d', extra[1])])
    asked, actives = [], []

    def record_poll(name, d, active):
        asked.append(name)
        actives.append(active)
        if len(asked) == 2:
            world.stop.set()                    # the user closes the window mid-pass
        return True

    monkeypatch.setattr(u, '_poll_account', record_poll)
    u._background()                             # THIS thread, no thread is started
    assert asked == ['a', 'b']
    assert actives == [world.active_norm, world.active_norm]     # usage.py:200
    assert world.stop.waits == [1, 1]           # the between-account gap, twice
    # the stop landed mid-pass and the loop RETURNED: no end-of-pass _stop.wait(300)
    assert world.events == [('wait', 1), 'set', ('wait', 1)]

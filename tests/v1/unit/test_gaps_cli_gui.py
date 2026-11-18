"""T-773: the ten highest-risk uncovered branches of archeus/cli/gui.py.

Fail-closed and denial paths first — a Core whose lock is held but whose
`core.json` cannot be read is never sent a byte, a shell with no local token
or with a refused launch code never attaches and never asks for a wider
credential, Pause all on an unreachable Core says only that, and the Attention
count goes silent rather than raising — then the boundary values (the waited-for
start that must happen exactly once, the 0/1/many pause counts, the event
cursor that must never move backwards or say what it is not allowed to say),
then the error paths and exit codes (`gui` without Qt exits 2, a failed attach
exits 1 with the reason on stderr, the tray's e-stop returns the command's own
code and words).

Style, fixtures and seams follow tests/v1/unit/test_fix_cli_gui.py and
tests/v1/unit/test_fix_cli_main.py: every HTTP answer arrives through faked
`client.Core.get`/`post` (`_open` itself raises, so no socket can open), every
discovery answer through the `archeus.infra.discovery` seams the integration
tests use, and the process spawn through `claude_sessions.proc.spawn_detached`
as tests/v1/integration/test_gui_shell.py fakes it. Nothing here needs a
display, a real process, a real terminal or Windows; the same assertions hold
on Linux and on Windows, and every temp file goes through the per-test
`archeus_home` (tmp_path) of tests/v1/conftest.py.
"""

import os
import re
import sys
import types

import pytest

from archeus.cli import gui
from archeus.cli import main as cli_main
from archeus.cli._api import endpoints
from archeus.cli.tui import client
from archeus.infra import discovery
from claude_sessions import proc

INFO = {'port': 8123, 'pid': 1, 'create_time': 0.0}
LOCAL_TOKEN = 'local-token'
OWN_TOKEN = 'redeemed-shell-token'


def _never(*a, **k):
    raise AssertionError('the shell started Core')


class Http:
    """Every request a client.Core would send, recorded and answered from
    *routes* ('METHOD /path' -> answer or exception). A request nobody scripted
    is a failure, not a silent default: a shell that suddenly talks to a route
    it should never touch has to fail here."""

    def __init__(self):
        self.routes = {}
        self.seen = []

    def answer(self, method, path, body, token):
        key = '%s %s' % (method, path)
        self.seen.append((key, body, token))
        if key not in self.routes:
            raise AssertionError('the shell sent a request nothing scripted: %s' % key)
        out = self.routes[key]
        if isinstance(out, BaseException):
            raise out
        return out


@pytest.fixture
def http(monkeypatch):
    h = Http()

    def post(self, path, body):
        return h.answer('POST', path, body, self._token)

    def get(self, path):
        return h.answer('GET', path, None, self._token)

    def boom(*a, **k):
        raise AssertionError('the shell opened a real socket')

    monkeypatch.setattr(client.Core, 'post', post)
    monkeypatch.setattr(client.Core, 'get', get)
    monkeypatch.setattr(client.Core, '_open', boom)
    return h


@pytest.fixture
def disc(monkeypatch):
    """discovery.discover() walks *script* (the last entry repeats);
    read_local_token and core_json_path are ours, so no home files exist."""
    class Disc:
        def __init__(self):
            self.script = [('not_running', None)]
            self.token = LOCAL_TOKEN

        def discover(self):
            return self.script.pop(0) if len(self.script) > 1 else self.script[0]

        def read_local_token(self):
            return self.token

        def core_json_path(self):
            return os.path.join('run', 'core.json')

    d = Disc()
    monkeypatch.setattr(discovery, 'discover', d.discover)
    monkeypatch.setattr(discovery, 'read_local_token', d.read_local_token)
    monkeypatch.setattr(discovery, 'core_json_path', d.core_json_path)
    return d


@pytest.fixture
def slept(monkeypatch):
    """The attach wait never burns real time; the sleeps themselves are read."""
    got = []
    monkeypatch.setattr(gui.time, 'sleep', lambda s: got.append(s))
    return got


def _redeemable(http):
    """Core answers the shell's own pairing exactly as the routes do."""
    http.routes['POST ' + endpoints.launch_code()] = {'code': 'CODE1'}
    http.routes['POST ' + endpoints.launch_redeem()] = {'token': OWN_TOKEN}


# ── fail-closed and denial ─────────────────────────────────────────────────────

def test_a_core_that_holds_its_lock_but_cannot_be_read_is_never_sent_anything(disc, http,
                                                                               slept):
    """gui.py:114,117-118 — the `unreadable` arm of attach's failure message.
    Core owns the lock but its core.json names a dead process: the token must
    not go to whoever holds that port, so the answer is words, no request, and
    the path to look at."""
    disc.script = [('unreadable', dict(INFO))]
    shell, why = gui.attach(start=_never, wait_s=0)
    assert shell is None
    assert why == ('Archeus Core holds its lock but cannot be read (%s); nothing was sent '
                   'to it' % os.path.join('run', 'core.json'))
    assert http.seen == []


def test_with_no_local_token_the_shell_never_talks_and_never_attaches(disc, http, slept):
    """gui.py:131-132 (`token is None: return None`) plus gui.py:120-121. A
    home whose run/local-token is gone has no proof this is the user's own
    machine: no request may leave, and the shell names the port it gave up on."""
    disc.script = [('running', dict(INFO))]
    disc.token = None
    shell, why = gui.attach(start=_never)
    assert shell is None
    assert why == 'Archeus Core on port 8123 did not give the shell a credential'
    assert http.seen == []


@pytest.mark.parametrize('stage', ['code', 'redeem'])
def test_a_refused_launch_code_or_redeem_is_no_shell_and_names_no_more_than_two_scopes(
        stage, disc, http, slept):
    """gui.py:134-140 (`except client.CoreError: return None`) plus the exact
    request bodies of gui.py:135-138. If either pairing step is refused the
    shell does not attach; and what it asked for must have been exactly the
    two shell scopes superseding its own slot — never a wider credential."""
    disc.script = [('running', dict(INFO))]
    if stage == 'code':
        http.routes['POST ' + endpoints.launch_code()] = client.CoreError(
            403, 'not_permitted', {'why': 'no'})
    else:
        http.routes['POST ' + endpoints.launch_code()] = {'code': 'CODE1'}
        http.routes['POST ' + endpoints.launch_redeem()] = client.CoreError(
            409, 'invalid_transition', {'from': 'used'})
    shell, why = gui.attach(start=_never)
    assert shell is None
    assert why == 'Archeus Core on port 8123 did not give the shell a credential'
    asked = [s for s in http.seen if s[0] == 'POST ' + endpoints.launch_code()][0]
    assert asked[1] == {'scopes': ['observe', 'control'], 'supersede': 'desktop shell'}
    assert asked[2] == LOCAL_TOKEN                     # the local token never left home
    if stage == 'redeem':
        redeemed = [s for s in http.seen if s[0] == 'POST ' + endpoints.launch_redeem()][0]
        assert redeemed[1] == {'code': 'CODE1', 'platform': 'desktop',
                               'name': 'desktop shell'}


def test_pause_all_on_a_core_that_cannot_be_reached_says_only_that(http):
    """gui.py:178-179, the `e.status == 0` arm. Unreachable Core is the one
    refusal the tray may report as a bare fact; any other refusal is spoken by
    sync.explain (the next test). Inverting the arm would print 'Archeus could
    not be reached. Nothing was sent.' here instead of the exact sentinel."""
    shell = gui.Shell(dict(INFO), client.Core(INFO['port'], OWN_TOKEN))
    http.routes['POST ' + endpoints.pause_all()] = client.CoreError(
        0, 'network', {'why': 'ConnectionRefusedError'})
    assert shell.pause_all() == gui.NOT_RUNNING


def test_pause_all_speaks_any_other_refusal_in_words_from_cores_own_code(http):
    """gui.py:178-179, the other arm. A 403 is not 'not running': the answer
    must be Core's own reason, so a shell that lost its `control` scope says
    so instead of claiming Core is down."""
    from archeus.cli.tui import sync
    shell = gui.Shell(dict(INFO), client.Core(INFO['port'], OWN_TOKEN))
    http.routes['POST ' + endpoints.pause_all()] = client.CoreError(
        403, 'not_permitted', {'why': 'the shell is not trusted'})
    assert shell.pause_all() == sync.explain(
        {'status': 403, 'code': 'not_permitted', 'detail': {'why': 'the shell is not trusted'}})


@pytest.mark.parametrize('status', [0, 403])
def test_attention_goes_silent_instead_of_raising_when_core_cannot_be_read(status, http):
    """gui.py:190-191 (`except client.CoreError: return None`). The tray menu
    is built on this: a Core that cannot be read shows no count, it does not
    raise and it never shows a stale 0 (which would read as 'nothing waits')."""
    shell = gui.Shell(dict(INFO), client.Core(INFO['port'], OWN_TOKEN))
    http.routes['GET ' + endpoints.attention_items()] = client.CoreError(status, 'network')
    assert shell.attention() is None


# ── boundary values ────────────────────────────────────────────────────────────

def test_a_core_that_is_starting_is_waited_for_and_started_exactly_once(disc, http, slept):
    """gui.py:106-113. not_running must call start() once (never again in the
    wait loop), the loop must sleep and re-discover, and success must hand back
    a Shell holding the *redeemed* token under the desktop-shell slot — not the
    local token, which stays home."""
    _redeemable(http)
    starts = []

    def start():
        starts.append(1)
        return ''
    disc.script = [('not_running', None), ('running', dict(INFO))]
    shell, why = gui.attach(start=start, wait_s=30)
    assert why is None and starts == [1] and slept == [0.2]
    assert shell.info == dict(INFO) and shell._own._token == OWN_TOKEN
    assert http.seen[0][0] == 'POST ' + endpoints.launch_code()
    assert http.seen[0][2] == LOCAL_TOKEN               # pairing asked with the local token
    assert http.seen[1] == ('POST ' + endpoints.launch_redeem(),
                            {'code': 'CODE1', 'platform': 'desktop', 'name': 'desktop shell'},
                            LOCAL_TOKEN)


@pytest.mark.parametrize('n', [0, 1, 2])
def test_the_pause_all_words_count_exactly(n, http):
    """gui.py:180-182 — the 0/1/many boundaries. 'Nothing was running' only for
    zero (a 0 shown as 'Paused 0' would lie the other way), the singular only
    for one, and every call carries a fresh 32-hex idempotency key."""
    shell = gui.Shell(dict(INFO), client.Core(INFO['port'], OWN_TOKEN))
    http.routes['POST ' + endpoints.pause_all()] = {'missions': [{'id': i} for i in range(n)]}
    expected = ('Nothing was running' if n == 0 else
                'Paused %d running mission%s' % (n, '' if n == 1 else 's'))
    assert shell.pause_all() == expected
    key = http.seen[0][1]['idempotency_key']
    assert re.fullmatch(r'[0-9a-f]{32}', key)


@pytest.mark.parametrize('kind,expected', [
    ('estopped', gui.ESTOPPED),
    ('approval_action', 'A tool call waits for your decision'),
    ('approval_unknown', 'A request waits for your decision'),
    ('approval_no_payload', 'A request waits for your decision'),
    ('breaker_open', 'fake cannot start a process; Archeus tries again in 5 minutes'),
    ('breaker_closed', None),
    ('silent', None),
], ids=['estopped', 'action', 'unknownkind', 'nopayload', 'open', 'closed', 'silent'])
def test_the_tray_says_exactly_the_three_things_it_may_say_and_never_their_content(
        kind, expected):
    """gui.py:51-59 — every arm of notice(). An e-stop, an approval named by
    kind (unknown or missing kind degrades to 'request', never raw payload),
    and a breaker that is *open* (a closed one is silence); anything else is
    silence, and no approval content or event body is ever spoken."""
    events = {
        'estopped': {'type': 'core.estopped'},
        'approval_action': {'type': 'approval.requested', 'payload': {'kind': 'action',
                                                                      'intent': 'rm -rf /'}},
        'approval_unknown': {'type': 'approval.requested', 'payload': {'kind': 'wizard'}},
        'approval_no_payload': {'type': 'approval.requested'},
        'breaker_open': {'type': 'harness.state_changed', 'payload': {'breaker': 'open'},
                         'subject': {'id': 'fake'}},
        'breaker_closed': {'type': 'harness.state_changed', 'payload': {'breaker': 'closed'},
                           'subject': {'id': 'fake'}},
        'silent': {'type': 'execution.tool_called', 'payload': {'input': 'secret'}},
    }
    assert gui.notice(events[kind]) == expected


def test_the_event_cursor_moves_only_over_events_and_never_speaks_the_ones_it_hid(http):
    """gui.py:199-205. after=None reads only the head (nothing older is ever
    said on opening); an empty page must leave the cursor exactly where it was
    (moving it would skip events); the cursor lands on the LAST seq, and only
    sayable events are said."""
    shell = gui.Shell(dict(INFO), client.Core(INFO['port'], OWN_TOKEN))
    http.routes['GET ' + endpoints.events(limit=1)] = ({'events': []}, 42)
    assert shell.notices(None) == (42, [])
    http.routes['GET ' + endpoints.events(after=7, limit=500)] = ({'events': []}, 43)
    assert shell.notices(7) == (7, [])            # cursor unmoved, nothing said
    http.routes['GET ' + endpoints.events(after=7, limit=500)] = ({'events': [
        {'seq': 8, 'type': 'execution.tool_called', 'payload': {'input': 'rm -rf /'}},
        {'seq': 9, 'type': 'core.estopped'},
    ]}, 44)
    assert shell.notices(7) == (9, [gui.ESTOPPED])


# ── error paths, exit codes ────────────────────────────────────────────────────

def test_an_expired_cursor_resyncs_to_the_head_and_other_errors_stay_put(http):
    """gui.py:202-203 — the 410 arm versus every other CoreError. A cursor
    Core no longer honours must return the head with nothing said (a tray that
    went silent at 410 never notifies again); a 500 must keep the cursor so no
    event is lost, and say nothing."""
    shell = gui.Shell(dict(INFO), client.Core(INFO['port'], OWN_TOKEN))
    http.routes['GET ' + endpoints.events(after=99, limit=500)] = \
        client.CoreError(410, 'cursor_expired')
    http.routes['GET ' + endpoints.events(limit=1)] = ({'events': []}, 120)
    assert shell.notices(99) == (120, [])
    http.routes['GET ' + endpoints.events(after=99, limit=500)] = \
        client.CoreError(500, 'internal')
    assert shell.notices(99) == (99, [])


def test_a_start_that_fails_says_why_and_nothing_is_waited_for_or_sent(disc, http, slept):
    """gui.py:106-109 — start() returning why must abort the attach with the
    reason, before the wait loop (no sleep, no second discovery, no request)."""
    disc.script = [('not_running', None)]
    shell, why = gui.attach(start=lambda: 'no python here')
    assert shell is None
    assert why == 'could not start Archeus Core: no python here'
    assert slept == [] and http.seen == []


@pytest.mark.parametrize('handle,err,expected', [
    (object(), '', ''),
    (None, 'denied', 'denied'),
    (None, '', 'it could not be run'),
], ids=['spawned', 'refused', 'wordless'])
def test_start_core_reports_only_whether_a_process_came_up(handle, err, expected,
                                                           monkeypatch):
    """gui.py:97-98 — the `'' if p is not None else (err or 'it could not be
    run')` line. A spawn that failed with no reason must still produce words
    (an empty why would reach attach as success and hang the wait for 30s on a
    Core that was never spawned), and the spawn must be the hidden-console
    `archeus core` with the log."""
    got = {}

    def spawn(argv, **kw):
        got.update(argv=argv, **kw)
        return handle, err
    monkeypatch.setattr(proc, 'spawn_detached', spawn)
    assert gui.start_core() == expected
    assert got['argv'][-1] == 'import sys; from archeus.cli.main import main; ' \
                              'sys.exit(main(["core"]))'
    assert got['hidden_console'] is True and got['log'] == gui.start_log()


def test_the_tray_e_stop_returns_the_commands_own_code_and_words(monkeypatch, capsys):
    """gui.py:144-151. The tray must not run `archeus estop`'s prints into the
    terminal and must not invent its own verdict: both streams are captured
    into one strip, and the exit code is the command's."""
    def estop():
        print('stopped 3 executions')
        print('Core will refuse new work', file=sys.stderr)
        return 2
    monkeypatch.setattr(cli_main, 'estop', estop)
    assert gui.estop() == (2, 'stopped 3 executions\nCore will refuse new work')
    captured = capsys.readouterr()
    assert captured.out == '' and captured.err == ''


def test_the_page_address_is_asked_for_in_the_pages_own_slot_or_gives_up(monkeypatch):
    """gui.py:167-171 — page_url must pass PAGE_SLOT (inverting it to None
    would silently stop revoking the previous page credential, leaving a dead
    shell's token live) and must hand back None, not a half URL, when the code
    cannot be had."""
    asked = []

    def launch_url(info, slot=None):
        asked.append((info, slot))
        return None if slot is None else 'http://127.0.0.1:%d/#launch=CODE&memory=1' % INFO[
            'port']
    monkeypatch.setattr(cli_main, 'launch_url', launch_url)
    shell = gui.Shell(dict(INFO), client.Core(INFO['port'], OWN_TOKEN))
    assert shell.page_url() == 'http://127.0.0.1:8123/#launch=CODE&memory=1'
    assert asked == [(dict(INFO), 'desktop shell page')]
    monkeypatch.setattr(cli_main, 'launch_url', lambda info, slot=None: None)
    assert shell.page_url() is None


def test_gui_without_webengine_exits_2_saying_the_browser_route(monkeypatch, capsys):
    """gui.py:209-215 — the ImportError arm of main(). Without Qt the user
    gets exit 2 and the `archeus core --open` alternative, and NOT a Core
    started behind their back (attach is never reached). Forced through
    sys.modules=None so it tests the same on a machine that has Qt."""
    monkeypatch.setitem(sys.modules, 'PyQt6', None)
    monkeypatch.setitem(sys.modules, 'PyQt6.QtWebEngineWidgets', None)
    monkeypatch.setattr(gui, 'attach', _never)
    assert gui.main() == 2
    err = capsys.readouterr().err
    assert 'PyQt6-WebEngine' in err and 'archeus core --open' in err


def test_gui_exits_1_and_prints_the_attach_reason_when_no_core_can_be_had(
        monkeypatch, capsys):
    """gui.py:216-219 — the failed-attach arm of main(): the reason goes to
    stderr verbatim and the code is 1 (no window, no traceback)."""
    monkeypatch.setitem(sys.modules, 'PyQt6', types.ModuleType('PyQt6'))
    monkeypatch.setitem(sys.modules, 'PyQt6.QtWebEngineWidgets',
                        types.ModuleType('PyQt6.QtWebEngineWidgets'))
    monkeypatch.setattr(gui, 'attach', lambda: (None, 'Archeus Core is not running'))
    assert gui.main() == 1
    assert capsys.readouterr().err == 'Archeus Core is not running\n'


def test_gui_hands_the_attached_shell_to_the_window_and_returns_its_code(monkeypatch):
    """gui.py:220-221 — main() must delegate to run_v1 with the shell and
    return the window's own exit code unchanged (a swallowed code here would
    hide a crashed Qt run from the CLI)."""
    qt = types.ModuleType('PyQt6')
    monkeypatch.setitem(sys.modules, 'PyQt6', qt)
    monkeypatch.setitem(sys.modules, 'PyQt6.QtWebEngineWidgets',
                        types.ModuleType('PyQt6.QtWebEngineWidgets'))
    shell = gui.Shell(dict(INFO), client.Core(INFO['port'], OWN_TOKEN))
    monkeypatch.setattr(gui, 'attach', lambda: (shell, None))
    seen = []
    window = types.ModuleType('claude_sessions.gui_qt')
    window.run_v1 = lambda s: seen.append(s) or 7
    monkeypatch.setitem(sys.modules, 'claude_sessions.gui_qt', window)
    assert gui.main() == 7
    assert seen == [shell]


def test_the_preload_and_tray_colour_never_follow_a_fixed_dark_scheme():
    """gui.py:72-82 — the `SHELL['dark' if dark else 'light']` selection in
    preload_bg and attention_colour. Swapping the schemes (or pinning dark,
    the ADR-0044 §4 bug) fails at least one of these four reads."""
    from archeus.cli.tui.tokens import SHELL
    assert gui.preload_bg(True) == SHELL['dark']['bg']
    assert gui.preload_bg(False) == SHELL['light']['bg']
    assert gui.attention_colour(True) == SHELL['dark']['attention']
    assert gui.attention_colour(False) == SHELL['light']['attention']


def test_the_profile_and_the_start_log_live_under_this_homes_entry(archeus_home):
    """gui.py:62-69 and 85-88 — profile_dir and start_log must sit under
    paths.archeus_home() (the per-test ARCHEUS_HOME; the entry §5.1 reserves
    for the Qt shell). A hardcoded home would put one user's web profile and
    Core's log into another's."""
    assert gui.profile_dir() == os.path.join(str(archeus_home), 'QtWebEngine', 'archeus')
    assert gui.start_log() == os.path.join(str(archeus_home), 'logs', 'gui-core.log')

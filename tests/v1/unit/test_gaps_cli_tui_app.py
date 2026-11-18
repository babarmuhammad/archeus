"""T-774: the highest-risk uncovered branches of archeus/cli/tui/app.py —
every denial is fail-closed (nothing is sent on a doubt), the boundary values
hold, and `main` fails with the documented exit codes. No real terminal: the
loop is never entered, every OS seam (stdout, terminal, discovery) is faked
through the same seams tests/v1/unit/test_fix_app.py uses.
"""

import pytest

from archeus.cli._api import endpoints
from archeus.cli.tui import app as A, client as C
from archeus.cli.tui.view import Style


def freeze():
    """A clock that never moves unless a test moves it."""
    return 0.0


class FakeCore:
    """Core's answers by path; unknown paths read back `None` (still reading),
    GETs can be made to refuse, POSTs are recorded and can be made to fail."""

    def __init__(self, data=None, scopes=('observe', 'control'), fails=None, errors=None):
        self.data = dict(data or {})
        self.scopes, self.posts, self.gets, self.fails = list(scopes), [], [], list(fails or [])
        self.errors = dict(errors or {})

    def get(self, path):
        self.gets.append(path)
        if path in self.errors:
            raise self.errors[path]
        if path in self.data:
            return self.data[path], 1
        if path == '/v1/sync':
            return {'client': {'scopes': list(self.scopes)}}, 1
        return None, None

    def post(self, path, body):
        self.posts.append((path, body))
        if self.fails:
            raise self.fails.pop(0)
        return {}


def app_on(core, clock=None):
    a = A.App(core, Style(False, 'dark', False), size=lambda: (100, 30), stream=False,
              clock=clock or freeze)
    a.signal('stream_open')
    return a


def cmd(core, *, key='M', scope='control', fields=(), confirm=None, disabled=None, sent=None):
    return {'key': key, 'label': 'Message', 'scope': scope,
            'run': lambda k, v: core.post('/m', dict(k=k, **v)),
            'reread': [], 'confirm': confirm, 'disabled': disabled,
            'fields': list(fields), 'done': None, 'ident': 'Message', 'sent': sent}


# ── denial and fail-closed paths ─────────────────────────────────────────────

def test_a_read_refused_with_401_signs_the_client_out_and_keeps_denying():
    core = FakeCore(errors={'/v1/sync': C.CoreError(401, 'unauthenticated')})
    app = app_on(core)
    app.press(cmd(core))
    assert app.conn['conn'] == 'unauthenticated'
    assert core.posts == [] and app.status[2] is True and 'control' in app.status[0]
    app.signal('stream_open')          # a stream that comes back must not un-sign-out
    app.press(cmd(core))
    assert core.posts == []


def test_a_reconnect_invalidates_every_cached_read_then_settles():
    t = [0.0]
    core = FakeCore()
    app = app_on(core, clock=lambda: t[0])
    app.read('/v1/sync')
    assert core.gets.count('/v1/sync') == 1
    app.signal('stream_lost')
    app.signal('stream_open')          # back: a new generation, resynced
    assert app.conn['conn'] == 'resynced' and app.conn['gen'] == 1
    assert app.cache['/v1/sync']['stale'] is True, \
        'a new generation marks every cached answer stale (app.py:83-84)'
    app.read('/v1/sync')               # the gen-0 answer may not be reused
    assert core.gets.count('/v1/sync') == 2
    t[0] = (A.SETTLE_MS - 1) / 1000.0
    app.pump()
    assert app.conn['conn'] == 'resynced', 'the banner stays until the settle time passes'
    t[0] = (A.SETTLE_MS + 1) / 1000.0
    app.pump()
    assert app.conn['conn'] == 'live' and app.settle_at is None


def test_a_cache_entry_from_an_older_generation_is_never_returned_as_current():
    core = FakeCore()
    app = app_on(core)
    app.read('/v1/sync')
    assert core.gets.count('/v1/sync') == 1
    app.cache['/v1/sync'] = {'data': {'client': {'scopes': ['observe', 'control']}},
                             'error': None, 'gen': 0, 'seq': 0, 'stale': False}
    app.conn = {'conn': 'live', 'gen': 1, 'since': 0}   # an entry that escaped the invalidation
    app.read('/v1/sync')
    assert core.gets.count('/v1/sync') == 2, \
        'read() itself must refuse an answer from an older generation (app.py:54-55)'
    assert app.cache['/v1/sync']['gen'] == 1


def test_pressing_a_command_while_offline_sends_nothing_and_says_why():
    core = FakeCore()
    app = app_on(core)
    app.signal('offline')
    app.press(cmd(core, fields=[('text', 'Text', True)]))
    assert core.posts == [] and app.mode is None, 'press must refuse before even opening a prompt'
    assert app.status[2] is True and 'Not connected' in app.status[0]


def test_a_command_is_denied_when_the_sync_answer_is_missing():
    core = FakeCore(data={'/v1/sync': None})    # Core answered `null`: no client, no scopes
    app = app_on(core)
    app.press(cmd(core, fields=[('text', 'Text', True)]))
    assert core.posts == [] and app.mode is None, 'no scopes is a denial, never a free pass'
    assert app.status[2] is True and 'control' in app.status[0]


def test_a_disabled_command_is_refused_with_its_reason_and_sends_nothing():
    core = FakeCore()
    app = app_on(core)
    app.press(cmd(core, disabled='Waiting for the run to end.', fields=[('text', 'Text', True)]))
    assert core.posts == [] and app.mode is None
    assert 'Waiting for the run to end.' in app.status[0] and app.status[2] is True


def test_a_confirm_key_that_is_not_y_sends_nothing():
    core = FakeCore()
    app = app_on(core)
    app.press(cmd(core, confirm='This stops the mission.'))
    assert app.mode['kind'] == 'confirm'
    app.handle(('char', 'n'))
    assert core.posts == [] and app.mode is None
    assert 'Cancelled' in app.status[0] and 'nothing was sent' in app.status[0]


def test_capital_y_on_the_confirm_card_sends_exactly_once():
    core = FakeCore()
    app = app_on(core)
    app.press(cmd(core, confirm='This stops the mission.'))
    app.handle(('char', 'Y'))
    assert app.mode is None and len(core.posts) == 1


def test_escaping_a_prompt_after_filling_the_first_field_sends_nothing():
    core = FakeCore()
    app = app_on(core)
    app.press(cmd(core, fields=[('a', 'A', True), ('b', 'B', True)]))
    assert app.mode['kind'] == 'prompt'
    app.handle(('char', 'x'))
    app.handle(('enter',))
    assert app.mode['kind'] == 'prompt' and app.mode['i'] == 1 and core.posts == []
    app.handle(('esc',))
    assert app.mode is None and core.posts == []
    assert 'Cancelled' in app.status[0] and app.status[2] is False


def test_a_whitespace_only_answer_to_a_required_field_is_refused_not_sent():
    core = FakeCore()
    app = app_on(core)
    app.press(cmd(core, fields=[('text', 'Text', True)]))
    app.handle(('char', ' '))
    app.handle(('enter',))
    assert core.posts == [] and app.mode is not None and app.mode['kind'] == 'prompt'
    assert app.status[0] == 'Text: required.' and app.status[2] is True
    app.handle(('char', 'z'))
    app.handle(('enter',))
    assert app.mode is None and len(core.posts) == 1
    assert core.posts[0][1]['text'] == ' z', 'the buffer is stored as typed, not stripped'


def test_enter_in_the_command_bar_with_no_hits_sends_nothing_and_does_not_crash():
    core = FakeCore()
    app = app_on(core)
    app.mode = {'kind': 'picker', 'q': 'zz', 'hits': [], 'i': 0}
    app.handle(('enter',))
    assert app.mode is None and core.posts == []


def test_control_c_quits_without_sending():
    core = FakeCore()
    app = app_on(core)
    app.handle(('char', '\x03'))
    assert app.quit is True and core.posts == []


# ── boundary values ──────────────────────────────────────────────────────────

def test_the_tell_hit_exists_only_for_a_real_query_and_matches_case_insensitively():
    app = app_on(FakeCore())
    assert all('Tell Archeus' not in label for label, _t in app.hits('   ')), \
        'no text, no tell: a blank bar is not a message'
    assert app.hits(' hi ')[-1] == ('Tell Archeus: hi', ('tell', 'hi'))
    assert 'Go to Now' in [label for label, _t in app.hits('GO TO NOW')]


def test_the_picker_cursor_cannot_leave_the_hit_list():
    app = app_on(FakeCore())
    app.handle(('char', ':'))
    m = app.mode
    assert m['kind'] == 'picker' and m['i'] == 0
    for _ in range(len(m['hits']) + 3):
        app.handle(('down',))
    assert m['i'] == len(m['hits']) - 1
    for _ in range(len(m['hits']) + 3):
        app.handle(('up',))
    assert m['i'] == 0


def test_a_narrow_terminal_is_still_given_the_minimum_width():
    app = A.App(FakeCore(), Style(False, 'dark', False), size=lambda: (10, 30), stream=False)
    app.signal('stream_open')
    lines = app.frame()
    assert lines and all(len(x) == A.MIN_WIDTH for x in lines)


def test_the_status_line_disappears_when_its_seconds_are_up():
    t = [0.0]
    app = app_on(FakeCore(), clock=lambda: t[0])
    app.say('Hold on.')
    app.dirty = False
    t[0] = (A.STATUS_S * 1000 - 1) / 1000.0
    assert app.pump() is False and app.status is not None, 'not yet its moment'
    t[0] = (A.STATUS_S * 1000 + 1) / 1000.0
    assert app.pump() is True and app.status is None


# ── error paths: refusals, exit codes, argument parsing ──────────────────────

def test_a_busy_refusal_is_retried_once_with_the_same_key_and_no_error_line():
    core = FakeCore(fails=[C.CoreError(503, 'busy')])
    app = app_on(core)
    app.execute(cmd(core, sent='Sent — reading it again.'), {'text': 'go'})
    assert len(core.posts) == 2, 'Core asked for the retry: exactly one more, same key'
    assert core.posts[0][1]['k'] == core.posts[1][1]['k']
    assert app.status == ('Sent — reading it again.', A.STATUS_S * 1000, False)


def test_a_policy_refusal_is_never_retried_and_is_explained_as_an_error():
    core = FakeCore(fails=[C.CoreError(403, 'policy_denied', {'reason': 'not now'})])
    app = app_on(core)
    app.execute(cmd(core), {'text': 'go'})
    assert len(core.posts) == 1, 'Core said no: nothing more may leave this client'
    assert app.status[0] == 'The policy denies it: not now' and app.status[2] is True


class _FakeTTY:
    encoding = 'utf-8'

    def __init__(self):
        self.reconfigured = []

    def isatty(self):
        return True

    def reconfigure(self, **kw):
        self.reconfigured.append(kw)


def _main_ready(monkeypatch, core=None):
    """`main` with discovery answered and the loop replaced: no terminal, no
    stream thread, no file is ever touched."""
    calls = []
    monkeypatch.setattr(C.Core, 'local', classmethod(lambda cls: (core or FakeCore(), None)))
    monkeypatch.setattr(A, 'run', lambda app, **kw: calls.append((app, kw)))
    monkeypatch.setattr('os.environ', {})
    return calls


@pytest.mark.parametrize('why, code, words', [
    ('not_running', 1, ['not running', 'never starts it']),
    ('unreadable', 2, ['discovery file is unreadable', 'nothing was sent']),
    ('no_token', 2, ['no local token', 'nothing was sent']),
], ids=['not_running', 'unreadable', 'no_token'])
def test_main_fails_closed_on_every_no_core_reason(why, code, words, monkeypatch, capsys):
    monkeypatch.setattr(C.Core, 'local', classmethod(lambda cls: (None, why)))
    monkeypatch.setattr(A, 'run', lambda *a, **k: pytest.fail('nothing may run without Core'))
    assert A.main(['--once']) == code
    out = capsys.readouterr().out
    for w in words:
        assert w in out


def test_an_unknown_flag_is_a_usage_error_with_exit_code_2(capsys):
    with pytest.raises(SystemExit) as e:
        A.main(['--colour', 'pink'])
    assert e.value.code == 2
    assert 'unrecognized arguments' in capsys.readouterr().err


def test_open_without_a_slash_gives_an_empty_id_and_extra_slashes_stay_in_the_id(monkeypatch):
    calls = _main_ready(monkeypatch)
    A.main(['--open', 'mission'])
    assert calls[-1][0].route == {'view': 'object', 'kind': 'mission', 'id': '', 'tab': None}
    A.main(['--open', 'mission/msn_1/extra'])
    assert calls[-1][0].route == {'view': 'object', 'kind': 'mission', 'id': 'msn_1/extra',
                                  'tab': None}


def test_the_live_screen_is_shown_only_on_a_real_terminal_and_never_with_once(monkeypatch):
    calls = _main_ready(monkeypatch)
    A.main([])                    # capsys' stdout is not a terminal
    assert calls[-1][1] == {'live': False, 'once': False}
    monkeypatch.setattr('sys.stdout', _FakeTTY())
    monkeypatch.setattr('claude_sessions.term.enable_vt', lambda: True)
    A.main([])
    assert calls[-1][1] == {'live': True, 'once': False}
    A.main(['--once'])
    assert calls[-1][1] == {'live': False, 'once': True}
    assert calls[-1][0].stream is not None, 'main builds the stream the real loop would start'


def test_a_keyboard_interrupt_in_the_loop_returns_130(monkeypatch):
    monkeypatch.setattr(C.Core, 'local', classmethod(lambda cls: (FakeCore(), None)))

    def boom(app, **kw):
        raise KeyboardInterrupt()
    monkeypatch.setattr(A, 'run', boom)
    monkeypatch.setattr('os.environ', {})
    assert A.main(['--once']) == 130


def test_a_tell_reaches_the_primary_conversation_with_the_typed_text():
    core = FakeCore()
    app = app_on(core)
    hits = app.hits('deploy the docs')
    app.mode = {'kind': 'picker', 'q': 'deploy the docs', 'hits': hits, 'i': len(hits) - 1}
    app.handle(('enter',))
    assert len(core.posts) == 1
    path, body = core.posts[0]
    assert path == endpoints.post_message('primary')
    assert body['text'] == 'deploy the docs' and set(body) == {'text', 'idempotency_key'}
    assert app.status[0] == 'Sent — Archeus is reading it.'

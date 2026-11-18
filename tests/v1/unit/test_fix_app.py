"""T-605: a command is gated where it is sent (not only where it is pressed), a
new message does not reuse the key of an earlier failed one, and the command
bar echoes its text cleaned."""

from archeus.cli.tui import app as A, client as C
from archeus.cli.tui.view import Style
from claude_sessions import render


class FakeCore:
    def __init__(self, scopes=('observe', 'control')):
        self.scopes, self.posts, self.fail = scopes, [], []

    def get(self, path):
        if path == '/v1/sync':
            return {'client': {'scopes': list(self.scopes)}}, 1
        return {}, 1

    def post(self, path, body):
        self.posts.append((path, body))
        if self.fail:
            raise self.fail.pop(0)
        return {}


def app_on(core):
    a = A.App(core, Style(False, 'dark', False), size=lambda: (100, 30), stream=False)
    a.signal('stream_open')
    return a


def tell(app, text):
    app.mode = {'kind': 'picker', 'q': text, 'hits': app.hits(text), 'i': 0}
    app.mode['i'] = len(app.mode['hits']) - 1
    app.picker_key(app.mode, ('enter',))


def test_the_command_bar_sends_nothing_while_the_stream_is_lost():
    core = FakeCore()
    app = app_on(core)
    app.signal('stream_lost')
    tell(app, 'deploy the docs')
    assert core.posts == []
    assert 'Not connected' in app.status[0]


def test_the_command_bar_sends_nothing_without_the_control_scope():
    core = FakeCore(scopes=('observe',))
    app = app_on(core)
    tell(app, 'deploy the docs')
    assert core.posts == []
    assert 'control' in app.status[0]


def message_act(core):
    return {'key': 'M', 'label': 'Message', 'scope': 'control', 'run': lambda k, v: core.post(
        '/m', {'k': k, 'text': v['text']}), 'reread': [], 'confirm': None, 'disabled': None,
        'fields': [('text', 'Text', True)], 'done': None, 'ident': 'Message', 'sent': None}


def test_a_prompt_finished_after_the_connection_dropped_sends_nothing():
    core = FakeCore()
    app = app_on(core)
    app.press(message_act(core))
    app.signal('stream_lost')
    app.handle(('char', 'x'))
    app.handle(('enter',))
    assert core.posts == []


def test_a_new_message_after_a_network_failure_gets_a_new_key():
    core = FakeCore()
    core.fail = [C.CoreError(0, 'network')]
    app = app_on(core)
    act = message_act(core)
    app.execute(act, {'text': 'deploy the docs'})
    app.execute(act, {'text': 'cancel everything'})
    app.execute(act, {'text': 'cancel everything'})
    keys = [b['k'] for _p, b in core.posts]
    assert keys[0] != keys[1]
    assert keys[1] != keys[2], 'the second one succeeded, so its key is spent'


def test_the_same_message_retried_after_a_network_failure_keeps_its_key():
    core = FakeCore()
    core.fail = [C.CoreError(0, 'network')]
    app = app_on(core)
    act = message_act(core)
    app.execute(act, {'text': 'deploy the docs'})
    app.execute(act, {'text': 'deploy the docs'})
    assert core.posts[0][1]['k'] == core.posts[1][1]['k']


def test_the_command_bar_echoes_its_text_cleaned():
    app = app_on(FakeCore())
    app.mode = {'kind': 'picker', 'q': 'a\x9d0;owned\x9cb', 'hits': [], 'i': 0}
    shown = '\n'.join(render.strip_ansi(x) for x in app.overlay([], 80, 20))
    assert '\x9d' not in shown and '\x9c' not in shown

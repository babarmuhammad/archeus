"""`archeus gui`: the desktop shell attached to Core (p19-design-gate B8).

What the window and its tray DO lives here, free of Qt, so it is tested against
a real Core with no display: find Core, starting it if it is absent as `archeus
core` does (and leaving it running when the shell quits: Core outlives the GUI,
target-architecture §4); the page's launch address (D2's scopes, as `archeus
core --open`); the shell's own credential; the tray's three actions; and where
the persistent web profile lives. The window itself is `claude_sessions.gui_qt.
run_v1`, the existing Qt lineage, which only calls back into a `Shell`.

The shell's credential is `observe` + `control`, redeemed from a launch code as
a device row named "desktop shell", and held in this process's memory only
(§9): it is what Pause all and the Attention count use, so neither depends on
the page being open. Its launch code takes the "desktop shell" slot
(p20-design-gate D1), so redeeming it revokes the previous shell's credential,
a crashed one's included: one shell credential is live at a time.
"""

import contextlib
import io
import os
import sys
import time

from ._api import endpoints

#: the shell's own grant (B8): enough to read Attention and to Pause all
SHELL_SCOPES = ['observe', 'control']
SHELL_NAME = 'desktop shell'
#: the page's slot (T-096): each page credential revokes the one before it
PAGE_SLOT = 'desktop shell page'
#: how long a Core this shell started may take to answer
START_WAIT_S = 30
NOT_RUNNING = 'Archeus Core is not running'
#: what the tray asks before its Emergency stop: the app's own confirmation (rulebook §6 O-1, §17)
ESTOP_CONFIRM = ('Every running execution is killed now and Archeus refuses new work until '
                 'you re-arm it. Missions are not lost; they wait.')
#: how often the tray reads Core's events while the window is hidden (P21 slice G)
NOTICE_EVERY_S = 10
#: an approval's kind in the tray's words; nothing else of an approval is ever said
APPROVAL_WORDS = {'plan': 'plan', 'task': 'task', 'action': 'tool call',
                  'route': 'route choice', 'start': 'start'}
ESTOPPED = 'Emergency stop: every execution was stopped'


def notice(event):
    """What the tray says for one event, or None (p21-design-gate D1): only an
    approval request and an e-stop, named by their kind, never by their content."""
    if event['type'] == 'core.estopped':
        return ESTOPPED
    if event['type'] == 'approval.requested':
        kind = (event.get('payload') or {}).get('kind')
        return 'A %s waits for your decision' % APPROVAL_WORDS.get(kind, 'request')
    return None


def profile_dir():
    """`<ARCHEUS_HOME>/QtWebEngine/archeus`: the persistent QtWebEngine profile
    (ADR-0044 §3, T5), inside the entry target-architecture §5.1 reserves for
    the Qt shell (`paths.QT_OWNED`). It holds the page's own storage — the
    appearance choice, B7's snapshot — across restarts. Not the page's device
    token: the page keeps that in memory only (T-096, p20 D1)."""
    from ..infra import paths
    return os.path.join(paths.archeus_home(), 'QtWebEngine', 'archeus')


def preload_bg(dark):
    """What the window shows before the page paints: the OS scheme's token
    background, never a fixed dark (ADR-0044 §4)."""
    from .tui.tokens import SHELL
    return SHELL['dark' if dark else 'light']['bg']


def attention_colour(dark):
    """The only colour the tray icon may carry (design system §3, :103)."""
    from .tui.tokens import SHELL
    return SHELL['dark' if dark else 'light']['attention']


def start_log():
    """Where a Core this shell starts writes its output."""
    from ..infra import paths
    return os.path.join(paths.archeus_home(), 'logs', 'gui-core.log')


def start_core():
    """Start `archeus core` in the background, as its own process with a
    console nobody sees (its executions start console programs). '' or why."""
    from claude_sessions import proc
    argv = [proc.python_exe(), '-c',
            'import sys; from archeus.cli.main import main; sys.exit(main(["core"]))']
    p, err = proc.spawn_detached(argv, hidden_console=True, log=start_log())
    return '' if p is not None else (err or 'it could not be run')


def attach(start=start_core, wait_s=START_WAIT_S):
    """(Shell, None), or (None, why) in words. Starts Core only when nothing
    holds its lock; a Core that is starting is waited for, never started twice."""
    from ..infra import discovery
    state, info = discovery.discover()
    if state == 'not_running':
        err = start()
        if err:
            return None, 'could not start Archeus Core: %s' % err
    deadline = time.monotonic() + wait_s
    while state != 'running' and time.monotonic() < deadline:
        time.sleep(0.2)
        state, info = discovery.discover()
    if state != 'running':
        return None, ('Archeus Core did not start (see %s)' % start_log()
                      if state == 'not_running' else
                      'Archeus Core holds its lock but cannot be read (%s); nothing was sent '
                      'to it' % discovery.core_json_path())
    own = _credential(info)
    if own is None:
        return None, 'Archeus Core on port %d did not give the shell a credential' % info['port']
    return Shell(info, own), None


def _credential(info):
    """The shell's own device token, redeemed from a launch code it asked for
    with the local token, and kept only in the returned object."""
    from ..infra import discovery
    from .tui import client
    token = discovery.read_local_token()
    if token is None:
        return None
    local = client.Core(info['port'], token)
    try:
        code = local.post(endpoints.launch_code(), {'scopes': SHELL_SCOPES,
                                                     'supersede': SHELL_NAME})['code']
        out = local.post(endpoints.launch_redeem(),
                         {'code': code, 'platform': 'desktop', 'name': SHELL_NAME})
    except client.CoreError:
        return None
    return client.Core(info['port'], out['token'])


def estop():
    """The tray's Emergency stop: `archeus estop`'s own code, which never
    starts Core (execution-architecture §10). (exit code, what it said)."""
    from . import main
    said = io.StringIO()
    with contextlib.redirect_stdout(said), contextlib.redirect_stderr(said):
        code = main.estop()
    return code, said.getvalue().strip()


class Shell:
    """One attached Core and the shell's own credential."""

    def __init__(self, info, own):
        self.info, self._own = info, own

    profile_dir = staticmethod(profile_dir)
    preload_bg = staticmethod(preload_bg)
    attention_colour = staticmethod(attention_colour)
    estop = staticmethod(estop)
    estop_confirm = ESTOP_CONFIRM
    NOTICE_EVERY_S = NOTICE_EVERY_S

    def page_url(self):
        """A fresh launch address for the window's page (D2's scopes) in the
        page's slot, its token kept in the page's memory only, or None."""
        from .main import launch_url
        return launch_url(self.info, PAGE_SLOT)

    def pause_all(self):
        """POST /v1/missions/pause-all with the shell's credential, in words."""
        from .tui import client, sync
        try:
            out = self._own.post(endpoints.pause_all(), {'idempotency_key': os.urandom(16).hex()})
        except client.CoreError as e:
            return NOT_RUNNING if e.status == 0 else sync.explain(e.refusal())
        n = len(out['missions'])
        return 'Paused %d running mission%s' % (n, '' if n == 1 else 's') if n else \
            'Nothing was running'

    def attention(self):
        """How many things wait on the user, or None when Core cannot be read.
        Read when the tray menu opens and when the window hides: no timer."""
        from .tui import client
        try:
            return self._own.get(endpoints.attention_items())[0]['count']
        except client.CoreError:
            return None

    def notices(self, after):
        """(the event head read, what the tray says) for what happened after
        *after*; with *after* None only the head, so nothing older is said. Core
        unreadable: (*after*, [])."""
        from .tui import client
        try:
            if after is None:
                return self._own.get(endpoints.events(limit=1))[1], []
            events = self._own.get(endpoints.events(after=after, limit=500))[0]['events']
        except client.CoreError:
            return after, []
        said = [s for s in map(notice, events) if s]
        return (events[-1]['seq'] if events else after), said


def main():
    try:
        import PyQt6.QtWebEngineWidgets  # noqa: F401
    except ImportError:
        print('archeus gui needs PyQt6 and PyQt6-WebEngine (pip install PyQt6 '
              'PyQt6-WebEngine); `archeus core --open` opens the app in a browser instead',
              file=sys.stderr)
        return 2
    shell, why = attach()
    if shell is None:
        print(why, file=sys.stderr)
        return 1
    from claude_sessions.gui_qt import run_v1
    return run_v1(shell)

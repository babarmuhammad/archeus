"""T-1311: the highest-risk uncovered branches of archeus claude_sessions/mcp.py
lines 324-372 inclusive (tip 51f4af3f): `_mcp_add_flow` and
`_mcp_add_with_extras`, the add-server flow and its cancellation at each prompt.

The ten selected branches, denial and fail-closed first, then boundaries, then
error paths:

 1. mcp.py:325-326  a None name stops before the transport menu or the runner
 2. mcp.py:328-329  a None transport stops before the target prompt or runner
 3. mcp.py:332-338  a None or empty stdio command stops before the scope menu
 4. mcp.py:334-338  a None or empty HTTP URL stops before the scope menu
 5. mcp.py:340-341  a None scope stops before extras or the runner
 6. mcp.py:363-365  a None stdio env answers (None, True); no runner, argv intact
 7. mcp.py:369-371  a None HTTP header answers (None, True); no runner
 8. mcp.py:372-373  a blank HTTP header is no extras, not a cancellation
 9. mcp.py:366-367  synthetic KEY=VAL pairs are inserted as -e pairs before the
                    separator; a blank env adds nothing
10. mcp.py:351-354  a cancelled runner result never reports an add; the HTTP and
                    header cancellations end-to-end, with the runner faked

Every probe is a fake: `text_input`, `menu`, `flash`, `run_with_progress`,
`get_claude_exe` and the account environment are replaced on the `mcp` module
(where the slice imported them by value) and `proc.run` is replaced by a
function that fails the test if anything reaches it. No real subprocess, no
network, no user home, no credential value. The prompts, menus and runner
calls are recorded so each assertion is about observable order, argv and the
absence of a spawn.
"""
import pytest

from claude_sessions import mcp as mcp_mod
from claude_sessions import config as _c
from claude_sessions import proc


class _Ui:
    """Scripted prompts and menus, recorded in order, plus the runner seam."""

    def __init__(self, monkeypatch, texts=(), menus=(), runner_returns=None):
        self.texts = list(texts)
        self.menus = list(menus)
        self.prompts = []
        self.menu_titles = []
        self.runs = []
        self.flashes = []
        self._runner_returns = runner_returns
        monkeypatch.setattr(mcp_mod, 'text_input', self._text)
        monkeypatch.setattr(mcp_mod, 'menu', self._menu)
        monkeypatch.setattr(mcp_mod, 'flash', lambda msg, ok=True, secs=0.8:
                            self.flashes.append((msg, ok)))
        monkeypatch.setattr(mcp_mod, 'run_with_progress', self._run)
        monkeypatch.setattr(mcp_mod, 'get_claude_exe', lambda: 'C:\\synthetic\\claude.exe')
        monkeypatch.setattr(_c, 'account_env', lambda cfgdir=None, harness=None: {'SYNTH_HOME': '1'})
        monkeypatch.setattr(proc, 'run', self._no_spawn)

    def _text(self, prompt, default=''):
        self.prompts.append(prompt)
        return self.texts.pop(0)

    def _menu(self, items, title, *a, **k):
        self.menu_titles.append(title)
        return self.menus.pop(0)

    def _run(self, args, crumbs, label, timeout=120, cwd=None, env=None):
        assert list(args)[1] == 'mcp'
        self.runs.append(list(args)[2:])
        return self._runner_returns if self._runner_returns is not None else ('OK', False)

    @staticmethod
    def _no_spawn(*a, **k):
        raise AssertionError('a subprocess was started from the add flow')


ARGS_HTTP = ['add', '-s', 'local', '-t', 'http', 'svc', 'https://synthetic.invalid/mcp']
ARGS_STDIO = ['add', '-s', 'local', '-t', 'stdio', 'svc', '--', 'npx', 'synth-server']


def test_a_none_name_stops_before_the_transport_menu_and_the_runner(monkeypatch):
    """Branch: mcp.py:325-326. A cancelled name prompt asks nothing further and
    starts nothing."""
    ui = _Ui(monkeypatch, texts=[None])
    mcp_mod._mcp_add_flow()
    assert ui.menu_titles == []
    assert ui.runs == [] and ui.flashes == []


def test_a_none_transport_stops_before_the_target_prompt_and_the_runner(monkeypatch):
    """Branch: mcp.py:328-329. A cancelled transport menu stops the flow before
    the command or URL is asked for."""
    ui = _Ui(monkeypatch, texts=['svc'], menus=[None])
    mcp_mod._mcp_add_flow()
    assert ui.prompts == ['MCP server name:']
    assert ui.runs == [] and ui.flashes == []


@pytest.mark.parametrize('target', [None, ''])
def test_a_missing_stdio_command_stops_before_the_scope_menu(monkeypatch, target):
    """Branch: mcp.py:332-333 (and the empty-string twin of the same test). No
    command means no scope question and no runner."""
    ui = _Ui(monkeypatch, texts=['svc', target], menus=['stdio'])
    mcp_mod._mcp_add_flow()
    assert len(ui.prompts) == 2
    assert ui.menu_titles == ['TRANSPORT']
    assert ui.runs == [] and ui.flashes == []


@pytest.mark.parametrize('target', [None, ''])
def test_a_missing_http_url_stops_before_the_scope_menu(monkeypatch, target):
    """Branch: mcp.py:334-338. The HTTP path has the same gate as stdio: a
    missing URL is not a scope choice and not an add."""
    ui = _Ui(monkeypatch, texts=['svc', target], menus=['http'])
    mcp_mod._mcp_add_flow()
    assert len(ui.prompts) == 2
    assert ui.menu_titles == ['TRANSPORT']
    assert ui.runs == [] and ui.flashes == []


def test_a_none_scope_stops_before_extras_or_the_runner(monkeypatch):
    """Branch: mcp.py:340-341. A cancelled scope menu asks for no env or header
    and runs nothing."""
    ui = _Ui(monkeypatch, texts=['svc', 'npx synth'], menus=['stdio', None])
    mcp_mod._mcp_add_flow()
    assert len(ui.prompts) == 2
    assert ui.menu_titles == ['TRANSPORT', 'SCOPE']
    assert ui.runs == [] and ui.flashes == []


def test_a_none_stdio_env_answers_cancelled_and_leaves_the_argv_alone(monkeypatch):
    """Branch: mcp.py:363-365. The env prompt cancelled: (None, True), the runner
    never runs, and the argv the caller built is not modified."""
    ui = _Ui(monkeypatch, texts=[None])
    args = list(ARGS_STDIO)
    assert mcp_mod._mcp_add_with_extras(args, 'stdio', 'svc') == (None, True)
    assert ui.runs == []
    assert args == ARGS_STDIO


def test_a_none_http_header_answers_cancelled_and_never_runs(monkeypatch):
    """Branch: mcp.py:369-371. The header prompt cancelled is a cancellation,
    not a header-less add: (None, True) and no runner call. (The card asked for
    a fallthrough test; the source has none, so this is a passing control.)"""
    ui = _Ui(monkeypatch, texts=[None])
    args = list(ARGS_HTTP)
    assert mcp_mod._mcp_add_with_extras(args, 'http', 'svc') == (None, True)
    assert ui.runs == []
    assert args == ARGS_HTTP


def test_a_blank_http_header_adds_nothing_and_is_not_a_cancellation(monkeypatch):
    """Branch: mcp.py:372-373. A blank header is the intentional "none": the
    runner is called once, with no -H pair, and its result is returned."""
    ui = _Ui(monkeypatch, texts=[''], runner_returns=('OUT', False))
    assert mcp_mod._mcp_add_with_extras(list(ARGS_HTTP), 'http', 'svc') == ('OUT', False)
    assert ui.runs == [ARGS_HTTP]
    assert '-H' not in ui.runs[0]


@pytest.mark.parametrize('env, extras', [
    ('SYNTH_A=1  SYNTH_B=two', ['-e', 'SYNTH_A=1', '-e', 'SYNTH_B=two']),
    ('   ', []),
    ('', []),
])
def test_stdio_env_pairs_go_before_the_separator_and_blank_adds_none(monkeypatch, env, extras):
    """Branch: mcp.py:366-367 and 375. Each KEY=VAL token becomes its own -e
    pair placed before the `--` separator; the command words stay after it."""
    ui = _Ui(monkeypatch, texts=[env], runner_returns=('OUT', False))
    assert mcp_mod._mcp_add_with_extras(list(ARGS_STDIO), 'stdio', 'svc') == ('OUT', False)
    argv = ui.runs[0]
    assert argv[:3] == ['add', '-s', 'local']
    assert argv[3:3 + len(extras)] == extras
    tail = argv[3 + len(extras):]
    assert tail == ['-t', 'stdio', 'svc', '--', 'npx', 'synth-server']


def test_a_cancelled_http_flow_is_reported_as_cancelled_and_never_as_added(monkeypatch):
    """Branch: mcp.py:351-354 end to end. The header prompt was cancelled: the
    flow flashes Cancelled, with no Added success, and starts no process."""
    ui = _Ui(monkeypatch, texts=['svc', 'https://synthetic.invalid/mcp', None],
             menus=['http', 'local'])
    mcp_mod._mcp_add_flow()
    assert ui.runs == []
    assert ui.flashes == [('Cancelled', False)]
    assert not any(msg.startswith('Added') for msg, _ in ui.flashes)


def test_a_runner_that_reports_cancelled_is_never_an_add(monkeypatch):
    """Branch: mcp.py:351-354 with the runner's own cancel. The header was blank
    so the runner runs; when it reports cancelled the flow shows Cancelled, not
    Added, and does not report a failure either."""
    ui = _Ui(monkeypatch, texts=['svc', 'https://synthetic.invalid/mcp', ''],
             menus=['http', 'local'], runner_returns=(None, True))
    mcp_mod._mcp_add_flow()
    assert len(ui.runs) == 1
    assert ui.flashes == [('Cancelled', False)]

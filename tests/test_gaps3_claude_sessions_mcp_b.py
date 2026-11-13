"""T-1175: the highest-risk uncovered branches of archeus claude_sessions/mcp.py
lines 247-404 inclusive (tip 56d53504) — `mcp_cli`, `_mcp_run`, `_list_servers`,
`mcp_manager_menu`, `_mcp_add_flow`, `_mcp_add_with_extras`, `_mcp_detail`,
`mcp_status_line`.

Everything here is a fake: `proc.run`, `run_with_progress`, `menu`, `text_input`,
`confirm`, `pager` and `flash` are replaced on the `mcp` module (where the slice
imported them by value) and the harness table, the selected homes and the
credential-bearing environment variables are invented by this file before any
entrypoint can reach host state. No real process, no network, no user home, no
credential file, no keyboard script. All assertions are on observable denial,
argv shape, prompt order and the ABSENCE of a spawn.

The ten selected branches, ranked by risk (fail-closed denial first, then argv
boundaries, then the cancellation error paths). The card report carries the
evidence — the closest existing test, and why its assertion misses the case:

1. mcp.py:264 + 275-276  the child env of BOTH spawn paths names the SELECTED
   home and drops the key that shadows the login (`_c.account_env`).
2. mcp.py:379-384        a remove whose confirmation was DECLINED, or whose scope
   prompt was cancelled, must run nothing and promise nothing.
3. mcp.py:261-263        a non-default home whose own binary is missing denies
   with ITS exe name and must not fall back to `get_claude_exe()`.
4. mcp.py:264-267        `mcp_cli`'s failure mapping: `proc.run` gave up (the
   timeout/no-spawn answer, None) and a non-zero exit both deny; absent streams
   are tolerated.
5. mcp.py:335-339 + 349-354  a cancel after the argv is fully built is inert, a
   runner cancel is never reported as an add, and a gave-up runner is never
   reported as a cancel.
6. mcp.py:341-345 + 357-369  stdio argv boundaries: the command keeps one argv
   element per token and the `-e` extras sit BEFORE `--`, never inside the
   server's own argv.
7. mcp.py:364-367        an http/sse header keeps its spaces inside ONE argv
   element; a blank header adds neither `-H` nor an empty element.
8. mcp.py:272-274        `_mcp_run` with no executable returns (None, False)
   without touching the progress runner (a missing binary is not a cancel).
9. mcp.py:326-327        cancel at the name prompt asks nothing further.
10. mcp.py:329-330       cancel at the transport prompt asks nothing further.

Probe 10 of the card ("error status precedes stale connected list",
mcp.py:396-397) was found already covered — tests/test_tui_mcp.py:97
`test_status_line_error_flag` asserts `unavailable` while `Sandbox` still holds
`mcp_servers = [('TestMCP', 'ok')]` and `_mcp_ready = True` — so it is replaced
by entries 5 and 8, which are genuinely uncovered inside this slice. The
adjacent `mcp_status_line` branches (398-399 not-ready, 401-402 no connected
row) are left to another card; see the report.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

from harness import Sandbox  # noqa: E402

from claude_sessions import harnesses, mcp as mcp_mod, proc  # noqa: E402


# ── seam fakes ───────────────────────────────────────────────

class _Recorder:
    """Records every call; answers from a canned queue, then None (a cancel).

    An exhausted queue answers None on purpose: that is what `ui.menu`,
    `ui.text_input` and `ui.pager` answer when the user presses ESC (ui.py:446,
    ui.py:717-722, and `pager` returns None on exit), so a prompt this file
    runs out of answers for cancels instead of hanging or silently continuing.
    """

    def __init__(self, results=(), default=None):
        self.calls = []
        self._left = list(results)
        self._default = default

    def __call__(self, *args, **kwargs):
        self.calls.append((list(args), dict(kwargs)))
        return self._left.pop(0) if self._left else self._default

    def __len__(self):
        return len(self.calls)

    def kw(self, i=0):
        return self.calls[i][1]


class _Result:
    """Stand-in for the CompletedProcess `proc.run` hands back."""

    def __init__(self, returncode=0, stdout='', stderr=None):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class _Ui:
    """Every interactive and OS seam of the slice, replaced on `mcp` itself.

    The slice reads `menu`, `text_input`, `confirm`, `pager`, `flash` and
    `run_with_progress` from its own module globals, so patching them here is
    the same seam the neighbouring tests patch — but driven by data, so a key
    landing in the wrong screen cannot change what a test asserts.
    """

    def __init__(self, monkeypatch, inputs=(), menus=(), runs=(), confirms=(),
                 pager_keys=(), progress=()):
        self.text_input = _Recorder(inputs)
        self.menu = _Recorder(menus)
        self.mcp_run = _Recorder(runs)
        self.confirm = _Recorder(confirms)
        self.pager = _Recorder(pager_keys)
        self.flash = _Recorder()
        self.progress = _Recorder(progress)
        for name, fake in (('text_input', self.text_input),
                           ('menu', self.menu),
                           ('_mcp_run', self.mcp_run),
                           ('confirm', self.confirm),
                           ('pager', self.pager),
                           ('flash', self.flash),
                           ('run_with_progress', self.progress)):
            monkeypatch.setattr(mcp_mod, name, fake)

    def flashes(self):
        return [(a[0], k.get('ok', True)) for a, k in self.flash.calls]


def _codex_home(monkeypatch, home, exe='C:\\fake\\codex.exe'):
    """Make `home` a Codex home and give it `exe` (None = not installed).

    The `of` fake answers the same descriptor every time it is asked, because
    `config.account_env` asks it a second time for the same home (config.py:925)
    and a queue that runs dry would answer the env build with None."""
    ofs = _Recorder([harnesses.descriptor('codex')], default=harnesses.descriptor('codex'))
    monkeypatch.setattr(harnesses, 'of', ofs)
    exes = _Recorder([exe], default=exe)
    monkeypatch.setattr(harnesses, 'exe', exes)
    return ofs, exes


# ── 1. selected-home env isolation (mcp.py:264, 275-276) ─────

def test_child_env_names_the_selected_home_on_both_spawn_paths(monkeypatch, tmp_path):
    """mcp.py:264 + 275-276 — dropping `env=`, or letting the ambient
    CLAUDE_CONFIG_DIR win, points `claude mcp add/remove` at the account the
    user did NOT select. Inverting either line sends the write to the wrong
    home, so this fails on that code."""
    Sandbox(monkeypatch, tmp_path)
    home = str(tmp_path / 'acct-b')
    ambient = str(tmp_path / 'ambient-a')
    monkeypatch.setenv('CLAUDE_CONFIG_DIR', ambient)      # inherited by archeus
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'sk-invented-not-a-real-key')
    monkeypatch.setenv('OPENAI_API_KEY', 'sk-invented-openai-key')
    monkeypatch.setenv('CODEX_HOME', str(tmp_path / 'codex-decoy'))
    fake_exe = 'C:\\fake\\claude.exe'
    monkeypatch.setattr(mcp_mod, 'get_claude_exe', lambda: fake_exe)

    runs = _Recorder(results=[_Result(stdout='added\n')])
    monkeypatch.setattr(proc, 'run', runs)
    ok, out = mcp_mod.mcp_cli(['add', '-s', 'user', '-t', 'stdio', 'srv', '--', 'npx', 'x'],
                              cfgdir=home)
    assert (ok, out) == (True, 'added')
    argv, kw = runs.calls[0]
    assert argv[0] == [fake_exe, 'mcp', 'add', '-s', 'user', '-t', 'stdio', 'srv',
                       '--', 'npx', 'x']
    env = kw['env']
    assert env is not None and env is not os.environ      # a copy, never the live map
    assert env['CLAUDE_CONFIG_DIR'] == home               # the SELECTED home wins
    assert env['CODEX_HOME'] == str(tmp_path / 'codex-decoy')   # not re-pointed
    assert 'ANTHROPIC_API_KEY' not in env                 # the login-shadowing key goes
    assert 'OPENAI_API_KEY' in env                        # another harness's key stays
    # the parent environment is untouched by a child-env build
    assert os.environ['CLAUDE_CONFIG_DIR'] == ambient
    assert 'ANTHROPIC_API_KEY' in os.environ

    # the TUI path carries the same contract, with its own 60 s cap
    prog = _Recorder(results=[('added', False)])
    monkeypatch.setattr(mcp_mod, 'run_with_progress', prog)
    out, cancelled = mcp_mod._mcp_run(['get', 'srv'], 'Loading srv...', cfgdir=home)
    assert (out, cancelled) == ('added', False)
    argv, kw = prog.calls[0]
    assert argv[0] == [fake_exe, 'mcp', 'get', 'srv']
    assert argv[1] == ('ARCHEUS', 'MCP') and 'Loading srv...' in argv[2]
    assert kw['timeout'] == 60
    assert kw['env']['CLAUDE_CONFIG_DIR'] == home
    assert 'ANTHROPIC_API_KEY' not in kw['env']

    # a Codex home is selected by ITS variable, on the same code path
    codex_home = str(tmp_path / 'codex-acct')
    ofs, _exes = _codex_home(monkeypatch, codex_home)
    runs2 = _Recorder(results=[_Result(stdout='codex ok')])
    monkeypatch.setattr(proc, 'run', runs2)
    ok, out = mcp_mod.mcp_cli(['list'], cfgdir=codex_home)
    assert (ok, out) == (True, 'codex ok')
    argv, kw = runs2.calls[0]
    assert argv[0] == ['C:\\fake\\codex.exe', 'mcp', 'list']
    assert ofs.calls[0][0][0] == codex_home               # the asked-about home
    assert kw['env']['CODEX_HOME'] == codex_home
    assert 'OPENAI_API_KEY' not in kw['env']
    assert kw['env']['CLAUDE_CONFIG_DIR'] == ambient      # Claude's selector untouched


# ── 2. remove confirmation (mcp.py:379-384) ─────────────────

def test_declined_removal_confirmation_runs_nothing_and_promise_nothing(monkeypatch,
                                                                         tmp_path):
    """mcp.py:381 `if scope and confirm(...)` — removing this guard deletes an
    MCP server from the user's config on a declined prompt; the assertion fails
    when the guard is inverted or the remove argv is built anyway."""
    Sandbox(monkeypatch, tmp_path)
    ui = _Ui(monkeypatch, menus=['user'], runs=[('name: inv-srv\n', False)],
             confirms=[False], pager_keys=['d', None])
    mcp_mod._mcp_detail('inv-srv')

    assert [a[0] for a, _k in ui.mcp_run.calls] == [['get', 'inv-srv']]   # the read only
    assert not [a for a, _k in ui.mcp_run.calls if a[0] and a[0][0] == 'remove']
    assert len(ui.confirm) == 1
    question, kwargs = ui.confirm.calls[0]
    assert kwargs.get('danger') is True                   # a destructive ask
    assert 'inv-srv' in question[0] and 'user' in question[0]
    assert not any(m.startswith('Removed') for m, _ok in ui.flashes())
    assert len(ui.pager) == 2                             # re-asked, not pretended-done
    assert ui.pager.calls[0][1]['extra_keys'] == ('d', 't')

    # a cancelled scope never reaches the confirmation at all
    ui = _Ui(monkeypatch, menus=[None], runs=[('name: inv-srv\n', False)],
             pager_keys=['d', None])
    mcp_mod._mcp_detail('inv-srv')
    assert ui.confirm.calls == []
    assert [a[0] for a, _k in ui.mcp_run.calls] == [['get', 'inv-srv']]
    assert ui.flashes() == []


# ── 3. missing harness executable (mcp.py:261-263) ──────────

def test_mcp_cli_missing_harness_exe_denies_without_touching_claude(monkeypatch,
                                                                    tmp_path):
    """mcp.py:261-263 — the missing-binary gate for a NON-default home. Drop it
    and `mcp_cli` runs `codex mcp list` with Claude's argv, or run the default
    binary against a Codex home; both mutate a CLI the user never picked."""
    Sandbox(monkeypatch, tmp_path)
    home = str(tmp_path / 'codex-acct')
    ofs, _exes = _codex_home(monkeypatch, home, exe=None)
    claude_consulted = []
    monkeypatch.setattr(mcp_mod, 'get_claude_exe',
                        lambda: (claude_consulted.append(1), 'C:\\claude.exe')[1])
    runs = _Recorder(results=[_Result(stdout='MUST NOT RUN')])
    monkeypatch.setattr(proc, 'run', runs)

    ok, out = mcp_mod.mcp_cli(['add', '-s', 'user', '-t', 'stdio', 'srv', '--', 'npx', 'x'],
                              cfgdir=home)
    assert ok is False
    assert out == 'codex.exe not found'                   # the descriptor's OWN name
    assert runs.calls == []                               # nothing was spawned
    assert claude_consulted == []                         # no fallback to Claude
    assert ofs.calls[0][0][0] == home


# ── 4. mcp_cli failure mapping (mcp.py:264-267) ─────────────

def test_mcp_cli_gave_up_runner_and_nonzero_exit_both_deny(monkeypatch, tmp_path):
    """mcp.py:265-266 (`r is None`) + 267 (`returncode == 0`) — a `proc.run`
    that gave up (timeout, binary gone from PATH) or exited non-zero must deny.
    Invert either and a refused `claude mcp remove` is reported to the GUI as
    done, and the caller's timeout is silently replaced by the 60 s default."""
    Sandbox(monkeypatch, tmp_path)
    home = str(tmp_path / 'acct-b')
    runs = _Recorder(results=[_Result(stdout='ok'),
                              _Result(returncode=1, stdout='no server named srv\n',
                                      stderr='error: not found\n'),
                              _Result(returncode=0, stdout=None, stderr=None)])
    monkeypatch.setattr(proc, 'run', runs)

    ok, out = mcp_mod.mcp_cli(['list'], cfgdir=home)
    assert (ok, out) == (True, 'ok')
    assert runs.kw(0)['timeout'] == 60                    # the documented default

    # a non-zero exit denies, with BOTH streams merged for the caller to read
    ok, out = mcp_mod.mcp_cli(['remove', 'srv', '-s', 'user'], cfgdir=home, timeout=30)
    assert ok is False and out == 'no server named srv\nerror: not found'
    assert runs.kw(1)['timeout'] == 30                    # the caller's cap is forwarded

    # a success whose streams are absent must not raise out of line 267
    ok, out = mcp_mod.mcp_cli(['list'], cfgdir=home)
    assert (ok, out) == (True, '')

    # and the gave-up answer (None) is a denial, never an empty success
    runs2 = _Recorder(results=[None, None])
    monkeypatch.setattr(proc, 'run', runs2)
    ok, out = mcp_mod.mcp_cli(['remove', 'srv', '-s', 'user'], cfgdir=home, timeout=15)
    assert ok is False and out == 'could not run Claude Code'
    assert runs2.kw(0)['timeout'] == 15
    # no child was ever started, so nothing was written and nothing is claimed
    ok, out = mcp_mod.mcp_cli(['add', '-s', 'user', '-t', 'stdio', 'srv', '--', 'npx', 'x'],
                              cfgdir=home)
    assert ok is False and out == 'could not run Claude Code'


# ── 5. cancel after the argv is built, and cancel honesty (mcp.py:335-339, 349-354) ──

def test_add_flow_cancels_are_inert_and_a_runner_cancel_is_never_an_add(monkeypatch,
                                                                        tmp_path):
    """mcp.py:335-336 + 338-339 (cancel at the target/scope prompt, with the
    argv already complete) and 349-354 (the `cancelled` flag). Remove the
    `if scope is None: return` guard and a cancelled add is WRITTEN to the
    account; ignore `cancelled` and an ESC'd add still flashes "Added srv"."""
    Sandbox(monkeypatch, tmp_path)

    # (a) cancel at the command/URL prompt: the scope menu is never asked
    ui = _Ui(monkeypatch, inputs=['srv', None], menus=['stdio', 'user'],
             runs=[('added', False)])
    mcp_mod._mcp_add_flow()
    assert len(ui.menu) == 1 and ui.mcp_run.calls == [] and ui.flashes() == []

    # (b) cancel at the scope prompt, with name+transport+target already collected
    ui = _Ui(monkeypatch, inputs=['srv', 'npx -y invented-server'], menus=['stdio', None],
             runs=[('added', False)])
    mcp_mod._mcp_add_flow()
    assert len(ui.menu) == 2 and ui.mcp_run.calls == [] and ui.flashes() == []

    # (c) ESC while the child runs: Cancelled, and nothing that reads as an add
    ui = _Ui(monkeypatch, inputs=['srv', 'npx -y invented-server', ''],
             menus=['stdio', 'user'], runs=[(None, True)])
    mcp_mod._mcp_add_flow()
    assert len(ui.mcp_run) == 1
    assert ('Cancelled', False) in ui.flashes()
    assert not any('Added' in m for m, _ok in ui.flashes())

    # (d) the runner gave up (timeout / launch failure): Add failed, NOT Cancelled
    ui = _Ui(monkeypatch, inputs=['srv', 'npx -y invented-server', ''],
             menus=['stdio', 'user'], runs=[(None, False)])
    mcp_mod._mcp_add_flow()
    assert ('Add failed', False) in ui.flashes()
    assert not any('Cancelled' in m for m, _ok in ui.flashes())

    # (e) the success line still says Added, with the name in it
    ui = _Ui(monkeypatch, inputs=['srv', 'npx -y invented-server', ''],
             menus=['stdio', 'user'], runs=[('added', False)])
    mcp_mod._mcp_add_flow()
    assert ('Added srv', True) in ui.flashes()


# ── 6. stdio argv boundaries (mcp.py:341-345, 357-363, 369) ─

def test_add_stdio_keeps_argv_boundaries_and_extras_before_the_double_dash(monkeypatch,
                                                                           tmp_path):
    """mcp.py:344-345 (`parts = target.split()`, `['--', *parts]`) + 362-363 +
    369 (`args[:3] + extra + args[3:]`). Append the extras instead of inserting
    them and `-e KEY=1` lands INSIDE the server command's own argv; join the
    command into one string and the server never starts."""
    Sandbox(monkeypatch, tmp_path)
    ui = _Ui(monkeypatch, inputs=['inv-srv', 'npx -y invented-server', 'KEY=1 OTHER=2'],
             menus=['stdio', 'project'], runs=[('added', False)])
    mcp_mod._mcp_add_flow()

    assert len(ui.mcp_run) == 1
    args, kwargs = ui.mcp_run.calls[0]
    argv = args[0]
    assert argv == ['add', '-s', 'project', '-e', 'KEY=1', '-e', 'OTHER=2',
                    '-t', 'stdio', 'inv-srv', '--', 'npx', '-y', 'invented-server']
    assert all(isinstance(a, str) for a in argv)
    assert argv.count('--') == 1
    edge = argv.index('--')
    assert '-e' not in argv[edge:] and '-s' not in argv[edge:] and '-t' not in argv[edge:]
    assert argv[edge + 1:] == ['npx', '-y', 'invented-server']    # one token, one element
    assert all(' ' not in a for a in argv[edge + 1:])             # never re-joined
    assert 'inv-srv' in args[1]                                   # the progress label

    # a blank env prompt adds neither `-e` nor an empty argv element
    ui = _Ui(monkeypatch, inputs=['inv-srv', 'npx -y invented-server', ''],
             menus=['stdio', 'project'], runs=[('added', False)])
    mcp_mod._mcp_add_flow()
    argv2 = ui.mcp_run.calls[0][0][0]
    assert argv2 == ['add', '-s', 'project', '-t', 'stdio', 'inv-srv', '--',
                     'npx', '-y', 'invented-server']
    assert '-e' not in argv2 and '' not in argv2


@pytest.mark.xfail(strict=True,
                   reason='source defect mcp.py:362 — `for kv in env.split()` raises '
                          'AttributeError when ui.text_input returns None on ESC '
                          '(ui.py:445-446 returns None on esc); every other prompt of this '
                          'flow (mcp.py:326, 335, 338, 366) treats a cancel as an inert '
                          'exit, so the stdio env prompt must too')
def test_add_stdio_cancel_at_the_env_prompt_is_inert_not_a_crash(monkeypatch, tmp_path):
    """mcp.py:360-363 — ESC at "Env vars KEY=VAL" must exit the add the way the
    name/target/scope cancels do, not raise out of the manager."""
    Sandbox(monkeypatch, tmp_path)
    ui = _Ui(monkeypatch, inputs=['inv-srv', 'npx -y invented-server', None],
             menus=['stdio', 'project'], runs=[('added', False)])
    mcp_mod._mcp_add_flow()
    assert ui.mcp_run.calls == []
    assert not any('Added' in m for m, _ok in ui.flashes())


# ── 7. http/sse header argv integrity (mcp.py:364-367) ───────

def test_add_http_header_is_one_argv_element_and_blank_adds_nothing(monkeypatch,
                                                                    tmp_path):
    """mcp.py:366-367 (`extra += ['-H', hdr]`). Split the header on its space —
    the shape `env.split()` uses two lines above — and the credential is cut in
    half while `Bearer`/`x` become positional argv the CLI parses as its own."""
    Sandbox(monkeypatch, tmp_path)
    url = 'https://mcp.invalid/x'
    hdr = 'Authorization: Bearer invented-token'
    ui = _Ui(monkeypatch, inputs=['hdr-srv', url, hdr], menus=['http', 'user'],
             runs=[('added', False)])
    mcp_mod._mcp_add_flow()

    argv = ui.mcp_run.calls[0][0][0]
    assert argv == ['add', '-s', 'user', '-H', hdr, '-t', 'http', 'hdr-srv', url]
    edge = argv.index('-H')
    assert argv[edge + 1] == hdr                          # spaces kept inside one element
    assert 'Bearer' not in argv and 'Authorization:' not in argv
    assert argv.count(url) == 1                           # the URL was not split either

    # a blank header asks for nothing, and leaves no empty element behind
    ui = _Ui(monkeypatch, inputs=['hdr-srv', url, ''], menus=['sse', 'local'],
             runs=[('added', False)])
    mcp_mod._mcp_add_flow()
    argv2 = ui.mcp_run.calls[0][0][0]
    assert argv2 == ['add', '-s', 'local', '-t', 'sse', 'hdr-srv', url]
    assert '-H' not in argv2 and '' not in argv2


# ── 8. _mcp_run with no executable (mcp.py:272-274) ─────────

def test_mcp_run_without_a_binary_denies_without_spawning_or_cancelling(monkeypatch,
                                                                        tmp_path):
    """mcp.py:273-274 — no claude.exe must answer (None, False) before the
    progress runner. Return (None, True) here and every caller flashes
    "Cancelled" for a machine that never had the binary; call the runner and
    the argv is built around a None executable."""
    Sandbox(monkeypatch, tmp_path)
    monkeypatch.setattr(mcp_mod, 'get_claude_exe', lambda: None)
    prog = _Recorder(results=[('NEVER', False)])
    monkeypatch.setattr(mcp_mod, 'run_with_progress', prog)

    out, cancelled = mcp_mod._mcp_run(['remove', 'srv', '-s', 'user'], 'Removing srv...')
    assert out is None
    assert cancelled is False             # a missing binary is not a user cancel
    assert prog.calls == []               # and nothing was asked to run


# ── 9-10. cancel at the first two prompts (mcp.py:326-327, 329-330) ──

def test_add_flow_cancel_at_the_name_prompt_asks_nothing_further(monkeypatch, tmp_path):
    """mcp.py:326-327 — an empty/cancelled name returns. Drop it and the flow
    collects a transport, a command and a scope and then runs `claude mcp add`
    with an empty server name."""
    Sandbox(monkeypatch, tmp_path)
    ui = _Ui(monkeypatch, inputs=[None], menus=['stdio', 'user'],
             runs=[('added', False)])
    mcp_mod._mcp_add_flow()
    assert len(ui.text_input) == 1        # the name prompt, and nothing after it
    assert ui.menu.calls == []            # the transport menu was never drawn
    assert ui.mcp_run.calls == []
    assert ui.flashes() == []

    # Enter on an empty buffer is the same denial (ui.py:443-444 returns '' stripped)
    ui = _Ui(monkeypatch, inputs=[''], menus=['stdio', 'user'],
             runs=[('added', False)])
    mcp_mod._mcp_add_flow()
    assert ui.menu.calls == [] and ui.mcp_run.calls == [] and ui.flashes() == []


def test_add_flow_cancel_at_the_transport_prompt_asks_nothing_further(monkeypatch,
                                                                      tmp_path):
    """mcp.py:329-330 — ESC out of the transport menu returns before any target
    prompt. Remove the guard and `transport` is None, the URL prompt is drawn
    for a transport the user refused, and the add runs with `-t None`."""
    Sandbox(monkeypatch, tmp_path)
    ui = _Ui(monkeypatch, inputs=['srv', 'npx -y invented-server'], menus=[None, 'user'],
             runs=[('added', False)])
    mcp_mod._mcp_add_flow()
    assert len(ui.menu) == 1
    assert ui.menu.calls[0][0][0] == [(t, t) for t in mcp_mod.MCP_TRANSPORTS]
    assert len(ui.text_input) == 1        # the target prompt was never asked
    assert ui.mcp_run.calls == []
    assert ui.flashes() == []

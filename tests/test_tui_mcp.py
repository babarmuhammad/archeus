import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from harness import Sandbox, run_flow, typed, UP, DOWN, RIGHT, ENTER, ESC

from claude_sessions import mcp as mcp_mod


def flat(*parts):
    out = []
    for p in parts:
        out.extend(p)
    return out


def fake_run(monkeypatch, calls):
    """Capture mcp args; return canned (stdout, cancelled)."""
    def _run(args, label, crumbs=('ARCHEUS', 'MCP')):
        calls.append(list(args))
        return ('ok', False)
    monkeypatch.setattr(mcp_mod, '_mcp_run', _run)


def test_add_stdio_server_argv(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    monkeypatch.setattr(mcp_mod, 'get_claude_exe', lambda: r'C:\fake.exe')
    calls = []
    fake_run(monkeypatch, calls)
    monkeypatch.setattr(mcp_mod, 'get_mcp_status', lambda *a: [])
    # Add: name -> transport(stdio, first) -> command -> scope(local, first)
    # -> env (blank)
    keys = flat(ENTER,                            # Add MCP server (first selectable)
                typed('myserver'), ENTER,         # name
                ENTER,                            # transport: stdio (first)
                typed('npx my-mcp'), ENTER,       # command
                ENTER,                            # scope: local (first)
                ENTER,                            # env blank
                ESC)                              # leave manager
    run_flow(monkeypatch, keys, mcp_mod.mcp_manager_menu)
    assert calls, "no mcp command issued"
    a = calls[0]
    assert a[0] == 'add' and 'myserver' in a
    assert '-s' in a and a[a.index('-s') + 1] == 'local'
    assert '-t' in a and a[a.index('-t') + 1] == 'stdio'
    assert '--' in a and 'npx' in a and 'my-mcp' in a


def test_add_http_server_with_header(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    monkeypatch.setattr(mcp_mod, 'get_claude_exe', lambda: r'C:\fake.exe')
    monkeypatch.setattr(mcp_mod, 'get_mcp_status', lambda *a: [])
    calls = []
    fake_run(monkeypatch, calls)
    keys = flat(ENTER,                             # Add MCP server (first selectable)
                typed('sentry'), ENTER,            # name
                DOWN, ENTER,                       # transport: http (second)
                typed('https://mcp.sentry.dev/mcp'), ENTER,  # url
                DOWN, ENTER,                       # scope: user (second)
                typed('Authorization: Bearer x'), ENTER,     # header
                ESC)
    run_flow(monkeypatch, keys, mcp_mod.mcp_manager_menu)
    a = calls[0]
    assert a[0] == 'add'
    assert a[a.index('-t') + 1] == 'http'
    assert a[a.index('-s') + 1] == 'user'
    assert '-H' in a and 'https://mcp.sentry.dev/mcp' in a


def test_remove_server_argv(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    monkeypatch.setattr(mcp_mod, 'get_claude_exe', lambda: r'C:\fake.exe')
    monkeypatch.setattr(mcp_mod, 'get_mcp_status', lambda *a: [('foo', 'ok')])
    calls = []
    fake_run(monkeypatch, calls)
    # open detail of 'foo' (first srv row), get is called, then d -> scope -> confirm yes
    keys = flat(ENTER,                  # select first server row -> detail (get)
                typed('d'),             # remove
                ENTER,                  # scope local (first)
                RIGHT, ENTER,           # confirm: No->Yes
                )
    run_flow(monkeypatch, keys, mcp_mod.mcp_manager_menu)
    # calls[0] = get foo, calls[1] = remove foo -s local
    assert any(c[0] == 'get' and 'foo' in c for c in calls)
    rem = [c for c in calls if c[0] == 'remove']
    assert rem and 'foo' in rem[0] and rem[0][rem[0].index('-s') + 1] == 'local'


def test_manager_no_claude(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    monkeypatch.setattr(mcp_mod, 'get_claude_exe', lambda: None)
    _, cap, _ = run_flow(monkeypatch, flat(ENTER), mcp_mod.mcp_manager_menu)
    assert 'not found' in cap.plain.lower()


def test_status_line_error_flag(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    monkeypatch.setattr(mcp_mod, '_mcp_error', True)
    monkeypatch.setattr(mcp_mod, '_mcp_ready', True)
    assert 'unavailable' in mcp_mod.mcp_status_line()


# ── the real parser (every other MCP test stubs get_mcp_status) ──

_LIST_OUTPUT = """Checking MCP server health...

notion: https://mcp.notion.com/mcp (HTTP) - ✔ Connected
asana: https://mcp.asana.com/sse (SSE) - ! Needs authentication
broken-one: npx -y some-server - ✘ Failed to connect
timed-out: npx -y other-server - Connection timed out
"""


def _fake_claude(monkeypatch, stdout, stderr=''):
    import subprocess
    class R:
        pass
    r = R()
    r.stdout, r.stderr, r.returncode = stdout, stderr, 0
    monkeypatch.setattr(mcp_mod, 'get_claude_exe', lambda: 'claude.exe')
    monkeypatch.setattr(subprocess, 'run', lambda *a, **k: r)


def test_a_failed_server_is_listed_not_dropped(monkeypatch):
    """`✘ Failed to connect` and `Connection timed out` matched neither branch,
    so those servers vanished from the list entirely — the one state the user
    most needs to see."""
    _fake_claude(monkeypatch, _LIST_OUTPUT)
    got = dict(mcp_mod.get_mcp_status())
    assert got == {'notion': 'ok', 'asana': 'auth',
                   'broken-one': 'fail', 'timed-out': 'fail'}


def test_status_icons_are_distinct_per_state():
    icons = {s: mcp_mod._status_icon(s) for s in ('ok', 'auth', 'fail')}
    assert len(set(icons.values())) == 3
    assert '✔' in icons['ok'] and '!' in icons['auth'] and '✘' in icons['fail']


def test_parser_skips_the_header_and_blank_lines(monkeypatch):
    _fake_claude(monkeypatch, 'Checking MCP server health...\n\n\n')
    assert mcp_mod.get_mcp_status() == []

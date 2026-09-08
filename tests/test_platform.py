"""The POSIX port, checked from whichever platform is running the suite.

The Windows half is exercised by the whole TUI suite. This file covers the
half that CI's Windows runners cannot reach by running it directly: the escape
decoder, the platform tables, and the seams that must stay single.
"""

import ast
import io
import os
import sys

import pytest

from claude_sessions import term

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   'claude_sessions')


class Feed:
    """Scripted bytes for the POSIX decoder.

    `getch` past the end BLOCKS on a real terminal — that is the whole reason
    the lookahead after an Escape must be the timed read — so here it raises
    instead. `timeout` past the end returns b'', which is what a bare Escape
    keypress actually looks like.
    """

    def __init__(self, data):
        self.data = list(data)

    def getch(self):
        if not self.data:
            raise AssertionError('a blocking read past the end of the input')
        return bytes([self.data.pop(0)])

    def timeout(self, _secs):
        return bytes([self.data.pop(0)]) if self.data else b''

    def install(self, monkeypatch):
        monkeypatch.setattr(term, 'BACKEND', 'posix')
        monkeypatch.setattr(term, 'getch', self.getch)
        monkeypatch.setattr(term, '_getch_timeout', self.timeout)


@pytest.mark.parametrize('seq,expected', [
    (b'\x1b[A', ('up',)),
    (b'\x1b[B', ('down',)),
    (b'\x1b[C', ('right',)),
    (b'\x1b[D', ('left',)),
    (b'\x1bOA', ('up',)),          # SS3 — what some terminals send in app mode
    (b'\x1b[3~', ('del',)),
    (b'\r', ('enter',)),
    (b'\n', ('enter',)),
    (b'\t', ('tab',)),
    (b'\x7f', ('back',)),          # POSIX Backspace is DEL, not BS
    (b'\x08', ('back',)),
    (b'x', ('char', 'x')),
])
def test_the_posix_decoder_speaks_the_same_event_vocabulary(seq, expected, monkeypatch):
    Feed(seq).install(monkeypatch)
    assert term.key_event() == expected


def test_a_bare_escape_is_escape_not_a_swallowed_arrow(monkeypatch):
    """The only thing separating the two is that nothing follows an Escape."""
    Feed(b'\x1b').install(monkeypatch)
    assert term.key_event() == ('esc',)


def test_escape_then_a_real_arrow_still_reads_as_an_arrow(monkeypatch):
    Feed(b'\x1b[A').install(monkeypatch)
    assert term.key_event() == ('up',)


def test_a_non_ascii_character_is_rebuilt_from_its_continuation_bytes(monkeypatch):
    Feed('è'.encode('utf-8')).install(monkeypatch)
    assert term.key_event() == ('char', 'è')


def test_a_four_byte_character_survives(monkeypatch):
    Feed('🙂'.encode('utf-8')).install(monkeypatch)
    assert term.key_event() == ('char', '🙂')


def test_the_windows_decoder_is_still_reachable_from_either_platform(monkeypatch):
    monkeypatch.setattr(term, 'BACKEND', 'windows')
    feed = Feed(b'\xe0H')
    monkeypatch.setattr(term, 'getch', feed.getch)
    assert term.key_event() == ('up',)


# ── the seams that must stay single ──────────────────────────

def _modules(root):
    for name in sorted(os.listdir(root)):
        if name.endswith('.py'):
            yield name, io.open(os.path.join(root, name), encoding='utf-8').read()


def test_only_term_imports_msvcrt():
    """It was `ui.py`'s import, and ui is imported by every screen — so on
    POSIX this one line made the entire package unimportable."""
    offenders = []
    for name, src in _modules(SRC):
        if name == 'term.py':
            continue
        for node in ast.walk(ast.parse(src)):
            if isinstance(node, ast.Import):
                offenders += ['%s:%d' % (name, node.lineno)
                              for a in node.names if a.name == 'msvcrt']
    assert not offenders, 'msvcrt imported outside term.py: ' + ', '.join(offenders)


def test_the_test_harness_does_not_import_msvcrt():
    """Every TUI test file imports harness, so a module-level `import msvcrt`
    there means POSIX collects ZERO tests — and a suite that collects nothing
    still reports success."""
    src = io.open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               'harness.py'), encoding='utf-8').read()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Import):
            assert all(a.name != 'msvcrt' for a in node.names)


def test_no_module_calls_os_system_unguarded():
    """`os.system('cls')` and `chcp 65001` are cmd builtins. Unguarded, they
    print an error to the user's terminal on every screen clear."""
    offenders = []
    for name, src in _modules(SRC):
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == 'system'
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == 'os'):
                # must sit under an `if os.name == 'nt'` / WINDOWS branch
                guarded = any(
                    isinstance(p, ast.If) and 'nt' in ast.dump(p.test)
                    for p in ast.walk(tree)
                    if isinstance(p, ast.If) and node in list(ast.walk(p)))
                if not guarded:
                    offenders.append('%s:%d' % (name, node.lineno))
    assert not offenders, 'unguarded os.system: ' + ', '.join(offenders)


# ── platform tables ──────────────────────────────────────────

def test_the_beep_hook_is_not_powershell_everywhere():
    from claude_sessions import hooks
    cmd = hooks.TEMPLATES['notify-on-stop']['entry']['hooks'][0]['command']
    if os.name == 'nt':
        assert 'powershell' in cmd
    else:
        assert 'powershell' not in cmd
    twice = hooks.TEMPLATES['notify-on-input-needed']['entry']['hooks'][0]['command']
    assert twice != cmd, 'the double-beep must differ from the single'


def test_the_claude_binary_has_no_exe_suffix_off_windows(monkeypatch, tmp_path):
    from claude_sessions import config
    monkeypatch.setattr(config, 'load_settings', lambda: {})
    monkeypatch.setattr(config, '_USERPROFILE', str(tmp_path))
    monkeypatch.setattr(config.shutil, 'which', lambda n: None)
    bindir = tmp_path / '.local' / 'bin'
    bindir.mkdir(parents=True)
    name = 'claude.exe' if os.name == 'nt' else 'claude'
    (bindir / name).write_text('#!', encoding='utf-8')
    assert config.get_claude_exe() == str(bindir / name)


def test_the_editor_table_is_per_platform():
    from claude_sessions import config
    cands = [c for c in config._editor_candidates() if c]
    joined = ' '.join(cands).lower()
    if os.name == 'nt':
        assert 'notepad' in joined
    else:
        assert 'notepad' not in joined


def test_spawn_terminal_never_reaches_a_windows_shell_off_windows(monkeypatch):
    """The four hand-rolled `cmd /c start` copies are the reason proc.py
    exists; only its Windows branch may emit one."""
    from claude_sessions import proc
    seen = {}

    class FakePopen:
        def __init__(self, argv, **kw):
            seen['argv'] = argv

    monkeypatch.setattr(proc.subprocess, 'Popen', FakePopen)
    monkeypatch.setattr(proc, 'WINDOWS', False)
    monkeypatch.setattr(sys, 'platform', 'linux')
    monkeypatch.setattr(proc.os.environ, 'get', lambda k, d=None: None)
    proc.spawn_terminal(['claude'], cwd=None, title='t')
    assert 'cmd' not in seen['argv']


def test_kill_tree_never_signals_our_own_process_group(monkeypatch):
    """os.killpg on a child that is NOT its own group leader takes archeus
    down with it — the child's group is ours."""
    from claude_sessions import proc
    killed = []

    class P:
        pid = 4242
        def poll(self): return None
        def kill(self): killed.append('direct')

    monkeypatch.setattr(proc, 'WINDOWS', False)
    monkeypatch.setattr(proc.os, 'getpgid', lambda pid: 1, raising=False)
    monkeypatch.setattr(proc.os, 'killpg',
                        lambda *a: killed.append('GROUP'), raising=False)
    proc.kill_tree(P())
    assert killed == ['direct'], 'killpg was used on a non-leader child'


def test_no_module_references_a_windows_only_constant_outside_a_windows_branch():
    """`subprocess.CREATE_NO_WINDOW` does not exist on POSIX, so a bare
    reference raises AttributeError at the CALL, not at import.

    mcp.get_mcp_status did exactly that inside a `try/except Exception: return
    []`, so every MCP server silently vanished from the list on macOS and Linux
    — an empty list, no error, nothing to notice for a whole release.

    Two forms are safe and both are in use: `getattr(subprocess, NAME, 0)`, and
    a plain reference inside an `if os.name == 'nt'` / `if WINDOWS` block (the
    editor spawn in config.py). Only an unguarded bare reference is a fault.
    """
    win_only = {'CREATE_NO_WINDOW', 'CREATE_NEW_CONSOLE', 'CREATE_NEW_PROCESS_GROUP',
                'STARTUPINFO', 'STARTF_USESHOWWINDOW', 'DETACHED_PROCESS'}

    def guarded_lines(tree):
        """Line numbers inside a branch that only runs on Windows."""
        out = set()
        for node in ast.walk(tree):
            if not isinstance(node, ast.If):
                continue
            t = ast.dump(node.test)
            if "'nt'" in t or "id='WINDOWS'" in t or "attr='WINDOWS'" in t:
                for stmt in node.body:
                    for sub in ast.walk(stmt):
                        if hasattr(sub, 'lineno'):
                            out.add(sub.lineno)
        return out

    bad = []
    for name in sorted(os.listdir(SRC)):
        if not name.endswith('.py'):
            continue
        tree = ast.parse(io.open(os.path.join(SRC, name), encoding='utf-8').read())
        safe = guarded_lines(tree)
        for node in ast.walk(tree):
            if (isinstance(node, ast.Attribute) and node.attr in win_only
                    and isinstance(node.value, ast.Name)
                    and node.value.id == 'subprocess'
                    and node.lineno not in safe):
                bad.append('%s:%d subprocess.%s' % (name, node.lineno, node.attr))
    assert not bad, ('use getattr(subprocess, NAME, 0) or an os.name check — '
                     'these raise on POSIX: %s' % bad)

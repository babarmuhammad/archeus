"""The TUI holds no shadow system (p17-design-gate §11) and reads the one set of
tables (A1): it imports no Core module, opens no file, keeps the generated
tables equal to their JSON sources, gives every destination a screen, keeps the
ASCII fallback injective, posts nothing by being connected, and always gives
the terminal back."""

import ast
import json
import os
import sys

import pytest

from archeus.cli.tui import _tables, app as A, screens as SC
from archeus.cli.tui.view import Style

from .conftest import app_on, spy

ROOT = os.path.join(os.path.dirname(__file__), '..', '..', '..')
TUI = os.path.join(ROOT, 'archeus', 'cli', 'tui')
TOKENS = os.path.join(ROOT, 'clients', 'app', 'tokens')
#: what the TUI may import beyond the standard library and itself
ALLOWED = {'archeus.infra.discovery', 'claude_sessions.render', 'claude_sessions.term'}


def _modules():
    for name in sorted(os.listdir(TUI)):
        if name.endswith('.py'):
            path = os.path.join(TUI, name)
            with open(path, encoding='utf-8') as f:
                yield name, ast.parse(f.read(), path)


def _imports(tree):
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                yield a.name
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                for a in node.names:
                    yield '%s.%s' % (node.module, a.name) if node.module else a.name
            elif node.level == 1:
                yield 'archeus.cli.tui'
            else:
                base = ['archeus', 'cli', 'tui'][:-(node.level - 1)]
                mod = '.'.join(base + ([node.module] if node.module else []))
                for a in node.names:
                    yield '%s.%s' % (mod, a.name)


def test_the_tui_imports_the_standard_library_itself_and_three_seams_only():
    bad = []
    for name, tree in _modules():
        for imp in _imports(tree):
            top = imp.split('.')[0]
            if top in sys.stdlib_module_names or imp.startswith('archeus.cli.tui'):
                continue
            if not any(imp == a or imp.startswith(a + '.') for a in ALLOWED):
                bad.append((name, imp))
    assert not bad, 'the TUI reaches Core only over HTTP: %s' % bad


def test_the_tui_opens_no_file_and_reads_nothing_under_the_home():
    """Redaction and state are Core's: the TUI reads the token and core.json
    through discovery, and nothing else from disk."""
    bad = []
    for name, tree in _modules():
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                f = node.func
                if (isinstance(f, ast.Name) and f.id == 'open') or (
                        isinstance(f, ast.Attribute) and f.attr in (
                            'read_text', 'read_bytes', 'listdir', 'scandir', 'archeus_home')):
                    bad.append((name, node.lineno))
            if isinstance(node, ast.Name) and node.id == 'paths':
                bad.append((name, node.lineno))
    assert not bad, bad


def _json(name):
    with open(os.path.join(TOKENS, name), encoding='utf-8') as f:
        return json.load(f)


def test_the_generated_tables_are_the_json_the_spa_reads():
    nav, inv = _json('navigation.json'), _json('invalidation.json')
    assert _tables.DESTINATIONS == nav['destinations']
    assert _tables.CONTROL_SECTIONS == nav['control_sections']
    assert _tables.INSPECTOR_TABS == nav['inspector_tabs']
    assert _tables.TABS == nav['tabs']
    assert _tables.RULES == inv['rules']


def test_every_destination_has_its_screen_and_nothing_else_is_one():
    assert set(SC.SCREENS) == {d['id'] for d in _tables.DESTINATIONS}


def test_the_ascii_fallback_tells_apart_what_the_glyphs_tell_apart():
    by_glyph = {}
    for c in _tables.CLASSES.values():
        by_glyph.setdefault(c['glyph'], set()).add(c['ascii'])
    assert all(len(v) == 1 for v in by_glyph.values())
    ascii_glyphs = [next(iter(v)) for v in by_glyph.values()]
    assert len(set(ascii_glyphs)) == len(ascii_glyphs)
    assert all(len(a) == 1 and ord(a) < 128 for a in ascii_glyphs)


def test_being_connected_sends_nothing_presence_is_not_a_session(core):
    app = app_on(core, live=False)
    s = spy(app)
    for sig in ('stream_open', 'frame', 'stream_lost', 'stream_open', 'settled'):
        app.signal(sig)
        app.frame()
    assert not s.posts


def test_the_terminal_is_given_back_on_every_way_out(monkeypatch):
    from claude_sessions import term
    restored = []
    monkeypatch.setattr(term, 'restore', lambda: restored.append(True))
    monkeypatch.setattr(term, 'kbhit', lambda: True)

    def boom():
        raise RuntimeError('a key broke it')
    monkeypatch.setattr(term, 'key_event', boom)
    app = A.App(_NoCore(), Style(), size=lambda: (80, 20), stream=False)
    with pytest.raises(RuntimeError):
        A.run(app, live=False)
    assert restored


class _NoCore:
    def get(self, path):
        from archeus.cli.tui.client import CoreError
        raise CoreError(0, 'network')

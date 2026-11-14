"""Control → Appearance in the TUI (ADR-0044 §6; p19-design-gate B9): the
terminal says which theme it is in — its own, from `--light` or
ARCHEUS_TUI_THEME — offers no command, and reads no app preference."""

from archeus.cli.tui.view import Style

from .conftest import plain
from .test_acceptance import _StubApp


def _app(theme):
    app = _StubApp({})
    app.st = Style(False, theme, False)
    app.go({'view': 'control', 'section': 'appearance'})
    return app


def test_the_terminal_names_its_own_theme_and_motion():
    for theme in ('dark', 'light'):
        app = _app(theme)
        text = plain(app)
        assert '%s — this terminal\'s own' % theme.capitalize() in text
        assert 'Nothing in the terminal moves' in text
        assert not [a for x in app._doc.lines for a in x['acts']]


def test_motion_moved_out_of_about():
    app = _StubApp({})
    app.go({'view': 'control', 'section': 'about'})
    assert 'Nothing in the terminal moves' not in plain(app)


def test_the_terminal_reads_no_app_preference(monkeypatch, tmp_path):
    (tmp_path / 'archeus-appearance').write_text('{"theme": "light"}')
    monkeypatch.setenv('ARCHEUS_HOME', str(tmp_path))
    monkeypatch.delenv('ARCHEUS_TUI_THEME', raising=False)
    assert Style.detect({}, None, True).theme == 'dark'
    assert Style.detect({'ARCHEUS_TUI_THEME': 'light'}, None, True).theme == 'light'

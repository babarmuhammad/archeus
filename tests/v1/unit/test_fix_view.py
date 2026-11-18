"""T-610: clean() removes the bidi marks that reorder text, wrap() fits columns
rather than characters, and an ASCII terminal gets only ASCII."""

from archeus.cli.tui.view import Style, clean, wrap
from claude_sessions import render


def test_clean_removes_the_bidi_marks_that_reorder_text():
    assert clean('run ‏delete‎-db؜.sh') == 'run delete-db.sh'


def test_wide_prose_is_wrapped_by_columns_and_none_of_it_is_lost():
    text = '汉' * 120
    lines = wrap(text, 40, 2)
    assert all(render.disp_width(x) <= 40 for x in lines)
    assert ''.join(x.strip() for x in lines) == text


def test_narrow_prose_wraps_as_before():
    assert wrap('hello world again', 30, 2) == ['  hello world again']
    assert wrap('one two three four', 14, 2) == ['  one two', '  three four']


def test_core_text_on_an_ascii_terminal_is_ascii():
    st = Style(False, 'dark', True)
    out = st.line('✅ done é 汉', 30)
    assert out.isascii()
    assert render.disp_width(out) == 30

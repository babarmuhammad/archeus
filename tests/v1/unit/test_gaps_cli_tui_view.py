"""T-776: the highest-risk uncovered branches of archeus/cli/tui/view.py.

view.py is the one sanitiser and the one styler between Core's strings and a
terminal, and the one place the TUI decides (from the environment and the
output stream) whether it may emit colour or non-ASCII glyphs at all. This file
re-opens the branches tests/v1/unit/test_fix_view.py, tests/v1/tui/
test_security.py, tests/v1/tui/test_appearance.py and tests/v1/tui/
test_acceptance.py (T09) leave open: the fail-closed paths first (`clean` on
None and on unterminated escapes, the refusal of colour and of glyphs that
cannot be trusted, the unknown role, class, theme and codec), then the boundary
values (`_columns` and `wrap` limits, the width floors), then the error paths
(the unknown theme, the unknown encoding, the state with no label).

Same style and fixtures as tests/v1/unit/test_fix_view.py and the T09 tests it
copies `_Tty` from: pure functions and fake streams only. No terminal, no OS
call, no Core, no clock, no thread, no file, and nothing that reads the real
environment — every input is a plain dict or an object with the two attributes
`detect` reads. The expectations are the same on every platform.
"""

import itertools
import re

import pytest

from archeus.cli.tui import view as V
from archeus.cli.tui._tables import CLASSES
from archeus.cli.tui.tokens import COLOURS
from archeus.cli.tui.view import (Style, _columns, clean, clean_lines, encodable, width_of,
                                  wrap)
from claude_sessions import render

# everything a terminal would act on, and the reordering marks: nothing here may
# survive clean() (the same shape tests/v1/tui/test_security.py asserts)
FOREIGN = re.compile('[\x00-\x08\x0b-\x1f\x7f-\x9f\u202a-\u202e\u2066-\u2069]')
SGR = re.compile(r'\x1b\[(?:0|1|38;5;\d+)m')

# every character that introduces or carries an escape sequence, plus ordinary
# text, so the exhaustive sweep below can build sequences and text mixed together
_ALPHABET = ('\x1b', '[', ']', '0', ';', 'm', 'J', '\x07', '\x9b', '\x9c', '\\', 'P', 'a',
             '\r', '\u202e')

#: the Unicode Bidi_Control property, hard-coded so the expectation cannot drift
#: with the unicodedata of whichever Python runs this
BIDI_CONTROL = ('\u061c', '\u200e', '\u200f', '\u202a', '\u202b', '\u202c', '\u202d',
                '\u202e', '\u2066', '\u2067', '\u2068', '\u2069')


class _Stream:
    """Only what view.py reads off an output stream: its encoding and whether it
    is a terminal. Never a real stream, so no test can move a real cursor."""

    def __init__(self, encoding='utf-8', tty=True):
        self.encoding = encoding
        self._tty = tty

    def isatty(self):
        return self._tty


class _NoTty:
    """A stream that cannot answer whether it is a terminal at all."""
    encoding = 'utf-8'


class _CoreText:
    """A value from a Core response that is not a str (JSON gives ints, and the
    occasional object reaches the screen through `str()`)."""

    def __str__(self):
        return 'a\tb\x1b[2Jc'


def _inert(s):
    assert '\x1b' not in s and '\x9b' not in s, repr(s)
    assert not FOREIGN.search(s), (repr(s), FOREIGN.findall(s))


# ── clean(): the injection boundary, fail-closed ─────────────────────────────

def test_clean_of_none_is_an_empty_line_never_the_word_none():
    """view.py:38 `'' if s is None else str(s)` — the None arm. Core can return a
    field with no value; taking the other arm prints `None` on screen as if it
    were the mission's own title."""
    assert clean(None) == ''
    assert clean_lines(None) == ['']
    # and the same arm's other side: a non-str value is stringified, then cleaned
    assert clean(42) == '42'
    assert clean(_CoreText()) == 'a    bc'


@pytest.mark.parametrize('length', [1, 2, 3, 4])
def test_no_string_of_escape_bits_survives_clean(length):
    """view.py:22-29, every alternative of `_SEQ` (CSI, OSC, DCS/SOS/PM/APC, the
    bare-ESC catch-all, 8-bit CSI and the 8-bit DCS/SOS/OSC/PM/APC set) and
    view.py:32 `_CTRL`. Removing any one alternative, or the `?` that makes the
    catch-all's final byte optional (a lone ESC), leaves a live sequence in
    clean()'s output."""
    for combo in itertools.product(_ALPHABET, repeat=length):
        s = ''.join(combo)
        out = clean(s)
        _inert(out)
        assert clean(out) == out, (repr(s), repr(out))     # one pass is enough


_PAYLOADS = {
    'osc-title': ('\x1b]0;owned\x07', True),
    'osc-clip': ('\x1b]52;c;cA\x1b\\', True),
    'osc-open': ('\x1b]8;;http://evil', False),
    'csi-erase': ('\x1b[2J\x1b[H', True),
    'csi-cursor': ('\x1b[10;1H', True),
    'sgr-hide': ('\x1b[8m', True),
    'sgr-open': ('\x1b[38;5;', False),
    'dcs': ('\x1bPq#0;2;0\x1b\\', True),
    'c1-csi': ('\x9b2J', True),
    'c1-apc': ('\x9d0;owned\x9c', True),
    'esc-reset': ('\x1b]', False),
    'charset': ('\x1b(B', True),
    'bell-bs': ('\x07\x08x', True),
    'nul-us': ('\x00\x1f', True),
    'del-c1': ('\x7f\x9f', False),
    'rlo': ('\u202eevil\u202c', True),
    'isolate': ('\u2066x\u2069', True),
}


@pytest.mark.parametrize('name', sorted(_PAYLOADS))
def test_a_named_payload_leaves_nothing_a_terminal_acts_on(name):
    """view.py:38-40, the three substitutions in order (`_SEQ`, then `_BREAK`,
    then `_CTRL`). Inverting the order — `_CTRL` before `_SEQ` — leaves the
    parameters of a split sequence able to rebuild one."""
    payload, tail_survives = _PAYLOADS[name]
    out = clean('before' + payload + 'after')
    _inert(out)
    assert out.startswith('before'), name
    if tail_survives:
        assert out.endswith('after'), name
    else:
        # fail-closed: an unterminated sequence takes the rest of the string with
        # it rather than printing half of it, so the loss is visible and safe
        assert 'after' not in out and 'evil' not in out, name


def test_an_unterminated_sequence_takes_the_rest_of_the_string():
    """view.py:24 and view.py:25, the `(?:\\x07|\\x1b\\\\)?` optional terminator of
    the OSC and DCS alternatives. Make that terminator required and an OSC that
    was never closed stops swallowing, so `0;owned` and everything after it is
    printed as text."""
    assert clean('a\x1b]0;evil title') == 'a'
    assert clean('a\x1bPq#0;2') == 'a'
    # a CSI with no final byte is not a sequence at all: only the ESC goes, and
    # what is left is printable junk, never something the terminal acts on
    assert clean('a\x1b[2') == 'a2'
    _inert(clean('a\x1b[2'))


def test_every_line_break_becomes_one_space_and_a_tab_four_spaces():
    """view.py:30 `_BREAK` and view.py:39, the sub that runs *before* `_CTRL`.
    Drop a character from `_BREAK` (say U+0085) and clean() returns a string the
    caller believes is one line but which moves the cursor down."""
    assert clean('a\tb') == 'a    b'
    assert clean('a\r\nb\x0bc\x0cd\x85e\u2028f\u2029g') == 'a b c d e f g'
    assert '\n' not in clean('a\r\nb') and '\r' not in clean('a\r\nb')
    assert clean(None) == ''


@pytest.mark.parametrize('ch', BIDI_CONTROL, ids=['u%04x' % ord(c) for c in BIDI_CONTROL])
def test_every_bidi_control_character_is_removed(ch):
    """view.py:32 `_CTRL`, the bidirectional half of the class. The five ranges
    (`\\u061c`, `\\u200e\\u200f`, `\\u202a-\\u202e`, `\\u2066-\\u2069`) are what let a
    mission title show characters in the other order; widen the class's upper
    bound by one and one of them stays."""
    assert clean('a' + ch + 'b') == 'ab'                       # control gone
    assert clean('\u05e2' + ch + 'ok') == '\u05e2ok'            # text kept


def test_the_annotation_marks_that_hide_text_are_removed():
    # the three marks go; the visible text between them stays
    assert clean('a\uFFF9hidden\uFFFBb') == 'ahiddenb'
    assert clean('\uFFF9x\uFFFAy\uFFFBz') == 'xyz'


# ── clean_lines and wrap: nothing after the cut may be lost ─────────────────

def test_clean_lines_splits_on_every_break_and_cleans_each_line_on_its_own():
    """view.py:45 `_BREAK.split(...)` — not `str('\\n').split`. A split that only
    knows `\\n` returns a single element containing U+2028 or U+0085, and those
    are then *removed* by clean() instead of ending a line, so two Core lines
    merge into one."""
    assert clean_lines('a\x1b[2Jb\nc') == ['ab', 'c']
    assert clean_lines('a\u2028b') == ['a', 'b']
    assert clean_lines('a\x85b') == ['a', 'b']
    assert clean_lines('a\r\nb') == ['a', 'b']
    assert clean_lines('') == ['']
    for line in clean_lines('one\ntwo\nthree'):
        _inert(line)


@pytest.mark.parametrize('width,indent', [(12, 0), (12, 2), (20, 2), (40, 0)])
def test_wrap_fits_columns_and_loses_no_text(width, indent):
    """view.py:140-143 — textwrap's char count, then `_columns`, then the indent.
    Remove the `_columns` re-split and a line of wide glyphs is `line()`ed to
    the frame and everything after the cut is gone from the screen."""
    text = ('Fix the \u6c49' * 3 + 'well-known-thing ' + '\x1b[2Jtail' + ' '
            + ('\u6c49' * 13) + ' ' + ('word ' * 11))
    lines = wrap(text, width, indent)
    assert lines, 'nothing came back'
    for x in lines:
        assert render.disp_width(x) <= width, repr(x)
        _inert(x)
    assert ''.join(x[:indent] for x in lines) == ' ' * indent * len(lines)
    lost = lambda s: re.sub(r'\s+', '', s)                      # noqa: E731
    assert lost(''.join(lines)) == lost(clean(text))


def test_an_empty_paragraph_still_occupies_a_line():
    """view.py:141 `or ['']` — `textwrap.wrap` returns [] for empty text, so
    without that arm an empty body wraps to *no* lines and the caller's frame
    loses the row it reserved for it."""
    assert wrap('', 20) == ['']
    assert wrap('', 20, 4) == ['    ']                    # the indent is paid even when empty
    assert wrap('\n', 20) == ['', '']                     # one line per break, none invented


def test_a_single_character_wider_than_the_limit_is_kept_not_dropped():
    """view.py:126 `if cur and used + w > limit` — the `cur` guard. Remove it and
    the first character of every piece is pushed into the previous one, or (with
    a zero-width combining mark, `w == 0`) detached from the base it belongs to."""
    assert _columns('\u6c49', 1) == ['\u6c49']                  # 2 columns in a 1-column limit
    assert _columns('\u6c49' * 3, 1) == ['\u6c49'] * 3
    assert _columns('a\u0301' * 3, 1) == ['a\u0301'] * 3         # the mark stays with its base
    assert _columns('', 10) == ['']                              # an empty line is still a line
    assert _columns('abc', 0) == ['a', 'b', 'c']


def test_the_wrap_floor_is_ten_columns_and_the_indent_is_always_paid():
    """view.py:137 `max(10, width - indent)`. Drop the 10 and a narrow hint
    wraps one character per line; drop the `- indent` and the indent pushes the
    line past the frame."""
    assert wrap('x' * 30, 4) == ['x' * 10] * 3
    assert wrap('hello world', 3, 2) == ['  hello', '  world']
    assert wrap('x', -50) == ['x']                               # a negative width cannot crash


# ── Style.detect: refuse colour and glyphs it cannot trust ──────────────────

def test_a_stream_that_cannot_say_it_is_a_terminal_gets_no_colour():
    """view.py:76 `getattr(stream, 'isatty', lambda: False)()` — the default.
    Make it `lambda: True` (or read `stream.isatty` unguarded, which raises) and
    a redirected or closed stdout starts emitting SGR codes into a pipe."""
    assert Style.detect({}, _NoTty(), True).colour is False
    assert Style.detect({}, _Stream(tty=False), True).colour is False
    assert Style.detect({}, _Stream(tty=True), True).colour is True


@pytest.mark.parametrize('given', ['no-such-theme', 'DARK', 'dark ', '', '\x1b[31m', None],
                         ids=['bogus', 'upper', 'trailing', 'empty', 'ansi-code',
                              'unset'])
def test_an_unknown_theme_never_reaches_the_colour_table(given):
    """view.py:79-80 `if theme not in COLOURS: theme = 'dark'` — the only thing
    between an environment value and `COLOURS[self.theme]` at view.py:88, which
    raises KeyError and takes the TUI down at start-up."""
    st = Style.detect({'ARCHEUS_TUI_THEME': given} if given is not None else {},
                      _Stream(), True)
    assert st.theme == 'dark'
    assert st.theme in COLOURS
    # the reason it matters: paint reads COLOURS[self.theme] with no fallback, so a
    # theme that got past this guard would raise KeyError in the first frame
    assert Style(True, st.theme, False).paint('x', 'text') == '\x1b[38;5;255mx\x1b[0m'


def test_the_theme_the_caller_gave_beats_the_environment():
    """view.py:78 `theme or env.get('ARCHEUS_TUI_THEME') or 'dark'` — the
    precedence. Swap the two arms and `--light` (app.py:554 passes it as the
    argument) stops meaning anything on a machine with the other default."""
    assert Style.detect({'ARCHEUS_TUI_THEME': 'light'}, _Stream(), True, 'dark').theme == 'dark'
    assert Style.detect({'ARCHEUS_TUI_THEME': 'light'}, _Stream(), True).theme == 'light'
    assert Style.detect({}, _Stream(), True).theme == 'dark'
    assert Style.detect({'ARCHEUS_TUI_THEME': ''}, _Stream(), True).theme == 'dark'


@pytest.mark.parametrize('given', ['yes', 'true', '0', '1 ', ''],
                         ids=['yes', 'true', 'zero', 'spaced', 'empty'])
def test_only_the_exact_flag_value_forces_ascii_glyphs(given):
    """view.py:81 `env.get('ARCHEUS_TUI_ASCII') == '1'` — the left arm. Accept any
    truthy string and a stray value turns a UTF-8 terminal into ASCII for no
    reason; accept nothing and the flag stops working."""
    assert Style.detect({'ARCHEUS_TUI_ASCII': given}, _Stream('utf-8', True), True).ascii is False
    assert Style.detect({'ARCHEUS_TUI_ASCII': '1'}, _Stream('utf-8', True), True).ascii is True


def test_an_encoding_the_os_cannot_name_is_never_assumed_utf8():
    """view.py:61-62, the `LookupError` arm of encodable(). Drop it and a stream
    reporting a codec Python has never heard of is treated as if it could carry
    every glyph, and an ASCII terminal shows mojibake instead of the table."""
    assert encodable(_Stream('archeus-not-a-codec')) is False
    assert Style.detect({}, _Stream('archeus-not-a-codec', True), True).ascii is True
    # the same question answered from the encoding itself, both ways
    assert encodable(_Stream('utf-8')) is True
    assert encodable(_Stream('cp1252')) is False


@pytest.mark.parametrize('given', ['', None], ids=['empty', 'none'])
def test_a_stream_that_reports_no_encoding_is_probed_as_ascii(given):
    """view.py:59 `getattr(stream, 'encoding', None) or 'ascii'` — the `or`. Read
    the attribute directly and `encoding = None` (a BytesIO-like stdout, which is
    what a captured stream is) raises TypeError instead of deciding ASCII."""
    assert encodable(_Stream(given)) is False
    assert Style.detect({}, _Stream(given, True), True).ascii is True
    assert encodable(None) is False


# ── the styler: what may be emitted, and what a state looks like ────────────

def test_only_a_role_the_theme_knows_emits_a_colour():
    """view.py:88-90 — the `if role else None` guard, the `n is not None` arm and
    the `if code else s` tail. Pass an unknown role through as a colour and a
    Core-supplied role string could inject SGR; emit an empty code and the frame
    fills with reset sequences."""
    st = Style(True, 'dark', False)
    assert st.paint('x', 'no-such-role') == 'x'
    assert st.paint('x', '\x1b[31m') == 'x'                      # a hostile role injects nothing
    assert st.paint('x', '', False) == 'x'                       # falsy role, no bold: no code
    assert st.paint('x', None, True) == '\x1b[1mx\x1b[0m'        # bold alone
    assert st.paint('x', 'state.active', True) == '\x1b[1m\x1b[38;5;75mx\x1b[0m'
    assert st.paint('x', 'text', False) == '\x1b[38;5;255mx\x1b[0m'
    assert Style(False, 'dark', False).paint('x', 'text', True) == 'x'
    assert Style(True, 'light', False).paint('x', 'text') == '\x1b[38;5;233mx\x1b[0m'


def test_core_text_is_cleaned_even_when_nothing_is_styled():
    """view.py:94 `self.paint(clean(s), role, bold)` — the clean must be in `t`,
    before paint's early return at view.py:86. Move it into `paint` and a
    monochrome terminal (the common case: colour is refused far more often than
    granted) prints the escape uncleaned."""
    mono = Style(False, 'dark', False)
    assert mono.t('\x1b[2Jfake prompt') == 'fake prompt'
    assert mono.t(None) == ''
    colour = Style(True, 'dark', False)
    assert colour.t('\x1b[2Jfake prompt', 'text') == '\x1b[38;5;255mfake prompt\x1b[0m'
    # nothing but the TUI's own SGR codes survives, exactly as the frame tests ask
    assert not FOREIGN.search(SGR.sub('', colour.t('\x1b]0;x\x07t', 'text')))


def test_an_unknown_class_or_an_unknown_state_draws_a_question():
    """view.py:98-99 `if c is None or look['glyph'] == '?'` — both halves. Drop
    the first and an unknown class raises KeyError; drop the second and a state
    Core invented is drawn with the neutral class's own glyph, which reads as a
    real state."""
    assert Style(False, 'dark', False).glyph({'cls': 'no-such-class', 'glyph': '\u2713'}) == '?'
    assert Style(False, 'dark', False).glyph({'cls': 'neutral', 'glyph': '?'}) == '?'
    assert Style(False, 'dark', False).glyph({'cls': 'done', 'glyph': '\u2713'}) == '\u2713'
    assert Style(False, 'dark', True).glyph({'cls': 'done', 'glyph': '\u2713'}) == '+'
    assert CLASSES['neutral']['glyph'] != '?', 'the two halves above would prove nothing'


def test_a_badge_is_never_colour_alone_and_a_state_it_does_not_know_is_inert():
    """view.py:102-106 — `present()` for a state no table knows (present.py:24-25
    returns the raw state as its label) and the `self.t(...)` half of the
    return. Change `t` to `paint` and Core's own state string reaches the
    terminal uncleaned; drop the glyph and colour is the only difference
    between two states."""
    colour, mono = Style(True, 'dark', False), Style(False, 'dark', False)
    hot = colour.badge('mission', 'COMPLETED')
    assert render.strip_ansi(hot) == mono.badge('mission', 'COMPLETED')
    assert SGR.search(hot), 'colour adds something, but never alone'
    assert '\u2713' in render.strip_ansi(hot) and 'Done' in render.strip_ansi(hot)
    bad = mono.badge('mission', '\x1b[2JpwnED')
    assert bad == '? pwnED', bad                                  # unknown state: '?' + the name
    _inert(SGR.sub('', colour.badge('mission', '\x1b]0;x\x07pwnED')))   # its own codes only


def test_a_state_with_no_label_is_still_named(monkeypatch):
    """view.py:105 `look['label'] or state`. With no label the badge would be a
    glyph and a colour — a state shown by colour alone, which §9 forbids."""
    monkeypatch.setattr(V, 'present', lambda m, s: {'cls': 'neutral', 'glyph': '?',
                                                     'role': 'text-2', 'label': None})
    assert Style(False, 'dark', False).badge('mission', 'SOMETHING_ODD') == '? SOMETHING_ODD'


def test_an_ascii_terminal_gets_no_glyph_it_cannot_print():
    """view.py:111-112, the `translate(_ASCII)` + `encode('ascii', 'replace')`
    arm. Skip it and an ASCII codepage terminal gets '?' where the state glyph
    should be, or raises UnicodeEncodeError out of the frame builder."""
    st = Style(False, 'dark', True)
    for c in CLASSES.values():
        out = st.line(c['glyph'] + ' text', 12)
        assert out.isascii(), c['glyph']
        assert render.disp_width(out) == 12
        assert '?' not in out, c['glyph']                          # every glyph has a mapping
    assert st.line('\u2500\u2502\u2192\u2026', 12) == '-|->...     '
    assert st.line('\u6c49' * 3, 8) == '???     '                # unmappable text: one '?' each


def test_the_truncation_mark_is_ascii_on_an_ascii_terminal():
    """view.py:114 `out.replace('\\u2026', '.') if self.ascii` — an ASCII terminal
    cannot print the ellipsis render.trunc appends (claude_sessions/render.py:64),
    and leaving it in makes the line one column wider than the frame as far as the
    terminal is concerned."""
    assert Style(False, 'dark', True).line('\u6c49' * 10, 5) == '????.'
    assert render.disp_width(Style(False, 'dark', True).line('\u6c49' * 10, 5)) == 5
    assert Style(False, 'dark', False).line('\u6c49' * 5, 5) == '\u6c49\u6c49\u2026'


def test_a_line_of_zero_width_is_empty():
    assert width_of(Style(False, 'dark', False).line('abc', 0)) == 0
    assert width_of(Style(False, 'dark', True).line('abc', 0)) == 0


def test_width_of_counts_the_columns_a_terminal_shows():
    """view.py:117-118 — the whole function; every width assertion above depends
    on it. Count `len(s)` instead and a styled or wide line is measured wider
    (or narrower, for the ANSI codes) than the frame it must fit."""
    assert width_of('\x1b[38;5;75mred\x1b[0m') == 3
    assert width_of('\u6c49') == 2
    assert width_of('a\u0301') == 1
    assert width_of(clean('\x1b[2Jx')) == 1

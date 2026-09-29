"""Terminal output for the TUI (p17-design-gate §9, §10): the one sanitiser, the
one styler, and the few layout rules every screen shares.

Terminal output is an injection boundary. Every string that came from Core — a
mission title, model-written text, a file name, an output tail, a routing
explanation, a relationship label, a refusal — goes through `clean()` before it
is laid out, so it can never set the title, write the clipboard, move the
cursor, hide text or forge a prompt. `Style.t()` is the only way screens put
Core text on screen; `Style.paint()` is for the TUI's own words.
"""

import re
import textwrap

from claude_sessions import render

from ._tables import CLASSES
from .present import present
from .tokens import COLOURS

# every escape and control sequence a terminal acts on, 7-bit and 8-bit
_SEQ = re.compile(r'''
    \x1b\[[0-?]*[ -/]*[@-~]                 # CSI (cursor, erase, SGR, modes)
  | \x1b\][^\x07\x1b]*(?:\x07|\x1b\\)?      # OSC (title, clipboard, hyperlinks)
  | \x1b[PX^_][^\x1b]*(?:\x1b\\)?           # DCS, SOS, PM, APC
  | \x1b[ -/]*[0-~]?                        # every other escape, and a bare ESC
  | \x9b[0-?]*[ -/]*[@-~]                   # 8-bit CSI
  | [\x90\x98\x9d\x9e\x9f][^\x07\x9c]*(?:\x07|\x9c)?   # 8-bit DCS/SOS/OSC/PM/APC
''', re.X)
_BREAK = re.compile('[\r\n  \x0b\x0c\x85]+')
# the rest of C0 and C1, DEL, and the bidirectional overrides that reorder text
_CTRL = re.compile('[\x00-\x1f\x7f-\x9f‪-‮⁦-⁩]')


def clean(s):
    """*s* as one line of inert text: no escape sequence, no control character,
    no line break (a break becomes a space), tabs as spaces."""
    s = _SEQ.sub('', '' if s is None else str(s))
    s = _BREAK.sub(' ', s.replace('\t', '    '))
    return _CTRL.sub('', s)


def clean_lines(s):
    """Multi-line Core text: each line cleaned on its own."""
    return [clean(x) for x in _BREAK.split('' if s is None else str(s))]


#: the TUI's own characters, and what an ASCII-only terminal gets instead
_ASCII = str.maketrans({'·': '-', '—': '-', '–': '-', '…': '...', '›': '>', '→': '->',
                        '←': '<-', '“': '"', '”': '"', '’': "'", '‘': "'", '✓': '+',
                        '✕': 'x', '●': '*', '◆': '!', '■': '#', '‖': '=', '◌': '~',
                        '○': 'o', '◇': '^', '─': '-', '│': '|'})
_PROBE = ''.join(sorted({c['glyph'] for c in CLASSES.values()})) + '›—…→─'


def encodable(stream):
    try:
        _PROBE.encode(getattr(stream, 'encoding', None) or 'ascii')
        return True
    except (UnicodeEncodeError, LookupError):
        return False


class Style:
    """Colour, glyphs and the theme, decided once at start (A7)."""

    def __init__(self, colour=False, theme='dark', ascii=False):
        self.colour, self.theme, self.ascii = colour, theme, ascii

    @classmethod
    def detect(cls, env, stream, vt_ok, theme=None):
        """Monochrome when NO_COLOR is set (any value), TERM=dumb, the output is
        not a terminal, or VT mode could not be enabled; ASCII glyphs when the
        output encoding cannot carry the symbols, or ARCHEUS_TUI_ASCII=1."""
        tty = bool(getattr(stream, 'isatty', lambda: False)())
        colour = (vt_ok and tty and 'NO_COLOR' not in env and env.get('TERM') != 'dumb')
        theme = theme or env.get('ARCHEUS_TUI_THEME') or 'dark'
        if theme not in COLOURS:
            theme = 'dark'
        ascii = env.get('ARCHEUS_TUI_ASCII') == '1' or not encodable(stream)
        return cls(colour, theme, ascii)

    def paint(self, s, role=None, bold=False):
        """The TUI's own text (never Core's: that is `t`)."""
        if not self.colour or (role is None and not bold):
            return s
        n = COLOURS[self.theme].get(role) if role else None
        code = ('\x1b[1m' if bold else '') + ('\x1b[38;5;%dm' % n if n is not None else '')
        return code + s + '\x1b[0m' if code else s

    def t(self, s, role=None, bold=False):
        """Text that came from Core: cleaned, then styled."""
        return self.paint(clean(s), role, bold)

    def glyph(self, look):
        c = CLASSES.get(look['cls'])
        if c is None or look['glyph'] == '?':
            return '?'
        return c['ascii'] if self.ascii else c['glyph']

    def badge(self, machine, state):
        """A state is always glyph + label (+ colour), never colour alone."""
        look = present(machine, state)
        return self.paint(self.glyph(look) + ' ', look['role']) + self.t(look['label'] or state,
                                                                           look['role'])

    def line(self, text, width):
        """The last step of every line: exactly *width* columns, and ASCII for an
        ASCII terminal (the truncation mark too, at the same width)."""
        if self.ascii:
            text = text.translate(_ASCII)
        out = render.fit(text, width)
        return out.replace('…', '.') if self.ascii else out


def width_of(s):
    return render.disp_width(s)


def wrap(text, width, indent=0):
    """Core prose wrapped to the width, already cleaned."""
    out = []
    for para in clean_lines(text):
        out.extend(textwrap.wrap(para, max(10, width - indent), break_long_words=True,
                                 break_on_hyphens=False) or [''])
    return [' ' * indent + x for x in out]

"""Render real TUI frames to PNG for the README.

The GUI can be screenshotted with a browser; the TUI cannot, and a terminal
capture pasted as text loses every colour the interface uses to mean something.
So this drives the actual screens through the same fake keyboard the test suite
uses, captures the ANSI they emit, and paints it with the palette archeus
itself resolves — a real frame, not a mock-up, and regenerable when the screens
change.

    py -3 tools/shot_tui.py

Writes docs/img/tui-*.png.
"""

import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tests'))

OUT = os.path.join(ROOT, 'docs', 'img')

#: the 16 ANSI colours, plus the 256-cube, resolved against the GUI palette so
#: the screenshots match the theme the app actually ships
BASE16 = [
    '#1b1f27', '#ff6b81', '#3fdd9d', '#f7b955', '#7dcfff', '#c792ea', '#56d4dd', '#c9d1d9',
    '#6a7381', '#ff8fa1', '#65e6b4', '#ffcd7a', '#a5e0ff', '#dcb4ff', '#8ae8ef', '#f0f6fc',
]
BG = '#0d1117'
FG = '#c9d1d9'


def cube(n):
    """xterm-256 index -> hex."""
    if n < 16:
        return BASE16[n]
    if n < 232:
        n -= 16
        r, g, b = n // 36, (n % 36) // 6, n % 6
        lv = [0, 95, 135, 175, 215, 255]
        return '#%02x%02x%02x' % (lv[r], lv[g], lv[b])
    v = 8 + (n - 232) * 10
    return '#%02x%02x%02x' % (v, v, v)


class Cell:
    __slots__ = ('ch', 'fg', 'bg', 'bold')

    def __init__(self, ch=' ', fg=None, bg=None, bold=False):
        self.ch, self.fg, self.bg, self.bold = ch, fg, bg, bold


_SGR = re.compile(r'\033\[([0-9;]*)m')


def parse(text, width=100):
    """ANSI text -> list of rows of Cells. Only the SGR subset archeus emits:
    reset, bold, the 16 base colours, and 38/48;5;<n>."""
    rows, cur = [], []
    fg = bg = None
    bold = False
    i = 0
    while i < len(text):
        m = _SGR.match(text, i)
        if m:
            codes = [int(c or 0) for c in (m.group(1) or '0').split(';')]
            j = 0
            while j < len(codes):
                c = codes[j]
                if c == 0:
                    fg = bg = None
                    bold = False
                elif c == 1:
                    bold = True
                elif 30 <= c <= 37:
                    fg = BASE16[c - 30]
                elif 90 <= c <= 97:
                    fg = BASE16[8 + c - 90]
                elif 40 <= c <= 47:
                    bg = BASE16[c - 40]
                elif 100 <= c <= 107:
                    bg = BASE16[8 + c - 100]
                elif c in (38, 48) and j + 2 < len(codes) and codes[j + 1] == 5:
                    col = cube(codes[j + 2])
                    if c == 38:
                        fg = col
                    else:
                        bg = col
                    j += 2
                j += 1
            i = m.end()
            continue
        ch = text[i]
        i += 1
        if ch == '\n':
            rows.append(cur)
            cur = []
            continue
        if ch == '\r' or ch == '\x1b':
            continue
        cur.append(Cell(ch, fg, bg, bold))
    if cur:
        rows.append(cur)
    return [r[:width] for r in rows]


def paint(rows, path, cols=100, pad=18):
    from PIL import Image, ImageDraw, ImageFont

    def font(name, size):
        for cand in (name, os.path.join(os.environ.get('WINDIR', r'C:\Windows'),
                                        'Fonts', name)):
            try:
                return ImageFont.truetype(cand, size)
            except Exception:
                continue
        return ImageFont.load_default()

    size = 15
    reg = font('consola.ttf', size)
    bold = font('consolab.ttf', size)
    # Consolas has no box-drawing icons or arrows, so those cells came out as
    # tofu. Segoe UI Symbol covers them; picked per GLYPH, not per run.
    sym = font('seguisym.ttf', size)

    # A missing glyph is not blank — the font draws .notdef, a filled box, so
    # "has a bounding box" says nothing. Compare the rendered mask against
    # .notdef itself instead.
    notdef = {f: bytes(f.getmask('￿')) for f in (reg, bold)}

    def pick(cell):
        base = bold if cell.bold else reg
        try:
            if bytes(base.getmask(cell.ch)) != notdef[base]:
                return base
        except Exception:
            pass
        return sym

    cw = int(reg.getlength('M'))
    ch = size + 6
    w = cols * cw + pad * 2
    h = len(rows) * ch + pad * 2
    img = Image.new('RGB', (w, h), BG)
    d = ImageDraw.Draw(img)
    for y, row in enumerate(rows):
        for x, cell in enumerate(row):
            px, py = pad + x * cw, pad + y * ch
            if cell.bg:
                d.rectangle([px, py, px + cw, py + ch], fill=cell.bg)
            if cell.ch != ' ':
                d.text((px, py + 2), cell.ch, font=pick(cell),
                       fill=cell.fg or FG)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    img.save(path)
    return w, h


def capture(build):
    """Run `build()` with stdout captured and the frame cache invalidated."""
    from claude_sessions import render
    buf = io.StringIO()
    real, sys.stdout = sys.stdout, buf
    try:
        render.invalidate()
        build()
    finally:
        sys.stdout = real
    return buf.getvalue()


# ── driving the real screens ─────────────────────────────────

def last_frame(text):
    """The final complete frame. Off a real console the renderer diff-writes,
    but stdout here is not a tty so every frame is printed whole, separated by
    the clear-screen escape."""
    parts = re.split(r'\033\[2J\033\[H', text)
    for chunk in reversed(parts):
        if chunk.strip():
            return chunk
    return text


#: the sandbox builds its projects under a real temp directory, and that path
#: is on screen in every frame. These images are published, so the machine's
#: own paths are rewritten to the same fictional workspace the GUI shots use.
DEMO_ROOT = '/demo'


def demoise(text, tmp):
    """Replace the sandbox's real temp path with the demo root, in both slash
    styles — the frame shows whichever the platform produced."""
    for base in (str(tmp), os.path.expanduser('~')):
        for form in (base, base.replace(os.sep, '/')):
            if form:
                text = text.replace(form, DEMO_ROOT)
    # the tail of a rewritten path keeps the platform's separators, which reads
    # as a mangled path rather than a demo one
    return re.sub(re.escape(DEMO_ROOT) + r'[^\s\x1b]*',
                  lambda m: m.group(0).replace('\\', '/'), text)


SHOTS = []


def shot(name, cols=100):
    """Register a screen: the decorated function drives it and returns nothing;
    whatever it printed is captured."""
    def deco(fn):
        SHOTS.append((name, cols, fn))
        return fn
    return deco


def main():
    import pytest  # noqa: F401  (harness imports it indirectly)
    from _pytest.monkeypatch import MonkeyPatch
    import tempfile
    from pathlib import Path

    import harness as H

    total = 0
    for name, cols, drive in SHOTS:
        mp = MonkeyPatch()
        tmp = Path(tempfile.mkdtemp(prefix='archeus-shot-'))
        try:
            sb = H.Sandbox(mp, tmp)
            mp.setattr('shutil.get_terminal_size',
                       lambda *a, _c=cols, **k: os.terminal_size((_c, 40)))
            text = demoise(drive(H, mp, sb), tmp)
            rows = parse(last_frame(text), width=cols)
            rows = [r for r in rows if any(c.ch != ' ' for c in r)] or rows
            path = os.path.join(OUT, 'tui-%s.png' % name)
            w, h = paint(rows, path, cols=cols)
            print('  %-14s %3d rows  %dx%d  %s' % (name, len(rows), w, h, path))
            total += 1
        finally:
            mp.undo()
    print('wrote %d frames to %s' % (total, OUT))
    return 0


@shot('main')
def _main_screen(H, mp, sb):
    """The project picker — the first thing anyone sees."""
    for n in ('acme-api', 'acme-web', 'checkout-service', 'design-system'):
        sb.add_project(n, n_sessions=3)
    from claude_sessions import main as main_mod
    cap = H.run_flow(mp, [k for part in (H.ESC,) for k in part], lambda: _catch(main_mod.run))[1]
    return cap.text


@shot('sessions')
def _sessions_screen(H, mp, sb):
    """One project's sessions, with the action hints that make the TUI fast."""
    actual, enc, folder, _sids = sb.add_project('acme-api', n_sessions=6)
    from claude_sessions.sessions import scan_sessions
    from claude_sessions.session_menu import sessions_menu
    rows = scan_sessions(folder)
    cap = H.run_flow(mp, [k for part in (H.ESC,) for k in part],
                     lambda: _catch(sessions_menu, rows, folder, 'acme-api',
                                    actual))[1]
    return cap.text


def _catch(fn, *a):
    try:
        return fn(*a)
    except SystemExit:
        return None
    except Exception:
        return None


if __name__ == '__main__':
    sys.exit(main())

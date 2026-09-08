"""A backtick inside a shader comment kills the entire GUI bundle.

The shaders live in JS template literals. A backtick written inside one — most
naturally by quoting an identifier in a comment, like vF — ENDS the string. The
GLSL after it is parsed as JavaScript, and because app.js, stage.js, motion.js
and instruments.js share one script scope, every `let` and every function in
the page dies with it.

What the user sees is the loading screen, forever, with no error on any surface
they would look at. It happened five times in one session before this existed,
and each time the symptom was indistinguishable from a hung server.

The check is deliberately textual rather than a JS parse. Two reasons: by the
time the bug exists the file no longer parses the way the author meant, so a
structural reading of it describes the damage rather than the cause; and the
one true oracle (`node --check`) is not something a Python test suite can
depend on being installed. `tools/smoke_gui.py` executes the page and is the
belt to this file's braces — it fails with "every top-level module reached the
page" and is mutation-verified against this exact bug.

Scope: a GLSL block, i.e. the run of lines between a line that OPENS a template
literal and the line that closes it. Comments outside one may quote whatever
they like — most of this codebase's prose does, and that is worth keeping.
"""
import pathlib
import re

import pytest

WEB = pathlib.Path(__file__).resolve().parent.parent / 'claude_sessions' / 'web'
FILES = sorted(WEB.glob('*.js'))

#: A template opens on a line whose LAST character is a backtick — which is how
#: every shader in this codebase is written (`vertexShader: ` + backtick, or
#: `const SF_CALM = ` + backtick). It closes on the first later line carrying a
#: backtick. Anything between the two is string content, whatever it looks like.
_OPENS = re.compile(r'`\s*$')

#: ...and closes where a backtick is followed by the punctuation that ends the
#: expression. NOT "ends the line": `sBackdrop(TH, ...backtick, u))` closes its
#: template mid-line, and requiring end-of-line walked straight past it and then
#: reported the real closer as the offence.
_CLOSES = re.compile(r'`\s*[;,)\]]')

#: ...and it is only interesting if it is actually GLSL. An HTML template in
#: app.js is a template literal too, and interpolating into one is the whole
#: point of it — `${...}` there is code, not a stray quote.
_GLSL = ('void main(', 'gl_FragColor', 'gl_Position', 'varying ', 'uniform ')


def _blocks(lines):
    """Yield (start, end) line indices of every GLSL template literal."""
    i = 0
    while i < len(lines):
        if _OPENS.search(lines[i]) and lines[i].count('`') % 2:
            # The closer is a line ENDING in a backtick (plus its punctuation),
            # which is how a template literal is actually terminated. Looking
            # for the first line with a backtick anywhere would stop at the
            # offending comment itself — the block would come out empty, and
            # the check would report nothing on the one file it exists for.
            for j in range(i + 1, len(lines)):
                if _CLOSES.search(lines[j]):
                    body = '\n'.join(lines[i + 1:j + 1])
                    if any(k in body for k in _GLSL):
                        yield i, j
                    i = j
                    break
            else:
                return
        i += 1


def _offences(src):
    lines = src.split('\n')
    out = []
    for a, b in _blocks(lines):
        for k in range(a + 1, b):
            if '`' in lines[k]:
                out.append((k + 1, lines[k].strip()[:70]))
    return out


@pytest.mark.parametrize('path', FILES, ids=lambda p: p.name)
def test_no_backtick_hides_in_a_shader_comment(path):
    bad = _offences(path.read_text(encoding='utf-8'))
    assert not bad, (
        f'{path.name}: a backtick inside a shader template ends the string and '
        f'takes the whole bundle with it — write the identifier bare:\n'
        + '\n'.join(f'  line {ln}: {txt}' for ln, txt in bad))


def test_the_scanner_catches_the_bug_and_leaves_ordinary_prose_alone():
    """The check is only worth having if it fires on the exact shape that
    caused the outage and stays quiet on the comments this codebase is full of.
    Both halves matter: a version of this that flagged every backtick in every
    comment was written first, and it reported 63 false positives in app.js —
    which is how a gate gets switched off rather than fixed."""
    tick = chr(96)
    glsl = 'const S = ' + tick + '\n  /* the ' + tick + 'vF' + tick + \
           ' varying */\n  void main(){ gl_FragColor = vec4(0.0); }' + tick + ';'
    assert _offences(glsl), 'the bug itself is not detected'
    ok = '/* ' + tick + 'calm' + tick + ' is per-skin */\nconst S = ' + tick + \
         '\n  void main(){ gl_FragColor = vec4(0.0); }' + tick + ';'
    assert not _offences(ok), 'a top-level comment must stay allowed'
    # an HTML template is a template literal too, and interpolating into one is
    # the point of it — this must not be mistaken for a shader
    html = 'const h = ' + tick + '\n  <div>${esc(name)}</div>\n' + tick + ';'
    assert not _offences(html), 'markup templates are not shaders'

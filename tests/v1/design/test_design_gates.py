"""The V1 client's design gates (p16-design-gate §15–§18, §24; ui-architecture
§7). They read the SOURCE the build ships — the token and presentation tables,
the stylesheets, the service worker, the components — so they run in the
Node-free `test` job. Mutation-verified by tools/mutate_p16.py (M26, M27)."""

import itertools
import json
import math
import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
APP = os.path.join(ROOT, 'clients', 'app')
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import gen_ui  # noqa: E402

TOKENS = gen_ui.load(gen_ui.TOKENS)
STYLES = [os.path.join(APP, 'src', 'styles', n) for n in ('app.css', 'tokens.css')]


def _css():
    return {p: re.sub(r'/\*.*?\*/', '', open(p, encoding='utf-8').read(), flags=re.S)
            for p in STYLES}


# ── generated files and the presentation table (D9) ──

def test_the_generated_ui_files_are_current():
    files, bad = gen_ui.outputs()
    assert not bad
    for path, text in files.items():
        assert open(path, encoding='utf-8').read() == text, 'stale: run py tools/gen_ui.py (%s)' % path


def test_every_state_of_every_machine_has_a_presentation():
    """M27: a machine state with no class is refused, as is a class that names
    nothing or a state the machine does not have."""
    from archeus.core.domain import states
    p = gen_ui.load(gen_ui.PRESENTATION)
    assert gen_ui.problems(p, TOKENS) == []
    for m in {row[0] for row in states.TABLE}:
        assert set(p['machines'][m]) == set(states.states(m)), m
    broken = json.loads(json.dumps(p))
    broken['machines']['mission'].pop('REVIEWING')
    assert any('REVIEWING' in b for b in gen_ui.problems(broken, TOKENS))


def test_only_a_completed_mission_is_done_and_ended_ok_is_not_success():
    p = gen_ui.load(gen_ui.PRESENTATION)['machines']
    assert [s for s, c in p['mission'].items() if c == 'done'] == ['COMPLETED']
    assert p['execution']['ENDED_OK'] != 'done'
    assert len({p['mission'][s] for s in ('APPROVAL_REQUIRED', 'APPROVED', 'EXECUTING',
                                          'VERIFYING', 'REVIEWING', 'COMPLETED')}) == 6


# ── contrast (§15.1; design system §3) ──

def _lin(c):
    c /= 255
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _lum(h):
    r, g, b = (int(h[i:i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)


def ratio(a, b):
    hi, lo = sorted((_lum(a), _lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def _lab(h):
    r, g, b = (_lin(int(h[i:i + 2], 16)) for i in (1, 3, 5))
    x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883

    def f(t):
        return t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116
    return 116 * f(y) - 16, 500 * (f(x) - f(y)), 200 * (f(y) - f(z))


SURFACES = ('bg', 'surface-1', 'surface-2', 'surface-3')
STATES = ('state.active', 'state.attention', 'state.blocked', 'state.paused', 'state.thinking',
          'state.done')


@pytest.mark.parametrize('theme', sorted(TOKENS['themes']))
def test_every_role_clears_its_contrast_floor_on_every_surface(theme):
    t = TOKENS['themes'][theme]
    floors = dict({'text': 4.5, 'text-2': 4.5, 'text-3': 3.0, 'focus': 3.0},
                  **{s: 4.5 for s in STATES})
    for surface in SURFACES:
        for role, floor in floors.items():
            got = ratio(t[role], t[surface])
            assert got >= floor, '%s %s on %s: %.2f < %.1f' % (theme, role, surface, got, floor)
    assert ratio(t['primary'], t['on-primary']) >= 4.5
    assert ratio(t['thread'], t['surface-1']) >= 3.0


@pytest.mark.parametrize('theme', sorted(TOKENS['themes']))
def test_state_colours_are_told_apart(theme):
    t = TOKENS['themes'][theme]
    for a, b in itertools.combinations(STATES, 2):
        assert math.dist(_lab(t[a]), _lab(t[b])) >= 20, (theme, a, b)


# ── motion (§18.1) and the Qt tear lesson ──

ALLOWED_MOTION = {'transform', 'opacity'}


def _blocks(css, at):
    """(name, body) of every `@<at> name { ... }` block, braces balanced."""
    out = []
    for m in re.finditer(r'@%s\s+([^{]+)\{' % at, css):
        depth, i = 1, m.end()
        while depth:
            depth += {'{': 1, '}': -1}.get(css[i], 0)
            i += 1
        out.append((m.group(1).strip(), css[m.end():i - 1]))
    return out


def test_keyframes_animate_only_transform_and_opacity():
    """M26: a keyframe that animates anything else fails here."""
    seen = 0
    for path, css in _css().items():
        for name, body in _blocks(css, 'keyframes'):
            props = set(re.findall(r'([a-z-]+)\s*:', body))
            assert props <= ALLOWED_MOTION, '%s @keyframes %s animates %s' % (
                os.path.basename(path), name, props - ALLOWED_MOTION)
            seen += 1
    assert seen >= 4, 'read the keyframes'


def test_transitions_move_only_transform_and_opacity_and_nothing_loops():
    for path, css in _css().items():
        for value in re.findall(r'transition\s*:\s*([^;]+);', css):
            if value.strip().startswith('none'):
                continue
            props = {part.split()[0] for part in value.split(',')}
            assert props <= ALLOWED_MOTION, (path, value)
        assert 'infinite' not in css and 'steps(' not in css, path
        for value in re.findall(r'animation\s*:\s*([^;]+);', css):
            v = value.replace('!important', '').split()
            assert v[0] == 'none' or v[-1] == '1', 'an animation must run once: %s' % value
        assert 'animation-iteration-count' not in css


def test_no_readback_effects():
    for path, css in _css().items():
        for bad in (r'backdrop-filter', r'mix-blend-mode', r'(^|[\s;{])filter\s*:'):
            assert not re.search(bad, css, re.M), (path, bad)


def test_reduced_motion_contrast_and_forced_colours_are_honoured():
    css = _css()[STYLES[0]]
    assert re.search(r'@media \(prefers-reduced-motion: reduce\)[^{]*\{[^}]*animation: none !important',
                     css, re.S)
    assert "html[data-motion='reduced']" in css
    assert '@media (prefers-contrast: more)' in css and '@media (forced-colors: active)' in css
    assert '@media (prefers-contrast: more)' in _css()[STYLES[1]]


#: What a width media query may touch: the chrome (where the navigation and the
#: inspector sit), and control target sizes. Every component reads its container.
CHROME = re.compile(r'^(\.shell\b|\.nav\b|\.nav-label|\.top\b|\.main\b|\.inspector\b|\.banner\b|'
                    r'\.badge\b|\.menu-control|\.cmd-open|:root|button|\.btn|input|select|textarea)')


def test_a_width_media_query_moves_only_the_chrome():
    seen = 0
    for path, css in _css().items():
        for cond, body in _blocks(css, 'media'):
            if 'width' not in cond:
                continue
            for sel in re.findall(r'([^{}]+)\{', body):
                for s in sel.split(','):
                    s = s.strip()
                    assert CHROME.match(s), '%s: %s inside @media %s is a component rule; use @container' % (
                        os.path.basename(path), s, cond)
                    seen += 1
    assert seen > 10
    assert '@container' in _css()[STYLES[0]]


# ── what reaches the page ──

def test_the_service_worker_never_caches_the_api():
    sw = open(os.path.join(APP, 'public', 'sw.js'), encoding='utf-8').read()
    code = re.sub(r'//.*', '', sw)
    assert "url.pathname.startsWith('/v1/')) return" in code
    assert '/v1' not in code.replace("url.pathname.startsWith('/v1/')) return", '')
    assert "addAll(['/'])" in code


def test_components_render_text_never_markup():
    """Agent output and every row are text: no `dangerouslySetInnerHTML`, no
    `innerHTML` (plan §27 Web; the strict CSP forbids inline script too)."""
    from archeus.api import auth
    for dirpath, _dirs, files in os.walk(os.path.join(APP, 'src')):
        for n in files:
            if n.endswith(('.ts', '.tsx')):
                src = open(os.path.join(dirpath, n), encoding='utf-8').read()
                assert 'dangerouslySetInnerHTML' not in src and 'innerHTML' not in src, n
    assert "script-src 'self'" in auth.CSP and 'unsafe-inline' not in auth.CSP


def test_the_manifest_names_what_the_pwa_needs():
    m = json.load(open(os.path.join(APP, 'public', 'manifest.webmanifest'), encoding='utf-8'))
    assert m['start_url'] == '/' and m['display'] == 'standalone'
    assert m['background_color'] == TOKENS['themes']['dark']['bg']
    for icon in m['icons']:
        assert os.path.exists(os.path.join(APP, 'public', icon['src'].lstrip('/'))), icon


# ── the spatial view's motion (p18-design-gate A7, A9, §13) ──

def _src(*parts):
    src = open(os.path.join(APP, 'src', *parts), encoding='utf-8').read()
    return re.sub(r'//.*$', '', re.sub(r'/\*.*?\*/', '', src, flags=re.S), flags=re.M)


def test_the_graph_loop_is_the_only_animation_frame_caller():
    """A9: one loop. Also checked by the TS suite (M19); here in the Node-free job."""
    callers = []
    for d, _dirs, files in os.walk(os.path.join(APP, 'src')):
        for f in files:
            if f.endswith(('.ts', '.tsx')):
                rel = os.path.relpath(os.path.join(d, f), os.path.join(APP, 'src')).split(os.sep)
                if re.search(r'requestAnimationFrame\s*\(', _src(*rel)):
                    callers.append('/'.join(rel))
    assert callers == ['graph/loop.ts'], callers


def test_the_layout_reads_no_clock_and_no_random():
    """A7: the same data and focus give the same picture (also TS, M13)."""
    src = _src('graph', 'layout.ts')
    assert 'function layout(' in src
    assert not re.search(r'Math\.random|Date\.now|performance\.now|new Date\(', src)

"""The V1 client's design gates (p16-design-gate §15–§18, §24; ui-architecture
§7). They read the SOURCE the build ships — the token and presentation tables,
the stylesheets, the service worker, the components — so they run in the
Node-free `test` job. Mutation-verified by tools/mutate_p16.py (M26, M27)."""

import colorsys
import copy
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


def test_every_mission_state_has_a_spine_position_and_the_closure_rules_hold():
    """ADR-0054 §2: a mission state with no position, a station name Core does not use, a
    hold entered from a state with no station, FAILED off its station and a second Done
    state are all refused, so a new state or a new hold edge fails the build until the
    table says where it goes. Mutation-verified by tools/mutate_v2u1.py."""
    from archeus.core.domain import states
    sp, p = gen_ui.load(gen_ui.SPINE), gen_ui.load(gen_ui.PRESENTATION)
    assert gen_ui.spine_problems(sp, p) == []
    assert set(sp['states']) == set(states.states('mission'))

    def broke(edit, table=None):
        d = copy.deepcopy(sp)
        edit(d)
        return gen_ui.spine_problems(d, p, table)

    assert any('REVIEWING' in b for b in broke(lambda d: d['states'].pop('REVIEWING')))
    assert any('NOT_A_STATE' in b for b in broke(lambda d: d['states'].update(NOT_A_STATE={'kind': 'ahead'})))

    def swap(d):
        d['stations'][4], d['stations'][5] = d['stations'][5], d['stations'][4]
    assert any('anchor' in b for b in broke(swap))
    assert any('Run' in b for b in broke(lambda d: d['stations'][3].update(label='Run')))
    hold = list(states.TABLE) + [('mission', 'CREATED', 'BLOCKED', 'x', None)]
    assert any('CREATED -> BLOCKED' in b for b in broke(lambda d: None, hold))
    assert any('FAILED' in b for b in broke(lambda d: d['states']['FAILED'].update(station=5)))
    assert any('COMPLETED' in b for b in broke(lambda d: d['states']['CANCELLED'].update(kind='complete')))
    assert any('sentence' in b for b in broke(lambda d: d['sentences'].update(held='{word} at {step}')))
    assert any('held' in b for b in broke(lambda d: d['sentences'].pop('held')))
    assert any('resumed' in b for b in broke(lambda d: d['states']['PAUSED'].update(kind='current', station=4)))


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
    floors = dict({'text': 4.5, 'text-2': 4.5, 'text-3': 4.5, 'focus': 3.0},
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


@pytest.mark.parametrize('theme', sorted(TOKENS['themes']))
def test_focus_is_never_read_as_a_state(theme):
    """ADR-0028: a focus ring is not a state. The amber focus was ΔE 12.3 from
    the attention amber (dark) and 7.1 from it (light), so a focused node read as
    "needs you". Focus is the thread ink now; it clears the same separation floor
    the state colours hold among themselves."""
    t = TOKENS['themes'][theme]
    for s in STATES:
        assert math.dist(_lab(t['focus']), _lab(t[s])) >= 20, (theme, 'focus', s)


def test_the_terminal_focus_is_never_a_state_colour():
    """The same rule after ANSI-256 quantization: in light, focus and attention
    had landed on the very same terminal colour (94)."""
    sys.path.insert(0, ROOT)
    from archeus.cli.tui.tokens import COLOURS
    for theme, c in COLOURS.items():
        states = {c[s] for s in STATES}
        assert c['focus'] not in states, (theme, c['focus'])
        assert len(states) == len(STATES), (theme, 'two states share a terminal colour')


def _hue(h):
    return colorsys.rgb_to_hls(*(int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)))[0] * 360


def _looks():
    """The four looks the app has: each theme, standard and high contrast."""
    return {'%s%s' % (name, suffix): t for name in sorted(TOKENS['themes'])
            for suffix, t in (('', TOKENS['themes'][name]), (' high contrast', gen_ui.hc_theme(TOKENS, name)))}


@pytest.mark.parametrize('theme', sorted(TOKENS['themes']))
def test_high_contrast_reaches_its_floors_on_every_surface(theme):
    """V2 visual language §4: text and every state 7:1 on every surface, focus 4.5:1,
    both lines 3:1 (non-text), the states still told apart and focus still not a state.
    Read through gen_ui.hc_theme (aliases over the per-theme overrides, as the cascade
    resolves them); the emission test below holds the CSS to the same values."""
    t = gen_ui.hc_theme(TOKENS, theme)
    floors = dict({'text': 7.0, 'text-2': 7.0, 'text-3': 7.0, 'focus': 4.5, 'line': 3.0, 'line-strong': 3.0},
                  **{s: 7.0 for s in STATES})
    for surface in SURFACES:
        for role, floor in floors.items():
            got = ratio(t[role], t[surface])
            assert got >= floor, '%s high contrast %s on %s: %.2f < %.1f' % (theme, role, surface, got, floor)
    assert ratio(t['primary'], t['on-primary']) >= 7.0
    for a, b in itertools.combinations(STATES, 2):
        assert math.dist(_lab(t[a]), _lab(t[b])) >= 20, (theme, a, b)
    for s in STATES:
        assert math.dist(_lab(t['focus']), _lab(t[s])) >= 20, (theme, 'focus', s)


def test_each_themes_high_contrast_values_are_emitted_under_every_form_that_selects_it():
    """The per-theme overrides reach the page by the attribute and by the OS preference,
    over the theme's own attribute and over `system` with its OS scheme (ADR-0044 §5)."""
    css = _css()[STYLES[1]]
    assert sorted(TOKENS['high_contrast']['themes']) == sorted(TOKENS['themes'])
    for theme, over in TOKENS['high_contrast']['themes'].items():
        other = 'light' if theme == 'dark' else 'dark'
        forms = [(":root[data-theme='%s'][data-contrast='high']" % theme, set()),
                 (":root:not([data-theme='%s'])[data-contrast='high']" % other, {'prefers-color-scheme: ' + theme}),
                 (":root[data-theme='%s']:not([data-contrast='standard'])" % theme, {'prefers-contrast: more'}),
                 (":root:not([data-theme='%s']):not([data-contrast='standard'])" % other,
                  {'prefers-contrast: more', 'prefers-color-scheme: ' + theme})]
        for sel, conds in forms:
            m = re.search(r'(@media [^{]+\{\s*)?' + re.escape(sel) + r'\s*\{([^{}]*)\}', css)
            assert m, (theme, sel)
            assert set(re.findall(r'\(([^)]*)\)', m.group(1) or '')) == conds, (theme, sel, m.group(1))
            for role, value in over.items():
                assert '--%s: %s;' % (role.replace('.', '-'), value) in m.group(2), (theme, sel, role)


def test_a_state_keeps_its_one_hue_in_every_look():
    """ADR-0017: one colour, one meaning, in every theme. A theme or a high contrast
    value moves a state's lightness, never its hue (V2 visual language §3.2)."""
    for s in STATES:
        hues = [_hue(t[s]) for t in _looks().values()]
        spread = max(min(abs(a - b), 360 - abs(a - b)) for a in hues for b in hues)
        assert spread <= 10, (s, [round(h) for h in hues])


def test_done_is_green_and_blocked_and_focus_are_the_owners_dark_values():
    """Owner, 2026-10-25: green Done (never the slate of paused), the V1 red for blocked,
    the prototype's focus in Dark."""
    for look, t in _looks().items():
        assert 120 <= _hue(t['state.done']) <= 170, look
    assert TOKENS['themes']['dark']['state.blocked'] == '#F07178'
    assert TOKENS['themes']['dark']['focus'] == '#FFF3CF'


def _over(fg, bg, alpha):
    mix = [round(alpha * int(fg[i:i + 2], 16) + (1 - alpha) * int(bg[i:i + 2], 16)) for i in (1, 3, 5)]
    return '#%02X%02X%02X' % tuple(mix)


@pytest.mark.parametrize('theme', sorted(TOKENS['themes']))
def test_text_on_the_attention_band_clears_its_floor(theme):
    """V2 visual language §8: the band is `state.attention` at alpha.band over the row's
    surface. The word is ink (4.5:1, every text role) and the amber figure is non-text
    (3:1); amber as text is not promised on the band in Light."""
    t = TOKENS['themes'][theme]
    for surface in SURFACES:
        band = _over(t['state.attention'], t[surface], TOKENS['alpha']['band'])
        for role in ('text', 'text-2', 'text-3'):
            assert ratio(t[role], band) >= 4.5, (theme, role, surface)
        assert ratio(t['state.attention'], band) >= 3.0, (theme, surface)


def test_the_v2_tokens_hold_their_approved_values_and_reach_the_css():
    """Owner, 2026-10-25: 44 px for primary desktop controls only, the breath's 6000 ms,
    the band's 12 %; no `text-muted` role (folded into `text-3`)."""
    assert TOKENS['targets'] == {'desktop': 28, 'desktop-primary': 44, 'phone': 44}
    assert TOKENS['motion']['breath'] == 6000 and TOKENS['alpha']['band'] == 0.12
    css = _css()[STYLES[1]]
    for decl in ('--target-desktop-primary: 44px;', '--dur-breath: 6000ms;', '--band: 0.12;'):
        assert decl in css, decl
    assert 'text-muted' not in TOKENS['themes']['dark']


def test_the_token_sets_are_refused_unless_dark_and_light_with_the_same_roles():
    assert gen_ui.token_problems(TOKENS) == []
    third = copy.deepcopy(TOKENS)
    third['themes']['sepia'] = dict(third['themes']['dark'])
    assert gen_ui.token_problems(third)
    short = copy.deepcopy(TOKENS)
    short['themes']['light'].pop('state.done')
    assert gen_ui.token_problems(short)
    stray = copy.deepcopy(TOKENS)
    stray['high_contrast']['themes']['dark']['state.mauve'] = '#FFFFFF'
    assert gen_ui.token_problems(stray)


def test_the_narrow_graph_note_is_not_a_problem():
    """ADR-0028: red means a problem the user must resolve. Below 600 px the
    graph gives way to its list — information, not an error — so the note must
    not wear the blocked colour (`.unavailable`, `.err`)."""
    src = open(os.path.join(APP, 'src', 'graph', 'GraphView.tsx'), encoding='utf-8').read()
    tag = re.search(r'<p className="([^"]*)"[^>]*data-graph-narrow', src)
    assert tag, 'the narrow-graph note is missing'
    assert not {'unavailable', 'err'} & set(tag.group(1).split()), tag.group(0)


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


MOTIONS = gen_ui.load(gen_ui.MOTION)['motions']


def _built(field):
    return {v for e in MOTIONS.values() if e['status'] == 'built' for v in e.get(field) or ()}


def test_every_keyframe_and_transition_is_a_registered_motion():
    """ADR-0024 §3: a keyframe or a transition the motion registry does not
    declare fails the build, and a registered one must really exist."""
    frames, moving = set(), set()
    for css in _css().values():
        frames |= {name for name, _body in _blocks(css, 'keyframes')}
        flat = re.sub(r'@[^{]+\{', '', css)            # innermost rules, whatever encloses them
        for sel, body in re.findall(r'([^{}]+)\{([^{}]*)\}', flat):
            t = re.search(r'transition\s*:\s*([^;]+);', body)
            if t and not t.group(1).strip().startswith('none'):
                moving |= {s.strip() for s in sel.split(',')}
    assert frames == _built('css'), 'keyframes %s, registered %s' % (sorted(frames), sorted(_built('css')))
    assert moving == _built('transition'), 'transitions on %s, registered %s' % (
        sorted(moving), sorted(_built('transition')))
    assert len(frames) >= 4 and moving


def test_the_left_edge_of_a_row_belongs_to_the_thread():
    """ADR-0026 §1 (P19.5 R5): the change rule is the 2 px left-edge rule in
    thread ink on a row the digest names, and only it: no other rule draws
    thread ink on a left edge, and nothing else draws on a row's left edge."""
    rules = []
    for css in _css().values():
        flat = re.sub(r'@[^{]+\{', '', css)
        rules += [({x.strip() for x in sel.split(',')}, body) for sel, body in re.findall(r'([^{}]+)\{([^{}]*)\}', flat)]
    inked = set().union(*(sel for sel, body in rules
                          if re.search(r'(border-left[^;]*|inset\s+2px\s+0[^;]*)var\(--thread\)', body)))
    assert inked == {'.thread-rule', '[data-thread]::before'}, inked
    bar = [body for sel, body in rules if sel == {'[data-thread]::before'} and 'content:' in body]
    assert bar and re.search(r'\bleft:\s*0;', bar[0]) and re.search(r'border-left:\s*2px solid var\(--thread\)', bar[0]) \
        and re.search(r'opacity:\s*0;', bar[0]), 'a 2 px bar on the left edge, clear until the row changed'
    assert any(sel == {"[data-thread='changed']::before"} and re.search(r'opacity:\s*1;', body) for sel, body in rules)
    ours = {'[data-thread]', '[data-thread]::before', "[data-thread='changed']::before", '.thread-rule'}
    rows = {'.row-item', '.rows', '.list'} | ours
    for sel, body in rules:
        if sel & rows and not sel <= ours:
            assert not re.search(r'border-left|inset\s+-?\d+px\s+0', body), (sel, body)


def test_every_loop_animation_is_a_registered_built_motion():
    """ADR-0024 §3 in the Node-free job (the TS suite checks it too): every
    `.animate(` names a built loop motion; no WAAPI, no bare duration."""
    calls = 0
    for d, _dirs, files in os.walk(os.path.join(APP, 'src')):
        for f in files:
            if f.endswith(('.ts', '.tsx')) and f != 'motion.ts':
                rel = os.path.relpath(os.path.join(d, f), os.path.join(APP, 'src')).split(os.sep)
                for arg in re.findall(r'\.animate\(([^)]*)\)', _src(*rel)):
                    calls += 1
                    m = re.fullmatch(r"\s*'([a-z-]+)'\s*", arg)
                    e = MOTIONS.get(m.group(1)) if m else None
                    assert e and e['status'] == 'built' and e['runs_on'] == 'loop', (
                        '%s: .animate(%s) is not a built loop motion' % ('/'.join(rel), arg))
    assert calls >= 2


def test_the_motion_registry_holds_the_approved_budgets():
    """ADR-0024 §6; gen_ui.motion_problems holds the shape (run by --check)."""
    assert not gen_ui.motion_problems({'motions': MOTIONS}, TOKENS)
    marker = MOTIONS['travelling-marker']
    assert marker['max_ms'] <= 600 and marker['cap'] <= 8 and marker['over_cap'] == 'drop-oldest'
    pulse = MOTIONS['execution-pulse']
    assert (pulse['max_ms'], pulse['cap'], pulse['min_interval_ms']) == (240, 12, 2000)
    assert MOTIONS['activity-halo']['max_ms'] is None and MOTIONS['activity-halo']['idle'] == 'static'
    assert all(e['replay'] is False for e in MOTIONS.values())


def test_the_presentation_clock_and_the_renderer_read_no_clock_and_no_random():
    """ADR-0024 §4, ADR-0029 §1: a motion is a pure function of (state,
    presentation time) — renderAt(t) — so neither file reads a clock, a
    random number or schedules a frame of its own."""
    for parts in (('state', 'timeline.ts'), ('graph', 'render.ts')):
        src = _src(*parts)
        assert not re.search(r'Math\.random|Date\.now|performance\.now|new Date\(|'
                             r'requestAnimationFrame|setTimeout|setInterval', src), parts
    # the rule's scope (ADR-0024 §4 as clarified): animation, rendering, layout
    # and presentation state — every file of graph/ and state/. An operational
    # identifier (data/commands.ts's idempotency-key fallback) is outside it.
    seen = 0
    for sub in ('graph', 'state'):
        for f in os.listdir(os.path.join(APP, 'src', sub)):
            if f.endswith(('.ts', '.tsx')):
                assert 'Math.random' not in _src(sub, f), '%s/%s' % (sub, f)
                seen += 1
    assert seen >= 12


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


# ── the application theme (ADR-0044, p19-design-gate B9) ──

def _boot():
    src = open(gen_ui.APPEARANCE_JS, encoding='utf-8').read()
    return json.loads(re.search(r'BG = (\{[^}]*\})', src).group(1))


def test_t6_only_the_token_sets_are_themes_and_each_has_its_attribute():
    """T4/T6: the themes a client may choose are exactly the token sets the
    contrast gates above run over, each emitted under its own attribute, the
    `system` mapping in media queries; high contrast both ways too."""
    assert sorted(_boot()) == sorted(TOKENS['themes']) == ['dark', 'light']
    css = _css()[STYLES[1]]
    for name in TOKENS['themes']:
        assert ":root[data-theme='%s']" % name in css, name
    assert re.search(r"@media \(prefers-color-scheme: light\) \{\s*:root:not\(\[data-theme='dark'\]\)", css)
    assert re.search(r"@media \(prefers-contrast: more\) \{\s*:root:not\(\[data-contrast='standard'\]\)", css)
    assert ":root[data-contrast='high']" in css
    for path, text in _css().items():
        for m in re.finditer(r"data-theme='([^']*)'", text):
            assert m.group(1) in TOKENS['themes'], (path, m.group(1))


def test_t6_the_appearance_boot_runs_before_the_stylesheet():
    """T6, statically: a classic `'self'` script (never inline, async, deferred or
    a module) loaded in <head> before anything that could paint."""
    html = open(os.path.join(APP, 'index.html'), encoding='utf-8').read()
    tags = re.findall(r'<(script|link)\b([^>]*)>', html)
    first = tags.index(('script', ' src="/src/state/appearance.js"'))
    assert html.index('</head>') > html.index('/src/state/appearance.js')
    assert not [t for t in tags[:first] if t[0] == 'script' or 'stylesheet' in t[1]]
    assert all(t[0] == 'link' or 'src=' in t[1] for t in tags), 'no inline script (CSP)'


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


def test_no_view_renders_json():
    """R1 (ADR-0029 §4, rulebook §5.13): a value is shown as words or as a
    structured list, never as JSON — not in the default view and not in
    Details. The browser gate (tests/v1/e2e/test_spa_copy.py) reads the
    pages; this one keeps the source from reaching for the shortcut."""
    for sub in ('surfaces', 'components'):
        for dirpath, _dirs, files in os.walk(os.path.join(APP, 'src', sub)):
            for n in files:
                if n.endswith(('.ts', '.tsx')):
                    assert 'JSON.stringify' not in open(os.path.join(dirpath, n), encoding='utf-8').read(), n


def _commands():
    """(file, names, command) for every ActionButton: the names it can show and
    the Core command it sends, as (api method, the decision it carries). A turn
    that carries a card's decision (P19 B5) is the word it sends."""
    out = []
    for sub in ('surfaces', 'components'):
        for dirpath, _dirs, files in os.walk(os.path.join(APP, 'src', sub)):
            for n in files:
                if not n.endswith('.tsx'):
                    continue
                for body in re.findall(r'<ActionButton\b(.*?)/>', open(os.path.join(dirpath, n), encoding='utf-8').read(), re.S):
                    lit = re.search(r'label="([^"]+)"', body)
                    alt = re.search(r"label=\{[^}]*\?\s*'([^']+)'\s*:\s*'([^']+)'\s*\}", body)
                    tpl = re.search(r'label=\{`([^`]+)`\}', body)
                    names = ((lit.group(1),) if lit else alt.groups() if alt else
                             (re.sub(r'\$\{[^}]*\}', '…', tpl.group(1)),) if tpl else ())
                    methods = re.findall(r'api\.(\w+)\(', body)
                    said = re.search(r"(?:decision|verdict|action|choice|text)\s*:\s*'(\w+)'|decideBody\(\w+,\s*'(\w+)'", body)
                    assert names and len(methods) == 1, (n, body[:120])
                    out.append((n, names, (methods[0], said and (said.group(1) or said.group(2)))))
    return out


def _bare(name, command):
    """Is *name* nothing but the verb Core gives *command*?"""
    method, said = command
    verb = said or re.match(r'[a-z]+', method).group(0)
    letters = lambda s: re.sub(r'[^a-z]', '', s.lower())  # noqa: E731
    stems = lambda s: {w[:5] for w in re.split(r'[^a-z]+', s.lower()) if w}  # noqa: E731
    return letters(name) == letters(verb) or stems(name) == stems(verb)


def test_one_name_per_command():
    """R1 (testing-strategy §7 `innerText`, rulebook §2.5 and §40.5): a Core
    command is called one thing everywhere, and a name means one command. A
    name may be shared only when it is the bare verb, sent to whichever object
    the page is about ("Stop" a mission, "Stop" an attempt); a name that says
    more than the verb ("Accept result") names exactly one command. Read from
    the source, so a button that only renders in a rare state is held too.
    Mutation-verified by tools/mutate_p19_5.py (N84, N85)."""
    found = _commands()
    assert len(found) >= 35, 'read only %d command buttons' % len(found)
    by_command, by_name = {}, {}
    for _n, names, cmd in found:
        by_command.setdefault(cmd, set()).add(names)
        for name in names:
            by_name.setdefault(name, set()).add(cmd)
    for cmd, names in by_command.items():
        assert len(names) == 1, '%s is called %s' % (cmd, sorted(names))
    for name, cmds in by_name.items():
        if len(cmds) > 1:
            assert all(_bare(name, c) for c in cmds), '"%s" names %s' % (name, sorted(cmds, key=str))


def test_the_command_name_rule_fails_what_the_rulebook_found():
    """The rule's own cases, without the source: the two collisions rulebook
    §2.5 recorded are refused, the shared bare verbs are not."""
    assert not _bare('Accept result', ('decideVerification', 'accept'))
    assert not _bare('Dismiss', ('rejectKnowledge', None)) and not _bare('Dismiss', ('ackDigest', None))
    for name, cmd in (('Stop', ('stopExecution', None)), ('Hand off', ('handoffSession', None)),
                      ('Reject', ('decideApproval', 'reject')), ('Reject', ('rejectKnowledge', None)),
                      ('Request changes', ('reviewMission', 'changes_requested'))):
        assert _bare(name, cmd), (name, cmd)


def test_the_manifest_names_what_the_pwa_needs():
    m = json.load(open(os.path.join(APP, 'public', 'manifest.webmanifest'), encoding='utf-8'))
    assert m['start_url'] == '/' and m['display'] == 'standalone'
    assert m['background_color'] == m['theme_color'] == TOKENS['themes']['dark']['bg']
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


# ── one edge implementation (p19-design-gate B1) ──

def _client_sources():
    """Every hand-written client module: the SPA's src/ and the TUI."""
    for top in (os.path.join(APP, 'src'), os.path.join(ROOT, 'archeus', 'cli', 'tui')):
        for dp, _ds, fs in os.walk(top):
            for f in fs:
                if f.endswith(('.ts', '.tsx', '.py')) and f not in ('edgeWords.ts', '_tables.py',
                                                                     'generated.ts'):
                    p = os.path.join(dp, f)
                    with open(p, encoding='utf-8') as fh:
                        yield os.path.relpath(p, ROOT), fh.read()


def _assembled_edges(src, fields):
    """Where *src* builds an edge itself: an `edge(out, …)` builder, or an
    object literal naming a relationship field Core emits."""
    names = '|'.join(re.escape(f) for f in fields)
    return (re.findall(r'\b_?edge\(\s*out\s*,', src)
            + re.findall(r"""['"]?field['"]?\s*:\s*['"](?:%s|relations\.)""" % names, src))


def test_no_client_assembles_an_edge():
    """Core's graph route is the one edge implementation; a client only says
    an edge in words (relations.ts edgeRows, present.py edge_rows)."""
    with open(os.path.join(APP, 'tokens', 'edges.json'), encoding='utf-8') as f:
        fields = list(json.load(f)['words'])
    bad = {p: hits for p, src in _client_sources() if (hits := _assembled_edges(src, fields))}
    assert not bad, bad


def test_the_edge_gate_finds_what_p18_shipped():
    """The gate fails the two forms the deleted mappers had."""
    fields = ['Execution.handoff_from']
    assert _assembled_edges("  edge(out, 'Execution.handoff_from', 'execution', e.handoff_from);",
                            fields)
    assert _assembled_edges("out.append({'rel': r, 'to': t, 'field': 'Execution.handoff_from'})",
                            fields)
    assert not _assembled_edges("const live = e.field === 'executions.task_id';", fields)


# ── generated client everywhere (p19-design-gate B11) ──

def _raw_paths(src):
    """Every `/v1/` path the SPA source spells out itself, comments aside."""
    code = re.sub(r'/\*[\s\S]*?\*/', '', src)
    code = re.sub(r'(^|\s)//[^\n]*', r'\1', code)
    return re.findall(r"""['"`]/v1/[^'"`]*""", code)


def test_the_spa_reads_every_path_from_the_generated_client():
    """A route rename must fail the type check, so no SPA module spells a
    `/v1/` path: reads use `paths.*`, commands `api.*` (generated.ts)."""
    skip = {os.path.join('src', 'api', 'generated.ts'), os.path.join('src', 'data', 'rules.ts')}
    bad = {}
    for dp, _ds, fs in os.walk(os.path.join(APP, 'src')):
        for f in fs:
            p = os.path.join(dp, f)
            if f.endswith(('.ts', '.tsx')) and os.path.relpath(p, APP) not in skip:
                with open(p, encoding='utf-8') as fh:
                    if hits := _raw_paths(fh.read()):
                        bad[os.path.relpath(p, APP)] = hits
    assert not bad, bad


def test_the_path_gate_finds_a_spelled_path_and_ignores_a_comment():
    assert _raw_paths("const s = useRead<X>('/v1/attention');")
    assert _raw_paths("useRead(`/v1/missions/${id}`)")
    assert not _raw_paths("// Core's `/v1/status` lists as live\nconst x = paths.status();")
    assert not _raw_paths("/** An edge as `/v1/world/graph` returns it */")


def _py_raw_paths(src):
    """Every string in Python source that is itself a `/v1/` path."""
    import ast
    return [n.value for n in ast.walk(ast.parse(src))
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and n.value.startswith('/v1/')]


def test_the_cli_and_the_tui_read_every_path_from_the_generated_client():
    """B11: the CLI and the TUI build every path with `archeus/cli/_api.py`."""
    top = os.path.join(ROOT, 'archeus', 'cli')
    bad = {}
    for dp, _ds, fs in os.walk(top):
        for f in fs:
            if f.endswith('.py') and f not in ('_api.py', '_tables.py'):
                with open(os.path.join(dp, f), encoding='utf-8') as fh:
                    if hits := _py_raw_paths(fh.read()):
                        bad[os.path.relpath(os.path.join(dp, f), ROOT)] = hits
    assert not bad, bad


def test_the_python_path_gate_finds_a_spelled_path():
    assert _py_raw_paths("app.read('/v1/attention')")
    assert _py_raw_paths("x = '/v1/missions/%s/plan' % mid")
    assert not _py_raw_paths("print('Core did not answer /v1/health')")

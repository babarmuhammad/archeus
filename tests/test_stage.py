"""The stage: one animated 3D background behind the whole app.

This is a deliberate, scoped reversal of "there is no ambient layer", and these
tests exist to hold the line that makes it a different thing from the layer that
was deleted:

  ONE surface, not thirty.   Guarded in tests/test_themes.py.
  Driven by state.          It is handed numbers a renderer already fetched; it
                            never issues a request, exactly like INST.set().
  It stops.                 Hidden, blurred, motion:off, stage:off, reduced
                            motion, lost context.
  It fails open.            No vendor bundle, no WebGL or a dead context all land
                            on the static CSS gradient with the app untouched.

Plus the two things a second GPU surface in this particular shell must never do:
introduce a CSS readback (the original cause of the Qt tearing) or make the app
depend on 890KB of vendored code having arrived.
"""
import re

from claude_sessions import gui, themes
from claude_sessions.gui_html import PAGE, VENDOR_FILES, vendor_asset

import inspect
_SRC = inspect.getsource(gui)
_CSS = PAGE[PAGE.index('<style>'):PAGE.index('</style>')]
#: all of stage.js — the object AND the scene factories, which is what the
#: "must not appear" assertions below want to cover
_STAGE = PAGE[PAGE.index('const STAGE_SCALE ='):PAGE.index('window.STAGE = STAGE;')]
_SCENES = PAGE[PAGE.index('const STAGE_SCENES = {'):PAGE.index('/* ── wiring ──')]


# ── the data ──────────────────────────────────────────────────

def test_every_skin_names_a_scene_that_exists():
    """A skin naming a missing scene falls back to 'hud' silently, so the skin
    would look identical to another one and nobody would know why."""
    for name, sk in themes.SKINS.items():
        assert sk['stage'] in themes.STAGE_SCENES, f'{name}: {sk["stage"]}'
        assert f"  {sk['stage']}(TH, c) {{" in _SCENES \
            or f"  '{sk['stage']}'(TH, c) {{" in _SCENES, \
            f'{name}: no {sk["stage"]} implementation'


def test_every_scene_is_worn_by_a_skin():
    """The other direction: an orphan scene is dead code that still costs review
    attention every time someone touches this file."""
    worn = {sk['stage'] for sk in themes.SKINS.values()}
    assert set(themes.STAGE_SCENES) == worn, set(themes.STAGE_SCENES) ^ worn


def test_bloom_is_off_where_the_skin_says_it_should_be():
    """Bloom costs two extra render targets. Brutalism has no glow by definition
    and the CRT draws its own in-shader, so both must genuinely skip the
    composer rather than run it at strength 0."""
    assert themes.SKINS['brutal']['bloom'] == 0
    assert themes.SKINS['crt']['bloom'] == 0
    assert 'if (!strength) return;' in _STAGE


def test_translucency_is_what_makes_the_stage_visible():
    """Fully opaque panels would hide the scene everywhere but the gutters, so
    every skin has to make a deliberate choice about it — and Brutalist choosing
    1.0 is a choice, not an oversight."""
    for name, sk in themes.SKINS.items():
        # the ceiling matters as much as the floor: at 0.9+ the scene is only
        # visible in the gutters, which is why the first cut looked like it had
        # no background at all ("i don't see anything with the graph")
        assert 0.5 <= sk['op'] <= 0.9, f'{name}: op={sk["op"]}'
    # Graph is the most translucent — it has a live lattice to sit over.
    assert themes.SKINS['graph']['op'] < themes.SKINS['brutal']['op']
    assert '--sk-op' in _CSS
    assert 'rgba(var(--panel-rgb' in _CSS


def test_the_user_can_override_transparency_for_every_look():
    """A look proposes an `op`; how much background you want behind your working
    surfaces is taste and monitor, so it is exposed and it wins everywhere.
    0 means "follow the look"."""
    assert 'def _surface(' in _SRC
    assert gui._surface({}) == 0
    assert gui._surface({'surface': 70}) == 70
    assert gui._surface({'surface': 5}) == 40, 'no floor — text would fight the scene'
    assert gui._surface({'surface': 'nope'}) == 0
    assert "st.setProperty('--sk-op',ST.surface?(ST.surface/100)" in PAGE
    assert 'id="sSurf"' in PAGE
    assert "post('/api/settings',{surface:+el.value})" in PAGE
    # dragging must not POST per pixel
    assert 'el.oninput=' in PAGE and 'el.onchange=' in PAGE


# ── the contract ──────────────────────────────────────────────

def test_the_stage_never_fetches_anything():
    """Same rule the instruments follow. A background that polls is a background
    that keeps the machine awake for its own benefit."""
    for dead in ('fetch(', 'api(', 'XMLHttpRequest', 'setInterval'):
        assert dead not in _STAGE, f'{dead} in the stage'


def test_it_is_driven_by_real_workspace_state():
    """The honest answer to "animated everywhere": the motion means something.
    Energy comes from running jobs, a launch shocks it, navigation ripples it."""
    for fn in ('energy(n)', 'shock()', 'impulse()', 'page(name)'):
        assert fn in _STAGE, fn
    assert 'function stageEnergy(jobs,burn)' in PAGE
    assert 'stageEnergy(liveJobs(),0)' in PAGE, 'jobs do not feed the stage'
    assert 'STAGE.shock()' in PAGE, 'the launch moment does not reach the stage'
    assert 'STAGE.page(page);STAGE.impulse();' in PAGE, 'navigation does not'
    # ...and NOT off throughput alone. Feeding a liveness test from a token
    # counter is the one-word bug that made the equalizer animate forever.
    # /4: the input is live Claude Code sessions now, not the rare background
    # job, so the scale has to have headroom or it pins at full all day
    assert 'const j=Math.min(1,(jobs||0)/4);' in PAGE


def test_every_pause_condition_is_present():
    """Five ways it must stop. Losing any one of them means a laptop rendering a
    3D scene into a window nobody is looking at."""
    assert 'if (document.hidden || !this.vis) return;' in PAGE   # tab hidden
    assert 'function setVis(v)' in PAGE                          # Qt blur/minimise
    assert '!MO.on' in _STAGE                                    # motion:off
    assert "this.tier === 'off'" in _STAGE                       # stage:off
    assert "MO_REDUCED ? 'off'" in PAGE                          # OS preference
    assert 'webglcontextlost' in _STAGE                          # driver reset


def test_it_is_frame_capped_and_render_scaled():
    """A background has nothing to say at 60fps, and devicePixelRatio is ignored
    on purpose: this is a soft full-screen field, not the instruments' hairline
    arcs (which clamp to 2 for exactly the opposite reason)."""
    assert 'const STAGE_SCALE = 0.75;' in PAGE
    # Idle sits in the 20s: low enough to be nearly free, high enough that the
    # drift reads as motion rather than a stutter. It was briefly dropped to 12
    # along with the brightness, and the background stopped looking animated —
    # see test_the_background_still_moves_when_nothing_is_happening.
    assert re.search(r'STAGE_FPS_IDLE = 2\d;', PAGE)
    assert 'if (this._acc < 1 / fps) return true;' in _STAGE
    assert 'devicePixelRatio' not in _STAGE, 'DPR must not drive the stage'


def test_the_fallback_chain_exists():
    """WebGL -> static gradient, at every failure point, with the app untouched.
    The washes paint from first byte and are only removed once GL has actually
    rendered a frame, so a slow module import is not a second of blank."""
    assert '_static()' in _STAGE and '_giveUp(why)' in _STAGE
    assert 'stage-off' in _CSS and 'stage-on' in _CSS
    assert 'html.stage-on body::before,html.stage-on body::after{opacity:0}' in _CSS
    assert 'body::before' in _CSS, 'the static wash was deleted, not kept'
    assert "if (!this._painted) { this._painted = true; this._live(); }" in _STAGE
    assert "window.addEventListener('vendor-failed'" in PAGE


def test_the_app_does_not_depend_on_the_vendor_bundle():
    """Every reach into the vendored globals is guarded. A failed import must
    cost the background and nothing else."""
    assert PAGE.count('if(window.STAGE)') + PAGE.count('if (window.STAGE)') >= 4
    assert 'const A = window.ANI;\n    if (!A) return null;' in PAGE
    # motion falls back to its own WAAPI path when anime is missing
    assert 'if (!A) {                                  // no vendor bundle: old path' in PAGE


def test_no_readback_layer_anywhere_near_the_canvas():
    """The whole reason bloom is affordable here is that it happens in GL. A CSS
    filter on or around this canvas would reintroduce the exact framebuffer
    readback that caused the Qt tearing."""
    stage_css = _CSS[_CSS.index('#stage{'):_CSS.index('body::before')]
    for dead in ('backdrop-filter', 'filter:', 'mix-blend-mode'):
        assert dead not in stage_css, f'{dead} on the stage layer'
    assert 'alpha: false' in _STAGE, 'a transparent surface costs a blend per composite'


# ── serving the vendored code ─────────────────────────────────

def test_vendored_libraries_are_present_with_their_licences():
    """Vendored, not CDN'd: the GUI is offline by design. Both are MIT and the
    licence text ships beside the code."""
    for f in ('three.module.min.js', 'three.core.min.js', 'anime.esm.min.js',
              'LICENSE-three.txt', 'LICENSE-anime.txt'):
        assert f in VENDOR_FILES, f
    for f in ('postprocessing/EffectComposer.js', 'postprocessing/UnrealBloomPass.js',
              'postprocessing/Pass.js', 'shaders/CopyShader.js'):
        assert f in VENDOR_FILES, f
    assert 'MIT' in VENDOR_FILES['LICENSE-three.txt'].read_text(encoding='utf-8')


def test_vendor_is_served_not_inlined():
    """~890KB in the page string on every load, for code no test asserts on, is
    pure cost. It is a separate cacheable route instead — and stage.js, which IS
    ours, stays inside PAGE so the string-matching tests can still see it."""
    assert 'three.module.min' not in PAGE.replace('"/vendor/three.module.min.js"', '')
    # The ceiling exists to catch an INLINED BUNDLE, so it is set against the
    # smallest one there is to inline: anime.esm.min.js at ~118KB (three is
    # ~365KB). 650KB leaves the page room to grow by a normal feature's worth of
    # markup and still fails the moment a vendor file lands inside it — the old
    # 600KB was 260 bytes above the page as shipped, so the next edit of any
    # size was going to fail it for the wrong reason.
    assert len(PAGE) < 650_000, f'page is {len(PAGE)} bytes — is a library inlined?'
    assert 'const STAGE = {' in PAGE, 'stage.js must stay in the bundle'


def test_the_vendor_route_is_reachable_without_the_guard_header():
    """A <script src> cannot attach X-Archeus, so a guarded route would 403
    every module fetch. Placed with / and /graph, before _guard()."""
    src = gui.do_GET_SOURCE if hasattr(gui, 'do_GET_SOURCE') else ''
    import inspect
    src = src or inspect.getsource(gui._Handler.do_GET)
    assert src.index("startswith('/vendor/')") < src.index('self._guard()')


def test_the_vendor_route_cannot_escape_its_directory():
    """The allowlist is a dict built by walking the directory, so traversal is a
    miss rather than a path-arithmetic bug waiting to be got wrong."""
    for evil in ('../gui.py', '../../pyproject.toml', '/etc/passwd',
                 '..%2Fgui.py', 'nope.js', '', '.'):
        assert vendor_asset(evil) is None, evil
    got = vendor_asset('anime.esm.min.js')
    assert got and got[1] == 'text/javascript' and len(got[0]) > 1000


def test_vendored_assets_are_cached_hard():
    """Pinned, immutable library code fetched once — not on every reload."""
    import inspect
    src = inspect.getsource(gui._Handler._serve_vendor)
    assert 'max-age=' in src and 'immutable' in src


# ── the setting ───────────────────────────────────────────────

def test_stage_tier_round_trips(monkeypatch, tmp_path):
    monkeypatch.setattr(gui._c, 'config_dir', str(tmp_path))
    # the DEFAULT is lite: bloom is opt-in after the first cut read as too much
    for saved, want in (({}, 'lite'), ({'stage': 'cinematic'}, 'cinematic'),
                        ({'stage': 'off'}, 'off'), ({'stage': 'bogus'}, 'lite')):
        assert gui._stage_tier(saved) == want, saved


def test_motion_off_forces_the_stage_off():
    """Someone who has asked for no animation has not asked for a 3D
    background, whatever the stage setting happens to say."""
    assert gui._stage_tier({'motion': 'off', 'stage': 'cinematic'}) == 'off'
    assert gui._stage_tier({'theme_motion': 'off'}) == 'off'   # legacy key


def test_the_setting_is_offered_and_persisted():
    assert "id=\"sStage\"" in PAGE
    assert "post('/api/settings',{stage:ST.stage})" in PAGE
    assert "localStorage.setItem('ctl_stage'" in PAGE
    assert 'stage' in gui._SETTING_KEYS


def test_lite_is_documented_as_the_tearing_escape_hatch():
    """The Qt surface-swap history is the reason this tier exists at all; if the
    note goes, the next person just turns the whole thing off."""
    assert 'lite' in themes.STAGE_TIERS
    assert 'tear' in PAGE[PAGE.index('const STAGE_NOTE={'):
                          PAGE.index('const STAGE_NOTE={') + 700]


# ── persistence ───────────────────────────────────────────────

def test_every_setting_the_gui_can_post_actually_survives_a_reload():
    """The one that bit hardest, and silently.

    load_settings() keeps only keys present in _DEFAULT_SETTINGS, and
    /api/settings does load -> mutate -> save. So a key the POST handler accepted
    but the defaults did not declare was written to disk once and then DELETED by
    the next save of any other setting. `world`, `skin`, `stage`, `motion` and
    `surface` were all in that state:

        "when i close and open the archeus app, it goes back to classic theme"

    `theme` happened to be declared, which is why it was the only appearance
    setting that appeared to work. Reading the POST allowlist straight out of the
    handler means a new setting cannot be added without also being declared."""
    from claude_sessions.config import _DEFAULT_SETTINGS
    keys = list(gui._SETTING_KEYS)
    assert 'world' in keys and 'surface' in keys, keys
    undeclared = [k for k in keys if k not in _DEFAULT_SETTINGS]
    assert not undeclared, f'accepted but discarded on read: {undeclared}'


def test_appearance_settings_round_trip_through_disk(tmp_path, monkeypatch):
    from claude_sessions import config as cfg
    monkeypatch.setattr(cfg, 'settings_file', str(tmp_path / 'archeus.json'))
    s = cfg.load_settings()
    s.update({'world': 'graph', 'skin': 'crt', 'stage': 'lite',
              'motion': 'subtle', 'surface': 64, 'theme': 'slate'})
    assert cfg.save_settings(s)
    back = cfg.load_settings()
    for k, v in (('world', 'graph'), ('skin', 'crt'), ('stage', 'lite'),
                 ('motion', 'subtle'), ('surface', 64), ('theme', 'slate')):
        assert back.get(k) == v, f'{k} did not survive: {back.get(k)!r}'
    # …and saving something ELSE must not wipe them, which is the actual failure
    back['default_effort'] = 'high'
    cfg.save_settings(back)
    again = cfg.load_settings()
    assert again.get('world') == 'graph', 'a later save deleted the world again'


def test_the_graph_links_carry_travelling_data():
    """The homage is not just the solids — connections.py runs particles along
    its edges, and so does this. Always moving (the links carry something), but
    faster and denser with energy, so it still reports rather than decorates.

    The per-segment seed is load-bearing: without it every edge pulses in
    lockstep and the field reads as a strobe rather than as traffic."""
    g = PAGE[PAGE.index('  graph(TH, c) {'):PAGE.index('  /* Terminal —')]
    assert 'float packet(float at, float head)' in g
    assert "gLink.setAttribute('lsd'" in g, 'no per-segment seed'
    assert 'attribute float lsd;' in g and 'vS = lsd;' in g
    # two packets per link, de-synchronised, and the speed reads energy
    assert 'fract(u_t * sp + vS)' in g and 'vS + 0.53' in g
    assert 'float sp = 0.16 + 0.42 * u_e;' in g
    # every attribute the link shader declares must exist on its geometry —
    # a declared-but-absent one reads as 0 and the lines silently vanish
    for a in ('lt', 'li', 'lsd'):
        assert f"gLink.setAttribute('{a}'" in g, a
        assert f'attribute float {a};' in g, a


def test_the_dodecahedra_vary_in_size_and_collide_by_mass():
    """A uniform spread gives forty forgettably similar solids. Cubing a flat
    hash gives a long tail — a few hubs among many leaves, the read the real
    architecture graph has. Once sizes differ, equal-mass collision is wrong:
    a pea would deflect a boulder."""
    g = PAGE[PAGE.index('  graph(TH, c) {'):PAGE.index('  /* Terminal —')]
    assert 'Math.pow(h, 3)' in g, 'size is not long-tailed'
    assert 'm: r * r * r' in g, 'no mass'
    assert 'const mi = nodes[i].m, mj = nodes[j].m, mt = mi + mj;' in g
    assert '(2 * mj / mt)' in g and '(2 * mi / mt)' in g
    assert 'if (vi - vj <= 0) continue;' in g, 'no separating-pair guard'
    # the wall inset, or a large solid half-leaves the frame
    assert 'BOUND[k] - nodes[i].r' in g

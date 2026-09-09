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

from claude_sessions import cluster_spec as CS, gui, themes
from claude_sessions.gui_html import PAGE, VENDOR_FILES, vendor_asset

import inspect
_SRC = inspect.getsource(gui)
_CSS = PAGE[PAGE.index('<style>'):PAGE.index('</style>')]
#: all of stage.js — the object AND the scene factories, which is what the
#: "must not appear" assertions below want to cover
_STAGE = PAGE[PAGE.index('const STAGE_SCALE ='):PAGE.index('window.STAGE = STAGE;')]
_SCENES = PAGE[PAGE.index('const STAGE_SCENES = {'):PAGE.index('/* ── wiring ──')]



#: the graph scene only — the other six scenes in this file draw other things.
#: Kept next to _STAGE rather than in the middle of the constellation tests,
#: because it is a module-level helper and every one of them reaches for it.
def _graph():
    return PAGE[PAGE.index('  graph(TH, c) {'):PAGE.index('  /* Terminal —')]


# ── the data ──────────────────────────────────────────────────

def test_every_skin_names_a_scene_that_exists():
    """A skin naming a missing scene falls back to 'hud' silently, so the skin
    would look identical to another one and nobody would know why."""
    for name, sk in themes.SKINS.items():
        assert sk['stage'] in themes.STAGE_SCENES, f'{name}: {sk["stage"]}'
        # a scene takes (TH, c) and MAY take more — the graph scene also takes
        # the renderer, because it builds an environment map with
        # PMREMGenerator. Pinning the exact arity made this test about a
        # signature rather than about whether the scene exists at all, which is
        # the thing it is for.
        assert re.search(r'\n  %s\(TH, c[^)]*\) \{' % re.escape(sk['stage']), _SCENES), \
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
    for the BACKGROUND: it is a soft full-screen field, and paying for a 4K one
    behind opaque cards is waste. That is the opposite of the instruments'
    clamp-to-2, which exists because they draw hairline arcs.

    A scene that IS hairlines raises its own scale, and the graph scene does —
    glass rods a few pixels wide and 42 beads per cage crawl and stair-step at
    0.75. That used to be a zen-only supersample read off devicePixelRatio,
    which meant the theme was sharper while you were looking at it than while
    you were using it; the scale belongs to the SCENE, and DPR is now read
    nowhere in the stage at all.

    ...AND THE SCENE'S NUMBER IS CAPPED BY A PIXEL BUDGET, which is the half
    that was missing and is most of why the graph world tore in the Qt shell.
    A scale is a MULTIPLIER: 1.5 was judged at one window size and silently
    became 3840x2160 = 8.3 million pixels of blended PBR on a 1440p panel, plus
    every mip of the bloom pass over the same area. The frame stopped finishing
    inside the compositor's budget and QtWebEngine swapped a surface
    mid-composite. The cap is on the PRODUCT, so a small window still gets the
    crisp hairlines the scene asked for."""
    assert 'const STAGE_SCALE = 0.75;' in PAGE
    # Idle sits in the 20s: low enough to be nearly free, high enough that the
    # drift reads as motion rather than a stutter. It was briefly dropped to 12
    # along with the brightness, and the background stopped looking animated —
    # see test_the_background_still_moves_when_nothing_is_happening.
    assert re.search(r'STAGE_FPS_IDLE = 2\d;', PAGE)
    assert 'if (this._acc < want - vs * 0.5) return true;' in _STAGE
    # comments stripped: the word survives in the note saying why it is gone
    code = re.sub(r'^\s*//.*$', '', re.sub(r'/\*.*?\*/', '', _STAGE, flags=re.S), flags=re.M)
    assert 'devicePixelRatio' not in code, 'DPR must not drive the background'
    assert 'const want = (this._sc && this._sc.scale) || STAGE_SCALE;' in _STAGE, \
        'the render scale is not the scene\'s own number'
    assert 'return Math.min(want, Math.sqrt(this._budget / px));' in _STAGE, \
        'the scene\'s scale is unbounded again — this is what tore the Qt surface'
    assert 'const STAGE_PIXEL_BUDGET = 3.0e6;' in PAGE
    # a window resize changes the cap, so the ratio has to be re-read there and
    # not only at build — otherwise a window dragged onto a bigger panel keeps
    # the small one's scale
    assert _STAGE.index('this._ren.setPixelRatio(this._ratio());') \
        < _STAGE.index('this._ren.setSize(w, h, false);'), \
        'resize() does not re-apply the pixel ratio'
    # ...and the scene that needs it asks for it
    assert 'const S = sScene(TH, cam, .5, 1.5);' in _graph(), \
        'the graph scene draws hairlines at the soft-field scale'


def test_the_drawing_buffer_is_preserved():
    """THE FLICKER, and the fact behind it was already written down in this file
    — attached to the wrong case.

    blur() carried it: with preserveDrawingBuffer:false the WebGL backbuffer is
    undefined once it has been presented, so Qt recomposites against a surface
    with nothing valid in it and you get artefacts. That was applied to the
    unfocused window, and `preserveDrawingBuffer: true` was dismissed
    everywhere else as "a buffer copy on every single frame to repair a state
    nobody is looking at".

    Somebody is looking at it. The stage draws at 30fps BY DESIGN and
    QtWebEngine composites at 60 — more often while scrolling — so every
    composite between two stage frames is exactly the surface that sentence
    describes. Reported as a strobe rather than a scanline tear: constant,
    worse on scroll, and clean the moment the stage is switched off, which is
    what identified it.

    The copy is per RENDERED frame, not per composite, and STAGE_PIXEL_BUDGET
    bounds what it copies — measured in the real Qt shell at 3.0M px on an
    Intel UHD it did not move the frame interval at all (p50 33.4ms against a
    33.4ms target, page rAF still a clean 16.7ms)."""
    assert 'preserveDrawingBuffer: true,' in _STAGE, \
        'the stage presents an undefined backbuffer again — this is the flicker'


def test_the_canvas_is_not_a_scanout_plane_candidate():
    """THE FULLSCREEN HALF, reported precisely: clean windowed, starts the
    moment the window goes fullscreen.

    That is a Windows compositing boundary and nothing about the scene. A
    windowed app is composited by DWM, DWM is always vsynced, and the canvas is
    simply re-composited on the frames it did not redraw — it cannot tear. A
    fullscreen or maximised window gets independent flip / multiplane overlay,
    where an OPAQUE canvas is eligible to become its own scanout plane. A plane
    updating every third vsync against a page plane updating every one puts two
    different moments on screen at once.

    `alpha: true` makes the canvas something that must be BLENDED into the
    page, so it is not a promotion candidate. Chromium decides that on the
    context attribute rather than on the pixels, and the pixels do not change:
    the clear colour is still --bg at alpha 1, every pass preserves a
    destination alpha of 1, so it stays opaque to look at.

    The old value was a deliberate cost decision — "a transparent surface has
    to be blended on every composite; an opaque one is a straight blit" — and
    the blit was the problem. Measured in the Qt shell after: fullscreen and
    windowed are now identical, p50 50.0ms against a 50.1ms target with the
    page's rAF a clean 16.7ms in both, where before fullscreen was the odd one
    out."""
    assert 'alpha: true,' in _STAGE, \
        'an opaque canvas can be promoted to its own scanout plane in fullscreen'
    # ...and NOT by drawing every vsync instead. That was the other candidate,
    # it is the obvious one, and measured it took the whole page from a 16.7ms
    # rAF to 66.6ms — far worse than the artefact. The divisor is never 1 by
    # fiat; it is ceil(target / vsync), times the compositor back-off.
    assert 'Math.max(1, Math.ceil(1 / fps / vs)) * vs * this._slow;' in _STAGE, \
        'fullscreen full-rate is back; it was measured and it is worse'


def test_the_frame_cap_is_a_whole_number_of_vsyncs():
    """THE TEARING BUG, and it was never a cost problem.

    Measured in the real Qt shell (tools/probe_qt.py, which exists because
    nothing else could): the page's own rAF ran a clean 16.7ms at BOTH p50 and
    p95 — solid 60Hz, zero long tasks — while the stage's frame interval came
    out p50 33.7ms and p95 50.1ms. Those are not "slow". They are exactly TWO
    and THREE vsyncs.

    The cap used to be an accumulator against a wall-clock target: draw once
    1/fps has elapsed. 1/34 is 29.4ms, a 60Hz display can only deliver 16.7,
    33.3 or 50.0, so it alternated 2,2,3,2,2,3 forever. That is a beat: the
    canvas swap lands at a different point of the compositor's cycle every
    frame, and on QtWebEngine's GPU hardware surface that is what reads as
    tearing. It was invisible to every measurement here because the AVERAGE is
    correct — only the distribution is wrong, and nothing was looking at one.

    After: p50 33.4ms against a 33.4ms target, p95 42ms, and the page still at
    a clean 16.7.

    CEIL and not round, so the stage never draws MORE often than the fps asked
    for and idle/busy stay on different divisors at 60Hz (3 and 2) instead of
    collapsing to the same one."""
    assert 'Math.max(1, Math.ceil(1 / fps / vs)) * vs' in _STAGE, \
        'the frame cap is a wall-clock target again — this is the tearing bug'
    # the display period is MEASURED. 60Hz is not a fact about anyone's machine
    # and a 120Hz panel needs a different divisor.
    assert 'const vs = Math.min(0.05, Math.max(1 / 144, this._vs || 1 / 60));' in _STAGE
    # ...as a MEDIAN. A minimum-ratchet latches on a short delta (measured: it
    # reported a 6.5ms vsync on a 60Hz panel) and a mean is pulled up by every
    # dropped frame. A median is indifferent to both.
    assert 'this._vr[this._vi++ % 31] = dt;' in _STAGE
    assert 'const s = this._vr.slice().sort((a, b) => a - b);' in _STAGE
    code = re.sub(r'^\s*//.*$', '', re.sub(r'/\*.*?\*/', '', _STAGE, flags=re.S), flags=re.M)
    assert 'Math.min(this._vs' not in code, 'the vsync estimate ratchets again'


def test_the_stage_backs_off_when_it_is_starving_the_compositor():
    """THE FULLSCREEN FLICKER, and it was a third resource nobody was managing.

    The canvas is full-viewport, so every frame it presents makes the
    compositor redraw the whole screen under the app's translucent panels. Our
    own DRAWING is trivial — measured on the reporting machine, a 3.75x cut in
    fill bought 4ms and a two-triangle scene ran at the same rate as this one —
    but at 2560x1440 on an Intel UHD the compositor cannot recomposite 24 times
    a second on top of everything else.

    What that looks like is not slowness. Chromium halves the page's frame rate
    when it cannot keep up, so the whole app lurches between 60 and 30Hz, which
    is what was reported as flickering. It appears in fullscreen and nowhere
    else because windowed the composited area is small enough to afford, and it
    survived a pixel budget, a triangle cut, `alpha`, `preserveDrawingBuffer`
    and `--disable-direct-composition` because none of those change how OFTEN
    the screen is recomposited. Measured, same scene, same machine:

        every frame:  page rAF p50 33.3ms / p95 83.3ms   30fps, lurching
        one in four:  page rAF p50 16.7ms / p95 33.3ms   60fps, steady

    The signal is the display period the stage already measures. Nothing else
    could see this: the stage's own interval sat within 25% of its target
    throughout, because it was hitting the target it asked for — on a page that
    had been slowed to half speed underneath it.

    ONE WAY UNTIL THE LAYOUT CHANGES. Back off and the period recovers; speed
    up on that and it strains again, forever. resize() resets it, because
    entering or leaving fullscreen is exactly when the answer changes and
    exactly when a resize fires."""
    assert '* vs * this._slow;' in _STAGE, 'the compositor back-off is not applied'
    assert '_slow: 1, _strain: 0,' in _STAGE
    # the TAIL, not the median. At _slow 2 the page's rAF was a healthy 16.7ms
    # at p50 and still 50ms at p95, so a median trigger stopped one rung early
    # while frames were still being dropped — and a dropped frame is the
    # flicker. One sort, two statistics.
    assert 'this._vsHi = s[27];' in _STAGE, 'strain reads the median again'
    assert 'this._vsHi > 0.020' in _STAGE
    # reset on resize is what makes one-way safe rather than permanent
    assert 'this._slow = 1; this._strain = 0;' in _STAGE, \
        'leaving fullscreen never gives the frame rate back'
    code = re.sub(r'^\s*//.*$', '', re.sub(r'/\*.*?\*/', '', _STAGE, flags=re.S), flags=re.M)
    assert '_slow /' not in code and '_slow--' not in code, \
        'the back-off can climb back up inside a layout, which oscillates'


def test_the_stage_measures_its_own_cost_and_steps_down_one_way():
    """Every number in stage.js was tuned under SwiftShader on a bench, and the
    handoff says so: "cost has not been measured on real hardware, and this pass
    ADDED to it". A background cannot ask what GPU it is on, so it watches
    itself — and the two properties that make that safe rather than annoying are
    both asserted here.

    WHAT IS MEASURED IS THE ACHIEVED INTERVAL, not the time around render().
    WebGL submission is asynchronous, so timing the render call measures command
    queueing, which on a saturated GPU is near zero; what a saturated GPU does
    is stall the next buffer swap, and that lands in `fdt`. Same family as
    _T/_Tw: never assert on how many frames the machine managed.

    ONE WAY, because a ladder that can climb back up oscillates — degrade, frame
    gets cheap, restore, frame gets expensive, forever. A background that
    changes quality twice a second is worse than a slow one."""
    assert '_watch(fdt, want)' in _STAGE and 'this._watch(fdt, want);' in _STAGE
    assert '_budget: STAGE_PIXEL_BUDGET, _degraded: 0' in _STAGE
    # two steps, then it stops trying — fill first (cheapest to give up), then
    # the tier, which is the ladder CLAUDE.md already documents
    assert 'if (this._degraded >= 2) return;' in _STAGE, 'the ladder can loop'
    # AN INTEGRATOR, not a consecutive run. The first cut needed 90 frames in a
    # row over budget and reset on any frame that was not — measured against
    # the real Qt shell it never fired once, because a machine that is short by
    # a fifth is late in bursts and a run of ninety never happens.
    assert 'this._over + (fdt > want * 1.5 ? 2 : -1)' in _STAGE, \
        'the ladder counts a consecutive run again, which never fires'
    assert "this._budget *= 0.5;" in _STAGE
    assert "this.tier = 'lite';" in _STAGE
    # a parked chain resuming is not a slow frame; blur() sets _acc = 1 on
    # purpose and one such sample would poison the mean for a minute
    assert 'if (fdt > 0.5) { this._over = 0; return; }' in _STAGE
    # nothing anywhere may raise the tier or the budget back
    code = re.sub(r'^\s*//.*$', '', re.sub(r'/\*.*?\*/', '', _STAGE, flags=re.S), flags=re.M)
    assert '_degraded--' not in code and '_degraded = 0' not in code, \
        'the degrade ladder is no longer one-way'


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
    # the canvas's own alpha moved to test_the_canvas_is_not_a_scanout_plane_candidate,
    # where it belongs: it is a PRESENTATION choice, not a readback one, and it
    # came out the other way once fullscreen was measured.


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
    # ~365KB). The rule for moving it, which is the only reason it is written
    # down: it must sit far enough above the page as shipped that a normal
    # feature's worth of markup does not trip it, and far enough below
    # page + 118KB that the smallest bundle still does. 600KB was 260 bytes
    # above the page and failed the next edit for the wrong reason; 650KB was
    # spent by the hull-faces pass and the brightness slider; 740KB was spent
    # by the cluster spokes and the five-section navigation together, and
    # tripped 239 bytes over. At 800KB against a ~740KB page, an inlined anime
    # lands at ~858KB and still fails.
    assert len(PAGE) < 800_000, f'page is {len(PAGE)} bytes — is a library inlined?'
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
    """The homage is not just the cages — connections.py runs particles along
    its edges, and so does this. Always moving (the conduits carry something),
    but faster and denser with energy, so it still reports rather than
    decorates.

    The de-synchronisation is load-bearing: without it every conduit pulses in
    lockstep and the field reads as a strobe rather than as traffic. It is a
    per-SEGMENT seed again, pushed identically onto both endpoints so it
    survives interpolation — the version that took it from the instanced
    conduit's LAYER went with the instanced conduit.

    ON THE SPEED, because the file has now carried two different answers. The
    three-layer tube ran at `0.045 + 0.11 * u_e`, with a note saying 0.16 read
    as a strobe there — and that was a packet on the CORE layer of a coaxial
    triple, dimmed by a housing and a glass sleeve over it. On a bare hairline
    it is the whole line that brightens, which is the value the graph theme ran
    at for its whole life before the cluster work and the one that was asked
    for back."""
    g = _graph()
    assert 'float sp = 0.16 + 0.42 * u_e;' in g, 'no packet speed'
    assert 'float packet(float at, float head){' in g, 'no packet'
    assert 'packet(vT, fract(u_t * sp + vS))' in g, 'the packet does not travel'
    # the second, slower packet at an offset phase — one dot per conduit reads
    # as a blink, two at different speeds read as traffic
    assert 'packet(vT, fract(u_t * sp * 0.72 + vS + 0.53)) * 0.7' in g
    # one seed per SEGMENT, on both ends
    assert 'const sd = ((seg * 9301 + 49297) % 233280) / 233280;' in g
    assert 'cs.push(sd, sd);' in g, 'the seed does not survive interpolation'
    # ...and the navigation surge, which is the one-shot on top of the loop
    assert 'u_pulse' in g[g.index('float packet('):], 'no navigation surge'


def test_the_clusters_vary_in_size_and_collide_by_mass():
    """A uniform spread gives forty forgettably similar cages. Raising a flat
    hash to a power gives a long tail — a few hubs among many leaves, the read
    the real architecture graph has and the read the reference constellation
    has. Once sizes differ, equal-mass collision is wrong: a pea would deflect
    a boulder. Phase 4 lengthened the tail (exponent 4, not 3), which makes the
    mass physics MORE load-bearing, not less — hence re-asserted here rather
    than relaxed."""
    g = _graph()
    # Exponent 3.4 over a 0.34 floor, and it is the FLOOR that has moved three
    # times — 0.10, then 0.16, now 0.34 — always for the same reason and always
    # by too little. The tail's SHAPE is right and the top is right; the bottom
    # is what kept failing. Below 0.22 a cluster is under the LOD ladder's
    # first break, so it draws no frame and no junctions at all, and at 0.16
    # thirteen of the forty landed there: a third of the frame was a wire
    # diagram of specks joined by conduit, where in cluster-render-field.png
    # every cage in the crop has its frame and its twelve lit junctions. So the
    # floor is asserted ABOVE the ladder's first break rather than as a
    # literal, which is the property that actually matters.
    assert 'Math.pow(h, 3.4) * 1.26' in g, 'size is not long-tailed enough'
    m = re.search(r'const r = ([\d.]+) \+ Math\.pow\(h', g)
    assert m, 'the radius floor is gone'
    from claude_sessions.cluster_spec import LOD_BREAKS
    assert float(m.group(1)) >= LOD_BREAKS[0], \
        f'floor {m.group(1)} is under the first LOD break — cages with no frame'
    assert 'm: r * r * r' in g, 'no mass'
    assert 'const mi = nodes[i].m, mj = nodes[j].m, mt = mi + mj;' in g
    assert '(2 * mj / mt)' in g and '(2 * mi / mt)' in g
    assert 'if (vi - vj <= 0) continue;' in g, 'no separating-pair guard'
    # the wall inset, or a large cage half-leaves the frame while its centre is
    # still legally inside. Re-asserted against the WEDGE rather than deleted:
    # x and y are no longer constants (see the frustum test below), but the
    # inset by the body's own radius is the part this line was protecting.
    assert 'WALL[k] - nodes[i].r' in g


def test_the_seeding_box_is_a_frustum_so_the_frame_is_full():
    """The reference field is edge to edge; ours had black gutters down both
    sides and along the bottom, and the queue listed it first.

    Measured, not judged. The box was a RECTANGLE 20.0 wide and 10.4 tall at
    every depth and the frame a perspective camera sees is a wedge: at the near
    slice (9.4 units out) the visible half-height is 4.89 and the box filled it
    exactly, while at the far slice (22.6 out) the visible half-height is 11.8
    and the box still only reached 4.94. So the back half of the field sat in
    the middle fifth of the frame. Neither lever the handoff named could fix
    that — more bodies packs the middle tighter and leaves the corners exactly
    as empty, and narrowing the box raises the density into the collision
    cascade the drift speeds were tuned against.

    Both halves are load-bearing and both are asserted: the SEEDING places x
    and y as a fraction of the frame at each body's own depth, and the DRIFT
    WALL is the same wedge one fill factor wider. A rectangular wall would
    shove every corner-seeded cage back into the box the seeding just left."""
    g = _graph()
    assert 'const frameH = z => (CAM_Z - (z - 3.0)) * TAN_HALF_FOV;' in g, \
        'the frame half-height is not derived from the camera'
    # the 3.0 is not decoration: u_np pushes every cluster that much further
    # back than the number the physics holds, so a wedge computed off the
    # physics z alone is the wrong wedge
    assert 'u.u_np.value[i].set(POS[i * 3], POS[i * 3 + 1], POS[i * 3 + 2] - 3.0)' in g
    assert 'const nh = frameH(nz) * SEED_FILL;' in g, 'seeding is not depth-scaled'
    assert '* nh * DESIGN_AR,' in g and '* nh,' in g, 'x and y are not fractions of the frame'
    assert 'const h = frameH(POS[i * 3 + 2]) * DRIFT_FILL;' in g, 'the wall is not a wedge'
    assert 'const WALL = [h * DESIGN_AR, h, BOUND_Z];' in g
    # ...and the hero is pulled forward, which SHRINKS the frame around it
    assert 'const heroK = frameH(BOUND_Z_NEAR) / frameH(nodes[hero].z);' in g, \
        'the hero can start outside the near frame'
    # the old rectangle must not come back
    assert 'const BOUND = [' not in g, 'the rectangular drift box is back'


def test_a_frame_rod_is_the_widest_thing_in_the_merged_buffer():
    """THE FRAME IS FLAT NOW, and it is in the buffer that was already there.

    It was two instanced cylinders per edge — a `glass` sleeve you read the
    lattice through and an opaque coaxial core that was the only thing in the
    scene writing depth. Both are gone with the rest of the 3D, and what is
    left is the observation underneath them: what made the frame read as a
    frame was never the lighting model. It is that it is three times the width
    of a shell rod and carries a junction at each end, and both of those
    survive being drawn as an additive ribbon.

    So the frame is more rods in the same merged buffer as the shell and the
    web, at the spec's own width and at full alpha against the shell's ~0.3 —
    thirty rods and four hundred and eighty cannot share a number, which is the
    argument ROD_ALPHA_BY_EDGES already makes for the shell itself."""
    g = _graph()
    frame = g[g.index('THE COARSE FRAME'):g.index('const gEdges')]
    assert 'rod(n, i,' in frame and 'CL.FRAME_HALF * n.r, 1.0, 2);' in frame, \
        'the frame is not a rod in the merged buffer'
    # ...and it is wider than the shell it sits over, or there is one mesh at a
    # middling thickness, which is what every reading of the still got wrong
    assert CS.FRAME_HALF > CS.SHELL_ROD_HALF * 2.5, (CS.FRAME_HALF, CS.SHELL_ROD_HALF)
    # nothing in this scene is lit, and nothing writes depth. COMMENTS
    # STRIPPED: this scene's docstring names every one of these, because what
    # was removed and why is the most useful thing it can say — and a gate that
    # cannot tell a note about a lighting model from a lighting model fails on
    # its own documentation.
    code = re.sub(r'^\s*//.*$', '', re.sub(r'/\*.*?\*/', '', g, flags=re.S), flags=re.M)
    for gone in ('MeshPhysicalMaterial', 'InstancedMesh', 'DirectionalLight',
                 'PMREMGenerator', 'glass: 1'):
        assert gone not in code, f'the 3D rendering is back: {gone}'
    assert 'depthWrite: false' in code and 'depthWrite: true' not in code


def test_a_node_on_the_cluster_is_a_DOT_WITH_AN_OUTER_CIRCLE():
    """The instruction, in as many words: "keep the nodes on the cluster as a
    dot which has an outer circle … just remove from all of this the 3d
    effect".

    A junction was three concentric MeshPhysicalMaterial spheres — a hot white
    core inside a coloured energy volume inside a glass housing — and drawn
    flat that object IS a dot with a ring around it: the white middle, the
    chord in the gap, and the housing's silhouette as the outer circle. The
    sprite shader already had the terms (it drew the shell beads with a core, a
    rim and a halo), so this is one buffer with three populations rather than a
    second pass.

    The three are told apart by `kd.x` — 0 the 162 shell beads, 1 the twelve
    junctions, 2 the lit centre — and by `kd.y`, the world radius, which is
    what makes a junction shrink with distance like the rods do. A junction is a
    fixed fraction of its own hull in the reference; sized in screen space
    instead, a far cluster is a ring of blobs."""
    g = _graph()
    assert "gJoint.setAttribute('kd'," in g, 'the populations are not separated'
    assert 'jk.push(1, CL.FRAME_BEAD_R * n.r);' in g, 'no junction population'
    assert 'jk.push(2, CL.CORE_SHELL_R * n.r);' in g, 'no centre'
    # the dot and the circle, and the two radii differ by population
    assert 'float rc = mix(0.16, 0.30, isN);' in g, 'no dot'
    assert 'float rr = mix(0.42, 0.46, isN);' in g, 'no outer circle'
    assert 'float ring = smoothstep(rr - 0.13, rr, d)' in g, \
        'the outer circle is not a ring — a filled disc is not what was asked for'
    # ...and the four-term version read off the second still is not to come
    # back: a spiked core, a filled bubble and two concentric hairlines were
    # all present in that image and the cluster was judged worse for them
    for gone in ('nFlare', 'nBub', 'nSh1', 'nSh2'):
        assert gone not in g, f'the rejected node stack is back: {gone}'
    # a junction is projected like geometry; a shell bead is a texture and is
    # not (a texture that scales to a quarter of a pixel is gone)
    assert 'float wrl = kd.y * u_res.y * projectionMatrix[1][1] * 0.5' in g
    assert 'gl_PointSize = kd.x > 0.5 ? clamp(wrl * 2.0, 2.0, 96.0) : scr;' in g


def test_the_roles_are_deepened_once_and_nothing_double_counts_it():
    """The theme's accents are pale by design and the reference's are not, and
    the fix is a LIGHTNESS one — which is why every saturation push before it
    failed. A cut across a frame tube in cluster-render-single.png reads
    (0, 55, 135) in the wall and (0, 128, 233) in the energy: red is zero in
    both. #7dcfff is (125, 207, 255) — the same hue and already s = 1.0, its
    max channel being 255, so no saturation can move it. Dropping L at constant
    H and S is what lands it there.

    The pow() curves are the other half of the same rule — a correction applied
    at the source must be REMOVED from every place that was approximating it —
    and this is now the second time it has applied. The lit pass carried three
    of them (a 1.25 saturation push and two albedo/emissive gammas inside
    F_SHADE) and every one went with the lighting model. What is left is the
    haze's own gamma, at 1.5, in the two passes that sum hundreds of additive
    rods; the ones at 2.5 and above were measured to crush the middle channel
    once the roles were deepened, and they must not come back."""
    g = _graph()
    assert 'const DEEP_L = 0.58, DEEP_S = 1.12;' in g
    assert "for (const k of ['u_acc', 'u_acc2', 'u_err', 'u_warn', 'u_ok'])" in g, \
        'the deepening does not cover all five hue roles'
    # u_bg is the ground this scene is mixed back toward and u_white is a
    # highlight GATE, not a hue. Deepening either is a different bug.
    assert 'u_bg' not in g[g.index('const DEEP_L'):g.index('// \u2500\u2500 node field')]
    assert 'setHSL(_hsl.h, Math.min(1, _hsl.s * DEEP_S), _hsl.l * DEEP_L)' in g
    # one gamma, one value, in the passes that overlap additively
    assert g.count('vec3(1.5))') == 2, g.count('vec3(1.5))')
    for gone in ('vec3(2.5))', 'vec3(2.05))', 'vec3(2.6));', 'vec3(2.4));',
                 'vec3(2.3));', 'ch, 1.90)'):
        assert gone not in g, f'a double-darkening curve is back: {gone}'


def test_a_cluster_has_two_scales_of_strut_and_a_shell_chosen_by_size():
    """The thing every reading of a still image missed, and the model settles:
    a cluster has 480 THIN shell rods and 20 THICK hub spokes, and the spokes
    are wider than the rods. The stills show both at once and the eye merges
    them, which is how this went from a dodecahedron (20/30) to a subdivided
    icosahedron (42/120) and was wrong both times — one mesh at a middling
    thickness is neither. Widen it and the cluster is a blown-out ball; thin it
    and it is a wire diagram.

    The two scales are now two PASSES, which is the form the split always
    wanted: the thick struts are lit instanced solids that occlude what is
    behind them, and the thin ones are the merged additive ribbon buffer. The
    widths themselves live in cluster_spec.py, because three renderers draw
    this object and a number typed into any one of them is a copy.

    The shell is chosen PER CLUSTER because a 480-rod shell inside eight pixels
    is a solid disc — the same failure `tools/make_gifs.py` and
    `connections.drawCluster` had to fix by apparent size."""
    g = _graph()
    assert 'const SHELL = [EDGES(0), EDGES(1), EDGES(2)];' in g, 'no LOD ladder'
    assert 'n.r < CL.LOD_BREAKS[0] ? 0 : n.r < CL.LOD_BREAKS[1] ? 1 : 2' in g, \
        'the shell is not size-chosen'
    assert 'const SPOKES = (() => {' in g, 'the hub spokes are gone'
    # ...and NO width is written here. Every one comes off the generated spec.
    assert 'CL.SHELL_ROD_HALF * n.r' in g, 'the shell rod width is hardcoded'
    assert 'CL.SPOKE_HALF * n.r' in g, 'the hub spoke width is hardcoded'
    assert 'CL.FRAME_HALF * n.r' in g, 'the frame tube width is hardcoded'
    assert 'Dodecahedron' not in g, 'a platonic solid is still in the graph scene'


def test_a_cluster_is_made_of_clusters():
    """THE trait. Every hull in the reference image encloses a population of
    smaller points — nodes made of nodes, which is the shape of this project's
    memory graph. The dodecahedral scene had no equivalent of it at all, so its
    absence is the one thing that would make the swap cosmetic.

    Direction off a Fibonacci sphere, radius off an INDEPENDENT hash: driving
    both from the same index piles every inner point at one pole."""
    g = _graph()
    assert 'gMote.setAttribute' in g and 'new TH.Points(gMote' in g, 'no interior'
    assert 'CL.MOTE_R * 0.9 * n.r * Math.pow(hr, 0.45)' in g, 'wrong interior radius law'
    assert 'const hr = ((k * 7919 + i * 104729) % 233280) / 233280;' in g
    assert 'Math.random(' not in g, 'the field must be identical on every reload'
    # count scales with the hull, or a leaf and a hub hold the same haze
    assert 'Math.pow(n.r / R_MAX, 1.8)' in g


def test_the_joints_are_deduplicated_to_the_distinct_hull_vertices():
    """IcosahedronGeometry is a triangle soup: 240 positions for 42 corners. A
    joint drawn per soup vertex stacks five or six ADDITIVE sprites on the same
    pixel, so the halo is five or six times too bright and costs that much
    fill. The dodecahedral version had exactly this bug (108 for 20), which is
    why its joints needed an alpha of 0.13 to look sane."""
    g = _graph()
    # ONE deduplicating reader now (CORNERS), used for both the 162 shell
    # corners and the 12 frame corners. Two copies of it was two chances for
    # the frame and the beads that sit on it to disagree about where a corner
    # is — and they are drawn by different passes, so nothing else would catch it.
    assert 'const CORNERS = d => {' in g, 'the soup is not deduplicated'
    assert 'if (seen.has(key)) continue;' in g
    assert 'const V_SHELL = CORNERS(2), V_FRAME = CORNERS(0);' in g
    assert 'for (const v of V) {' in g, 'joints are not built from the deduped set'


def test_the_inner_web_turns_against_the_cage_around_it():
    """A cluster is made of clusters — a 480-edge cage at 1.0 R with a second
    one at 0.53 R inside it — and until the two turned separately nobody could
    see the second one. Every rod in the merged buffer was spun by one call, so
    the inner cage was rigidly locked to the outer and read as one object with
    a denser middle.

    OPPOSITE, at -1: the mirror of the outer cage's own motion, which is what
    "turn opposite" means and is also the fastest the pair can read without
    either one turning faster — the RELATIVE rate is what the eye picks up, and
    at -1 it is twice the cluster's own. It shipped once at -0.62 (reversed and
    slower, on the grounds that slower is calmer) and that is the number this
    assertion exists to stop coming back. A co-rotation at a different rate is
    only legible while you watch one rod. The offset stops them starting
    aligned, which is the one moment the effect is invisible.

    And ONLY the web takes it. The shell, the coarse frame and the spokes are
    one object; a frame that drifted against its own hull would be a bug, not
    an effect — which is why `nd.z` is a population rather than a boolean."""
    g = _graph()
    assert 'const rod = (n, i, A, B, half, alpha, pop) => {' in g, \
        'a rod does not know which population it is in'
    assert 'en.push(i, half, pop);' in g
    assert "gEdges.setAttribute('nd', new TH.Float32BufferAttribute(en, 3));" in g, \
        'the population never reaches the shader'
    # the four populations, and the web is the only one that is 1
    for call, pop in (('CL.SHELL_ROD_HALF * n.r, dens, 0)', 0),
                       ('CL.WEB_ROD_HALF * n.r, 0.75, 1)', 1),
                       ('CL.FRAME_HALF * n.r, 1.0, 2)', 2),
                       ('CL.SPOKE_HALF * n.r, 0.42, 3)', 3)):
        assert call in g, f'population {pop} is not tagged'
    # ...and the clock, which must be NEGATIVE and offset
    assert 'float own = step(0.5, nd.z) * step(nd.z, 1.5);' in g, \
        'the own-clock test is not scoped to the web alone'
    assert 'float tw = mix(u_t, -u_t + 1.7, own);' in g, \
        'the web does not turn at the exact opposite of the cluster'
    # comments stripped, for the third time in this file: the shader says what
    # it shipped as and why, and a gate that cannot tell a note about a number
    # from the number fails on its own documentation
    code = re.sub(r'^\s*//.*$', '', re.sub(r'/\*.*?\*/', '', g, flags=re.S), flags=re.M)
    assert 'u_t * -0.62' not in code, 'the reversed-but-slower web is back'
    assert 'spin(position, ndv.x, tw)' in g and 'spin(eo, ndv.x, tw)' in g, \
        'both ends of a rod must take the same clock or it stretches'


def test_the_shell_beads_stay_a_texture_and_do_not_outnumber_the_junctions():
    """162 against 12 is thirteen to one, and at one alpha every cluster was a
    ball of white dots — which is why the junctions were pulled out of this
    buffer into the solid pass in the first place. They are back in it, so the
    hierarchy has to be in the SHADER rather than in which pass you are in.

    Three levers, and they are different questions: the shell bead is smaller
    (screen-space, so it stays a texture at every distance), its dot is half
    the radius of a junction's, and its ring carries less than half the alpha.
    The reference has the junctions as the things you look at and the shell as
    a surface they sit on."""
    g = _graph()
    beads = g[g.index('const jp = [], jn = [], jk = [];'):g.index("gJoint.setAttribute('kd'")]
    assert 'const V = n.lod === 2 ? V_SHELL : V_FRAME;' in beads, \
        'the shell beads do not follow the LOD their cage earned'
    assert 'jk.push(0, 0);' in beads, 'a shell bead is not screen-sized'
    # ...and the shader reads the hierarchy off it
    assert 'float isN = step(0.5, vK);' in g
    assert 'ring * mix(0.34, 0.72, isN)' in g, 'the ring does not favour a junction'
    assert 'core * mix(0.55, 0.62, isN)' in g
    # deduplicated, because IcosahedronGeometry is a triangle soup and drawing
    # it stacks five or six additive sprites on every corner
    assert 'const CORNERS = d => {' in g
    assert 'const seen = new Set(), out = [];' in g


def test_a_conduit_carries_the_chord_of_the_cluster_at_each_END():
    """"The connection inherits colour information from the clusters it
    connects" — so a cyan cage joined to a magenta one is joined by something
    cyan at one end and magenta at the other, and neither a third colour nor a
    blend of the two.

    On a LineSegments that is free: each endpoint vertex reads the chord of its
    OWN cluster into vPal and the fragment interpolates between them. The
    instanced version had to inject a per-vertex axis to get the same thing,
    which is most of what went with it."""
    g = _graph()
    link = g[g.index('5 \u2500\u2500 THE CONDUITS'):]
    assert 'vPal = u_pal[a];' in link, 'the conduit does not read a chord at all'
    assert 'chord(vPal, mix(0.12, 0.84, vT), 0.0)' in link, \
        'the conduit does not walk its own chord along its length'
    # both ends are placed from u_np, so the line follows its cages as they
    # drift — and a declared-but-absent attribute reads as 0, which pins every
    # segment to node 0 and gives it zero length
    for a in ("gLink.setAttribute('ci'", "gLink.setAttribute('cj'",
              "gLink.setAttribute('cat'", "gLink.setAttribute('csd'"):
        assert a in link, f'missing conduit attribute: {a}'
    assert 'vec3 pa = u_np[a], pb = u_np[b];' in link


def test_the_lattice_is_seeded_in_a_volume_and_linked_by_proximity():
    """Two failures with one cause: the field was a spiral on a disc, and the
    links were index offsets along that spiral.

    A golden-angle spiral spreads points on a DISC, so every cage sat on a ring
    with an empty middle. And `i+8` on a spiral is an arbitrary partner on the
    far side of the box, which draws a fan of long chords across the frame —
    a necklace, not a lattice. The reference image is a VOLUME linked to its
    own neighbours.

    The neighbours are taken ONCE, at rest, and then held: a lattice whose
    edges are recomputed every frame is a different picture every frame, and
    the drift is meant to stretch the structure rather than rewire it."""
    g = _graph()
    assert 'const GX = 5, GY = 4, GZ = 2;' in g, 'not a volume lattice'
    assert 'Math.cos(ang) * rad' not in g, 'the spiral seeding survived'
    assert 'const PAIRS = [];' in g and 'near.sort((a, b) => a[0] - b[0]);' in g
    assert 'for (const k of [1, 2, 3, 8])' not in g, 'index-offset links survived'
    # and the hash that sizes a cage must not be the one that places it, or
    # every hub lands in one corner — which is exactly what happened with the
    # linear-congruential hash: its only three hub-sized values over 40
    # consecutive integers were i = 17, 18, 19.
    assert 'Math.sin(i * 12.9898) * 43758.5453' in g
    assert '(i * 9301 + 49297)' not in g.split('const r = 0.10')[0][-400:]


def test_depth_washes_toward_the_background_before_calm_not_instead_of_it():
    """Distance used to be expressed only as z, so a far cage was as bright as
    a near one and the field read flat. The wash is exponential because that is
    how a haze accumulates — and it mixes toward u_bg BEFORE calm(), which is
    the brightness ceiling the whole stage is subject to. A scene that replaces
    calm() with its own fog has opted out of the one rule the background exists
    under.

    There is ONE spelling of it again. There were two while the cluster had a
    lit half — the raw-shader passes computed it from their own `dist` and the
    instanced solids computed it inside an injected `<project_vertex>`
    replacement, where the depth had to be spelled `-mvPosition.z` because that
    is the chunk where mvPosition exists. The solids are gone; so is the second
    spelling, and every pass in the scene now reads the same line."""
    g = _graph()
    # The onset is 16 and not 7, and that number is not cosmetic. The camera
    # sits at z=8.4 and the field spans z=+2..-11, so NOTHING is closer than
    # ~15 units — starting the haze at 7 put every cage in it, which is not a
    # depth cue, it is a global dimmer set to about a half.
    #
    # The RATE came down from 0.075 to 0.042 when the seeding box was deepened
    # from a 3.4 span to a 6.6 one. The depth is where the brief's background
    # network comes from — distant cages, smaller and dimmer, rather than a
    # flat starfield — and at the old rate a cage at 22 units was a dark lump
    # instead of a dim cluster. In cluster-render-field.png the far cages are
    # roughly half the brightness of the near ones and still obviously coloured.
    assert g.count('vF = exp(-max(0.0, dist - 16.0) * 0.042);') == 5, \
        'all five passes fade with depth'
    assert 'mvPosition' not in g, 'the injected solid path is back'
    # counted, not just ordered: a loop over zero matches passes vacuously, and
    # that is exactly how this gate failed its own mutation the first time
    assert g.count('mix(u_bg, col, vF);') == 5, 'a pass does not wash with depth'
    for m in re.finditer(r'mix\(u_bg, col, vF\);', g):
        out = g.index('gl_FragColor', m.end())
        assert 'calm(' in g[out:out + 200], \
            'the fog replaced calm() instead of preceding it'



def test_the_five_passes_each_know_where_they_sit():
    """Five draw calls, and every one of them is additive, depth-TESTED and
    never depth-WRITING — which is what "no 3D" means in this scene: nothing is
    shaded by a light and nothing occludes anything.

    That makes render ORDER the only thing deciding what reads as being in
    front, so each pass states its own. Faces under everything (they are the
    hull's volume), the rods over them, the conduits under the cages they join,
    the interior population inside, the nodes brightest and last."""
    g = _graph()
    order = {}
    for m in re.finditer(r'(m[A-Z][a-zA-Z]*)\.renderOrder = (\d+);', g):
        order[m.group(1)] = int(m.group(2))
    assert set(order) == {'mEdges', 'mFaces', 'mJoint', 'mMote', 'mLink'}, order
    assert order['mFaces'] < order['mEdges'] < order['mMote'] < order['mJoint'], order
    assert order['mLink'] < order['mFaces'], order
    # every pass, additively, with no depth write anywhere
    # FOUR additive and one NOT, and the exception is the point: the hull's
    # faces are a smoky VOLUME, so they have to occlude what is behind them
    # rather than sum with it. Everything else in the scene is light.
    assert g.count('blending: TH.AdditiveBlending') == 4, \
        g.count('blending: TH.AdditiveBlending')
    assert g.count('blending: TH.NormalBlending') == 1
    assert g.count('depthWrite: false, depthTest: true') == 5


def test_a_conduit_stops_ON_a_hull_and_never_crosses_it():
    """Run a conduit to the CENTRE of a cluster and every one of them crosses
    its own cage, which is what turns a lattice into a scribble. CONDUIT_REACH
    is how far into a hull the reference's tube goes; the endpoint is pushed
    out along the conduit's own axis by that fraction of the cluster's radius.

    CONDUIT_CLAMP is the guard, and it is not decoration: two hulls close
    enough that the two insets would cross INVERT the segment, so the line runs
    backwards out of both of them. The clamp is a fraction of the gap, so it
    can never exceed half of it."""
    g = _graph()
    link = g[g.index('5 \u2500\u2500 THE CONDUITS'):]
    assert 'float inset = min(u_nd[a].w * ${F(CL.CONDUIT_REACH)},' in link, \
        'the conduit does not reach into the hull'
    assert 'L * ${F(CL.CONDUIT_CLAMP)});' in link, \
        'no inversion guard on the surface push'
    assert 'pa + dv / L * inset' in link, 'the inset is not along the axis'
    assert CS.CONDUIT_CLAMP < 0.5, 'the clamp can exceed half the gap'


def test_gold_and_green_reach_the_constellation():
    """SIX ROLES, and every one of them is bound.

    u_warn (#e0af68) was bound by sU() from the start and NO shader in the
    graph scene read it, so gold was the cheapest hue the field could gain;
    u_ok followed for the same reason. u_err is the third of them, and it is
    the one the reference most obviously needed: a cluster there holds violet
    AND magenta at once, and until it was bound every hue the stage could reach
    was cool, gold or green.

    The roles are numbered in `claude_sessions/cluster_spec.py` so the same
    index means the same hue in all three renderers, and roleCol() is the one
    place that turns a number into a colour.

    err is pulled a third of the way toward the violet accent on the way
    through. It is a SALMON in most palettes because its real job is to read as
    a failure against body text, and used raw it made every cluster coral."""
    assert 'u_ok: {value: c.ok}' in _STAGE, 'u_ok is not bound'
    assert 'u_err: {value: c.err' in _STAGE, 'the magenta role is not bound'
    assert 'u_white: {value: new TH.Color(0xffffff)}' in _STAGE, 'white is not a role'
    assert 'err: C(p.err || p.accent2),' in _STAGE, 'the palette never supplies it'
    # every role reaches roleCol, and roleCol is the ONLY place a number
    # becomes a colour — two of those is two chances for a renderer to
    # disagree with the spec about which index is gold
    for role in ('u_acc2', 'u_err', 'u_warn', 'u_ok', 'u_white'):
        assert f'c = mix(c, ' in _STAGE and role in _STAGE, role
    assert _STAGE.count('vec3 roleCol(float r){') == 1

    # the weights are counted off the reference field, and violet leads it
    from claude_sessions import cluster_spec as CS
    total = sum(w for w, _n, _r in CS.PALETTE_FAMILIES)
    by = {n: w for w, n, _r in CS.PALETTE_FAMILIES}
    assert by['violet'] / total >= 0.35, 'violet no longer leads the field'
    warm = by['gold'] / total
    assert warm >= 0.12, f'gold is a rarity again: {warm}'
    cool = (by['violet'] + by['blend'] + by['cyan']) / total
    assert cool >= 0.5, 'cool no longer leads'
    # ...and NO family is one colour repeated. That is the rule the whole
    # rewrite exists for, stated where the data is.
    for _w, name, roles in CS.PALETTE_FAMILIES:
        assert len(set(roles)) >= 3, f'{name} is not a chord: {roles}'
        assert all(0 <= r <= 5 for r in roles), name



def test_a_cage_is_one_hue_but_not_only_one_hue():
    """THE rule the whole cluster pass exists for: never reduce a cluster to a
    single flat colour. A per-cage `tone` indexed a shared five-stop ramp, so a
    cage was one colour because the code could not express another — and in the
    reference one cluster runs violet into magenta into cyan with gold picking
    out individual struts.

    Every pass reads `chord(pal, gradT(...), hot)`: a colour derived from
    POSITION inside the cage, so the two ends of one rod differ and the
    fragment interpolates between them. The count is what keeps a pass from
    quietly going back to a flat tint — five draw calls and the chord in every
    one of them, plus the material factory's own."""
    g = _graph()
    assert g.count('chord(') >= 5, g.count('chord(')
    assert g.count('gradT(') >= 3, g.count('gradT(')
    # comments stripped: the word survives in the note saying what the chord
    # replaced, which is worth keeping
    code = re.sub(r'^\s*//.*$', '', re.sub(r'/\*.*?\*/', '', g, flags=re.S), flags=re.M)
    assert 'hue5(' not in code, 'the one-hue ramp is back'
    # ...and the family table is the shared source, so the site agrees
    assert 'const FAM = CL.PALETTE_FAMILIES;' in g
    for _w, name, roles in CS.PALETTE_FAMILIES:
        assert len(set(roles)) >= 3, f'{name} is not a chord: {roles}'


def test_the_theme_looks_the_same_whether_or_not_you_are_looking_at_it():
    """NO MODE MAY CHANGE THE STAGE. This replaces "only zen may lift the
    brightness ceiling", which was the same fence pointing the other way.

    `calm` mixes every scene back toward --bg because the first cut was
    rejected as "overstimulating, confonde". Zen — the app hidden, the canvas
    the only thing on screen — was allowed to lift it, and over time it
    acquired four exceptions: calm +0.12, gain x1.12, the `cinematic` tier
    forced over a user who had chosen `lite`, and a supersample off
    devicePixelRatio. The result was two themes:

        "theme on vs theme off have different brightness and settings, i like
         the one where i am only viewing the theme, so keep those settings for
         the theme and the theme toggle shouldn't change brightness"

    Three of the four are the stage's own settings now and the fourth is gone
    outright, because `lite` is a COST setting (it drops EffectComposer, and
    the tearing ladder in CLAUDE.md starts there) and a display mode may not
    overrule one. Measured with the app chrome hidden by hand so the two
    samples differ only by what the stage decided: identical p95, and the
    settings page — which used to dim to 0.78 — no longer dims at all.

    The lift keeps the two fences that were about the LIFT rather than about
    the mode: it raises the skin's own value rather than replacing it, and it
    is capped below 1 so a bright skin cannot wash out to flat colour."""
    m = re.search(r'return Math\.min\(([\d.]+), base \* k \+ STAGE_LIFT\);', _STAGE)
    assert m, 'the ceiling is no longer one expression over the skin plus a lift'
    cap = float(m.group(1))
    assert cap < 1.0, 'a ceiling of 1 is no ceiling'
    lift = float(re.search(r'const STAGE_LIFT = ([\d.]+);', _STAGE).group(1))
    assert 0 < lift <= 0.5, lift
    # every skin still has to clear the cap with the lift applied, or the
    # loudest ones flatten into the same picture
    for name, sk in themes.SKINS.items():
        assert sk.get('calm', 0.3) + lift <= cap + 1e-9, name
    # exactly one expression decides the ceiling. The three inputs compose in
    # _calm() or they disagree somewhere — which is the `gate['diff']` lesson
    # in a different costume: two producers of one value is two chances to get
    # it wrong.
    assert _STAGE.count('calm: this._calm()') == 1, 'a second calm producer'
    # the OTHER half of "brighter" in an alpha-composited scene: calm decides
    # how far a colour comes up off the page, gain how much of it survives its
    # own alpha. Moving one without the other reaches a ceiling and still looks
    # dim, which is exactly how the zen lift got there.
    assert 'const STAGE_GAIN = 1.12;' in _STAGE
    assert 'dens: this._gain()' in _STAGE, 'gain never reaches a scene'
    # ...and NOTHING in the stage knows about the mode any more. Comments
    # stripped: the word survives in the notes saying why it is gone.
    code = re.sub(r'^\s*//.*$', '', re.sub(r'/\*.*?\*/', '', _STAGE, flags=re.S), flags=re.M)
    assert '_zen' not in code, 'the stage reads the display mode again'
    assert 'STAGE.zen' not in PAGE, 'app.js still tells the stage about zen'
    # per-page EXPOSURE is gone with it, for the same reason: a page you happen
    # to be on cannot be a reason for the theme to be a different theme. The
    # camera bias stays — it changes the composition, not the exposure.
    pages = _STAGE[_STAGE.index('const STAGE_PAGES = {'):]
    pages = pages[:pages.index('};')]
    assert 'd:' not in pages, 'per-page density is back'
    assert 'c:' in pages, 'the per-page camera bias is gone too'


def test_the_brightness_ceiling_is_a_setting_and_it_scales_rather_than_replaces():
    """`calm` was tuned to one verdict ("overstimulating, confonde") and later
    to its exact opposite ("too dim, I can't see anything"). That is what a
    constant standing in for a preference looks like, so it is a setting.

    It has to SCALE the skin's value rather than replace it, or every look
    collapses to one brightness and the roster stops meaning anything — the
    same failure as the palette generator that rebuilt every theme from one
    hue. And it defaults to 0 = "ask the look", the convention `surface`
    already uses for panel opacity."""
    from claude_sessions import config, gui
    assert 'brightness' in config._DEFAULT_SETTINGS, 'load_settings would drop it'
    # the API allowlist is derived from the defaults, so declaring it is what
    # makes /api/settings accept it — assert the derivation, not a literal list
    assert 'brightness' in gui._SETTING_KEYS
    assert gui._brightness({}) == 0, 'no preference must mean "ask the look"'
    assert gui._brightness({'brightness': 10}) == 40, 'not clamped at the floor'
    assert gui._brightness({'brightness': 9999}) == 220, 'not clamped at the top'
    assert gui._brightness({'brightness': 'nonsense'}) == 0
    assert 'base * k' in _STAGE, 'the preference replaces instead of scaling'
    assert 'this.glowPct > 0 ? this.glowPct / 100 : 1' in _STAGE, \
        '0 no longer means "ask the look"'


def test_the_lattice_drifts_rather_than_jostles():
    """Four numbers, one complaint: "the movement of the clusters is really
    erratic now".

    The cause was not any one of them — it was that the seeding changed from a
    spiral on a disc to a 5x4x2 lattice in a smaller box, which packs the same
    40 bodies far more densely, while the starting speeds, the restitution and
    the drag all stayed where they had been tuned for the sparse version. A
    dense box of nearly-elastic bodies with almost no drag does not settle: it
    accumulates energy from its own collisions and jitters forever.

    So density and speed are one dial with two names, and these four are pinned
    together because changing any one of them alone is what produced it."""
    g = _graph()
    # resting drift, and the energy term that still doubles it
    assert 'const sp = 0.18 + 0.5 * e;' in g, 'the resting drift is a scurry again'
    assert 'Math.cos(a) * 0.075' in g, 'the seed velocities are back up'
    # a knock has to decay in seconds, not minutes, or a collision stops
    # reading as an event and becomes the permanent state of the field
    assert 'VEL[a] *= 0.994;' in g, 'the drag is a whisper again'
    assert '(vj - vi) * 0.35;' in g, 'the collisions are elastic again'
    # and the tether that holds a satellite near its hub is a suggestion
    assert '* 1.9) * 0.10 * dt;' in g, 'the satellite spring is stiff again'


def test_the_hero_cluster_is_near_enough_to_read():
    """Every cage sat at roughly the same distance, so every cage was roughly
    the same size on screen and none could be LOOKED at — the cage, the
    population inside it and the beads on its surface are three separate pieces
    of structure, and at 40px across they are one grey speck.

    The hero is the LARGEST cage rather than a 41st body: adding one would
    break the 5x4x2 lattice, and the biggest hull is the one whose interior is
    worth coming close to. It keeps its physics — it drifts, it collides, its
    satellites still orbit it — at a quarter speed, so it stays in the
    foreground for minutes rather than seconds."""
    g = _graph()
    assert 'const BOUND_Z_NEAR = 2.6;' in g
    assert 'nodes[hero].z = BOUND_Z_NEAR;' in g, 'the hero is not at the front'
    assert 'for (let i = 1; i < N; i++) if (nodes[i].r > nodes[hero].r) hero = i;' in g, \
        'the hero is not the largest cage'
    assert 'nodes[i].hero ? sp * 0.25 : sp' in g, 'the hero drifts away as fast as the rest'

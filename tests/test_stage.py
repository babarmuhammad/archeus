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

    Zen is the one place the reasoning inverts, and it is fenced to that: the
    app is hidden, nothing competes for the frame, and the scene is now thin
    glass rods and small beads — hairlines, which crawl and stair-step at 0.75.
    So `_ratio()` supersamples there and ONLY there, which is why the DPR read
    below is asserted to live inside that function rather than being banned."""
    assert 'const STAGE_SCALE = 0.75;' in PAGE
    # Idle sits in the 20s: low enough to be nearly free, high enough that the
    # drift reads as motion rather than a stutter. It was briefly dropped to 12
    # along with the brightness, and the background stopped looking animated —
    # see test_the_background_still_moves_when_nothing_is_happening.
    assert re.search(r'STAGE_FPS_IDLE = 2\d;', PAGE)
    assert 'if (this._acc < 1 / fps) return true;' in _STAGE
    # DPR is read in exactly one place, and that place returns `base` — the
    # unchanged 0.75 — whenever zen is off.
    assert _STAGE.count('devicePixelRatio') == 1, 'DPR must not drive the background'
    fn = _STAGE[_STAGE.index('  _ratio() {'):]
    fn = fn[:fn.index(chr(10) + '  },')]
    assert 'devicePixelRatio' in fn, 'DPR is read outside the render-scale resolver'
    assert 'if (!this._zen) return base;' in fn, 'the background pays for zen'
    assert 'Math.min(2,' in fn, 'supersampling is uncapped'


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
    """The homage is not just the solids — connections.py runs particles along
    its edges, and so does this. Always moving (the links carry something), but
    faster and denser with energy, so it still reports rather than decorates.

    The de-synchronisation is load-bearing: without it every conduit pulses in
    lockstep and the field reads as a strobe rather than as traffic. It used to
    come from a per-segment seed attribute on a ribbon; the conduit is three
    nested instanced cylinders now, so it comes from the LAYER — one number the
    instance already carries, and no extra attribute to keep in step."""
    g = _graph()
    assert 'float ph = fract(u_t * sp + float(int(vLay)) * 0.31);' in g, 'no packet'
    assert 'float pk = pow(max(0.0, 1.0 - abs(vT - ph) * 22.0), 2.0) * core;' in g
    # SLOW. At 0.16 a packet crossed a link in about six seconds and read as a
    # strobe rather than as something travelling; the point of it is that you
    # can watch one go. The energy term still triples it, which is the half
    # that has to stay legible — a busy workspace is visibly busier.
    assert 'float sp = 0.045 + 0.11 * u_e;' in g
    # the packet rides the CORE layer only. On the housing it would be a light
    # running along the outside of an opaque shell, which is not what a conduit
    # carrying something looks like.
    assert 'float core = step(1.5, vLay);' in g


def test_the_clusters_vary_in_size_and_collide_by_mass():
    """A uniform spread gives forty forgettably similar cages. Raising a flat
    hash to a power gives a long tail — a few hubs among many leaves, the read
    the real architecture graph has and the read the reference constellation
    has. Once sizes differ, equal-mass collision is wrong: a pea would deflect
    a boulder. Phase 4 lengthened the tail (exponent 4, not 3), which makes the
    mass physics MORE load-bearing, not less — hence re-asserted here rather
    than relaxed."""
    g = _graph()
    # exponent 3.4 over a 0.16 floor. Still a long tail — a handful of hubs
    # among many leaves — but the reference FIELD is a packed frame, and at
    # a 0.10 floor half of it was specks with bare conduit between them.
    assert 'Math.pow(h, 3.4) * 1.44' in g, 'size is not long-tailed enough'
    assert '0.16 + Math.pow' in g, 'the floor is back where the field went sparse'
    assert 'm: r * r * r' in g, 'no mass'
    assert 'const mi = nodes[i].m, mj = nodes[j].m, mt = mi + mj;' in g
    assert '(2 * mj / mt)' in g and '(2 * mi / mt)' in g
    assert 'if (vi - vj <= 0) continue;' in g, 'no separating-pair guard'
    # the wall inset, or a large cage half-leaves the frame
    assert 'BOUND[k] - nodes[i].r' in g


# ── the constellation (Phase 4) ────────────────────────────────
# Every assertion below is an observation from the reference image, written
# down. notes/constellation-study.md is the prose; this is the gate.

def _graph():
    return PAGE[PAGE.index('  graph(TH, c, ren) {'):PAGE.index('  /* Terminal —')]


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


def test_a_node_is_a_solid_bead_inside_a_transparent_shell():
    """The reference image's junctions are not dots and not soft blobs: each is
    a whole opaque near-white bead inside a translucent coloured sphere you can
    see through, with the shell legible only by its rim.

    They are REAL SPHERES now. Drawn as point sprites they were dots — twelve
    of them against 162 shell beads, and the frame they mark vanished into the
    mesh however the alphas were set. Four nested parts, at the model's own
    radii (Hub_HotCore / Hub_EnergyCore / Hub_GlassShell / Hub_Housing), and
    the glass is legible because its ALPHA is driven by the Fresnel term: a
    transparent sphere at a flat 40%% is a washer, and its rim is the only
    thing that says it is a sphere at all.

    What is still a sprite is the 162-strong shell texture, and there the three
    parts have to be step-like: the version before it was one smoothstep from
    the middle outward, which is a gradient, and a gradient reads as a smudge
    at every size."""
    g = _graph()
    # the junction: real geometry, at the model's radii, in the solid pass
    assert 'ball(p, CL.FRAME_BEAD_R * n.r)' in g, 'the junction is not a sphere'
    # ...and its two inner shells have their OWN spec keys now. They used to be
    # the conduit hub's ratios with the hot core multiplied by 1.7, which put
    # the white core (0.053 R) on top of the energy shell (0.061 R): no pink
    # ever showed, and a junction was a white blob in a grey bubble. In both
    # references the pink core is about half the glass sphere.
    assert 'CL.FRAME_BEAD_HOT * n.r' in g, 'no hot core inside the glass'
    assert 'CL.FRAME_BEAD_ENERGY * n.r' in g, 'no energy shell inside the glass'
    # ...and the glass is a rim, which is what makes it read as glass without a
    # backdrop-filter anywhere near this app. A BAND and not a ramp: the ramp
    # was a soft bubble, and what the reference has is a hard bright ring you
    # read the core through.
    assert 'smoothstep(0.55, 0.96, fres)' in g, 'the glass shell has no Fresnel alpha'
    assert "key: 'glass', glass: 1" in g and 'fresA: 1' in g

    # the shell texture, still sprites, still crisp
    assert 'float aa = 0.02 + 0.10 * (1.0 - vD);' in g, 'no antialiasing width'
    assert 'float core = 1.0 - smoothstep(0.16 - aa, 0.16 + aa, d);' in g
    assert 'float rim  = smoothstep(0.30, 0.42, d)' in g, 'the bead has no wall'
    assert 'core * 0.72' in g, 'the bead core is not white-dominant'
    # size by mass AND size by depth AND defocus: three cues, not one
    assert '(1.5 + 3.4 * vR) * (0.45 + 0.75 * vD)' in g
    assert '(1.0 + 1.1 * (1.0 - vD))' in g, 'a far bead does not defocus'



def test_a_link_is_a_tube_with_a_hue_at_each_end():
    """A link is a COAXIAL TRIPLE, not a tube, and the part names in
    `connection.glb` are the spec: a dark housing that gives it a silhouette,
    a translucent glass layer you see through, a hot filament at the axis, one
    luminous rail on the OUTSIDE of the housing, a gold collar where it meets
    each hull and a glass hub at each end.

    Every version before the model was read had ONE shell and the argument was
    only ever about its falloff — core-led it reads as a hairline with a glow,
    wall-led as an empty pipe, and neither is what the object is.

    It used to be a camera-facing ribbon, which was the right answer while
    everything was additive: WebGL ignores lineWidth, so LineSegments can only
    draw a hairline. A ribbon cannot occlude anything, and occlusion is what
    the whole solid pass is for — so the three layers are three radii of one
    instanced cylinder, told apart by the layer number the instance already
    carries. One mesh, one draw call, and the layers cannot disagree about
    where the axis is.

    And it carries BOTH clusters' chords, so a cyan cluster joined to a magenta
    one is joined by something cyan at one end and magenta at the other."""
    g = _graph()
    assert "key: 'conduit', link: 1" in g, 'the conduit is not instanced geometry'
    assert 'new TH.CylinderGeometry(1, 1, 1, 14, 1, true)' in g, 'not a tube'
    # the three radii, off the spec and not typed in here
    assert '[CL.CONDUIT_HOUSING, CL.CONDUIT_GLASS, CL.CONDUIT_CORE]' in g
    for layer in ('float housing = 1.0 - step(0.5, vLay);',
                  'float glass = step(0.5, vLay) * (1.0 - step(1.5, vLay));',
                  'float core = step(1.5, vLay);'):
        assert layer in g, layer
    # the rail is OFF-AXIS on purpose: symmetry is what made every earlier tube
    # read as a smear — a real cylinder lit from somewhere has a top
    assert 'float rail = exp(-pow((vAng - 2.05) / 0.20, 2.0)) * housing;' in g
    # ...and it lands ON something: a gold ring and a glass hub at each end,
    # which is what "the collar reads as a hard cut" was asking for. A shader
    # threshold could fade the end; only geometry can put a ring there.
    assert 'new TH.TorusGeometry(CL.COLLAR_D * 0.5, CL.COLLAR_THICK * 0.5' in g
    assert "key: 'collar'" in g and "key: 'hub'" in g

    # ...and the cage struts are still ribbons, for the reason a link used to
    # be: they are hairlines, there are half a million of them, and nothing
    # behind them needs occluding.
    assert 'new TH.Mesh(gEdges' in g, 'the shell rods are LineSegments again'
    assert 'mv.xyz += side * ew * nd.y;' in g, 'the rod width is not per-rod'

    # THE CONNECTION INHERITS FROM BOTH CLUSTERS. This is the brief's rule and
    # it is the thing a single global accent could never express.
    assert 'vPal = u_pal[ia]; vPal2 = u_pal[ib];' in g
    assert 'chord(vPal, mix(0.12, 0.84, vT), vHot)' in g
    assert 'chord(vPal2, mix(0.84, 0.12, vT), vHot)' in g

    # ...deepened before it is summed. Every additive pass in this scene
    # deepens its hue first: the palette's accents are PALE by design (they
    # clear a contrast floor as TEXT) and two pale colours added together are
    # white, which is why violet, gold and teal cages all came out white-blue
    # whatever the alphas were. The lit passes need it too, and there it is a
    # pow on the albedo BEFORE the lights rather than on the sum after.
    import re as _re
    pw = [float(m) for m in _re.findall(r'vec3\((\d\.\d+)\)\)', g)]
    assert len([e for e in pw if e >= 1.5]) >= 3, f'a pass sums at full lightness: {pw}'



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

    There are two spellings of it now and that is not duplication: the four
    raw-shader haze passes compute it from their own `dist`, and the lit solids
    compute it once inside the injected `<project_vertex>` replacement, where
    the depth is `-mvPosition.z` because that chunk is where mvPosition exists.
    One number, two places it can be reached from."""
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
    assert g.count('vF = exp(-max(0.0, dist - 16.0) * 0.042);') == 4, 'all four haze passes'
    assert g.count('vFar = exp(-max(0.0, -mvPosition.z - 16.0) * 0.042);') == 1, 'the solids'
    # counted, not just ordered: a loop over zero matches passes vacuously, and
    # that is exactly how this gate failed its own mutation the first time
    assert g.count('mix(u_bg, col, vF);') == 4, 'a haze pass does not wash with depth'
    assert g.count('ch = mix(u_bg, ch, vFar);') == 1, 'the solids do not'
    for m in re.finditer(r'mix\(u_bg, col, vF\);', g):
        out = g.index('gl_FragColor', m.end())
        assert 'calm(' in g[out:out + 200], \
            'the fog replaced calm() instead of preceding it'
    # ...and the solids' own wash is followed by calm() on the very next line,
    # for the same reason
    i = g.index('ch = mix(u_bg, ch, vFar);')
    assert 'calm(ch, u_bg, u_calm' in g[i:i + 160]



def test_a_link_is_a_beam_a_strut_is_a_filament_and_a_node_is_the_brightest():
    """Two reversals live in this ordering and both were paid for by looking at
    the reference image again.

    The first: the original scene gave struts +0.35 and links +0.34, so the
    field read as one undifferentiated web. Separating them was right.

    The second: the separation was made the wrong way round. Links were pushed
    BELOW struts (+0.18 against +0.30) on the reading that "links are almost
    background" — and they are not. The long filaments between clusters are
    among the brightest things in that image, pale cyan running to white. What
    is nearly background there is the far field, which vF already spends.

    So: hull faces < shell mesh < conduits < the lit cores. The faces are the
    dimmest thing by a distance because they are a volume and not a line; the
    cores and the beads stay the brightest because only a near-white surface
    clears the 0.55 bloom threshold.

    The ladder survived the move to lit solids because it is expressed in
    `calm`, which every pass still passes through however it is blended — but
    it is now read from two places, and that is the thing to keep honest: a raw
    haze shader writes the number into its own GLSL, and a lit solid declares
    it in its material config for F() to substitute. Asserting only the GLSL
    form would have silently stopped covering six of the ten passes."""
    g = _graph()
    face, mesh, link, hot = 0.26, 0.30, 0.42, 0.50
    # the haze passes, where the number is in the shader
    assert f'u_calm + {face:.2f}' in g, 'the hull faces left the ladder'
    assert f'u_calm + {mesh:.2f}' in g, 'the shell mesh left the ladder'
    assert f'u_calm + {hot:.2f}' in g, 'the beads left the ladder'
    # the lit solids, where it is config that F() substitutes
    assert f'calm: {link}' in g, 'the conduit left the ladder'
    assert f'calm: {hot}' in g, 'the cores left the ladder'
    assert face < mesh < link < hot



def test_a_link_joins_two_nodes_and_never_crosses_a_hull():
    """Not one filament in the reference image is drawn across a hull's
    interior — they begin and end ON the hulls. So each endpoint is pushed out
    of its own centre by its own radius toward the other end. The min() is the
    guard for two large cages resting against each other: without it the push
    crosses over and inverts the segment.

    Both numbers come off the spec now rather than being typed into the shader,
    because the conduit is drawn by three renderers and 0.86 written into any
    one of them is a copy. They reach GLSL through F(), which is not decoration:
    GLSL has no implicit int-to-float, so a reach of 1 would emit `1` and every
    expression it lands in would fail to compile."""
    g = _graph()
    assert 'gA = pa + gAx * min(u_nd[ia].w * ${F(CL.CONDUIT_REACH)}, ' \
           'L * ${F(CL.CONDUIT_CLAMP)});' in g, 'no inversion guard on the surface push'
    assert 'gB = pb - gAx * min(u_nd[ib].w * ${F(CL.CONDUIT_REACH)}, ' \
           'L * ${F(CL.CONDUIT_CLAMP)});' in g, 'the far end is not anchored'
    # ...and the last few percent of a conduit fades, so there is no hard end
    # even where the clamp stops it short of the hull
    assert 'float ends = smoothstep(0.0, 0.05, vT)' in g, 'the conduit ends square'
    assert 'float L = max(length(dv), 1e-4);' in g, 'normalize() can divide by zero'



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
    """NEVER REDUCE A CLUSTER TO A SINGLE FLAT COLOUR. It is the rule the brief
    calls the most important, and it is the one this scene broke by
    construction: hue5(n.tone) took a number that was CONSTANT across a
    cluster, so a cluster was one colour because the code could not express
    anything else. Per-strut jitter toward the next stop was the previous
    answer and it is not enough — it gives a cage of two hues, where the
    reference has one cluster running violet into magenta into cyan with gold
    picking out individual struts.

    So a cluster wears a CHORD of four roles, and chord() walks between them by
    a number derived from POSITION. Every input the brief names is in gradT and
    each does a different job: the angular term gives the gradient a direction
    (so two clusters wearing the same chord are still not the same object
    rotated), the radial term makes the centre a different colour from the rim,
    the noise breaks the sweep up (a clean sweep reads as a stripe), and the
    per-cluster seed offsets the noise so the same chord is still a different
    picture.

    The walk is WEIGHTED, not three even thirds: a violet cluster is roughly
    six parts its primary, three its secondary and one its accent. An even
    split put as much magenta on it as violet and the field came out pink."""
    g = _graph()
    # the ramp is named in the prose above the scene, which is where the
    # history belongs; what must not come back is a CALL to it or the
    # helper being injected into one of these shaders again
    assert 'hue5(v' not in g, 'the one-hue-per-cluster ramp is back'
    assert 'SF_HUE5' not in g, 'the one-hue ramp is injected into a graph shader'
    assert 'const FAM = CL.PALETTE_FAMILIES;' in g, 'the chord is not from the spec'
    assert 'pal: fam[2],' in g, 'a cluster does not carry a chord'
    # the gradient's four inputs, in the one place that computes it
    assert _STAGE.count('float gradT(vec3 local, vec3 axis, float seed, float scale){') == 1
    for term in ('float ang = dot(d, axis) * 0.5 + 0.5;',
                 'float rad = clamp(length(local), 0.0, 1.2);',
                 'float n = vnoise3(local * scale + seed * 31.7);'):
        assert term in _STAGE, term
    # ...and the axis and the seed are PER CLUSTER, not global
    assert 'axis: [Math.cos(a1) * Math.sin(a2), Math.cos(a2), Math.sin(a1) * Math.sin(a2)],' in g
    assert 'u.u_axis = {value: nodes.map(' in g and 'u.u_pal = {value: nodes.map(' in g
    # The weighted walk, and the stops are 0.52/0.88 rather than 0.40/0.74.
    # gradT is centred near 0.5, so a first stop at 0.40 hands most of the
    # geometry to the SECONDARY role: a violet cage came out cyan-dominant with
    # violet only at its poles, where both references are violet WITH blue in
    # them. The stops are what give the primary the middle of the range back.
    assert 'vec3 col = mix(a, b, smoothstep(0.52, 0.88, t));' in _STAGE
    assert 'col = mix(col, c, smoothstep(0.86, 1.0, t));' in _STAGE
    # EVERY pass reads it, or a cluster's frame disagrees with its own mesh
    assert g.count('chord(') >= 8, g.count('chord(')



def test_only_zen_may_lift_the_brightness_ceiling():
    """`calm` mixes every scene back toward --bg because the first cut of the
    stage was rejected as "overstimulating, confonde" and both users then wore
    the one skin with no background at all. That ceiling is correct for a
    background and wrong for zen, where the app is hidden and this canvas is
    the only thing on screen — the same lift that would make it a competitor to
    the interface is what makes it visible when there is no interface.

    So the exception is allowed, and fenced three ways: it RAISES the skin's
    own value rather than replacing it (a quiet skin stays quieter than a loud
    one), it is capped below 1 so a bright skin cannot wash out to flat colour,
    and `_zen` is the only term in the expression that is not the skin's."""
    m = re.search(r'return Math\.min\(([\d.]+), base \* k'
                  r' \+ \(this\._zen \? ([\d.]+) : 0\)\);', _STAGE)
    assert m, 'the zen lift is gone, or is no longer expressed as a lift'
    cap, lift = float(m.group(1)), float(m.group(2))
    assert cap < 1.0, 'a ceiling of 1 is no ceiling'
    assert 0 < lift <= 0.5, lift
    # every skin still has to clear the cap with the lift applied, or zen would
    # silently flatten the loudest ones into the same picture
    for name, sk in themes.SKINS.items():
        assert sk.get('calm', 0.3) + lift <= cap + 1e-9, name
    # exactly one expression decides the ceiling. The three inputs compose in
    # _calm() or they disagree somewhere — which is the `gate['diff']` lesson
    # in a different costume: two producers of one value is two chances to get
    # it wrong.
    assert _STAGE.count('calm: this._calm()') == 1, 'a second calm producer'
    # Exactly two things read the mode, and they are the two halves of what
    # "brighter" means in an alpha-composited scene: _calm() decides how far a
    # colour comes up off the page, _gain() decides how much of it survives its
    # own alpha. Moving only the first is what left zen at the 0.95 ceiling and
    # still visibly dim. Anything else reaching for _zen is a third opinion.
    assert _STAGE.count('this._zen ?') == 2, 'zen leaked past calm and gain'
    assert 'dens: this._dens * this._gain()' in _STAGE, 'gain never reaches a scene'


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

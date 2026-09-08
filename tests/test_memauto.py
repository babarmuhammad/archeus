"""Auto-memory updates everything, and overwrites nothing it did not write.

    "se abilitato auto memory, tutte le cose riguardanti memoria devono essere
     aggiornate automaticamente, tenendo in mente di non sovrascrivere regole
     importanti che non sono state auto generate da archeus"

Two halves, and the second is the load-bearing one. Silent automation that
rewrites a file is only acceptable if the boundary of what it may rewrite is
exact and tested — so the tests below seed hand-written content in every place
archeus writes and assert it comes back byte-identical.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from claude_sessions import memory, claude_md, memrules, lessons
from claude_sessions.config import _MEMORY_START, _MEMORY_END


HAND_WRITTEN = """# My project

This paragraph is mine. Nobody generated it and nothing may rewrite it.

## House rules
- always run the linter
- never touch vendor/

<!-- ARCHEUS:MEMORY:START -->
## Project memory (archeus — auto-maintained)

- stale content that SHOULD be replaced
<!-- ARCHEUS:MEMORY:END -->

## Notes after the block
Also mine. Also untouchable.
"""


def _mem(entities=(), extracted=1):
    # `last_extracted` is how a cycle reports how many units it actually
    # re-extracted; auto_cycle's `graph` flag reads it. Default 1 = "the refresh
    # did work", which is what most of these fixtures mean.
    return {'entities': list(entities), 'relations': [], 'summaries': {},
            'provenance': {}, 'module_edges': [], 'lessons_scanned': {},
            'session_counter': 0, 'last_extracted': extracted,
            'pending_units': 0}


# ── the boundary ──────────────────────────────────────────────

def test_the_claudemd_block_is_the_only_thing_rewritten(tmp_path):
    """Prose above it, prose below it, and the user's own headings all survive.
    Only the region between the sentinels changes."""
    p = tmp_path / 'proj'
    p.mkdir()
    md = p / 'CLAUDE.md'
    md.write_text(HAND_WRITTEN, encoding='utf-8')

    ok, old, new = claude_md.write_memory_block(str(p), '- fresh digest line')
    assert ok
    assert 'stale content' not in new
    assert '- fresh digest line' in new
    # everything outside the sentinels is byte-identical
    assert new[:new.index(_MEMORY_START)] == old[:old.index(_MEMORY_START)]
    assert (new[new.index(_MEMORY_END):].replace(_MEMORY_END, '', 1)
            == old[old.index(_MEMORY_END):].replace(_MEMORY_END, '', 1))
    for line in ('This paragraph is mine.', '- always run the linter',
                 '- never touch vendor/', 'Also mine. Also untouchable.'):
        assert line in new, line


def test_rewriting_the_block_is_idempotent(tmp_path):
    """Same digest in, same bytes out.

    It was not: the seam between the closing sentinel and the text after it was
    concatenated rather than normalised, so every rewrite inserted one more
    blank line. Harmless when a human triggered it occasionally; a slow leak now
    that auto_cycle runs unattended on a timer."""
    p = tmp_path / 'proj'
    p.mkdir()
    md = p / 'CLAUDE.md'
    md.write_text(HAND_WRITTEN, encoding='utf-8')

    claude_md.write_memory_block(str(p), '- digest')
    once = md.read_text(encoding='utf-8')
    for _ in range(5):
        claude_md.write_memory_block(str(p), '- digest')
    assert md.read_text(encoding='utf-8') == once, 'the file grows on every write'
    assert '\n' * 3 not in once, 'blank lines accumulated'


def test_a_hand_written_rules_file_is_never_touched(tmp_path):
    """`.claude/rules/` holds both. archeus owns the `archeus-mem-` prefix
    and must treat everything else in that directory as someone's work."""
    p = tmp_path / 'proj'
    rules = p / '.claude' / 'rules'
    rules.mkdir(parents=True)
    mine = rules / 'our-conventions.md'
    mine.write_text('# ours\nnever delete me\n', encoding='utf-8')
    # a stale generated one, which SHOULD be pruned
    stale = rules / 'archeus-mem-gone.md'
    stale.write_text('# old unit\n', encoding='utf-8')
    before = mine.read_bytes()

    memrules.sync_rules(str(p), str(tmp_path / 'folder'), _mem())

    assert mine.read_bytes() == before, 'a hand-written rule was modified'
    assert mine.is_file()
    assert not stale.exists(), 'a stale generated rule was not pruned'


def test_decay_never_evicts_a_pinned_lesson(tmp_path):
    """Pinning is the user saying "keep this". Ageing it out anyway would make
    the pin a lie, and the whole cycle unsafe to run unattended."""
    mem = _mem([
        {'type': 'lesson', 'name': 'pinned one', 'status': 'pinned', 'last_used': 0},
        {'type': 'lesson', 'name': 'approved old', 'status': 'approved', 'last_used': 0},
        {'type': 'component', 'name': 'not a lesson', 'last_used': 0},
    ])
    mem['session_counter'] = 500
    evicted = memrules and lessons.apply_decay(mem, {'memory_lessons_ttl': 30})
    names = {e['name'] for e in mem['entities']}
    assert 'pinned one' in names, 'a pinned lesson was evicted'
    assert 'not a lesson' in names, 'decay hit a non-lesson entity'
    assert 'approved old' not in names, 'nothing aged out at all'
    assert evicted == 1


# ── the cycle actually covers everything ──────────────────────

def test_auto_cycle_mines_lessons_not_just_the_graph(tmp_path, monkeypatch):
    """The gap this exists to close: refresh_memory alone left lessons frozen."""
    calls = []
    monkeypatch.setattr(memory, 'refresh_memory',
                        lambda *a, **k: calls.append('graph') or _mem())
    monkeypatch.setattr(memory, 'load_memory', lambda *a, **k: _mem())
    monkeypatch.setattr(memory, 'save_memory', lambda *a, **k: None)
    monkeypatch.setattr(lessons, 'pending_sids', lambda *a, **k: ['s1', 's2'])
    monkeypatch.setattr(lessons, 'scan_sessions',
                        lambda *a, **k: calls.append('lessons') or (2, 2))
    monkeypatch.setattr(memory, 'sync_to_claudemd',
                        lambda *a, **k: calls.append('claudemd'))
    monkeypatch.setattr(memrules, 'sync_rules', lambda *a, **k: calls.append('rules'))

    out = memory.auto_cycle(str(tmp_path), str(tmp_path), 'proj')

    assert 'graph' in calls, 'the graph was not refreshed'
    assert 'lessons' in calls, 'lessons were not mined — the original bug'
    assert out['lessons'] == 2
    # the digest COUNTS lessons, so it has to be rewritten after they land
    assert calls.index('claudemd') > calls.index('lessons'), calls
    assert 'rules' in calls


def test_lessons_off_is_honoured(tmp_path, monkeypatch):
    """'off' is a real answer, not a default to be overridden by automation."""
    from claude_sessions import config as cfg
    calls = []
    monkeypatch.setattr(cfg, 'load_settings',
                        lambda: dict(cfg._DEFAULT_SETTINGS, memory_lessons='off'))
    monkeypatch.setattr(memory, 'refresh_memory', lambda *a, **k: _mem())
    monkeypatch.setattr(memory, 'load_memory', lambda *a, **k: _mem())
    monkeypatch.setattr(memory, 'save_memory', lambda *a, **k: None)
    monkeypatch.setattr(lessons, 'scan_sessions',
                        lambda *a, **k: calls.append('lessons') or (0, 0))

    memory.auto_cycle(str(tmp_path), str(tmp_path), 'proj')
    assert calls == [], 'mined lessons despite memory_lessons=off'


def test_a_failing_lesson_scan_does_not_lose_the_graph_refresh(tmp_path, monkeypatch):
    """Unattended work must degrade, not roll back. A Claude call that fails
    mid-scan cannot cost the graph update that already succeeded."""
    monkeypatch.setattr(memory, 'refresh_memory', lambda *a, **k: _mem())
    monkeypatch.setattr(memory, 'load_memory', lambda *a, **k: _mem())
    monkeypatch.setattr(memory, 'save_memory', lambda *a, **k: None)
    monkeypatch.setattr(lessons, 'pending_sids', lambda *a, **k: ['s1'])

    def boom(*a, **k):
        raise RuntimeError('claude call failed')
    monkeypatch.setattr(lessons, 'scan_sessions', boom)

    out = memory.auto_cycle(str(tmp_path), str(tmp_path), 'proj')
    assert out['graph'] is True
    assert out['lessons'] == 0


def test_both_auto_paths_use_the_one_cycle():
    """Two entry points refresh memory automatically — the GUI scheduler and
    the detached worker. If either keeps calling refresh_memory directly, that
    half of the product silently stops learning again."""
    import inspect
    from claude_sessions import gui_api, main as main_mod
    g = inspect.getsource(gui_api._refresh_project)
    assert 'auto_cycle' in g and 'refresh_memory(' not in g, g
    # `_bg_scan_worker` does not exist — the function is `_bg_scan_cli`, so the
    # `else 0` fallback made `worker` the WHOLE module and the assertion below
    # trivially true. Half this guard had never tested anything.
    assert not hasattr(main_mod, '_bg_scan_worker')
    worker = inspect.getsource(main_mod._bg_scan_cli)
    assert 'auto_cycle' in worker and 'refresh_memory(' not in worker


def test_the_cycle_stamps_when_it_last_ran(tmp_path, monkeypatch):
    """Silent automation still has to be legible."""
    saved = {}
    monkeypatch.setattr(memory, 'refresh_memory', lambda *a, **k: _mem())
    monkeypatch.setattr(memory, 'load_memory', lambda *a, **k: _mem())
    monkeypatch.setattr(memory, 'save_memory',
                        lambda p, f, mem: saved.update(mem))
    monkeypatch.setattr(lessons, 'pending_sids', lambda *a, **k: [])

    memory.auto_cycle(str(tmp_path), str(tmp_path), 'proj')
    assert saved.get('auto_updated'), saved
    assert 'auto_last' in saved


# ── one setting, every runner ────────────────────────────────
# The GUI checkbox wrote project_defaults[enc].auto_memory and only the GUI
# scheduler read it; the TUI's on-open scan and the detached worker gated on
# the global memory_auto_refresh, which had no control on either surface. So
# ticking the box did nothing outside a running GUI window.

def test_every_runner_reads_the_same_per_project_flag(tmp_path, monkeypatch):
    from harness import Sandbox
    from claude_sessions import memhub, gui_api
    sb = Sandbox(monkeypatch, tmp_path)
    actual, enc, folder, _ = sb.add_project('alpha')

    # the sandbox cannot resolve an encoded folder back to a fake drive, so the
    # scheduler's project list is supplied directly — what is under test is the
    # FILTER, which used to read a flag nothing else in the product wrote
    from claude_sessions import gui
    monkeypatch.setattr(gui, 'list_projects', lambda: [
        {'path': actual, 'encoded': enc, 'primary_cfgdir': str(sb.cfg)}])

    assert memory.auto_enabled(actual, enc) is False
    assert gui_api._auto_projects() == []

    memhub.set_auto_memory(enc, True)                 # the TUI control
    assert memory.auto_enabled(actual, enc) is True   # …seen by the schedulers
    assert [p for p, _f, _e in gui_api._auto_projects()] == [actual]

    memhub.set_auto_memory(enc, False)
    assert memory.auto_enabled(actual, enc) is False
    assert gui_api._auto_projects() == []


def test_background_auto_memory_is_explicit_opt_in(tmp_path, monkeypatch):
    """`memory_auto_refresh` defaults to 'open' and means "refresh when you open
    this". Letting it also mean "poll every project hourly" would put a Claude
    spend on every project archeus can see."""
    from harness import Sandbox
    from claude_sessions import config
    sb = Sandbox(monkeypatch, tmp_path)
    actual, enc, folder, _ = sb.add_project('alpha')
    assert config.load_settings().get('memory_auto_refresh') == 'open'
    assert memory.auto_enabled(actual, enc) is False
    assert memory.refresh_on_open(actual, enc) is True


def test_background_auto_memory_owns_the_spend_so_opening_adds_no_cycle(tmp_path, monkeypatch):
    """Opting a project into background auto-memory used to also mean "refresh
    whenever you open it". So the configured cadence bounded nothing: the
    scheduler waited the interval and then navigating to the project spent a
    cycle anyway. Background auto-memory means launch + interval, and nothing
    else — pressing Build with Claude is still a decision the user can make."""
    from harness import Sandbox
    from claude_sessions import config, memhub
    sb = Sandbox(monkeypatch, tmp_path)
    actual, enc, folder, _ = sb.add_project('alpha')
    assert config.load_settings().get('memory_auto_refresh') == 'open'

    memhub.set_auto_memory(enc, True)
    assert memory.auto_enabled(actual, enc) is True, 'the scheduler still picks it up'
    assert memory.refresh_on_open(actual, enc) is False, \
        'the scheduler owns the cadence; opening must not add a cycle'


def test_the_gui_asks_the_same_question_the_tui_does(tmp_path, monkeypatch):
    """`api_memory_autoscan` re-derived "refresh on open?" from the global
    setting, so the per-project flag was ignored in the GUI entirely — which is
    the surface the report came from. One reader, `memory.refresh_on_open`."""
    from harness import Sandbox
    from claude_sessions import gui_api, memhub
    sb = Sandbox(monkeypatch, tmp_path)
    actual, enc, folder, _ = sb.add_project('alpha')
    started = []
    monkeypatch.setattr(gui_api, '_refresh_async',
                        lambda p, f, auto_cap=6: started.append((p, auto_cap)))
    monkeypatch.setattr(memory, 'is_stale', lambda *a, **k: True)

    memhub.set_auto_memory(enc, True)
    body = {'path': actual, 'enc': enc, 'cfgdir': str(sb.cfg)}
    assert gui_api.api_memory_autoscan({}, body)['running'] is False
    assert started == [], 'opening a scheduled project started a cycle'

    # forcing is a decision, not navigation — and it is uncapped
    gui_api.api_memory_autoscan({}, dict(body, force=True))
    assert started == [(actual, None)]


def test_turning_it_off_turns_off_the_open_scan_too(tmp_path, monkeypatch):
    from harness import Sandbox
    from claude_sessions import memhub
    sb = Sandbox(monkeypatch, tmp_path)
    actual, enc, folder, _ = sb.add_project('alpha')
    memhub.set_auto_memory(enc, False)
    assert memory.refresh_on_open(actual, enc) is False, \
        'an explicit no must beat the global default'


def test_the_tui_starts_the_same_scheduler_the_gui_does(tmp_path, monkeypatch):
    """It had one caller, in run_gui — so "keep this updated automatically"
    silently meant "while the GUI window is open"."""
    import inspect
    from claude_sessions import main as main_mod
    src = inspect.getsource(main_mod.run)
    assert 'start_auto_memory_scheduler' in src


# ── with auto-memory on, memory must never sit stale ─────────
#
#     "make sure if auto memory is on and the project is getting updated then
#      the memory should never go stale"
#
# Three separate ways it could, all closed here: a capped cycle that abandons
# the remainder, a scheduler that waits a full hour before finishing what it
# started, and a project whose memory is verified current but whose freshness
# baseline is never re-stamped.

def test_repeated_ticks_converge_to_not_stale(monkeypatch, tmp_path):
    from harness import Sandbox
    from claude_sessions import gui_api
    sb = Sandbox(monkeypatch, tmp_path)
    actual, enc, folder, _ = sb.add_project('alpha')
    for i in range(9):
        d = os.path.join(actual, f'mod{i}')
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, 'a.py'), 'w', encoding='utf-8') as f:
            f.write('x = 1\n')

    calls = []
    monkeypatch.setattr(memory, '_extract', lambda c, w, unit='', progress='':
                        calls.append(unit) or {'summary': 's ' + unit,
                                               'entities': [{'name': 'E' + unit,
                                                             'type': 'module',
                                                             'summary': 's'}],
                                               'relations': []})
    from claude_sessions import memhub, gui
    memhub.set_auto_memory(enc, True)
    monkeypatch.setattr(gui, 'list_projects', lambda: [
        {'path': actual, 'encoded': enc, 'primary_cfgdir': str(sb.cfg)}])

    assert memory.is_stale(actual, folder) is True     # nine modules, no graph
    owed = None
    for _ in range(10):
        owed = gui_api._auto_scan_pass()
        if not memory.is_stale(actual, folder):
            break
    assert not memory.is_stale(actual, folder), 'it never caught up'
    assert owed is False, 'and the last pass reported nothing owed'
    assert len(set(calls)) == 9, 'every module was eventually extracted'


def test_a_capped_pass_does_not_shorten_the_cadence(monkeypatch, tmp_path):
    """A cycle does at most auto_cap modules, and the rest wait for the NEXT
    scheduled pass — not for a shorter catch-up one.

    The loop used to come back in 45s for as long as any project still owed
    work, on the reasoning that memory should converge rather than sit stale.
    That inverted the point of the cap: across several opted-in projects it is
    most of a daily limit inside an hour, and on a rate-limited account it was
    six *failed* extractions repeating forever. The cap decides what one pass
    may spend; the interval decides how often that happens."""
    from harness import Sandbox
    from claude_sessions import gui_api, memhub, gui
    sb = Sandbox(monkeypatch, tmp_path)
    actual, enc, folder, _ = sb.add_project('alpha')
    for i in range(9):
        d = os.path.join(actual, f'mod{i}')
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, 'a.py'), 'w', encoding='utf-8') as f:
            f.write('x = 1\n')
    monkeypatch.setattr(memory, '_extract', lambda c, w, unit='', progress='':
                        {'summary': 's', 'entities': [{'name': 'E' + unit,
                                                       'type': 'module',
                                                       'summary': 's'}],
                         'relations': []})
    memhub.set_auto_memory(enc, True)
    monkeypatch.setattr(gui, 'list_projects', lambda: [
        {'path': actual, 'encoded': enc, 'primary_cfgdir': str(sb.cfg)}])

    assert gui_api._auto_scan_pass() is True, 'nine modules, cap of six'

    from claude_sessions import config as config_mod
    monkeypatch.setattr(config_mod, 'load_settings',
                        lambda: {'auto_memory_interval': 1800})
    assert gui_api._next_wait(owed=True) == 1800, 'work left must not shorten the wait'
    assert gui_api._next_wait(owed=False) == 1800
    monkeypatch.setattr(config_mod, 'load_settings',
                        lambda: {'auto_memory_interval': 5})
    assert gui_api._next_wait(owed=True) == gui_api.MIN_INTERVAL, 'the floor holds'


def test_a_project_that_is_already_current_still_reports_fresh(monkeypatch, tmp_path):
    """A commit that touches no source file moves HEAD. Nothing needs
    re-extracting — and the workspace screen used to call the project stale
    anyway, because only a refresh that DID work re-stamped the baseline."""
    from harness import Sandbox
    from claude_sessions import workspace
    sb = Sandbox(monkeypatch, tmp_path)
    actual, enc, folder, _ = sb.add_project('alpha')
    d = os.path.join(actual, 'mod1')
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, 'a.py'), 'w', encoding='utf-8') as f:
        f.write('x = 1\n')
    monkeypatch.setattr(memory, '_extract', lambda *a, **k:
                        {'summary': 's', 'entities': [{'name': 'E', 'type': 'module',
                                                       'summary': 's'}],
                         'relations': []})
    monkeypatch.setattr(workspace, '_git_head', lambda p: ('a' * 40, 'a' * 7, 'main'))
    memory.refresh_memory(actual, folder, 'alpha')
    assert not memory.is_stale(actual, folder)

    monkeypatch.setattr(workspace, '_git_head', lambda p: ('b' * 40, 'b' * 7, 'main'))
    _m, _live, checks, _score, _safe = workspace.compute_status(actual, folder)
    assert {c['name']: c['state'] for c in checks}['repo'] == 'stale'

    # a cycle that finds nothing to do is still a verification that memory
    # matches the code, and must say so
    memory.refresh_memory(actual, folder, 'alpha')
    _m, _live, checks, _score, _safe = workspace.compute_status(actual, folder)
    states = {c['name']: c['state'] for c in checks}
    assert states['repo'] == 'fresh' and states['claude_md_fresh'] == 'fresh'


# ── it runs on launch, then on the interval ──────────────────
#
#     "if i want to build auto memory it should do it automatically when i
#      launch archeus, then do it periodically on the configured time period,
#      right now i have to click on a project then it starts updating memory"
#
# The loop had no coverage at all: only that the stop flag could be set.

def test_the_scheduler_runs_a_pass_on_launch(monkeypatch):
    """Not "when you open a project" — on start."""
    import threading
    from claude_sessions import gui_api
    passes = threading.Event()
    monkeypatch.setattr(gui_api, 'STARTUP_DELAY', 0.05)
    monkeypatch.setattr(gui_api, '_auto_scan_pass',
                        lambda: passes.set() or False)
    monkeypatch.setattr(gui_api, '_sched_started', False)
    try:
        gui_api.start_auto_memory_scheduler()
        assert passes.wait(5), 'no pass ran after launch'
    finally:
        gui_api.stop_auto_memory_scheduler()


def test_it_keeps_going_after_the_first_pass(monkeypatch):
    """One pass at launch is not "periodically". The cadence itself is
    `_next_wait`'s job and is asserted there; this only proves the loop comes
    back, so it drives the wait through that seam rather than through a settings
    interval it cannot make shorter than a minute."""
    import threading
    from claude_sessions import gui_api
    n = []
    done = threading.Event()

    def _pass():
        n.append(1)
        if len(n) >= 3:
            done.set()
        return True                       # work still owed

    monkeypatch.setattr(gui_api, 'STARTUP_DELAY', 0.05)
    monkeypatch.setattr(gui_api, '_next_wait', lambda owed=False: 0.05)
    monkeypatch.setattr(gui_api, '_auto_scan_pass', _pass)
    monkeypatch.setattr(gui_api, '_sched_started', False)
    try:
        gui_api.start_auto_memory_scheduler()
        assert done.wait(5), f'only {len(n)} pass(es) ran; it does not repeat'
    finally:
        gui_api.stop_auto_memory_scheduler()


def test_a_stopped_scheduler_stops(monkeypatch):
    """A daemon thread that ignores the stop flag outlives the window."""
    import threading
    import time
    from claude_sessions import gui_api
    n = []
    monkeypatch.setattr(gui_api, 'STARTUP_DELAY', 0.05)
    monkeypatch.setattr(gui_api, '_next_wait', lambda owed=False: 0.05)
    monkeypatch.setattr(gui_api, '_auto_scan_pass', lambda: n.append(1) or True)
    monkeypatch.setattr(gui_api, '_sched_started', False)
    gui_api.start_auto_memory_scheduler()
    time.sleep(0.4)
    gui_api.stop_auto_memory_scheduler()
    seen = len(n)
    assert seen, 'it never ran'
    time.sleep(0.4)
    assert len(n) == seen, 'it kept running after being stopped'


def test_both_interfaces_start_it(monkeypatch):
    """It had ONE caller, in run_gui — so "keep this updated automatically"
    silently meant "while the GUI window is open"."""
    import inspect
    from claude_sessions import gui, main as main_mod
    assert 'start_auto_memory_scheduler' in inspect.getsource(gui.run_gui)
    assert 'start_auto_memory_scheduler' in inspect.getsource(main_mod.run)

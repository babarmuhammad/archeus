"""The P19.5 motion-foundation mutation suite (ADR-0024, ADR-0029 §6): break
each gate's invariant, run the test written for it, and require it to fail.

    py tools/mutate_p19_5.py            every mutation
    py tools/mutate_p19_5.py N01 N11    only these

The runner is tools/mutate_p18.py's (tools/mutate_p11.py's snippet engine:
each snippet occurs once, the guarding tests pass on the unmutated tree first,
files are restored whatever happens; a browser-guarded mutant rebuilds the
SPA). It edits sources: run it with nothing else running against the tree.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mutate_p18  # noqa: E402  (its runner)

REG = 'clients/app/tokens/motion.json'
REG_TS = 'clients/app/src/state/motion.ts'
TL = 'clients/app/src/state/timeline.ts'
LOOP = 'clients/app/src/graph/loop.ts'
GV = 'clients/app/src/graph/GraphView.tsx'
CSS = 'clients/app/src/styles/app.css'
TS = 'node:test/motion.test.ts'
DG = 'tests/v1/design/test_design_gates.py::'
E2E = 'tests/v1/e2e/test_spa_motion.py::'
IDLE = E2E + 'test_idle_archeus_runs_no_frame_and_no_animation'
REPLAY = E2E + 'test_a_historical_event_heard_again_never_replays_or_restarts'

MUTATIONS = [
    # ── the registry ──
    ('N01', 'a registered motion allowed to replay', [(REG,
     '"idle": "never", "replay": false,\n      "reduced": "jump:',
     '"idle": "never", "replay": true,\n      "reduced": "jump:')],
     [DG + 'test_the_motion_registry_holds_the_approved_budgets']),
    ('N02', 'the travelling marker over its 600 ms budget (registry)', [(REG,
     '"max_ms": 600, "easing": "linear",',
     '"max_ms": 700, "easing": "linear",')],
     [DG + 'test_the_motion_registry_holds_the_approved_budgets']),
    ('N03', 'the travelling marker over its 600 ms budget and 8 cap (generated)', [(REG_TS,
     '"max_ms": 600,\n    "token": null,\n    "ttl_ms": null,\n    "ttl_error_ms": null,\n    "easing": "linear",\n    "cap": 8,',
     '"max_ms": 700,\n    "token": null,\n    "ttl_ms": null,\n    "ttl_error_ms": null,\n    "easing": "linear",\n    "cap": 9,')],
     [TS]),
    ('N04', 'a motion with no text equivalent', [(REG_TS,
     '"equivalent": "the chip\'s text"',
     '"equivalent": ""')],
     [TS]),
    ('N05', 'an approved, unbuilt motion binds a keyframe', [(REG,
     '"trigger": "a list gained or lost a row (keyed reconcile)",\n      "driven_by": "event", "runs_on": "css",',
     '"trigger": "a list gained or lost a row (keyed reconcile)",\n      "driven_by": "event", "runs_on": "css", "css": ["state-in"],')],
     [DG + 'test_the_generated_ui_files_are_current']),
    ('N06', 'the registry claims a keyframe that does not exist', [(REG,
     '"css": ["dialog-in"]',
     '"css": ["dialog-in", "gone-in"]')],
     [DG + 'test_every_keyframe_and_transition_is_a_registered_motion']),
    ('N07', 'an unregistered keyframe', [(CSS,
     '@media (prefers-reduced-motion: reduce) {',
     '@keyframes spin {\n  to {\n    transform: rotate(1turn);\n  }\n}\n\n'
     '@media (prefers-reduced-motion: reduce) {')],
     [DG + 'test_every_keyframe_and_transition_is_a_registered_motion']),
    ('N08', 'an unregistered transition', [(CSS,
     '.btn.primary {',
     '.chip {\n  transition: opacity var(--dur-state) var(--ease);\n}\n\n.btn.primary {')],
     [DG + 'test_every_keyframe_and_transition_is_a_registered_motion']),
    ('N09', 'a WAAPI animation outside the registry (TS gate)', [(GV,
     '    const c = canvas.current!;\n',
     '    const c = canvas.current!;\n    c.animate([{ opacity: 0 }, { opacity: 1 }], 200);\n')],
     [TS]),
    ('N10', 'a WAAPI animation outside the registry (Node-free gate)', [(GV,
     '    const c = canvas.current!;\n',
     '    const c = canvas.current!;\n    c.animate([{ opacity: 0 }, { opacity: 1 }], 200);\n')],
     [DG + 'test_every_loop_animation_is_a_registered_built_motion']),
    ('N11', 'an approved, unbuilt motion run by the client', [(GV,
     "!loop!.animate('execution-pulse')) return;",
     "!loop!.animate('execution-pulse') || !loop!.animate('travelling-marker' as never)) return;")],
     [TS]),
    ('N12', 'a built loop motion nothing runs', [(GV,
     "loopRef.current?.animate('camera-settle')",
     "loopRef.current?.animate('execution-pulse')")],
     [TS]),
    # ── the presentation clock ──
    ('N13', 'an event read again is presented again', [(TL,
     'seq <= (this.seen.get(motion) ?? -Infinity)',
     'seq < (this.seen.get(motion) ?? -Infinity)')],
     [TS]),
    ('N14', 'an event read again is presented again, in the browser', [(TL,
     'seq <= (this.seen.get(motion) ?? -Infinity)',
     'seq < (this.seen.get(motion) ?? -Infinity)')],
     [REPLAY]),
    ('N15', 'a completed presentation stays animated', [(TL,
     'if (t >= s.start && t < s.start + ms)',
     'if (t >= s.start)')],
     [TS]),
    ('N16', 'a motion started under reduced motion', [(TL,
     'if (reduced || ms === null) return false;',
     'if ((reduced && false) || ms === null) return false;')],
     [TS]),
    ('N17', 'the cap ignored', [(TL,
     'if (same.length >= m.cap) {',
     'if (same.length >= m.cap * 1000) {')],
     [TS]),
    ('N18', 'the newest dropped at the cap instead of the oldest', [(TL,
     'this.shows.splice(this.shows.indexOf(same[0]), 1);',
     'this.shows.splice(this.shows.indexOf(same[same.length - 1]), 1);')],
     [TS]),
    ('N19', 'renderAt reads the wall clock (TS)', [(TL,
     'p: (t - s.start) / ms',
     'p: (performance.now() - s.start) / ms')],
     [TS]),
    ('N20', 'renderAt reads the wall clock (Node-free gate)', [(TL,
     'p: (t - s.start) / ms',
     'p: (performance.now() - s.start) / ms')],
     [DG + 'test_the_presentation_clock_and_the_renderer_read_no_clock_and_no_random']),
    # ── the idle invariant ──
    ('N21', 'the loop keeps scheduling with nothing to animate (unit idle gate)', [(LOOP,
     '    if (this.anims.size) this.kick();',
     '    if (true) this.kick();')],
     [TS]),
    ('N22', 'the loop keeps scheduling with nothing to animate (browser idle gate)', [(LOOP,
     '    if (this.anims.size) this.kick();',
     '    if (true) this.kick();')],
     [IDLE]),
    ('N23', 'a perpetual CSS animation on an idle page (browser idle gate)', [(CSS,
     '.state .glyph {\n  display: inline-block;\n}',
     '.state .glyph {\n  display: inline-block;\n  animation: state-in var(--dur-state) var(--ease) infinite;\n}')],
     [IDLE]),
]

if __name__ == '__main__':
    mutate_p18.MUTATIONS = MUTATIONS
    sys.exit(mutate_p18.run(sys.argv[1:]))

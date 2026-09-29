"""The P16 mutation suite (p16-design-gate §24.2): break each design-critical
semantic of the V1 client and its backend seams, run the tests that guard it,
and require them to fail.

    py tools/mutate_p16.py            every mutation
    py tools/mutate_p16.py M04 M13    only these

The runner is tools/mutate_p11.py's (exact snippets, each occurring once,
restored whatever happens), extended to the client: a guard named
`node:<file>` runs `node --test` on that file in clients/app (type stripping,
no framework); anything else is a pytest node id. It edits sources: run it with
nothing else running against the tree.
"""

import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mutate_p11  # noqa: E402  (its snippet engine)

ROOT = mutate_p11.ROOT
APP = os.path.join(ROOT, 'clients', 'app')
PRES = 'clients/app/src/state/presentation.ts'
PRESENT = 'clients/app/src/state/present.ts'
CONN = 'clients/app/src/data/connection.ts'
CMDS = 'clients/app/src/data/commands.ts'
INV = 'clients/app/src/data/invalidation.ts'
REL = 'clients/app/src/graph/relations.ts'
NAV = 'clients/app/src/nav/destinations.ts'
ANN = 'clients/app/src/a11y/announce.ts'
CTRL = 'clients/app/src/surfaces/Control.tsx'
STREAM = 'clients/app/src/api/stream.ts'
CSS = 'clients/app/src/styles/app.css'
PJSON = 'clients/app/tokens/presentation.json'
ATT = 'archeus/core/application/attention.py'
OUT = 'archeus/core/execution/output.py'
RTS = 'archeus/api/routes.py'
AUTH = 'archeus/api/auth.py'

T_PRES = 'node:test/presentation.test.ts'
T_PRESENT = 'node:test/present.test.ts'
T_CONN = 'node:test/connection.test.ts'
T_INV = 'node:test/invalidation.test.ts'
T_REL = 'node:test/relations.test.ts'
T_SHELL = 'node:test/shell.test.ts'
SEAMS = 'tests/v1/integration/test_ui_seams.py'
DESIGN = 'tests/v1/design/test_design_gates.py'

MUTATIONS = [
    # ── the lifecycle's look: proposed ≠ approved ≠ executing ≠ verified ≠ accepted ──
    ('M01', 'a mission waiting for approval looks approved', [(PRES,
     '    "APPROVAL_REQUIRED": "needs_you",\n    "APPROVED": "approved",',
     '    "APPROVAL_REQUIRED": "approved",\n    "APPROVED": "approved",')], [T_PRES]),
    ('M02', 'an approved mission looks executing', [(PRES,
     '    "APPROVED": "approved",\n    "BLOCKED": "blocked",',
     '    "APPROVED": "active",\n    "BLOCKED": "blocked",')], [T_PRES]),
    ('M03', 'a verifying mission looks done', [(PRES,
     '    "UNDERSTANDING": "planning",\n    "VERIFYING": "verifying"',
     '    "UNDERSTANDING": "planning",\n    "VERIFYING": "done"')], [T_PRES]),
    ('M04', 'a verified, unreviewed mission looks accepted', [(PRES,
     '    "RESUMED": "active",\n    "REVIEWING": "reviewing",',
     '    "RESUMED": "active",\n    "REVIEWING": "done",')], [T_PRES]),
    ('M05', 'an execution that exited ok looks like success', [(PRES,
     '    "ENDED_OK": "neutral",', '    "ENDED_OK": "done",')], [T_PRES]),
    ('M06', 'a superseded plan version is shown as current', [(REL,
     "inactive: v.state === 'SUPERSEDED' || v.state === 'REJECTED',", 'inactive: false,')],
     [T_REL]),
    # ── realtime: stale is never current ──
    ('M07', 'a view reads as current while the stream reconnects', [(CONN,
     "  if (c.conn === 'reconnecting' || c.conn === 'connecting') return entry.hasData ? "
     "'reconnecting' : 'unavailable';",
     "  if (false) return 'reconnecting';")], [T_CONN]),
    ('M08', 'a resync does not make what was read before stale', [(CONN,
     "return s.conn === 'connecting' ? to('connecting', true) : to('resynced', true);",
     "return s.conn === 'connecting' ? to('connecting', true) : to('resynced');")], [T_CONN]),
    ('M09', 'a recently seen client is shown as connected', [(PRESENT,
     "      return 'seen in the last minute';",
     "      return `connected (${p.connections} streams)`;")], [T_PRESENT]),
    ('M10', "a session row wears its mission's state", [(CTRL,
     '                    <StateBadge machine="session" state={x.state} />\n'
     '                    <span className="title mono">{x.id}</span>',
     '                    <StateBadge machine="mission" state={x.state} />\n'
     '                    <span className="title mono">{x.id}</span>')], [T_SHELL]),
    # ── the graph's list form: authoritative edges only ──
    ('M11', 'a hand-off edge points the wrong way', [(REL,
     "edge(out, 'continues', 'execution', e.handoff_from, 'Execution.handoff_from');",
     "edge(out, 'continues', 'execution', e.id, 'Execution.handoff_from');")], [T_REL]),
    ('M12', 'a verification is linked to an execution it did not record', [(REL,
     "edge(out, 'checked the work of', 'execution', v.execution_id, 'Verification.execution_id');",
     "edge(out, 'checked the work of', 'execution', v.execution_id ?? v.plan_id, "
     "'Verification.execution_id');")], [T_REL]),
    # ── model × harness × account, approvals, commands ──
    ('M13', 'the model is merged into the harness field', [(PRESENT,
     "    { key: 'harness', label: 'Harness', value: v(r.harness_id) },",
     "    { key: 'harness', label: 'Harness', value: v(r.harness_id) + ' ' + v(r.model) },")],
     [T_PRESENT]),
    ('M14', 'a decision does not echo the displayed action hash', [(CMDS,
     '  return { decision, action_hash: a.action_hash, expected_version: a.version,',
     '  return { decision, action_hash: String(a.version), expected_version: a.version,')],
     [T_SHELL]),
    ('M15', 'a network retry gets a new idempotency key', [(CMDS,
     "  outcome === 'network' ? prev : fresh();", '  fresh();')], [T_SHELL]),
    # ── accessibility, motion, responsive ──
    ('M16', 'a state badge renders a glyph without a label', [(PRESENT,
     '  return { glyph: l.glyph, label: l.label || state, role: l.role, cls: l.cls };',
     "  return { glyph: l.glyph, label: '', role: l.role, cls: l.cls };")], [T_PRES]),
    ('M17', 'the reduced-motion setting is ignored', [(CMDS,
     "  systemReduced || pref === 'reduced' ? 'reduced' : 'full';",
     "  systemReduced ? 'reduced' : 'full';")], [T_SHELL]),
    ('M18', 'a phone loses Attention from its tab bar', [(NAV,
     "{ id: 'attention', label: 'Attention', key: 'j', phone: 'tab',",
     "{ id: 'attention', label: 'Attention', key: 'j', phone: 'menu',")], [T_SHELL]),
    ('M19', 'the polite announcer speaks on every frame', [(ANN,
     '      if (now - last >= every) {\n        last = now;\n        pending = null;',
     '      if (true) {\n        last = now;\n        pending = null;')], [T_SHELL]),
    # ── the backend seams (D2–D5) ──
    ('M20', 'attention omits knowledge proposals', [(ATT,
     "entities.KnowledgeItem, **{'state': 'CANDIDATE'})",
     "entities.KnowledgeItem, **{'state': 'CONFIRMED'})")],
     [SEAMS + '::test_attention_lists_exactly_what_waits_on_the_user']),
    ('M21', 'attention lists an approval already decided', [(ATT,
     "entities.Approval, **{'state': 'PENDING'})", 'entities.Approval)')],
     [SEAMS + '::test_attention_lists_exactly_what_waits_on_the_user']),
    ('M22', 'the output tail is not redacted', [(OUT,
     '    events = [json.loads(redact(json.dumps(e, ensure_ascii=False))) for e in snap.events]',
     '    events = list(snap.events)')],
     [SEAMS + '::test_the_output_tail_is_redacted_resumable_and_empty_before_a_process']),
    ('M23', "a mission's timeline carries another mission's events", [(ATT,
     '        subjects[kind] = [r.entity.id for r in rows.where(conn, cls, mission_id=mission_id)]',
     '        subjects[kind] = [r.entity.id for r in rows.where(conn, cls)]')],
     [SEAMS + '::test_the_timeline_holds_the_missions_own_events_and_no_other']),
    ('M24', "a launch grant exceeds its minter's scopes", [(RTS,
     "        if s not in req.principal['scopes']:\n            raise Refused(403, 'scope_required', "
     "{'scope': s})",
     "        if False:\n            raise Refused(403, 'scope_required', {'scope': s})")],
     [SEAMS + '::test_a_launch_grant_never_exceeds_the_minters_own_scopes']),
    ('M25', 'the default launch grant is widened', [(AUTH,
     "LAUNCH_SCOPES = ('observe',)", "LAUNCH_SCOPES = ('observe', 'control')")],
     [SEAMS + '::test_a_launch_code_carries_the_grant_its_minter_chose']),
    # ── the design gates themselves ──
    ('M26', 'a keyframe animates a paint property', [(CSS,
     '@keyframes state-in {\n  from {\n    opacity: 0;',
     '@keyframes state-in {\n  from {\n    background: red;\n    opacity: 0;')],
     [DESIGN + '::test_keyframes_animate_only_transform_and_opacity']),
    ('M27', 'a mission state has no presentation class', [(PJSON,
     '"RESUMED": "active", "VERIFYING": "verifying", "REVIEWING": "reviewing",',
     '"RESUMED": "active", "VERIFYING": "verifying",')],
     [DESIGN + '::test_the_generated_ui_files_are_current']),
    ('M28', 'a mission frame stops re-reading what waits on the user', [(INV,
     "  mission: ['/v1/missions**', '/v1/attention', '/v1/digest', '/v1/status**'],",
     "  mission: ['/v1/missions**', '/v1/digest', '/v1/status**'],")], [T_INV]),
    ('M29', 'opening the stream starts a session (presence treated as a session)', [(STREAM,
     '        emit({ event: OPENED });',
     "        emit({ event: OPENED });\n        void fetch('/v1/sessions', { method: 'POST' });")],
     [T_SHELL]),
]


def _run(tests, fail_fast=True):
    """(returncode, output) of the guarding tests: pytest ids and node test files."""
    node = [t[5:] for t in tests if t.startswith('node:')]
    py = [t for t in tests if not t.startswith('node:')]
    out, code = '', 0
    try:
        if py:
            r = subprocess.run([sys.executable, '-m', 'pytest', '-q', '-p', 'no:cacheprovider',
                                *(['-x'] if fail_fast else []), *sorted(set(py))], cwd=ROOT,
                               capture_output=True, text=True, timeout=mutate_p11.TIMEOUT_S,
                               env=mutate_p11._ENV)
            out, code = out + r.stdout[-3000:], code or r.returncode
        if node and not (fail_fast and code):
            r = subprocess.run(['node', '--experimental-strip-types', '--no-warnings', '--test',
                                *sorted(set(node))], cwd=APP, capture_output=True, text=True,
                               timeout=mutate_p11.TIMEOUT_S, shell=os.name == 'nt')
            out, code = out + r.stdout[-3000:], code or r.returncode
    except subprocess.TimeoutExpired:
        return 1, 'timed out'
    return code, out


def run(selected=()):
    chosen = [m for m in MUTATIONS if not selected or m[0] in selected]
    for _mid, _what, edits, _tests in chosen:          # every snippet checked before any run
        mutate_p11._apply(edits)
    code, out = _run([t for m in chosen for t in m[3]], fail_fast=False)
    if code:
        raise SystemExit('the guarding tests fail on the unmutated tree; fix them first:\n%s' % out)
    survived, killed = [], []
    for mid, what, edits, tests in chosen:
        files = mutate_p11._apply(edits)
        try:
            for path, (_src, mutated) in files.items():
                with open(path, 'w', encoding='utf-8', newline='') as f:
                    f.write(mutated)
            caught = _run(tests)[0] != 0
        finally:
            for path, (src, _mutated) in files.items():
                with open(path, 'w', encoding='utf-8', newline='') as f:
                    f.write(src)
                mutate_p11._drop_pyc(path)
        (killed if caught else survived).append(mid)
        print('%-5s %-8s %s' % (mid, 'killed' if caught else 'SURVIVED', what), flush=True)
    print('\n%d/%d killed' % (len(killed), len(killed) + len(survived)))
    return 1 if survived else 0


if __name__ == '__main__':
    sys.exit(run(sys.argv[1:]))

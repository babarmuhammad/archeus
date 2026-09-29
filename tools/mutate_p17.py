"""The P17 mutation suite (p17-design-gate §12.2): break each invariant of the V1
TUI, run the test that guards that invariant directly, and require it to fail.

    py tools/mutate_p17.py            every mutation
    py tools/mutate_p17.py M01 M20    only these

The runner is tools/mutate_p11.py's snippet engine (each snippet occurs once,
every guarding test passes on the unmutated tree first, files restored whatever
happens). Each mutant names the test written for its invariant, never an
unrelated safeguard that happens to fail. It edits sources: run it with nothing
else running against the tree.
"""

import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mutate_p11  # noqa: E402  (its snippet engine)

ROOT = mutate_p11.ROOT
TUI = 'archeus/cli/tui/'
APP, SCR, VIEW, PRES, SYNC, CLI, TAB = (TUI + n for n in (
    'app.py', 'screens.py', 'view.py', 'present.py', 'sync.py', 'client.py', '_tables.py'))
T = 'tests/v1/tui/'
ACC, SEC, BND, PAR, CLT = (T + n for n in ('test_acceptance.py', 'test_security.py',
                                           'test_boundaries.py', 'test_parity.py',
                                           'test_client.py'))
G3 = 'tests/v1/judge/test_g03_one_model.py::test_the_tui_shows_the_mission_the_api_reports'
DESIGN = 'tests/v1/design/test_design_gates.py::test_the_generated_ui_files_are_current'

MUTATIONS = [
    ('M01', 'the sanitiser bypassed for a mission title', [(SCR,
     "    bits = [app.st.badge('mission', m['state']), T(app, m['title'], 'text')]",
     "    bits = [app.st.badge('mission', m['state']), app.st.paint(m['title'], 'text')]")],
     [SEC + '::test_a_hostile_mission_title_and_objective_reach_no_frame_whole']),
    ('M02', 'NO_COLOR ignored', [(VIEW,
     "        colour = (vt_ok and tty and 'NO_COLOR' not in env and env.get('TERM') != 'dumb')",
     "        colour = (vt_ok and tty and env.get('TERM') != 'dumb')")],
     [ACC + '::test_T09_monochrome_whenever_colour_cannot_be_trusted']),
    ('M03', 'two ASCII glyphs collide', [(TAB,
     " 'paused': {'glyph': '‖', 'ascii': '=',",
     " 'paused': {'glyph': '‖', 'ascii': '#',")],
     [BND + '::test_the_ascii_fallback_tells_apart_what_the_glyphs_tell_apart']),
    ('M04', 'a destination dropped from the TUI screen map', [(SCR,
     "SCREENS = {'now': now, 'work': work, 'world': world, 'attention': attention, 'control': control}",
     "SCREENS = {'now': now, 'work': work, 'world': world, 'attention': attention}")],
     [BND + '::test_every_destination_has_its_screen_and_nothing_else_is_one']),
    ('M05', 'an execution that exited 0 rendered as done', [(TAB,
     "               'ENDED_OK': 'neutral',",
     "               'ENDED_OK': 'done',")],
     [PAR]),
    ('M06', 'route candidates ordered by the client', [(SCR,
     "    for c in d.get('candidates') or []:",
     "    for c in sorted(d.get('candidates') or [], key=json.dumps):")],
     [ACC + '::test_T05_candidates_are_shown_in_the_order_core_recorded_them']),
    ('M07', 'the resource line merges the model into the harness', [(PRES,
     "    out = [{'key': 'harness', 'label': 'Harness', 'value': _str(r.get('harness_id')) or '—'},",
     "    out = [{'key': 'harness', 'label': 'Harness',\n"
     "            'value': ' '.join(filter(None, (_str(r.get('harness_id')), _str(r.get('model')))))\n"
     "            or '—'},")],
     [PAR]),
    ('M08', 'a frame payload written into what is shown', [(APP,
     "            else:\n                self.invalidate(S.stale_by(v))",
     "            else:\n                self.invalidate(S.stale_by(v))\n"
     "                for e in self.cache.values():\n"
     "                    if isinstance(e['data'], dict):\n"
     "                        e['data'].update((v.get('data') or {}))")],
     [ACC + '::test_T15_a_frame_invalidates_by_identity_and_an_unknown_kind_nothing']),
    ('M09', 'an approval shown as approved before the re-read', [(APP,
     "            self.say(act['sent'] or 'Sent — reading it again.')",
     "            self.say(act['sent'] or 'Sent — reading it again.')\n"
     "            for e in self.cache.values():\n"
     "                if isinstance(e['data'], dict) and 'action_hash' in e['data']:\n"
     "                    e['data']['state'] = 'APPROVED'")],
     [ACC + '::test_T03_a_plan_is_approved_from_attention_confirmed_in_prose_and_read_back']),
    ('M10', 'a retry sent with a new idempotency key', [(APP,
     "        key = self.keys.get(act['ident']) or S.new_key()",
     "        key = S.new_key()")],
     [ACC + '::test_T03_the_same_action_keeps_its_key_across_a_network_retry']),
    ('M11', 'an approval frame no longer makes Attention stale', [(TAB,
     " 'approval': ['/v1/approvals**', '/v1/attention', '/v1/missions**'],",
     " 'approval': ['/v1/approvals**', '/v1/missions**'],")],
     [ACC + '::test_T15_a_frame_invalidates_by_identity_and_an_unknown_kind_nothing']),
    ('M12', 'the token carried in an error', [(CLI,
     "            raise CoreError(0, 'network', {'why': type(e).__name__}) from None",
     "            raise CoreError(0, 'network', {'why': type(e).__name__,\n"
     "                                           'token': self._token}) from None")],
     [CLT + '::test_an_unreachable_core_is_a_network_refusal_with_nothing_of_the_token']),
    ('M13', 'a non-loopback address accepted', [(CLI,
     "LOOPBACK = '127.0.0.1'",
     "LOOPBACK = 'localhost'")],
     [CLT + '::test_the_client_only_ever_speaks_to_loopback']),
    ('M14', 'a decision sent without its confirmation', [(APP,
     "        if act['confirm']:\n            self.mode = {'kind': 'confirm'",
     "        if False:\n            self.mode = {'kind': 'confirm'")],
     [ACC + '::test_T03_a_plan_is_approved_from_attention_confirmed_in_prose_and_read_back']),
    ('M15', 'a command offered where the state has no trigger', [(SCR,
     "    if P.offers('mission', m['state'], 'pause'):",
     "    if True:")],
     [ACC + '::test_T04_a_command_the_state_has_no_trigger_for_is_not_offered']),
    ('M16', 'the generated TUI tables stale against their source', [(TAB,
     "'label': 'Attention',",
     "'label': 'Attend',")],
     [DESIGN, BND + '::test_the_generated_tables_are_the_json_the_spa_reads']),
    ('M17', 'an inspector tab missing for a kind', [(TAB,
     "INSPECTOR_TABS = {'mission': ['outcome', 'plan', 'now', 'evidence', 'why', 'timeline', 'relations'],",
     "INSPECTOR_TABS = {'mission': ['outcome', 'plan', 'now', 'evidence', 'why', 'timeline'],")],
     [BND + '::test_the_generated_tables_are_the_json_the_spa_reads']),
    ('M18', 'an expired cursor reconnected without a resync', [(CLI,
     "                if e.status == 410:\n                    last = None\n"
     "                    self.out.put(('signal', 'resync'))",
     "                if e.status == 410:\n                    last = None")],
     [CLT + '::test_an_expired_cursor_is_a_resync']),
    ('M19', 'a frame of an unknown kind makes everything stale', [(SYNC,
     "    rx = [_compile(p, subject.get('id') or '') for p in RULES.get(kind, [])] if kind else []",
     "    rx = [_compile(p, subject.get('id') or '') for p in RULES.get(kind, ['/v1/**'])] "
     "if kind else []")],
     [ACC + '::test_T15_a_frame_invalidates_by_identity_and_an_unknown_kind_nothing']),
    ('M20', 'lines no longer fitted to the terminal', [(VIEW,
     "        out = render.fit(text, width)",
     "        out = text")],
     [ACC + '::test_T10_no_line_is_wider_than_the_terminal_at_any_width']),
    ('M21', 'the Work row labelled from another machine than the mission', [(SCR,
     "    bits = [app.st.badge('mission', m['state']), T(app, m['title'], 'text')]",
     "    bits = [app.st.badge('task', m['state']), T(app, m['title'], 'text')]")],
     [G3]),
    ('M22', 'the TUI imports Core', [(SCR,
     "import json\n",
     "import json\n\nimport archeus.core.domain.states  # noqa: F401\n")],
     [BND + '::test_the_tui_imports_the_standard_library_itself_and_three_seams_only']),
    ('M23', 'the TUI reads a file under the home', [(CLI,
     "        token = discovery.read_local_token()\n        if token is None:\n            return None, 'no_token'",
     "        token = discovery.read_local_token()\n        if token is None:\n            return None, 'no_token'\n"
     "        open(discovery.core_json_path()).close()")],
     [BND + '::test_the_tui_opens_no_file_and_reads_nothing_under_the_home']),
    ('M24', 'the relation tier word dropped', [(SCR,
     "            if e.get('tier'):\n                bits.append(T(app, e['tier'].lower(), 'text-2'))",
     "            if False:\n                bits.append(T(app, e['tier'].lower(), 'text-2'))")],
     [ACC + '::test_relations_say_the_tier_and_the_field_in_words']),
    ('M25', 'a verb parsed in the command line', [(APP,
     "        if needle:\n            hits.append(('Tell Archeus: ' + q.strip(), ('tell', q.strip())))",
     "        if needle.startswith('approve'):\n"
     "            hits.insert(0, ('Approve', ('go', {'view': 'attention'})))\n"
     "        if needle:\n            hits.append(('Tell Archeus: ' + q.strip(), ('tell', q.strip())))")],
     [ACC + '::test_T11_the_command_line_goes_to_a_mission_or_tells_archeus_unparsed']),
    ('M26', 'opening the stream starts a session (presence treated as a session)', [(APP,
     "        self.conn = S.next_state(self.conn, sig, self.now_ms())",
     "        self.conn = S.next_state(self.conn, sig, self.now_ms())\n"
     "        if sig == 'stream_open':\n"
     "            self.core.post('/v1/sessions', {})")],
     [BND + '::test_being_connected_sends_nothing_presence_is_not_a_session']),
    ('M27', 'every row of a long list built', [(SCR,
     "            for m in ms[:PAGE]:",
     "            for m in ms:")],
     [ACC + '::test_T15_a_thousand_missions_render_in_budget_with_one_read_per_list']),
    ('M28', 'the terminal left raw after an exception', [(APP,
     "        if live:\n            render.screen_restore()\n        term.restore()",
     "        if live:\n            render.screen_restore()")],
     [BND + '::test_the_terminal_is_given_back_on_every_way_out']),
]


def _run(tests, fail_fast=True):
    try:
        r = subprocess.run([sys.executable, '-m', 'pytest', '-q', '-p', 'no:cacheprovider',
                            *(['-x'] if fail_fast else []), *sorted(set(tests))], cwd=ROOT,
                           capture_output=True, encoding='utf-8', errors='replace',
                           timeout=mutate_p11.TIMEOUT_S, env=mutate_p11._ENV)
    except subprocess.TimeoutExpired:
        return 1, 'timed out'
    return r.returncode, r.stdout[-3000:]


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

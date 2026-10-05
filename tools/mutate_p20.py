"""The P20 mutation suite (p20-design-gate §4.1; D14's ids are provisional until
the user decides it). Slice A, item 83: the e-stop with Core down or not
answering (Q01-Q08); slice B, F7 and F8, Control → About's emergency stop
(Q09-Q17; an e2e-guarded mutant rebuilds the SPA); slice C, F4's stream
takeover (Q18-Q25) and item 86's one shell credential at a time (Q26-Q32).

    py tools/mutate_p20.py            every mutation
    py tools/mutate_p20.py Q01 Q05    only these

The runner is tools/mutate_p18.py's (tools/mutate_p11.py's snippet engine:
each snippet occurs once, the guarding tests pass on the unmutated tree first,
files are restored whatever happens). It edits sources: run it with nothing
else running against the tree.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mutate_p18  # noqa: E402  (its runner)

NODE = 'archeus/node/local.py'
MAIN = 'archeus/cli/main.py'
D = 'tests/v1/integration/test_estop_drills.py::'
G5 = 'tests/v1/judge/test_g05_estop.py::test_the_estop_works_with_core_down_and_core_comes_back_disarmed'
CTRL = 'clients/app/src/surfaces/Control.tsx'
PRES = 'clients/app/src/state/present.ts'
UI = 'clients/app/src/components/ui.tsx'
AB = 'tests/v1/e2e/test_spa_estop_about.py::'
ES_TS = 'node:test/estop.test.ts'
SSE = 'archeus/api/sse.py'
CMD = 'archeus/core/application/commands.py'
GUI = 'archeus/cli/gui.py'
ROUTES = 'archeus/api/routes.py'
SCHEMAS = 'archeus/api/schemas.py'
TK = 'tests/v1/integration/test_stream_takeover.py::'
TKU = 'tests/v1/unit/test_stream_takeover_units.py::'
SH = 'tests/v1/integration/test_gui_shell.py::'

MUTATIONS = [
    # Slice A, item 83: execution-architecture §10 path 2
    ('Q01', 'the Core-less e-stop writes no sentinel', [(NODE,
     "        cls.engage_estop()\n        killed, gone = [], []\n",
     "        killed, gone = [], []\n")],
     [D + 'test_A02_the_sentinel_is_written_before_any_kill']),
    ('Q02', 'the sentinel is written after the kills', [(NODE,
     "        cls.engage_estop()\n        killed, gone = [], []\n",
     "        killed, gone = [], []\n"), (NODE,
     "        return killed, gone\n",
     "        cls.engage_estop()\n        return killed, gone\n")],
     [D + 'test_A02_the_sentinel_is_written_before_any_kill']),
    ('Q03', 'a process with an end line is killed too', [(NODE,
     "        for x in cls.unended():\n",
     "        for x in cls.registry():\n")],
     [D + 'test_A01_core_down_kills_exactly_the_live_registry_processes']),
    ('Q04', 'a reused pid is killed (create_time not checked)', [(NODE,
     "proc.kill_pid_tree(x.get('pid'), x.get('create_time'))",
     "proc.kill_pid_tree(x.get('pid'), proc.process_create_time(x.get('pid')))")],
     [D + 'test_A01_core_down_kills_exactly_the_live_registry_processes']),
    ('Q05', 'with Core down nothing is killed (the P19 placeholder)', [(MAIN,
     "        killed, _ = LocalNode.estop_without_core()\n",
     "        killed = []\n")],
     [D + 'test_A01_core_down_kills_exactly_the_live_registry_processes', G5]),
    ('Q06', 'a Core that answers and refuses is bypassed', [(MAIN,
     "            if e.code != 'network':\n",
     "            if False:\n")],
     [D + 'test_A04_a_core_that_answers_and_refuses_is_not_bypassed']),
    ('Q07', 'a Core that does not answer stops the e-stop', [(MAIN,
     "            if e.code != 'network':\n",
     "            if True:\n")],
     [D + 'test_A03_a_core_that_does_not_answer_is_stopped_without_it']),
    ('Q08', 'an unwritable sentinel reads as a stop', [(MAIN,
     "              file=sys.stderr)\n        return 2\n    print('emergency stop without Core",
     "              file=sys.stderr)\n        return 0\n    print('emergency stop without Core")],
     [D + 'test_A05_a_sentinel_that_cannot_be_written_is_a_failure_not_a_stop']),
    # Slice B, F7 and F8: Control → About's emergency stop (D3, D4)
    ('Q09', 'an unreachable Core is shown in its last-read state', [(CTRL,
     "  const armed = canCommand(conn.conn) ? health.data?.armed : undefined;",
     "  const armed = canCommand(conn.conn) || conn.gen >= 0 ? health.data?.armed : undefined;")],
     [AB + 'test_with_core_unreachable_the_state_is_not_guessed']),
    ('Q10', 'a disarmed Core is offered the Emergency stop', [(CTRL,
     "      {armed === true ? (", "      {armed !== undefined ? (")],
     [AB + 'test_armed_stop_then_disarmed_rearm_only_from_cores_answer']),
    ('Q11', "a re-arm is said without Core's armed answer", [(PRES,
     "    return out.armed\n      ? {", "    return true\n      ? {")],
     [ES_TS]),
    ('Q12', 'a failure inside Core reads as a refusal', [(UI,
     "ce.status >= 500 ? 'failed' : 'refused'", "'refused'")],
     [AB + 'test_a_refused_a_failed_and_an_unanswered_stop_claim_nothing']),
    ('Q13', "the stopped count is not Core's", [(PRES,
     "${out.stopped?.length ?? 0} execution(s)", "0 execution(s)")],
     [ES_TS]),
    ('Q14', 'a status line outlives the state it describes', [(CTRL,
     "said && (said.when === undefined || said.when === armed) ? said : null",
     "said ? said : null")],
     [AB + 'test_armed_stop_then_disarmed_rearm_only_from_cores_answer']),
    ('Q15', 'a refused or failed press says nothing', [(UI,
     "      if (report) report({ ok: false,", "      if (report) void ({ ok: false,")],
     [AB + 'test_a_refused_a_failed_and_an_unanswered_stop_claim_nothing']),
    ('Q16', 'an unreachable Core is given a state in words', [(PRES,
     "  if (armed === undefined)\n", "  if (false)\n")],
     [ES_TS]),
    ('Q17', 'no answer reads as a refusal', [(PRES,
     "  if (o.kind === 'network')\n", "  if (false)\n")],
     [ES_TS]),

    # Slice C, F4 (D2): at a device's stream cap the newest stream wins
    ('Q18', "a device's cap refuses again (item 112 back)", [(SSE,
     "            if len(mine) >= PER_DEVICE:\n"
     "                oldest = mine[0]                # `_open` is in opening order\n"
     "                self._open.remove(oldest)\n",
     "            if len(mine) >= PER_DEVICE:\n"
     "                raise TooManyStreams()\n")],
     [TK + 'test_two_reloads_leave_the_live_page_its_stream_at_once', TKU[:-2]]),
    ('Q19', 'the newest stream is closed instead of the oldest', [(SSE,
     "                oldest = mine[0]", "                oldest = mine[-1]")],
     [TK + 'test_the_newest_wins_the_oldest_closes_and_no_other_stream_is_touched',
      TKU + 'test_the_oldest_of_the_device_is_superseded_and_told_every_way']),
    ('Q20', "the pool's cap no longer refuses", [(SSE,
     "            elif len(self._open) >= MAX_STREAMS:\n", "            elif False:\n")],
     [TK + 'test_the_pools_cap_is_still_a_refusal_and_a_capped_device_still_takes_over']),
    ('Q21', "a capped device is refused at the pool's cap", [(SSE,
     "            oldest = None\n",
     "            oldest = None\n            if len(self._open) >= MAX_STREAMS:\n"
     "                raise TooManyStreams()\n")],
     [TK + 'test_the_pools_cap_is_still_a_refusal_and_a_capped_device_still_takes_over',
      TKU + 'test_the_pools_cap_refuses_a_new_device_but_not_a_capped_ones_takeover']),
    ('Q22', "another device's stream is taken over", [(SSE,
     "            mine = [s for s in self._open if s.device_id == device_id]\n",
     "            mine = list(self._open)\n")],
     [TK + 'test_the_newest_wins_the_oldest_closes_and_no_other_stream_is_touched',
      TKU + 'test_the_oldest_of_the_device_is_superseded_and_told_every_way']),
    ('Q23', 'the superseded stream is never flagged closing', [(SSE,
     "            oldest.closing.set()\n", "")],
     [TKU + 'test_the_oldest_of_the_device_is_superseded_and_told_every_way']),
    ('Q24', 'the superseded stream is not hung up', [(SSE,
     "            oldest.hangup()\n", "")],
     [TKU + 'test_the_oldest_of_the_device_is_superseded_and_told_every_way']),
    ('Q25', 'a takeover is recorded as a presence transition', [(SSE,
     "        return s, not mine\n", "        return s, True\n")],
     [TK + 'test_a_takeover_is_no_presence_transition']),
    ('Q33', 'a stream superseded before its 200 is cut mid-handshake', [(SSE,
     "            if oldest.started:", "            if True:")],
     [TKU + 'test_a_stream_superseded_before_its_200_is_not_cut_mid_handshake']),

    # Slice C, item 86 (D1): a new shell launch revokes the previous shell's credential
    ('Q26', 'a superseding redeem revokes nothing', [(CMD,
     "    if supersede is not None:\n        for r in", "    if False:\n        for r in")],
     [SH + 'test_a_new_shell_launch_revokes_the_previous_shells_credential',
      SH + 'test_a_crashed_shell_is_revoked_at_the_next_launch_across_a_core_restart',
      SH + 'test_concurrent_launches_leave_exactly_one_live_shell']),
    ('Q27', 'every active client is revoked, slot or not', [(CMD,
     "            if r.entity.supersede == supersede and r.entity.state == 'ACTIVE':\n",
     "            if r.entity.state == 'ACTIVE':\n")],
     [SH + 'test_an_ordinary_launch_code_supersedes_nothing_and_is_never_superseded']),
    ('Q28', 'the slot is not recorded on the client', [(CMD,
     "                        supersede=supersede,\n", "")],
     [SH + 'test_a_new_shell_launch_revokes_the_previous_shells_credential']),
    ('Q29', 'the shell does not ask for its slot', [(GUI,
     ",\n                                                     'supersede': SHELL_NAME})", "})")],
     [SH + 'test_a_new_shell_launch_revokes_the_previous_shells_credential']),
    ('Q30', "the launch code drops the minter's slot", [(ROUTES,
     "scopes, (req.body or {}).get('supersede'))", "scopes, None)")],
     [SH + 'test_a_new_shell_launch_revokes_the_previous_shells_credential']),
    ('Q31', 'a non-admin client mints a superseding code', [(ROUTES,
     "    Route('POST', '/v1/devices/launch/code', launch_code, 'admin',",
     "    Route('POST', '/v1/devices/launch/code', launch_code, 'control',")],
     [SH + 'test_only_admin_on_loopback_mints_a_superseding_code_and_only_for_the_shell']),
    ('Q32', 'the slot is free text', [(SCHEMAS,
     "    'supersede': {'type': 'string', 'nullable': True, 'enum': list(entities.SUPERSEDE_SLOTS)}},",
     "    'supersede': {'type': 'string', 'nullable': True}},")],
     [SH + 'test_only_admin_on_loopback_mints_a_superseding_code_and_only_for_the_shell']),
]

if __name__ == '__main__':
    mutate_p18.MUTATIONS = MUTATIONS
    sys.exit(mutate_p18.run(sys.argv[1:]))

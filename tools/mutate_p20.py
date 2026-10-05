"""The P20 mutation suite (p20-design-gate §4.1; D14's ids are provisional until
the user decides it). Slice A, item 83: the e-stop with Core down or not
answering (Q01-Q08); slice B, F7 and F8, Control → About's emergency stop
(Q09-Q17; an e2e-guarded mutant rebuilds the SPA).

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
]

if __name__ == '__main__':
    mutate_p18.MUTATIONS = MUTATIONS
    sys.exit(mutate_p18.run(sys.argv[1:]))

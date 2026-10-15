"""The P20 mutation suite (p20-design-gate §4.1; D14, decided by the user
2026-10-15). Slice A, item 83: the e-stop with Core down or not
answering (Q01-Q08); slice B, F7 and F8, Control → About's emergency stop
(Q09-Q17; an e2e-guarded mutant rebuilds the SPA); slice C, F4's stream
takeover (Q18-Q25, Q33) and item 86's one shell credential at a time (Q26-Q32);
slice D, F6's touch exit from the command bar (Q34-Q37); slice E, PV-10
(ADR-0049, D6): settings-source opt-ins, the inventory and the exit-code-2
deny (Q38-Q79; two e2e-guarded mutants rebuild the SPA); slice F, PV-22
(ADR-0052): tool removal, the CLI snapshot, the MCP deny and Skill (Q80-Q99);
slice I, the secrets gate (Q100-Q103); slice H, the breaker drills (D13) and
the two defects the fuzz harness found (D12) (Q104-Q110); H-F1, re-enabling
starts the counts afresh (Q111-Q112), and T-093's corrected secrets gate: a
secret written twice, a mode changed after the create (Q113-Q114); slice J,
D10's re-arm step-up from a paired client (Q115-Q117); T-094's review: the
gate tests and drills no mutant named, and the defects its stronger fuzz
corpus and oracle found (Q118-Q124); T-103's review: the static census's
sinks and the runtime secrets gate (Q125-Q128).

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
CMDBAR = 'clients/app/src/surfaces/CommandBar.tsx'
PAL = 'clients/app/src/state/palette.ts'
CC = 'tests/v1/e2e/test_spa_command_close.py::'
PAL_TS = 'node:test/palette.test.ts'
OPT = 'archeus/core/application/optins.py'
ENT = 'archeus/core/domain/entities.py'
SRC = 'archeus/harnesses/sources.py'
HOOK = 'archeus/harnesses/hook.py'
AGENT = 'archeus/harnesses/fake_agent.py'
CCA = 'archeus/harnesses/claude_code/adapter.py'
MGR = 'archeus/core/execution/manager.py'
EXE = 'archeus/core/application/executions.py'
MISSION = 'clients/app/src/surfaces/Mission.tsx'
SU = 'tests/v1/unit/test_settings_sources_units.py::'
PRS = 'tests/v1/integration/test_presence.py::'
SI = 'tests/v1/integration/test_settings_sources.py::'
G6 = 'tests/v1/judge/test_g06_security.py::'
API = 'tests/v1/unit/test_api_structure.py::test_the_route_table_is_exactly_the_p35b_to_p18_tables'
OPT_E2E = 'tests/v1/e2e/test_spa_opt_ins.py::'
PARITY_TS = 'node:test/parity.test.ts'
PARITY_PY = 'tests/v1/tui/test_parity.py'
TOOLS = 'archeus/harnesses/claude_code/tools.py'
FAKE = 'archeus/harnesses/fake.py'
FU = 'tests/v1/unit/test_tool_removal_units.py::'
FR = 'tests/v1/integration/test_tool_removal.py::'
G6F = G6 + 'test_a_tool_the_task_does_not_hold_never_runs_and_never_reaches_the_hook'
DISC = 'archeus/infra/discovery.py'
AUTH = 'archeus/api/auth.py'
AUTO = 'archeus/core/application/automations.py'
AUTHZ = 'archeus/core/application/authorization.py'
CANON = 'archeus/core/execution/canonical.py'
SEC = 'tests/v1/unit/test_p20_secrets.py::'
XI = 'tests/v1/integration/test_execution.py::'
PR = 'tests/v1/integration/test_presence.py::'
AU = 'tests/v1/integration/test_automation.py::'
FZ = 'tests/v1/integration/test_p20_fuzz.py::'
WRT = 'archeus/infra/db/writer.py'
KNOW = 'archeus/core/application/knowledge.py'
MATCH = 'archeus/core/automation/matcher.py'
AE = 'tests/v1/integration/test_api_errors.py::'
FREE = AE + 'test_a_bad_value_inside_a_free_form_field_is_a_400_not_a_500'
H04B = ('tests/v1/integration/test_policy_http.py::'
        'test_H04b_a_malformed_simulated_action_or_rule_is_a_400_not_a_500')
RTM = 'archeus/core/runtime.py'
RUN_LOCAL = ('tests/v1/integration/test_p20_secrets_runtime.py::'
             'test_no_minted_credential_is_at_rest_outside_its_one_home')

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

    # Slice D, F6 (D5): the command bar has a touch exit
    # (`hidden` on a `.btn` is not a mutant: `.btn`'s display overrides it)
    ('Q34', 'the Close button is not there', [(CMDBAR,
     '        <button type="button" className="btn secondary cmd-close" onClick={onClose}>\n'
     '          Close\n'
     '        </button>\n', '')],
     [CC + 'test_on_a_phone_close_and_a_backdrop_tap_each_close_the_bar_and_restore_focus']),
    ('Q35', 'Close closes nothing', [(CMDBAR,
     'className="btn secondary cmd-close" onClick={onClose}>',
     'className="btn secondary cmd-close" onClick={() => undefined}>')],
     [CC + 'test_on_a_phone_close_and_a_backdrop_tap_each_close_the_bar_and_restore_focus']),
    ('Q36', 'a backdrop tap closes nothing', [(CMDBAR,
     'if (e.target === e.currentTarget && onBackdrop(',
     'if (e.target === e.currentTarget && false && onBackdrop(')],
     [CC + 'test_on_a_phone_close_and_a_backdrop_tap_each_close_the_bar_and_restore_focus']),
    ('Q37', "a tap on the bar's own padding closes it", [(PAL,
     '  return x < box.left ||', '  return true || x < box.left ||')],
     [PAL_TS, CC + 'test_on_a_phone_close_and_a_backdrop_tap_each_close_the_bar_and_restore_focus']),

    # Slice E, PV-10 (ADR-0049, D6): the opt-in command and what applies
    ('Q38', 'a non-user principal opts a source in', [(OPT,
     "    if actor.kind != 'user_device':\n", "    if False:\n")],
     [SI + 'test_I04_only_a_user_device_may_and_only_for_a_real_owner_within_its_sources',
      G6 + 'test_only_a_user_device_opts_a_settings_source_in']),
    ('Q39', "another owner's opt-in applies", [(OPT,
     "for r in rows.where(conn, entities.OptIn, **{owner + '_id': oid})",
     "for r in rows.where(conn, entities.OptIn)")],
     [SI + 'test_I05_an_opt_in_applies_to_exactly_its_own_account_and_project']),
    ('Q40', 'an opted-out row still applies', [(OPT,
     "                if r.entity.opted_in]", "                if True]")],
     [SI + 'test_I05_an_opt_in_applies_to_exactly_its_own_account_and_project']),
    ('Q41', 'a change is not recorded as an event', [(OPT,
     "    tx.append(new_event('opt_in.changed',", "    (lambda e: e)(new_event('opt_in.changed',")],
     [SI + 'test_I01_an_account_opt_in_is_one_row_whose_version_counts_every_change']),
    ('Q42', 'an owner opts in a source it does not hold', [(ENT,
     "        if self.kind == 'source' and self.name not in SOURCE_OWNERS[self.owner]:",
     "        if self.kind == 'source' and self.name not in SOURCE_OWNERS['account'] + SOURCE_OWNERS['project']:")],
     [SU + 'test_E14_an_opt_in_has_one_owner_its_own_sources_and_never_a_path',
      SI + 'test_I04_only_a_user_device_may_and_only_for_a_real_owner_within_its_sources']),
    ('Q43', 'an opt-in name may be a path', [(ENT,
     "        if not _OPT_IN_NAME.fullmatch(self.name) or '..' in self.name:",
     "        if not self.name:")],
     [SU + 'test_E14_an_opt_in_has_one_owner_its_own_sources_and_never_a_path']),
    ('Q44', 'a control-scope client writes an opt-in', [(ROUTES,
     "    Route('POST', '/v1/opt-ins', set_opt_in, 'admin',",
     "    Route('POST', '/v1/opt-ins', set_opt_in, 'control',")],
     [SI + 'test_H01_opt_ins_are_admin_written_and_observe_read', API]),
    # the flags
    ('Q45', 'no --setting-sources when nothing is opted in (the CLI loads every source)', [(SRC,
     "    a = ['--setting-sources', ','.join(flags['setting_sources']), '--strict-mcp-config']",
     "    a = (['--setting-sources', ','.join(flags['setting_sources'])] if flags['setting_sources'] else []) + ['--strict-mcp-config']")],
     [SU + 'test_E02_the_argv_always_names_the_sources_even_when_none',
      SI + 'test_I06_an_execution_records_its_inventory_and_is_given_exactly_its_flags']),
    ('Q46', 'no --strict-mcp-config', [(SRC,
     "    a = ['--setting-sources', ','.join(flags['setting_sources']), '--strict-mcp-config']",
     "    a = ['--setting-sources', ','.join(flags['setting_sources'])]")],
     [SU + 'test_E02_the_argv_always_names_the_sources_even_when_none']),
    ('Q47', 'every source is loaded', [(SRC,
     "    flags = {'setting_sources': [s for s in SOURCES if s in opted_sources or s in recorded_only],",
     "    flags = {'setting_sources': list(SOURCES),")],
     [SU + 'test_E01_with_nothing_opted_in_every_source_is_excluded',
      G6 + 'test_an_execution_records_its_settings_sources_and_excludes_them_by_default']),
    ('Q48', 'skills are never disabled', [(SRC,
     "    if flags['disable_slash_commands']:\n", "    if False:\n")],
     [SU + 'test_E02_the_argv_always_names_the_sources_even_when_none']),
    ('Q49', 'any opt-in enables every skill', [(SRC,
     "    skill_in = any(status(src) != 'excluded' for src, _s in found) or dir_skills",
     "    skill_in = bool(opt_ins) or dir_skills")],
     [SU + 'test_E09_skills_stay_disabled_unless_a_skill_is_opted_in']),
    ('Q50', "a project's opt-in passes the account's server of that name", [(SRC,
     "            on = (owner, n) in opted_mcp\n",
     "            on = n in {m for _o, m in opted_mcp}\n")],
     [SU + 'test_E06_strict_mcp_passes_only_the_opted_in_server_of_its_own_owner']),
    ('Q51', 'every MCP server definition reaches --mcp-config', [(SRC,
     "        got = ((d or {}).get('mcpServers') or {}).get(s['name'])\n"
     "        if isinstance(got, dict) and s['name'] not in out:\n"
     "            out[s['name']] = got\n",
     "        for k, got in ((d or {}).get('mcpServers') or {}).items():\n"
     "            out.setdefault(k, got)\n")],
     [SU + 'test_E06_strict_mcp_passes_only_the_opted_in_server_of_its_own_owner',
      SI + 'test_I07_the_owners_opt_ins_reach_the_spawn_and_no_one_elses']),
    ('Q52', "a plugin directory outside the home's plugins is loaded", [(SRC,
     "        if isinstance(p, str) and os.path.isdir(p) and _inside(p, root):",
     "        if isinstance(p, str) and os.path.isdir(p):")],
     [SU + 'test_E08_a_plugin_that_resolves_outside_the_homes_plugins_is_not_loaded']),
    ('Q53', "a settings file's env reaches the inventory", [(SRC,
     "    plugins = d.get('enabledPlugins')\n",
     "    out += [('env', '%s=%s' % kv) for kv in sorted((d.get('env') or {}).items())]\n"
     "    plugins = d.get('enabledPlugins')\n")],
     [SU + 'test_E11_no_secret_reaches_the_record',
      SI + 'test_I08_the_stored_inventory_carries_no_secret']),
    # the record
    ('Q54', 'the inventory is stored unredacted', [(MGR,
     "                data = redact(json.dumps(got, sort_keys=True)).encode('utf-8')",
     "                data = json.dumps(got, sort_keys=True).encode('utf-8')")],
     [SI + 'test_I08_the_stored_inventory_carries_no_secret']),
    ('Q55', 'the spawn is not given the recorded flags', [(MGR,
     "                spec = replace(spec, inventory=json.loads(data))\n", "")],
     [SI + 'test_I07_the_owners_opt_ins_reach_the_spawn_and_no_one_elses']),
    ('Q56', 'an inventory that cannot be taken still spawns', [(MGR,
     "        except Exception as err:\n"
     "            self._do(X.refuse, execution_id=e.id, stop_reason='workspace',\n"
     "                     reason='the settings sources could not be inventoried: %s'\n"
     "                     % type(err).__name__)\n"
     "            return True\n",
     "        except Exception as err:\n"
     "            pass\n")],
     [SI + 'test_I09_an_inventory_that_cannot_be_taken_starts_nothing']),
    ('Q67', 'an inventory failure is uncharged (the task is re-dispatched every tick)', [(MGR,
     "            self._do(X.refuse, execution_id=e.id, stop_reason='workspace',\n"
     "                     reason='the settings sources could not be inventoried",
     "            self._do(X.refuse, execution_id=e.id, stop_reason='binding',\n"
     "                     reason='the settings sources could not be inventoried")],
     [SI + 'test_I09_an_inventory_that_cannot_be_taken_starts_nothing']),
    ('Q57', 'the execution does not reference its inventory', [(EXE,
     "                                         'inventory_sha256': inventory_sha256},",
     "                                         'inventory_sha256': None},")],
     [SI + 'test_I06_an_execution_records_its_inventory_and_is_given_exactly_its_flags',
      G6 + 'test_an_execution_records_its_settings_sources_and_excludes_them_by_default']),
    ('Q58', 'the execution read leaves the inventory out', [(EXE,
     "    out['inventory'] = inventory(row.entity.inventory_sha256)\n",
     "    out['inventory'] = None\n")],
     [SI + 'test_I06_an_execution_records_its_inventory_and_is_given_exactly_its_flags']),
    # the deny form, and every way the hook could let a call through
    ('Q59', 'a deny is JSON at exit 0 again', [(HOOK,
     "        return '', reason or 'denied by Archeus', DENY_EXIT",
     "        return json.dumps({'hookSpecificOutput': {'hookEventName': 'PreToolUse', "
     "'permissionDecision': 'deny', 'permissionDecisionReason': reason}}), '', 0")],
     [SU + 'test_E16_a_deny_is_exit_code_2_with_the_reason_on_stderr',
      SI + 'test_I10_a_deny_reaches_the_agent_as_the_exit_code_2_block']),
    ('Q60', 'a failing hook exits with another code', [(HOOK,
     "    if code in (0, DENY_EXIT):", "    if code is not None:")],
     [SU + 'test_E18_a_hook_crash_halts_and_never_exits_with_another_code']),
    ('Q61', "the interpreter's own exit flush decides the code", [(HOOK,
     "    os._exit(code)", "    sys.exit(code)")],
     [SU + 'test_E22_a_hook_that_cannot_write_its_answer_still_exits_with_the_deny']),
    ('Q62', "Claude Code's timeout is shorter than the hook's own deadline", [(CCA,
     "HOOK_TIMEOUT_S = 120", "HOOK_TIMEOUT_S = 30")],
     [SU + 'test_E19_a_core_that_never_answers_is_a_halt_before_claude_codes_own_timeout']),
    ('Q63', 'the fake agent halts on a failing hook (a fail-open hook goes unseen)', [(AGENT,
     "    if r.returncode != 0:\n        return 'proceed',",
     "    if r.returncode != 0:\n        return 'halt',")],
     [SU + 'test_E20_the_fake_agent_lets_a_failing_hook_through_as_claude_code_would']),
    # the read-only surfaces
    ('Q64', 'the inventory says skills are disabled when they are not', [(PRES,
     "    ['Skills', f.disable_slash_commands ? 'disabled' : 'enabled: a skill is opted in'],",
     "    ['Skills', 'disabled'],")],
     [PARITY_TS]),
    ('Q65', "an execution's inspector does not show what it inherited", [(MISSION,
     "            <InventoryBlock x={x} />\n", "            {false && <InventoryBlock x={x} />}\n")],
     [OPT_E2E + 'test_an_execution_shows_what_it_inherited_beside_its_why']),
    ('Q66', 'an opt-out is listed as opted in', [(CTRL,
     "<td>{x.opted_in ? 'opted in' : 'opted out'}</td>", "<td>{'opted in'}</td>")],
     [OPT_E2E + 'test_the_opt_ins_are_listed_read_only_and_follow_core']),
    # P20 slice E closeout (O4, O5): the halt's deny and the inventory's rule,
    # both from PV-19 against the real CLI
    ('Q68', 'a halt lets the call it answers through (the CLI runs it first)', [(HOOK,
     "                'hookSpecificOutput': {'hookEventName': 'PreToolUse',\n"
     "                                       'permissionDecision': 'deny',",
     "                'hookSpecificOutput': {'hookEventName': 'PreToolUse',\n"
     "                                       'permissionDecision': 'allow',")],
     [SU + 'test_E17_allow_and_halt_keep_their_json_at_exit_0',
      SU + 'test_E18_a_hook_crash_halts_and_never_exits_with_another_code']),
    ('Q69', 'the fake agent blocks on continue: false alone (a halt without its deny goes unseen)',
     [(AGENT,
       "        if spec.get('permissionDecision') == 'deny':\n            return 'halt',",
       "        if True:\n            return 'halt',")],
     [SU + 'test_E23_the_fake_agent_halts_as_claude_code_does']),
    ('Q70', 'a CLAUDE.md is recorded loaded whatever its source', [(SRC,
     "        add(src, 'claude_md', label, status(src),",
     "        add(src, 'claude_md', label, 'not_excludable',")],
     [SU + 'test_E01_with_nothing_opted_in_every_source_is_excluded',
      SU + 'test_E03_managed_settings_always_apply_and_claude_md_follows_its_source']),
    ('Q71', "an excluded source's skills are recorded loaded once slash commands are on", [(SRC,
     "        add(src, 'skill', s, status(src))",
     "        add(src, 'skill', s, 'not_excludable' if skill_in and status(src) == 'excluded'"
     " else status(src))")],
     [SU + 'test_E07_a_plugin_is_loaded_by_its_own_directory_and_carries_its_skills',
      SU + 'test_E09_skills_stay_disabled_unless_a_skill_is_opted_in']),
    ('Q72', "the CLI's built-in plugins are silently omitted", [(SRC,
     "    add('cli', 'plugin', 'built-in plugins', 'builtin')\n", "")],
     [SU + 'test_E01_with_nothing_opted_in_every_source_is_excluded']),
    ('Q73', 'the bundled skills are recorded loaded under --disable-slash-commands', [(SRC,
     "'builtin' if skill_in else 'excluded')", "'builtin')")],
     [SU + 'test_E01_with_nothing_opted_in_every_source_is_excluded']),
    ('Q74', "an ancestor's CLAUDE.local.md is recorded under project", [(SRC,
     "            out.append((src, os.path.join(cur, rel), os.path.join(cur, rel)))",
     "            out.append(('project', os.path.join(cur, rel), os.path.join(cur, rel)))")],
     [SU + 'test_E24_every_claude_md_follows_its_setting_source_ancestors_too']),
    ('Q75', "a plugin's manifest hooks are not recorded", [(SRC,
     "        if isinstance(man.get('hooks'), dict):\n            hooks.append(",
     "        if False:\n            hooks.append(")],
     [SU + 'test_E25_what_a_plugin_brings_and_the_synced_skills_are_recorded']),
    ('Q76', "the skill paths a plugin's manifest declares are not read", [(SRC,
     "    for rel in [declared] if isinstance(declared, str) else declared or ():",
     "    for rel in ():")],
     [SU + 'test_E25_what_a_plugin_brings_and_the_synced_skills_are_recorded']),
    ('Q77', "the account's synced skills are not recorded", [(SRC,
     "            add('user', 'skill', s, status('user'), via='synced')",
     "            pass")],
     [SU + 'test_E25_what_a_plugin_brings_and_the_synced_skills_are_recorded']),
    ('Q78', "a plugin's MCP servers are recorded loaded under --strict-mcp-config", [(SRC,
     "            add(tag, 'mcp_server', m, 'excluded')",
     "            add(tag, 'mcp_server', m, st)")],
     [SU + 'test_E25_what_a_plugin_brings_and_the_synced_skills_are_recorded']),
    ('Q79', 'a plugin enabled by a source brings nothing into the record', [(SRC,
     "                elif type_ == 'plugin':\n                    plugin(src, name, status(src))",
     "                elif type_ == 'plugin':\n                    add(src, type_, name, status(src))")],
     [SU + 'test_E25_what_a_plugin_brings_and_the_synced_skills_are_recorded']),

    # Slice F, PV-22 (ADR-0052): tool removal beneath the hook; C1, C2, C3
    ('Q80', 'a mapping row is removed (exec)', [(TOOLS,
     "         'exec': ('Bash', 'PowerShell'),\n",
     "")],
     [FU + 'test_F01_every_set_of_action_classes_gets_exactly_its_mapped_offered_tools',
      FU + 'test_F10_every_action_class_and_every_canonicaliser_tool_has_a_mapping']),
    ('Q81', '--allowedTools is passed (it pre-approves)', [(TOOLS,
     "    deny = mcp_deny(inventory)\n",
     "    deny = mcp_deny(inventory)\n    a += ['--allowedTools', a[1]]\n")],
     [FU + 'test_F01_every_set_of_action_classes_gets_exactly_its_mapped_offered_tools',
      FU + 'test_F02_the_adapter_always_passes_tools_and_settings_and_never_allowed_tools']),
    ('Q82', 'nothing opted in, and no MCP tool is denied', [(TOOLS,
     "        return ['mcp__*']",
     "        return []")],
     [FU + 'test_F04_nothing_opted_in_denies_every_mcp_tool',
      FR + 'test_R01_a_removed_tool_never_runs_and_never_reaches_the_hook', G6F]),
    ('Q83', 'no --settings (the hook is not installed)', [(CCA,
     "             '--settings', self._settings(spec)]",
     "             ]")],
     [FU + 'test_F02_the_adapter_always_passes_tools_and_settings_and_never_allowed_tools',
      SU + 'test_E21_claude_code_is_spawned_with_the_flags_of_its_recorded_inventory']),
    ('Q84', 'an empty --tools is left out (the CLI would offer every tool)', [(TOOLS,
     "    a = ['--tools', ','.join(allowed(action_classes, skill=not flags['disable_slash_commands']))]",
     "    names = allowed(action_classes, skill=not flags['disable_slash_commands'])\n"
     "    a = ['--tools', ','.join(names)] if names else []")],
     [FU + 'test_F03_a_task_with_no_mapped_class_is_given_an_empty_tools_never_none']),
    ('Q85', 'an excluded tool is mapped (Task under read)', [(TOOLS,
     "TOOLS = {'read': ('Read', 'Glob', 'Grep', 'LS'),",
     "TOOLS = {'read': ('Read', 'Glob', 'Grep', 'LS', 'Task'),")],
     [FU + 'test_F11_every_offered_tool_is_mapped_or_excluded_and_the_snapshot_says_what_is_not_offered']),
    ('Q86', 'Skill is always allowed', [(TOOLS,
     "    return names + [SKILL] if skill else names",
     "    return names + [SKILL]")],
     [FU + 'test_F08_skill_is_allowed_exactly_when_an_opted_in_source_brings_a_skill',
      FR + 'test_R05_skill_exists_exactly_when_an_opted_in_source_brings_a_skill']),
    ('Q87', 'Skill is never allowed, so an opted-in skill cannot be used', [(TOOLS,
     "    return names + [SKILL] if skill else names",
     "    return names")],
     [FU + 'test_F08_skill_is_allowed_exactly_when_an_opted_in_source_brings_a_skill',
      FR + 'test_R05_skill_exists_exactly_when_an_opted_in_source_brings_a_skill']),
    ('Q88', 'Skill follows the opposite of the slash-commands flag', [(TOOLS,
     "skill=not flags['disable_slash_commands']",
     "skill=flags['disable_slash_commands']")],
     [FU + 'test_F08_skill_is_allowed_exactly_when_an_opted_in_source_brings_a_skill']),
    ('Q89', 'an MCP deny uses the raw server name (matches nothing in Claude Code)', [(TOOLS,
     "    return re.sub(r'[^A-Za-z0-9_-]', '_', server)",
     "    return server")],
     [FU + 'test_F06_a_deny_names_a_server_as_claude_code_names_its_tools',
      FR + 'test_R03_an_opted_in_mcp_server_stays_usable_and_the_excluded_are_denied_by_name']),
    ('Q90', 'a colliding excluded server is denied, taking the opted-in one with it', [(TOOLS,
     "                   and mcp_name(i['name']) not in opted})",
     "                   })")],
     [FU + 'test_F07_an_excluded_server_that_collides_with_an_opted_in_one_is_not_denied',
      FR + 'test_R04_an_excluded_server_whose_name_collides_with_the_opted_in_one_is_not_denied']),
    ('Q91', 'mcp__* is denied even with a server opted in', [(TOOLS,
     "    if not opted:\n        return ['mcp__*']",
     "    if True:\n        return ['mcp__*']")],
     [FU + 'test_F05_with_an_opt_in_each_named_excluded_server_is_denied_and_the_opted_in_never',
      FR + 'test_R03_an_opted_in_mcp_server_stays_usable_and_the_excluded_are_denied_by_name']),
    ('Q92', "a plugin's MCP server is denied by a name Claude Code was never seen to give it", [(TOOLS,
     "                   and i.get('source') in ('user', 'project')\n",
     "")],
     [FU + 'test_F05_with_an_opt_in_each_named_excluded_server_is_denied_and_the_opted_in_never']),
    ('Q93', 'a mapped name the CLI does not offer reaches --tools (LS, MultiEdit)', [(TOOLS,
     " for t in tools if t in have]",
     " for t in tools]")],
     [FU + 'test_F01_every_set_of_action_classes_gets_exactly_its_mapped_offered_tools',
      FU + 'test_F02_the_adapter_always_passes_tools_and_settings_and_never_allowed_tools']),
    ('Q94', 'the fake agent runs a tool absent from --tools', [(AGENT,
     "    return '--tools' not in flags or name in _names(flags['--tools'])",
     "    return True")],
     [FU + 'test_F12_the_fake_agent_never_runs_a_tool_absent_from_tools',
      FR + 'test_R01_a_removed_tool_never_runs_and_never_reaches_the_hook', G6F]),
    ('Q95', 'the fake agent ignores --disallowedTools', [(AGENT,
     "                p.count('__') == 1 and p.startswith('mcp__') and name.startswith(p + '__')):\n"
     "            return False",
     "                p.count('__') == 1 and p.startswith('mcp__') and name.startswith(p + '__')):\n"
     "            pass")],
     [FU + 'test_F13_the_fake_agent_loads_only_strict_mcp_servers_and_honours_each_deny',
      FR + 'test_R03_an_opted_in_mcp_server_stays_usable_and_the_excluded_are_denied_by_name']),
    ('Q96', 'the fake agent offers an MCP server --strict-mcp-config did not load', [(AGENT,
     "        return _server(name) in loaded",
     "        return True")],
     [FU + 'test_F13_the_fake_agent_loads_only_strict_mcp_servers_and_honours_each_deny']),
    ('Q97', 'the Claude Code adapter passes no tool flags', [(CCA,
     "        a += tools.tool_argv(spec.task_contract.get('action_classes') or (), spec.inventory)\n",
     "")],
     [FU + 'test_F02_the_adapter_always_passes_tools_and_settings_and_never_allowed_tools',
      FU + 'test_F03_a_task_with_no_mapped_class_is_given_an_empty_tools_never_none']),
    ('Q98', 'the fake harness standing in for tool removal passes no tool flags', [(FAKE,
     "        if self._tools:",
     "        if False:")],
     [FR + 'test_R01_a_removed_tool_never_runs_and_never_reaches_the_hook', G6F]),
    ('Q99', "the snapshot stops recording LS as mapped but not offered", [(TOOLS,
     "    'mapped_not_offered': ('LS', 'MultiEdit'),",
     "    'mapped_not_offered': ('MultiEdit',),")],
     [FU + 'test_F11_every_offered_tool_is_mapped_or_excluded_and_the_snapshot_says_what_is_not_offered']),
    # Slice I: the secrets review's gate (D7)
    ('Q100', 'the local token file is not created exclusively', [(DISC,
     "os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)",
     "os.open(path, os.O_CREAT | os.O_WRONLY, 0o600)")],
     [SEC + 'test_the_local_token_file_is_created_exclusively_with_a_posix_owner_only_mode']),
    ('Q101', 'the local token file is readable by others', [(DISC,
     "os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)",
     "os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)")],
     [SEC + 'test_the_local_token_file_is_created_exclusively_with_a_posix_owner_only_mode']),
    ('Q102', 'a step-up PIN record is cheap to brute-force', [(CMD,
     "PIN_ITERATIONS = 200_000",
     "PIN_ITERATIONS = 1_000")],
     [SEC + 'test_a_step_up_pin_is_kept_only_as_a_pbkdf2_record']),
    ('Q103', 'a secret is drawn somewhere the table does not name', [(MGR,
     "'hook_' + secrets.token_urlsafe(32)",
     "'hook_' + secrets.token_hex(32)")],
     [SEC + 'test_every_source_in_archeus_is_in_the_secrets_table_with_its_count']),
    # Slice H, D13: each breaker tripped and its recovery observed
    ('Q104', 'the breaker counts every failure, not only resource and auth', [(EXE,
     "and x.entity.failure in ('resource', 'auth') and x.entity.ended_at]",
     "and x.entity.ended_at]")],
     [XI + 'test_D13_the_execution_breaker_trips_opens_cools_and_recovers']),
    ('Q105', 'an OPEN account never cools down', [(EXE,
     "elif a.health == 'OPEN' and now - since >= COOLDOWN_S:",
     "elif False:")],
     [XI + 'test_D13_the_execution_breaker_trips_opens_cools_and_recovers']),
    ('Q106', 'a successful probe does not recover a DEGRADED account', [(EXE,
     "elif a.health == 'DEGRADED' and beat and any(t > since for t in oks):",
     "elif False:")],
     [XI + 'test_D13_the_execution_breaker_trips_opens_cools_and_recovers']),
    ('Q107', 'a right PIN does not reset the wrong-PIN count', [(AUTH,
     "            self._n.pop(device_id, None)\n",
     "            pass\n")],
     [PR + 'test_D13_the_pin_breaker_resets_on_a_right_pin_and_a_new_pairing_recovers']),
    ('Q108', 'a suspended automation cannot be re-enabled', [(AUTO,
     "'user_reenables' if row.entity.state == 'SUSPENDED'",
     "'enable_within_policy' if row.entity.state == 'SUSPENDED'")],
     [AU + 'test_D13_a_reenabled_automation_fires_again']),
    # Slice H, D12: what the fuzz harness found
    ('Q109', "a simulated action or rule built from a malformed dict is a 500", [(AUTHZ,
     "    except TypeError as e:",
     "    except KeyError as e:")],
     ['tests/v1/integration/test_policy_http.py::'
      'test_H04b_a_malformed_simulated_action_or_rule_is_a_400_not_a_500',
      FZ + 'test_no_fuzzed_command_body_is_a_500']),
    ('Q110', 'a path the OS cannot resolve raises out of the canonicaliser', [(CANON,
     "    except (OSError, ValueError):",
     "    except KeyError:")],
     ['tests/v1/unit/test_execution_units.py::'
      'test_a_path_the_os_cannot_resolve_is_unclassified_not_an_error',
      FZ + 'test_the_canonicaliser_answers_every_fuzzed_call_conservatively']),
    # H-F1 (the owner, 2026-10-15): re-enabling starts the counts afresh
    ('Q111', 'the loop guard counts the runs from before the re-enable', [(AUTO,
     "    recent = [(r.state, r.reason_code) for r in _armed_window(tx, a)]",
     "    recent = [(r.entity.state, r.entity.reason_code) for r in tx.where("
     "entities.AutomationRun, automation_id=a.id)]")],
     [AU + 'test_D13_a_reenabled_automation_fires_again']),
    ('Q112', 'the rate limit counts the missions from before the re-enable', [(AUTO,
     "    made = sum(1 for r in _armed_window(tx, a) if r.state in _CREATED)",
     "    made = sum(1 for r in tx.where(entities.AutomationRun, automation_id=a.id)"
     " if r.entity.state in _CREATED)")],
     [AU + 'test_H_F1_a_rate_limited_automation_reenabled_within_the_hour_fires']),
    # T-093's corrected secrets gate: writers, not draw sites
    ('Q113', 'the local token is also written to a second file', [(DISC,
     "        f.write(token)\n",
     "        f.write(token)\n    open(path + '.bak', 'w').write(token)\n")],
     [SEC + 'test_every_secret_write_in_archeus_is_in_the_writers_table']),
    ('Q114', "the local token's mode is changed after its exclusive create", [(DISC,
     "        f.write(token)\n",
     "        f.write(token)\n    os.chmod(path, 0o644)\n")],
     [SEC + 'test_no_code_in_archeus_changes_a_files_mode']),
    # Slice J, D10 (V2-3 resolved 2026-10-15: paired devices only)
    ('Q115', 'a paired client re-arms without its PIN', [(EXE,
     "    if not authorization._step_up_valid(tx, actor, step_up):",
     "    if False:")],
     [PRS + 'test_J01_a_paired_client_re_arms_only_with_its_pin',
      PRS + 'test_J02_a_paired_client_without_a_pin_cannot_re_arm_and_the_desktop_can']),
    ('Q116', "the re-arm route drops the client's proof", [(ROUTES,
     "        out = req.run(req.api.executions.rearm, {'step_up': proof})",
     "        out = req.run(req.api.executions.rearm, {'step_up': None})")],
     [PRS + 'test_J01_a_paired_client_re_arms_only_with_its_pin']),
    ('Q117', 'a wrong re-arm PIN is not counted toward the revocation', [(ROUTES,
     "        if proof is not None and 'step-up' in e.result.reason:\n"
     "            _step_up_failed(req)",
     "        if proof is not None and 'step-up' in e.result.reason:\n"
     "            pass")],
     [PRS + 'test_J03_five_wrong_re_arm_pins_revoke_the_client_as_an_approvals_would']),
    # T-094's review: the gate tests and drills no Q mutant named, and its fixes
    ('Q118', 'the CLI draws a secret where it drew an idempotency key', [(MAIN,
     "    body = {'headless': headless, 'idempotency_key': os.urandom(16).hex()}",
     "    body = {'headless': headless, 'idempotency_key': secrets.token_hex(16)}")],
     [SEC + 'test_the_cli_draws_only_idempotency_keys_and_request_ids']),
    ('Q119', 'a credential row can be inserted with its plaintext token', [(WRT,
     "    def insert_token(self, *, token_hash, kind, principal_id, scopes, actor, expires_at=None):",
     "    def insert_token(self, *, token_hash, kind, principal_id, scopes, actor, expires_at=None,"
     " token=None):")],
     [SEC + 'test_device_and_hook_credentials_are_stored_as_hashes_only']),
    # the kill has no enforcement branch, and the e-stop reaches it twice (the
    # command's stop and the manager's disarmed check): this mutant takes the
    # one place both meet, named by E24 (hooked) and the registry-only drill
    ('Q120', 'a stopping execution under the e-stop waits out the grace before its kill', [(MGR,
     "        if state == 'STOPPING' and (disarmed or e.stop_reason in _NOW",
     "        if state == 'STOPPING' and (False")],
     [XI + 'test_E24_the_estop_kills_everything_now_and_core_stays_disarmed_until_rearmed',
      XI + 'test_D13_the_estop_with_core_running_kills_a_registry_only_execution']),
    ('Q121', 'a simulated extra rule reaches the engine unchecked', [(AUTHZ,
     "        extra = [_simulated_rule(conn, i, r) for i, r in enumerate(extra_rules)]",
     "        extra = [R.rule(**dict(r, id=r.get('id') or 'simulated:%d' % i, source='user'))"
     " for i, r in enumerate(extra_rules)]")],
     [H04B, FZ + 'test_no_fuzzed_command_body_is_a_500']),
    ('Q122', 'a path tool with no usable path is classified on the workspace', [(CANON,
     "        if given and not _text(given[0]) or not given and tool not in OPTIONAL_PATH:",
     "        if False:")],
     ['tests/v1/unit/test_execution_units.py::'
      'test_an_input_missing_what_its_tool_needs_is_unclassified',
      FZ + 'test_the_canonicaliser_answers_every_fuzzed_call_conservatively']),
    ('Q123', "a forget selector's ids reach the database unchecked", [(KNOW,
     "                and all(isinstance(i, str) for i in selector['ids'])):",
     "                or True):")],
     [FREE]),
    ('Q124', "an automation trigger's type reaches the registry unchecked", [(MATCH,
     "    if not isinstance(t, str) or t not in types:",
     "    if t not in types:")],
     [FREE]),
    # T-103's review: the static census's sinks, and the runtime gate
    ('Q125', 'the local token is written again through the dotted atomic writer', [(DISC,
     "        f.write(token)\n",
     "        f.write(token)\n    config.write_json_atomic(path + '.json', {'t': token})\n")],
     [SEC + 'test_every_secret_write_in_archeus_is_in_the_writers_table']),
    ('Q126', 'the local token is logged to core.log', [(RTM,
     "        discovery.write_local_token(token)\n",
     "        discovery.write_local_token(token)\n        log.info('local token %s', token)\n")],
     [SEC + 'test_every_secret_write_in_archeus_is_in_the_writers_table', RUN_LOCAL]),
    ('Q127', "the local token's mode is changed through an aliased chmod", [(DISC,
     "        f.write(token)\n",
     "        f.write(token)\n    from os import chmod as ch\n    ch(path, 0o644)\n")],
     [SEC + 'test_no_code_in_archeus_changes_a_files_mode']),
    # a database row: a shape the static census cannot see, by construction
    ('Q128', "a launch-redeemed device's token is stored as its name", [(ROUTES,
     "        'name': (req.body.get('name') or '').strip() or 'browser (%s)' % req.body['platform'],",
     "        'name': token,")],
     [RUN_LOCAL]),
]

if __name__ == '__main__':
    mutate_p18.MUTATIONS = MUTATIONS
    sys.exit(mutate_p18.run(sys.argv[1:]))

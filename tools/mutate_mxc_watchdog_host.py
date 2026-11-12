"""The PV20 B13 mutation suite: break each property of the heartbeat channel, Core's sender
and proxy, the watchdog host and its entry point that tests/v1/unit/test_mxc_watchdog_host.py
holds, run the test written for it, and require it to fail.

    py tools/mutate_mxc_watchdog_host.py                 every mutation
    py tools/mutate_mxc_watchdog_host.py WH01 WH10       only these

It edits archeus/node/mxc_heartbeat.py, mxc_watchdog_host.py, mxc_watchdog.py and local.py, and
restores them whatever happens: run it with nothing else against the tree.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mutate_p18  # noqa: E402

HB = 'archeus/node/mxc_heartbeat.py'
HOST = 'archeus/node/mxc_watchdog_host.py'
WATCHDOG = 'archeus/node/mxc_watchdog.py'
LOCAL = 'archeus/node/local.py'
T = 'tests/v1/unit/test_mxc_watchdog_host.py::'

CLOSED = T + 'test_the_sender_and_the_proxy_are_closed_by_default'
HOST_CLOSED = T + 'test_the_host_is_closed_by_default'
TORN = T + 'test_a_line_still_being_written_waits_for_its_newline'
ONCE = T + 'test_the_channel_hands_each_message_over_once'
SHRANK = T + 'test_a_channel_that_shrank_or_vanished_is_a_fault'
VANISHED = T + 'test_a_channel_that_was_read_and_vanished_is_a_fault'
DAMAGED = T + 'test_a_damaged_line_is_never_guessed_past'
NEVER_WRITTEN = T + 'test_a_malformed_message_is_never_written'
MONOTONIC = T + 'test_heartbeats_climb_in_sequence_and_never_in_the_past'
CLOCK = T + 'test_a_clock_that_cannot_be_read_writes_no_heartbeat'
STALE = T + 'test_a_launch_is_refused_while_the_host_is_absent_stale_or_unreadable'
SHAPE = T + 'test_a_status_of_the_wrong_shape_is_unreadable'
ACTED = T + 'test_a_launch_is_refused_once_the_host_has_acted'
REPORT = T + 'test_the_report_is_the_hosts_and_only_armed_lets_a_launch_stand_down'
REFUSED = T + 'test_a_launch_the_host_refused_reads_back_uncertain'
SOLE = T + 'test_a_proxy_stands_down_only_from_a_sole_armed_job'
MALFORMED = T + 'test_a_malformed_job_is_refused_before_anything_is_written'
OTHER = T + 'test_a_registration_naming_another_process_than_the_ledger_is_refused'
FORGED = T + 'test_a_registration_with_no_journal_is_refused_and_never_killed'
AGAIN = T + 'test_the_kill_asks_the_ledger_again'
HUNG = T + 'test_a_hung_core_gets_the_sentinel_first_and_then_the_identity_checked_kill'
DEAD = T + 'test_a_dead_core_is_killed_for_without_a_sentinel'
ONE_SENTINEL = T + 'test_the_sentinel_is_engaged_once_for_every_job'
UNVERIFIED = T + 'test_a_sentinel_that_cannot_be_verified_never_withholds_the_kill'
UNCONFIRMED = T + 'test_a_kill_that_does_not_confirm_is_uncertain'
REUSED_CORE = T + 'test_a_core_pid_reused_by_another_process_is_a_dead_core'
MALFORMED_CORE = T + 'test_a_malformed_core_reading_is_uncertain_and_stops_core'
BEFORE = T + 'test_beats_from_before_the_watch_began_are_dropped_not_taken_for_a_fault'
REARM = T + 'test_a_stand_down_of_the_sole_job_retires_the_watch_and_the_next_job_rearms'
SHARED = T + 'test_a_stand_down_for_a_shared_or_other_job_is_ignored'
CHANNEL_FAULT = T + 'test_a_damaged_channel_is_uncertain_and_stops_core'
IDLE = T + 'test_an_idle_host_ends_when_core_is_gone_and_not_before'
STATUS = T + 'test_every_tick_publishes_the_status_the_proxy_reads'
RUN = T + 'test_run_ticks_until_the_watch_ends_and_never_after'
EXIT = T + 'test_the_entry_point_runs_the_host_to_the_end_of_its_watch'
NO_READERS = T + 'test_an_open_host_with_no_native_readers_still_refuses'
NODE = T + 'test_the_node_beats_once_per_sweep_and_only_with_a_sender'
ENDED = T + 'test_a_job_that_ended_still_has_its_ownership_record_for_the_kill'
BEAT_FAULT = T + 'test_a_failed_beat_is_the_sweeps_fault_not_a_silent_skip'

SENTINEL_GATE = '        if self._core_seen is True:'
ENGAGE_ONCE = '        if self.sentinel is None:'
CORE_STOP = '        self.core_stop = self._unstopped() or STOPPED'
STOP_CALL = '            self.terminate(self.core_pid, self.core_create_time)'
UNREAD = "            return 'stop not verified: %s' % type(err).__name__"
UNCERTAIN_GATE = '        if self.state() == mxc_watchdog.UNCERTAIN and self.core_stop != STOPPED:'
RETRY_GATE = '        if self.stop_attempts:\n            self.core_stop = self._unstopped()'
RETRY_CAP = '        if self.stop_attempts == MAX_STOP_ATTEMPTS:'
RETRY_CALL = ('        self.stop_attempts += 1\n        try:\n'
              '            self.terminate(self.core_pid, self.core_create_time)\n')
VERIFY_LAST = '        self.core_stop = self._unstopped() or STOPPED\n'
SENTINEL_FIRST = '        self._engage_sentinel()\n        if self.stop_attempts:'
DONE = '        return self.core_stop == STOPPED or (self.core_stop is None and self.core_gone) or ('
ROLLBACK_ORDER = T + 'test_a_rollback_engages_the_sentinel_then_stops_core_by_identity_then_verifies'
FAILED_STOP = T + 'test_a_failed_stop_keeps_supervision_active_and_reports_it'
LEFT_CORE = T + 'test_a_stop_that_leaves_core_running_is_reported_not_claimed'
LEFT_WORKLOAD = T + 'test_a_stop_that_leaves_an_owned_workload_running_is_reported_not_claimed'
RETRY_EXIT = T + 'test_core_that_exits_after_a_failed_first_attempt_is_verified_stopped_on_the_next_tick'
RETRY_FLAKY = T + 'test_a_verification_that_briefly_fails_is_read_again_on_the_next_tick'
RETRY_CAP_TEST = T + 'test_a_survivor_gets_two_more_identity_bound_attempts_then_a_persistent_failure'
RETRY_REUSE = T + 'test_a_pid_reused_between_the_retries_is_never_terminated'
CLAIMED = T + 'test_a_terminate_that_claims_success_does_not_make_the_stop_stopped'
ABSENT_NOTHING = T + 'test_a_core_already_gone_with_nothing_owned_is_stopped_whatever_terminate_says'
ABSENT_WORKLOAD = T + 'test_a_core_already_gone_with_a_workload_still_running_is_not_stopped'
UNREADABLE_BACK = T + 'test_a_stop_that_cannot_read_identities_back_is_not_reported_stopped'
KILL = "        return self.terminate(job['pid'], job['create_time']) is True"
OWNED = "        if invalid or [r['op'] for r in records[:2]] != OWNED_OPS:"

MUTATIONS = [
    ('WH01', 'the sender and the proxy open without the flag', [(HB,
     '    if (switches.heartbeat if switches is not None else HEARTBEAT_ENABLED) is not True:',
     '    if False:')], [CLOSED]),
    ('WH02', 'the heartbeat flag ships open', [(HB,
     'HEARTBEAT_ENABLED = False', 'HEARTBEAT_ENABLED = True')], [CLOSED]),
    ('WH03', 'the host flag ships open', [(HOST,
     'HOST_ENABLED = False', 'HOST_ENABLED = True')], [HOST_CLOSED]),
    ('WH04', 'an open host starts with no native readers', [(HOST,
     "    if bindings is None or enabled(bindings.get('switches'), 'host', HOST_ENABLED) is not True:",
     "    if enabled((bindings or {}).get('switches'), 'host', HOST_ENABLED) is not True:")], [NO_READERS]),
    ('WH05', 'a line still being written is read as a message', [(HB,
     "        data = data[:data.rfind(b'\\n') + 1]", '        data = data')], [TORN]),
    ('WH06', 'the reader forgets where it was', [(HB,
     '        self.offset += len(data)', '        pass')], [ONCE]),
    ('WH07', 'a channel that shrank is read from past its end', [(HB,
     '                if stream.tell() < self.offset:', '                if False:')], [SHRANK]),
    ('WH08', 'a channel that vanished after it was read is no messages', [(HB,
     '            if self.offset:', '            if False:')], [VANISHED]),
    ('WH09', 'a line of the wrong shape is accepted on read', [(HB,
     "                    or set(message) != KINDS[message['kind']]):", '                    ):')],
     [DAMAGED]),
    ('WH10', 'a message of the wrong shape is written', [(HB,
     "        if message.get('kind') not in KINDS or set(message) != KINDS[message['kind']]:",
     '        if False:')], [NEVER_WRITTEN]),
    ('WH11', 'a stepped clock makes a heartbeat older than the one before', [(HB,
     '            now = max(now, self.sent_at)', '            pass')], [MONOTONIC]),
    ('WH12', 'a heartbeat clock that cannot be read is written anyway', [(HB,
     '        if type(now) not in (int, float) or not math.isfinite(now):', '        if False:')],
     [CLOCK]),
    ('WH13', 'a stale host status is read as armed', [(HB,
     "        if not 0 <= self.clock() - status['at'] <= self.max_age_s:", '        if False:')],
     [STALE]),
    ('WH14', 'a status of an unknown state is read', [(HB,
     "                or status.get('state') not in mxc_watchdog.STATES + ('IDLE',)",
     '                or False')], [SHAPE]),
    ('WH15', 'a launch is registered with a host that already acted', [(HB,
     "        if status['state'] not in (mxc_watchdog.ARMED, 'IDLE', mxc_watchdog.STOOD_DOWN):",
     '        if False:')], [ACTED]),
    ('WH16', 'a host that holds no watch yet is read as armed', [(HB,
     "        if status['state'] == 'IDLE':", '        if False:')], [REPORT]),
    ('WH17', 'a registration the host refused is not the launch concern', [(HB,
     "        refused = sorted(self.registered & set(status['rejected']))", '        refused = []')],
     [REFUSED]),
    ('WH18', 'a launch stands the host down from a shared watch', [(HB,
     "        if report['state'] != mxc_watchdog.ARMED or len(report['recorded']) != 1:",
     '        if False:')], [SOLE]),
    ('WH19', 'a malformed job is registered', [(HB,
     '        problem = mxc_watchdog._job_problem(job)', '        problem = None')], [MALFORMED]),
    ('WH20', 'a registration naming another process than the ledger is watched', [(HOST,
     "        if (records[1]['pid'], records[1]['create_time']) != (pid, create_time):",
     '        if False:')], [OTHER]),
    ('WH21', 'a registration with no ownership record in the ledger is watched', [(HOST,
     OWNED, '        if False:')], [FORGED]),
    ('WH22', 'the kill trusts the registration without asking the ledger again', [(HOST,
     '            raise ValueError(problem)', '            pass')], [AGAIN]),
    ('WH23', 'a hung Core is killed for with no sentinel', [(HOST,
     SENTINEL_GATE, '        if False:')], [HUNG]),
    ('WH24', 'a dead Core gets the sentinel too', [(HOST,
     SENTINEL_GATE, '        if True:')], [DEAD]),
    ('WH25', 'the sentinel is engaged again for every job', [(HOST,
     ENGAGE_ONCE, '        if True:')], [ONE_SENTINEL]),
    ('WH26', 'a sentinel that fails stops the kill', [(HOST,
     '                engaged = False', '                raise')], [UNVERIFIED]),
    ('WH27', 'a sentinel that reads back false is recorded engaged', [(HOST,
     '                engaged = self.engage_sentinel() is True',
     '                engaged = self.engage_sentinel() is not None')], [UNVERIFIED]),
    ('WH28', 'a kill that did not confirm is taken as done', [(HOST,
     KILL, "        return self.terminate(job['pid'], job['create_time']) is not None")],
     [UNCONFIRMED]),
    ('WH29', 'the kill names the pid alone', [(HOST,
     KILL, "        return self.terminate(job['pid'], None) is True")], [HUNG]),
    ('WH30', 'a reused Core pid is the Core', [(HOST,
     '        return current == create_time',
     '        return current is not None')], [REUSED_CORE]),
    ('WH31', 'an unreadable Core identity is read as a dead Core', [(HOST,
     '        if current is not None and (type(current) is not int or current <= 0):',
     '        if False:')], [MALFORMED_CORE]),
    ('WH32', 'a beat from before the watch began reaches the watchdog', [(HOST,
     "        if self.dog is not None and message['sent_at'] >= self.dog.armed_at:",
     '        if self.dog is not None:')], [BEFORE]),
    ('WH33', 'a stood down watch is never re-armed', [(HOST,
     '            if self.dog is None or self.dog.state is mxc_watchdog.STOOD_DOWN:',
     '            if self.dog is None:')], [REARM]),
    ('WH34', 'a stand-down of another job stands the watch down', [(HOST,
     "                and self.dog.report()['recorded'] == [message['execution_id']]):",
     '                ):')], [SHARED]),
    ('WH35', 'a damaged channel is swallowed and the watch goes on', [(HOST,
     "            self.fault = 'channel read failed: %s' % type(err).__name__", '            pass')],
     [CHANNEL_FAULT]),
    ('WH36', 'the watchdog reads a damaged channel as quiet', [(HOST,
     '            raise ValueError(self.fault)', '            pass')], [CHANNEL_FAULT]),
    ('WH37', 'an idle host outlives Core', [(HOST,
     '        self.core_gone = alive is False', '        self.core_gone = False')], [IDLE]),
    ('WH38', 'a failed stop of Core ends the host', [(HOST,
     DONE, '        return True or (')],
     [FAILED_STOP, MALFORMED_CORE]),
    ('WH39', 'the status is never published', [(HOST,
     '        self.channel.write_status(self.report())', '        pass')], [STATUS]),
    ('WH40', 'the loop does not wait between ticks', [(HOST,
     '            sleep(poll_s)', '            sleep(0)')], [RUN]),
    ('WH41', 'an uncertain watch exits as a success', [(HOST,
     "    return 0 if report['state'] in (mxc_watchdog.FIRED, mxc_watchdog.STOOD_DOWN, IDLE) else 3",
     '    return 0')], [EXIT]),
    ('WH42', 'the node never beats', [(LOCAL,
     '            self.heartbeat.beat()', '            pass')], [NODE]),
    ('WH43', 'the node beats with no sender', [(LOCAL,
     '        if self.heartbeat is not None:', '        if True:')], [NODE]),
    ('WH44', 'a beat that failed is skipped and the sweep goes on', [(LOCAL,
     '            self.heartbeat.beat()', '            self.heartbeat and None')], [BEAT_FAULT]),
    ('WH45', 'a job whose journal moved on loses its kill', [(HOST,
     OWNED, "        if invalid or [r['op'] for r in records] != OWNED_OPS:")], [ENDED]),
    ('WH46', 'a clock stepped back under the last beat leaves the watch armed', [(WATCHDOG,
     '        if not _number(now) or now < self.last_clock:',
     '        if not _number(now) or now < self.armed_at:')],
     ['tests/v1/unit/test_gaps2_node_mxc_watchdog.py::'
      'test_a_clock_rewound_below_the_last_beat_is_not_a_quiet_forever']),
    ('WH47', 'the stop engages the sentinel after terminating Core', [(HOST,
     SENTINEL_FIRST, '        if self.stop_attempts:'),
     (HOST, RETRY_CALL + "        except Exception:\n            pass\n",
      RETRY_CALL + "        except Exception:\n            pass\n        self._engage_sentinel()\n")],
     [ROLLBACK_ORDER]),
    ('WH48', 'the stop does not terminate Core', [(HOST,
     STOP_CALL, '            None')], [ROLLBACK_ORDER, FAILED_STOP]),
    ('WH49', 'the stop is not verified', [(HOST,
     CORE_STOP, '        self.core_stop = STOPPED')],
     [LEFT_CORE, LEFT_WORKLOAD, ABSENT_WORKLOAD]),
    ('WH50', 'a stop that cannot read identities back is reported as stopped', [(HOST,
     UNREAD, '            return None')], [UNREADABLE_BACK]),
    ('WH51', 'a failed stop is never tried again', [(HOST,
     UNCERTAIN_GATE, '        if self.state() == mxc_watchdog.UNCERTAIN and self.core_stop is None:')],
     [RETRY_EXIT, RETRY_FLAKY, RETRY_CAP_TEST]),
    ('WH52', 'terminate answering False decides the stop without verification', [(HOST,
     STOP_CALL, "            if self.terminate(self.core_pid, self.core_create_time) is not True:\n"
                "                self.core_stop = 'Core did not stop'\n                return")],
     [ABSENT_NOTHING]),
    ('WH53', 'a fourth identity-bound stop attempt is made', [(HOST,
     RETRY_CAP, '        if False:')], [RETRY_CAP_TEST]),
    ('WH54', 'a retried stop terminates by pid alone', [(HOST,
     RETRY_CALL, RETRY_CALL.replace('self.core_create_time', 'None'))], [RETRY_CAP_TEST]),
    ('WH55', 'a retry skips the re-verification and calls terminate again', [(HOST,
     RETRY_GATE, '        if False:\n            self.core_stop = self._unstopped()')], [RETRY_REUSE]),
    ('WH56', 'a stop is decided by what terminate answered', [(HOST,
     STOP_CALL, '            self._answer = self.terminate(self.core_pid, self.core_create_time) is True'),
     (HOST, VERIFY_LAST, "        self.core_stop = STOPPED if getattr(self, '_answer', False) "
                         "else (self._unstopped() or STOPPED)\n")], [CLAIMED]),
]


if __name__ == '__main__':
    mutate_p18.MUTATIONS = MUTATIONS
    sys.exit(mutate_p18.run(sys.argv[1:]))

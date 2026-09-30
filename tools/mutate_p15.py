"""The P15 mutation suite (p15-design-gate §20): break each safety property of
pairing, presence, remote access and client runtime, run the tests that guard
it, and require them to fail.

    py tools/mutate_p15.py            every mutation
    py tools/mutate_p15.py M04 M13    only these

Same runner as tools/mutate_p11.py: each mutation replaces exact snippets
(each must occur once), runs its tests, and restores the files whatever
happens; a mutation the tests do not catch ("survived") fails the run. It
edits sources: run it with nothing else running against the tree.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mutate_p11  # noqa: E402  (one runner)

AUTH = 'archeus/api/auth.py'
SRV = 'archeus/api/server.py'
RTS = 'archeus/api/routes.py'
SSE = 'archeus/api/sse.py'
SCH = 'archeus/api/schemas.py'
CMD = 'archeus/core/application/commands.py'
AZN = 'archeus/core/application/authorization.py'
I = 'tests/v1/integration/test_presence.py'
U = 'tests/v1/unit/test_presence_units.py'
G6 = 'tests/v1/judge/test_g06_security.py'

#: A disconnect taken as authoritative: the client's work is paused (M14), or
#: its sessions closed (M13), when its last stream goes.
_ON_CLOSE = """        except Exception:           # a trace is never a reason to refuse or keep a stream
            pass
        if not opened:
            from ..core.application import sessions as S
            with self.db.read() as conn:
                gone = %s
            for x in gone:
                req.run(%s, keyed=False)"""

MUTATIONS = [
    # ── authentication and revocation (§6.4, §8.4) ──
    ('M01', 'a revoked paired credential still authenticates', [(AUTH,
     "    if cred['revoked_at'] is not None or cred['device_state'] != 'ACTIVE':\n"
     "        return False",
     "    if False:\n        return False")],
     [I + '::test_P04_P21_a_revoked_client_loses_its_stream_now_and_cannot_come_back',
      I + '::test_P05_two_clients_of_one_user_coexist_and_revoke_independently']),
    ('M02', 'a local-only route checks the peer only', [(RTS,
     "    if not (auth.loopback_peer(req.peer) and req.api.origin.local_host(req.headers.get("
     "'Host'))):",
     "    if not auth.loopback_peer(req.peer):")],
     [I + '::test_R2_a_tunnel_forwarded_request_cannot_reach_a_local_only_route']),
    ('M03', 'an expired pairing code is accepted', [(AUTH,
     "        if hit is None or self.clock() > hit[0]:",
     "        if hit is None:")],
     [I + '::test_P02_a_pairing_code_expires']),
    ('M04', 'a pairing code is not spent', [(AUTH,
     "            hit = self._codes.pop(token_hash(code), None)",
     "            hit = self._codes.get(token_hash(code), None)")],
     [I + '::test_P03_a_pairing_code_works_once_even_when_raced']),
    ('M05', "the start's scopes are ignored at redemption", [(RTS,
     "        'scopes': grant['scopes'], 'expires_at': expires, 'origin': 'paired',",
     "        'scopes': list(auth.PAIR_SCOPES), 'expires_at': expires, 'origin': 'paired',")],
     [I + '::test_P01_a_new_client_pairs_with_exactly_the_scopes_chosen_at_the_start']),
    ('M06', 'the pairing failure breaker never trips', [(AUTH,
     "            if len(self._fails) > self.FAIL_LIMIT:",
     "            if False:")],
     [I + '::test_R4_failed_redemptions_burn_every_live_code_and_lock_pairing']),
    ('M07', "a revoked client's stream keeps running", [
        (RTS, "    req.api.sse.close_device(req.params['id'])", "    pass"),
        (SSE, "            return auth.live(queries.credential(conn, presented_hash), "
              "presented_hash)", "            return True")],
     [I + '::test_P04_P21_a_revoked_client_loses_its_stream_now_and_cannot_come_back',
      G6 + '::test_revoking_a_device_closes_its_live_stream']),
    # ── step-up (§6.6) ──
    ('M08', 'paired is read from the declared platform only', [(AZN,
     "    return device.origin == 'paired' or device.platform in PAIRED_PLATFORMS",
     "    return device.platform in PAIRED_PLATFORMS")],
     [I + '::test_P14_R1_a_paired_client_approves_through_p9_with_its_pin']),
    ('M09', 'any PIN is a valid proof', [(CMD,
     "    return hmac.compare_digest(got.encode('ascii'), want.encode('ascii'))",
     "    return True")],
     [I + '::test_R1_five_wrong_pins_revoke_the_client_and_no_pin_means_no_step_up',
      U + '::test_a_pin_is_stored_as_pbkdf2_and_only_matches_itself']),
    ('M10', 'wrong PINs never revoke', [(RTS,
     "    if req.principal['origin'] == 'paired' and req.api.step_up.failed(device):",
     "    if False:")],
     [I + '::test_R1_five_wrong_pins_revoke_the_client_and_no_pin_means_no_step_up']),
    # ── offline intent and conflicts (§12, §14) ──
    ('M11', 'a queued live-only command is accepted', [(SRV,
     "                    and (route.method, route.path) not in routes.REPLAYABLE):",
     "                    and False):")],
     [I + '::test_P12_a_queued_command_is_refused_unless_declared_replayable']),
    ('M12', 'resume drops expected_version', [(RTS,
     "    return 200, req.run(req.api.missions.resume, {\n"
     "        'mission_id': req.params['id'], 'expected_version': "
     "req.body.get('expected_version')})",
     "    return 200, req.run(req.api.missions.resume, {'mission_id': req.params['id']})")],
     [I + '::test_P13_a_mutation_built_on_a_stale_read_is_refused']),
    ('M22', 'a retried command loses its idempotency key', [(SRV,
     "        key = self.body.get('idempotency_key') if keyed else None",
     "        key = None")],
     [I + '::test_P11_a_retry_after_a_lost_answer_does_nothing_twice',
      I + '::test_P24_reconnecting_during_an_approval_decides_it_once']),
    # ── presence is not ownership (§5, §10) ──
    ('M13', "a dropped connection closes the client's sessions", [(SSE,
     "        except Exception:           # a trace is never a reason to refuse or keep a "
     "stream\n            pass",
     _ON_CLOSE % ("[x for x in S.listing(conn) if x['state'] == 'OPEN']",
                  "S.close, {'session_id': x['id']}"))],
     [I + '::test_P16_P30_resuming_is_p12s_and_a_connection_is_never_a_session']),
    ('M14', "a dropped connection pauses the running missions", [(SSE,
     "        except Exception:           # a trace is never a reason to refuse or keep a "
     "stream\n            pass",
     _ON_CLOSE % ("queries.list_missions(conn, 'EXECUTING', None)",
                  "req.api.missions.pause, {'mission_id': x['id']}"))],
     [I + '::test_P07_P08_P23_a_client_going_away_ends_nothing_and_reconnecting_repeats'
          '_nothing']),
    ('M20', 'every connection is traced, not only the transitions', [
        (SSE, "            if first:\n                self._trace(req, stream, True)",
              "            if True:\n                self._trace(req, stream, True)"),
        (SSE, "            if self._unregister(stream):",
              "            if self._unregister(stream) or True:")],
     [I + '::test_R5_presence_is_traced_on_transitions_only_with_the_connection']),
    # ── realtime and resync (§11, §13) ──
    ('M15', 'the stream narrowing is ignored', [(SSE,
     "    def keep(e):\n        return ((not projects",
     "    def keep(e):\n        return True or ((not projects")],
     [I + '::test_P20_a_stream_narrowed_to_a_project_carries_no_other_projects_frames',
      I + '::test_P27_constrained_links_narrow_the_stream_and_page_the_catch_up']),
    ('M18', 'X-Archeus-Seq claims a state newer than the read', [(SRV,
     "                        extra['X-Archeus-Seq'] = str(outbox.head(conn))",
     "                        extra['X-Archeus-Seq'] = str(outbox.head(conn) + 1000)")],
     [I + '::test_P25_a_client_can_tell_current_from_stale']),
    ('M19', 'the sync anchor reports a stale head', [(RTS,
     "        head, floor = outbox.head(conn), outbox.floor(conn)",
     "        head, floor = outbox.floor(conn), outbox.floor(conn)")],
     [I + '::test_P09_P26_the_sync_anchor_says_who_where_and_from_which_cursor']),
    # ── remote hosts (§8) ──
    ('M16', 'a tunnel host is accepted over plain http', [(AUTH,
     "        return self.origin if host in (None, self.host) else 'https://%s' % host",
     "        return self.origin if host in (None, self.host) else 'http://%s' % host")],
     [I + '::test_R3_a_remote_host_is_accepted_only_as_itself_over_https']),
    ('M23', 'a local credential is honoured through the tunnel', [(SRV,
     "                if (self.principal['origin'] != 'paired'",
     "                if False and (self.principal['origin'] != 'paired'")],
     [I + '::test_R3_a_remote_host_is_accepted_only_as_itself_over_https']),
    # ── ownership (§9, §15) ──
    ('M17', 'a redemption may carry a model', [(SCH,
     "    'name': {'type': 'string', 'nullable': True}, 'pin': {'type': 'string', "
     "'nullable': True}},",
     "    'name': {'type': 'string', 'nullable': True}, 'pin': {'type': 'string', "
     "'nullable': True}, 'model': {'type': 'string', 'nullable': True}},")],
     [U + '::test_P32_a_redemption_cannot_carry_a_selection_or_a_scope']),
    ('M21', "the route drops the client's step-up proof on its way to P9", [(RTS,
     "            'action_hash': b['action_hash'], 'note': b.get('note'), "
     "'step_up': b.get('step_up'),",
     "            'action_hash': b['action_hash'], 'note': b.get('note'), 'step_up': None,")],
     [I + '::test_P14_R1_a_paired_client_approves_through_p9_with_its_pin']),
]


if __name__ == '__main__':
    mutate_p11.MUTATIONS = MUTATIONS
    sys.exit(mutate_p11.run(sys.argv[1:]))

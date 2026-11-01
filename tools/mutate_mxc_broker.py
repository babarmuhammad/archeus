"""The PV-20 B10 mutation suite: break each rule of the broker's MXC transport (the
attested loopback listener per grant, the grant's bindings, the per-request re-check, the
revocation, the terms and account-health recheck), run the test written for it, and
require it to fail.

    py tools/mutate_mxc_broker.py               every mutation
    py tools/mutate_mxc_broker.py L01 L05       only these

It edits archeus/node/broker_listener.py, broker.py, mxc_boundary.py and
archeus/core/execution/manager.py and restores them whatever happens: run it with nothing
else against the tree.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mutate_p18  # noqa: E402

LST = 'archeus/node/broker_listener.py'
BRK = 'archeus/node/broker.py'
BND = 'archeus/node/mxc_boundary.py'
MGR = 'archeus/core/execution/manager.py'
T = 'tests/v1/unit/test_broker_listener.py::'
E = 'tests/v1/unit/test_broker_execution.py::'

MUTATIONS = [
    ('L01', 'a listener that is not on loopback is kept', [(LST,
     '            if not ipaddress.ip_address(host).is_loopback:',
     '            if False:')],
     [T + 'test_a_listener_that_is_not_on_loopback_is_refused_and_closed']),
    ('L02', 'the shipped bind is not loopback', [(LST,
     '        sock.bind((HOST, 0))',
     "        sock.bind(('0.0.0.0', 0))")],
     [T + 'test_a_real_loopback_socket_is_attested_served_and_closed_on_revoke']),
    ('L03', 'a listener that failed to build stays open', [(LST,
     '        except BaseException:\n            sock.close()\n            raise\n\n'
     '    def launch_bridge',
     '        except BaseException:\n            pass\n            raise\n\n'
     '    def launch_bridge')],
     [T + 'test_a_backend_that_cannot_be_built_leaves_no_listener_and_no_grant']),
    ('L04', 'a transport with no broker still starts', [(LST,
     '        if self.broker is None:',
     '        if False:')],
     [T + 'test_a_transport_with_no_broker_serves_nothing']),
    ('L05', 'the attestor is waited on without a bound', [(LST,
     '            evidence = origin.bounded(self.backend.attest, ctx)',
     '            evidence = self.backend.attest(ctx)')],
     [T + 'test_an_attestor_that_hangs_is_a_refusal_not_a_stall']),
    ('L06', 'the evidence is not validated', [(LST,
     '        if not origin.validate_evidence(ctx, evidence):',
     '        if False:')],
     [T + 'test_a_peer_that_is_not_an_attested_execution_is_closed_unread']),
    ('L07', 'any attested origin is served', [(LST,
     '        if evidence.origin is not OriginClass.EXECUTION:',
     '        if False:')],
     [T + 'test_a_peer_that_is_not_an_attested_execution_is_closed_unread',
      T + 'test_the_users_own_process_is_refused_through_the_shipped_backend']),
    ('L08', 'a peer off the loopback is served', [(LST,
     '        if not origin.direct_loopback(ctx) or ctx.local_endpoint[1] != self.port:',
     '        if ctx.local_endpoint[1] != self.port:')],
     [T + 'test_a_peer_that_is_not_on_the_loopback_is_refused_whatever_the_attestor_says']),
    ('L09', 'a connection to another port is served', [(LST,
     '        if not origin.direct_loopback(ctx) or ctx.local_endpoint[1] != self.port:',
     '        if not origin.direct_loopback(ctx):')],
     [T + 'test_a_connection_to_another_port_is_refused_whatever_the_attestor_says']),
    ('L10', 'a process with no principal is served', [(LST,
     '        if not (isinstance(principal, str) and principal):',
     '        if False:')],
     [T + 'test_an_execution_process_that_maps_to_no_principal_is_refused']),
    ('L11', 'the grant names the principal, not the backend', [(LST,
     '                conn.sendall, principal, self)',
     '                conn.sendall, self.binding.principal, self)')],
     [T + 'test_the_principal_the_backend_observed_is_what_the_broker_checks']),
    ('L12', 'a grant answers at any listener', [(LST,
     '                conn.sendall, principal, self)',
     '                conn.sendall, principal)')],
     [T + 'test_a_token_answers_only_at_the_listener_it_was_issued_at']),
    ('L13', 'the peer is not checked again when its request arrives', [(LST,
     "                _Gate(conn.makefile('rb'), lambda: self._still(ctx, evidence)),",
     "                conn.makefile('rb'),")],
     [T + 'test_a_peer_that_is_no_longer_the_attested_process_is_refused',
      T + 'test_a_pid_recycled_between_accept_and_request_is_refused']),
    ('L14', 'only an explicit False fails the re-check', [(LST,
     '            ok = origin.bounded(self.backend.valid, ctx, evidence) is True',
     '            ok = origin.bounded(self.backend.valid, ctx, evidence) is not False')],
     [T + 'test_a_peer_that_is_no_longer_the_attested_process_is_refused']),
    ('L15', 'a re-check that fails passes', [(LST,
     '        except Exception:\n            ok = False',
     '        except Exception:\n            ok = True')],
     [T + 'test_a_peer_that_is_no_longer_the_attested_process_is_refused']),
    ('L16', 'the re-check is waited on without a bound', [(LST,
     '            ok = origin.bounded(self.backend.valid, ctx, evidence) is True',
     '            ok = self.backend.valid(ctx, evidence) is True')],
     [T + 'test_a_re_check_that_hangs_is_a_refusal']),
    ('L17', 'the attested binding is never released', [(LST,
     '                    origin.bounded(self.backend.release, ctx, evidence)',
     '                    0')],
     [T + 'test_the_peer_is_checked_again_when_its_request_arrives_and_released_after']),
    ('L18', 'a failing release escapes the handler', [(LST,
     '                except Exception:\n                    pass',
     '                except OSError:\n                    pass')],
     [T + 'test_a_release_that_fails_does_not_unserve_the_response']),
    ('L19', 'closing the listener leaves its connections open', [(LST,
     '        for sock in [self.sock] + conns:',
     '        for sock in [self.sock]:')],
     [T + 'test_revoking_the_execution_closes_its_listener_and_cuts_what_it_holds',
      T + 'test_a_real_loopback_socket_is_cut_when_its_grant_is_revoked_mid_request']),
    ('L20', 'a closed listener is not marked closed', [(LST,
     '            self._closed = True\n            conns = list(self._conns)',
     '            self._closed = False\n            conns = list(self._conns)')],
     [T + 'test_a_revoked_listener_serves_nothing_even_a_connection_already_accepted']),
    ('L21', 'a connection accepted after the close is served', [(LST,
     '            if self._closed:\n                _close(conn)\n                return',
     '            if False:\n                _close(conn)\n                return')],
     [T + 'test_a_revoked_listener_serves_nothing_even_a_connection_already_accepted']),
    ('L22', 'an accept-time refusal leaves no audit row', [(LST,
     '        self._transport.broker.audit.append({',
     '        list().append({')],
     [T + 'test_a_peer_that_is_not_an_attested_execution_is_closed_unread']),
    ('L23', 'the connection cap is not enforced', [(LST,
     '            if not self._slots.acquire(blocking=False):\n                _close(conn)\n'
     '                continue',
     '            if False:\n                _close(conn)\n                continue')],
     [T + 'test_the_connection_cap_closes_the_next_unread']),
    ('L24', 'a served connection keeps its slot', [(LST,
     '        finally:\n            self._slots.release()',
     '        finally:\n            pass')],
     [T + 'test_a_served_connection_frees_its_slot']),
    ('L25', 'a silent peer is never timed out', [(LST,
     '            conn.settimeout(wire.IDLE_S)',
     '            pass')],
     [T + 'test_an_attested_execution_with_its_token_is_served']),
    ('L26', 'two connections share an accept generation', [(LST,
     '                accept_generation=secrets.token_hex(16))',
     "                accept_generation='g')")],
     [T + 'test_every_connection_has_its_own_accept_generation']),
    ('B01', 'a grant forgets its port', [(BRK,
     "                               'active': 0, 'port': port}",
     "                               'active': 0, 'port': 0}")],
     [T + 'test_a_grant_binds_a_loopback_listener_and_answers_its_port']),
    ('B02', "reach answers another execution's port", [(BRK,
     "                         if g['binding'].execution_id == execution_id), None)",
     "                         if True), None)")],
     [T + 'test_reach_is_none_without_a_grant_and_after_it_ends',
      T + 'test_without_a_grant_the_boundary_names_no_proxy']),
    ('B03', 'a token answers at any endpoint', [(BRK,
     "        if endpoint is not None and g['endpoint'] is not endpoint:",
     '        if False:')],
     [T + 'test_a_token_answers_only_at_the_listener_it_was_issued_at']),
    ('B04', 'serve forgets the endpoint it was reached at', [(BRK,
     '            g, d = self.authorize(_bearer(head), principal, endpoint)',
     '            g, d = self.authorize(_bearer(head), principal)')],
     [T + 'test_a_token_answers_only_at_the_listener_it_was_issued_at']),
    ('M01', 'the terms are not rechecked', [(MGR,
     '                and permitted and account is not None',
     '                and account is not None')],
     [E + 'test_the_recheck_follows_the_terms_every_request',
      E + 'test_terms_withdrawn_mid_run_end_the_next_request']),
    ('M02', 'the account health is not rechecked', [(MGR,
     '                and account.entity.health in ROUTABLE)',
     '                and True)')],
     [E + 'test_the_recheck_follows_the_accounts_health']),
    ('M03', 'a missing account is live', [(MGR,
     '                and permitted and account is not None',
     '                and permitted and True')],
     [E + 'test_an_account_that_is_gone_is_not_live']),
    ('X01', 'the launch names no proxy', [(BND,
     "            proxy_url=None if port is None else 'http://%s:%d' % (broker_listener.HOST, port))",
     '            proxy_url=None)')],
     [T + 'test_the_boundary_proxy_is_its_own_executions_listener']),
    ('X02', "the launch asks for another execution's grant", [(BND,
     '        port = None if self.broker is None else self.broker.reach(key)',
     '        port = None if self.broker is None else self.broker.reach(profile)')],
     [T + 'test_the_boundary_proxy_is_its_own_executions_listener']),
]


if __name__ == '__main__':
    mutate_p18.MUTATIONS = MUTATIONS
    sys.exit(mutate_p18.run(sys.argv[1:]))

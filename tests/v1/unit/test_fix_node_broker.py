"""Regression tests for hostile-audit findings on archeus/node/broker.py."""

from .test_provider_broker import Resp, Transport, binding, broker, issued, request, serve


def test_a_revoked_grant_stops_relaying_a_stream_even_while_core_still_calls_it_live():
    box = {}

    class Revoking(Resp):
        def read1(self, n):
            if self._c and len(self._c) == 3:
                box['b'].revoke(box['bd'].execution_id)
            return super().read1(n)

    b, _ = broker(send=lambda *a: Revoking(chunks=[b'one', b'two', b'three']))
    box['b'] = b
    bd, token, _ = issued(b)
    box['bd'] = bd
    out, _ = serve(b, request(token=token))
    assert out.endswith(b'one')


def test_two_concurrent_issues_for_one_execution_leave_one_live_grant():
    class Racing(Transport):
        racing = True

        def create(self, name, principal):
            if self.racing:
                self.racing = False
                b.issue(binding(execution_id=bd.execution_id, process_seq=2))
            return super().create(name, principal)

    b, _ = broker(transport=Racing())
    bd = binding()
    b.issue(bd)
    assert sum(1 for g in b._grants.values()
               if g['binding'].execution_id == bd.execution_id) == 1

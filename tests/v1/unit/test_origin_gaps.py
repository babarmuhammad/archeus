"""T-234 (T-212 inventory §1 and §2): the GAP lines in the origin contract that
neither `test_api_origin.py` nor `test_hook_mailbox_origin.py` covered. Pure
contract only: `archeus/api/origin.py` and the shipped stub
`archeus/node/origin_windows.py` (imported on Linux exactly as AO's
`test_evidence_validation_and_native_stub` already does), driven through fakes.
No Windows API, no server, no harness, no sleeps.

Not here by design: the G1-G3 fake-process-table stories (PID plus creation
time, dead-owner fail-closed, attest-at-accept) belong to the attestor card
T-231 and to the time-bound integration xfail named in origin.py's activation
blocker; nothing in this file touches them."""

import dataclasses

import pytest

from archeus.api import origin
from archeus.node.origin_windows import WindowsOriginBackend


def _context(generation='a'):
    return origin.ConnectionContext(object(), ('127.0.0.1', 1), ('127.0.0.1', 2), generation)


def _evidence(**over):
    fields = dict(origin=origin.OriginClass.USER, path=origin.PathClass.DIRECT_LOCAL,
                  process_binding=object(), accept_generation='a', reason='approved')
    fields.update(over)
    return origin.OriginEvidence(**fields)


# ── OriginEvidence defaults and ConnectionContext shape (§1, GAP rows) ──

def test_evidence_built_without_arguments_is_the_undetermined_unapproved_answer():
    """The matrix at AO:114 leans on these defaults but never looked at them:
    nothing a backend forgets may default to an approvable value."""
    evidence = origin.OriginEvidence()
    assert evidence.origin is origin.OriginClass.UNDETERMINED
    assert evidence.path is origin.PathClass.UNAPPROVED
    assert evidence.identity is None
    assert evidence.process_binding is None
    assert evidence.accept_generation == ''
    assert evidence.reason == 'unavailable'


def test_the_connection_context_is_frozen_and_keeps_all_four_fields():
    sock = object()
    context = origin.ConnectionContext(sock, ('127.0.0.1', 1), ('127.0.0.1', 2), 'a')
    assert (context.socket is sock
            and context.local_endpoint == ('127.0.0.1', 1)
            and context.remote_endpoint == ('127.0.0.1', 2)
            and context.accept_generation == 'a')
    for field, value in (('accept_generation', 'b'), ('socket', object()),
                         ('remote_endpoint', ('10.0.0.1', 9))):
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(context, field, value)


# ── validate_evidence: the conjuncts AO's `bad` tuple never reached ──

@pytest.mark.parametrize('not_a_context', [None, 'ctx', object(), 42])
def test_validate_evidence_refuses_anything_that_is_not_a_connection_context(not_a_context):
    """The first conjunct (origin.py:81) had no failing input; and the arguments
    are not interchangeable — evidence must never masquerade as context."""
    assert not origin.validate_evidence(not_a_context, _evidence())
    assert not origin.validate_evidence(_evidence(), _context())


def test_an_empty_accept_generation_is_refused_even_when_the_evidence_matches():
    """origin.py:86: a mismatched generation was tested (AO:135) but '' vs ''
    passes :85 and must still fail — an unbound generation authorizes nothing."""
    context, evidence = _context(''), _evidence(accept_generation='')
    assert evidence.accept_generation == context.accept_generation      # :85 would pass
    assert not origin.validate_evidence(context, evidence)
    assert origin.validate_evidence(_context('a'), _evidence())         # the control


@pytest.mark.parametrize('identity', ['exec-1', 'a', 'x' * 128])
def test_an_identity_inside_the_length_bound_validates(identity):
    """The 0 < len <= 128 bound (origin.py:89) was never exercised: no AO good
    case ever set an identity at all."""
    assert origin.validate_evidence(_context(), _evidence(identity=identity))


@pytest.mark.parametrize('identity', ['', 'x' * 129, 7, 3.5, ['a']])
def test_an_identity_outside_the_length_bound_or_not_a_str_is_refused(identity):
    assert not origin.validate_evidence(_context(), _evidence(identity=identity))


@pytest.mark.parametrize('kind', [origin.OriginClass.EXECUTION, origin.OriginClass.VERIFIER])
def test_execution_and_verifier_never_validate_without_an_identity(kind):
    """origin.py:92-93: the identity requirement for the two machine classes had
    no test in either direction."""
    assert origin.validate_evidence(_context(), _evidence(origin=kind, identity='exec-1'))
    assert not origin.validate_evidence(_context(), _evidence(origin=kind, identity=None))


@pytest.mark.parametrize('reason', ['a', 'approved_2', 'z' + '0' * 63, 'unavailable'])
def test_a_well_formed_reason_validates(reason):
    assert origin.validate_evidence(_context(), _evidence(reason=reason))


@pytest.mark.parametrize('reason', ['', 'Approved', '1abc', 'a-b', 'a b', 'x' * 65, None, 1])
def test_a_malformed_or_non_str_reason_is_refused(reason):
    """AO only broke the reason with 'x'*65; the regex itself (origin.py:90-91)
    and the isinstance guard had no failing input."""
    assert not origin.validate_evidence(_context(), _evidence(reason=reason))


# ── authorize_transport: the branches the AO matrix never fed ──

@pytest.mark.parametrize('not_evidence', [None, 'user', 'unapproved', object(), 42])
def test_authorize_transport_refuses_anything_that_is_not_evidence(not_evidence):
    """origin.py:106's isinstance conjunct had no failing input — the matrix
    only ever passed a real OriginEvidence (AO:114)."""
    assert not origin.authorize_transport(not_evidence, local_host=True, remote_host=False)


@pytest.mark.parametrize('path', list(origin.PathClass))
def test_authorize_transport_refuses_raw_strings_where_str_enum_equality_passes(path):
    """OriginClass/PathClass are str Enums, so `origin != OriginClass.USER` lets
    a raw 'user' through; only the second isinstance check (origin.py:108)
    refuses it. Without that guard both cases below would authorize."""
    for raw in (origin.OriginEvidence(origin='user', path=path, process_binding=object(),
                                      accept_generation='a'),
                origin.OriginEvidence(origin=origin.OriginClass.USER, path='direct_local',
                                      process_binding=object(), accept_generation='a')):
        assert not origin.authorize_transport(raw, local_host=True, remote_host=True,
                                              credential_origin=None, tunnel_route=True)


@pytest.mark.parametrize('credential', ['shared', '', True, False, 'Local', 'paired'])
def test_the_direct_local_path_answers_only_to_no_credential_or_the_local_one(credential):
    """origin.py:110-111: paired was in the matrix; the rest of the credential
    space was not, and every value outside (None, 'local') must refuse."""
    evidence = _evidence()
    assert not origin.authorize_transport(evidence, local_host=True, remote_host=False,
                                          credential_origin=credential)
    assert origin.authorize_transport(evidence, local_host=True, remote_host=False)
    assert origin.authorize_transport(evidence, local_host=True, remote_host=False,
                                      credential_origin='local')


@pytest.mark.parametrize('host,expected', [('host', True), ('', False), (0, False), (1, True)])
def test_the_direct_local_host_is_read_as_truthiness(host, expected):
    """bool(local_host) (origin.py:111): only True/False were ever fed."""
    assert origin.authorize_transport(_evidence(), local_host=host,
                                      remote_host=False) is expected


@pytest.mark.parametrize('remote,expected', [('host', True), (0, False), ('', False)])
def test_the_remote_host_is_read_as_truthiness_on_the_tunnel_path(remote, expected):
    evidence = _evidence(path=origin.PathClass.REGISTERED_TUNNEL)
    assert origin.authorize_transport(evidence, local_host=False, remote_host=remote,
                                      credential_origin=None, tunnel_route=True) is expected


@pytest.mark.parametrize('tunnel_route,expected', [(1, True), ('', False)])
def test_the_tunnel_route_flag_is_read_as_truthiness(tunnel_route, expected):
    """bool(... tunnel_route ...) (origin.py:113): the matrix fed only True/False."""
    evidence = _evidence(path=origin.PathClass.REGISTERED_TUNNEL)
    assert origin.authorize_transport(evidence, local_host=False, remote_host='host',
                                      credential_origin=None,
                                      tunnel_route=tunnel_route) is expected


# ── the shipped stub (§2): assert everything the AO stub test left unchecked ──

def test_the_windows_stub_attests_only_the_generation_back_and_nothing_else():
    """AO:140 asserted `origin == UNDETERMINED` and nothing more: the
    accept_generation carry-over and the other five default fields of the
    returned evidence were never pinned (origin_windows.py:10-11)."""
    context = _context('g41')
    evidence = WindowsOriginBackend().attest(context)
    assert evidence == origin.OriginEvidence(accept_generation='g41')
    assert evidence.accept_generation == context.accept_generation
    assert evidence.origin is origin.OriginClass.UNDETERMINED
    assert evidence.path is origin.PathClass.UNAPPROVED
    assert evidence.identity is None
    assert evidence.process_binding is None
    assert evidence.reason == 'unavailable'


def test_the_windows_stub_answer_is_refused_by_both_gates_end_to_end():
    """The 'stub evidence must be unusable' GAP: nobody ever ran the stub's own
    evidence through validate_evidence or authorize_transport."""
    context = _context('g41')
    evidence = WindowsOriginBackend().attest(context)
    assert not origin.validate_evidence(context, evidence)
    for credential in (None, 'local', 'paired'):
        for local, remote in ((True, False), (False, True), (True, True)):
            assert not origin.authorize_transport(evidence, local_host=local,
                                                  remote_host=remote,
                                                  credential_origin=credential,
                                                  tunnel_route=True)


def test_the_windows_stub_valid_is_false_even_on_fully_valid_evidence_and_release_is_quiet():
    """valid() False on a *valid* evidence is AO:141; the rest — valid() False on
    the stub's own attest output, and release() raising nothing on any input —
    was only ever 'called without raising' (AO:142)."""
    context, backend, good = _context(), WindowsOriginBackend(), _evidence()
    assert origin.validate_evidence(context, good)
    assert backend.valid(context, good) is False
    assert backend.valid(context, backend.attest(context)) is False
    backend.release(context, good)
    backend.release(context, None)

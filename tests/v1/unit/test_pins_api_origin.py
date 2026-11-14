"""T-821 hand-mutant pins on `archeus/api/origin.py`: one test per condition that
no existing test of `tests/v1` would have failed on. Each test names the branch it
holds down, and each was run against a mutated copy of the module (under
/work/scratch only) to show it goes red when that branch is inverted, removed or
loosened. Pure module: no server, no socket, no Windows API, no real process, no
clock, no fixture beyond this file.
"""

import dataclasses

import pytest

from archeus.api import origin

ORIGIN_WIRE = [(origin.OriginClass.USER, 'user'),
               (origin.OriginClass.EXECUTION, 'execution'),
               (origin.OriginClass.VERIFIER, 'verifier'),
               (origin.OriginClass.UNDETERMINED, 'undetermined')]
PATH_WIRE = [(origin.PathClass.DIRECT_LOCAL, 'direct_local'),
             (origin.PathClass.REGISTERED_TUNNEL, 'registered_tunnel'),
             (origin.PathClass.HOP, 'hop'),
             (origin.PathClass.DEPUTY, 'deputy'),
             (origin.PathClass.UNAPPROVED, 'unapproved')]
EVIDENCE_FIELDS = [('origin', origin.OriginClass.UNDETERMINED),
                   ('path', origin.PathClass.HOP),
                   ('identity', 'process:4124:100.0'),
                   ('process_binding', object()),
                   ('accept_generation', 'gen-2'),
                   ('reason', 'attested')]


def _evidence(**over):
    fields = dict(origin=origin.OriginClass.USER, path=origin.PathClass.DIRECT_LOCAL,
                  process_binding=object(), accept_generation='a', reason='approved')
    fields.update(over)
    return origin.OriginEvidence(**fields)


def _reader(*args):
    return None


# ── the enum wire contract (origin.py:18-31) ──

@pytest.mark.parametrize('member,wire', ORIGIN_WIRE, ids=[w for _, w in ORIGIN_WIRE])
def test_an_origin_class_is_named_by_its_own_wire_value(member, wire):
    """No test ever compared a member to its wire string, so renaming one leaves
    every refusal reading the same to itself: the value a refusal prints is free."""
    assert member.value == wire
    assert origin.OriginClass(wire) is member


@pytest.mark.parametrize('member,wire', PATH_WIRE, ids=[w for _, w in PATH_WIRE])
def test_a_path_class_is_named_by_its_own_wire_value(member, wire):
    assert member.value == wire
    assert origin.PathClass(wire) is member


def test_the_origin_classes_are_four_distinct_answers():
    assert [m.name for m in origin.OriginClass] == ['USER', 'EXECUTION', 'VERIFIER',
                                                     'UNDETERMINED']
    assert len({m.value for m in origin.OriginClass}) == 4


def test_the_path_classes_are_five_distinct_paths():
    assert [m.name for m in origin.PathClass] == ['DIRECT_LOCAL', 'REGISTERED_TUNNEL',
                                                   'HOP', 'DEPUTY', 'UNAPPROVED']
    assert len({m.value for m in origin.PathClass}) == 5


@pytest.mark.parametrize(
    'enum,member,wire',
    [(origin.OriginClass, origin.OriginClass.USER, 'user'),
     (origin.PathClass, origin.PathClass.DIRECT_LOCAL, 'direct_local')],
    ids=['origin', 'path'])
def test_the_classes_are_str_enums_so_only_the_isinstance_guards_gate_them(enum, member,
                                                                           wire):
    """The str mixin (origin.py:18, 25) is what lets a raw 'user' pass
    `evidence.origin != OriginClass.USER`, which is why authorize_transport needs
    its second isinstance conjunct (origin.py:140) at all. Dropping the mixin
    turns that conjunct into dead code and nothing else in tests/v1 notices."""
    assert isinstance(member, str)
    assert wire == member
    assert enum(wire) is member


# ── OriginEvidence is immutable once the connection holds it (origin.py:39) ──

@pytest.mark.parametrize('field,value', EVIDENCE_FIELDS,
                         ids=[f for f, _ in EVIDENCE_FIELDS])
def test_an_evidence_the_connection_holds_cannot_be_rewritten_in_place(field, value):
    """`ConnectionContext` was pinned frozen (T-234) but `OriginEvidence` never
    was: an unfrozen evidence lets a backend hand back one answer and have a
    re-check see another."""
    evidence = _evidence()
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(evidence, field, value)


# ── the injected reader bundle has no default outside fact (origin.py:57-60) ──

@pytest.mark.parametrize('missing', ['resolve_owner', 'read_process', 'clock'],
                         ids=['owner', 'process', 'clock'])
def test_the_reader_bundle_refuses_to_be_built_without_an_outside_fact(missing):
    """A defaulted reader would answer from the process instead of from the
    caller; nothing fed this constructor except a fully-populated bundle."""
    readers = {'resolve_owner': _reader, 'read_process': _reader, 'clock': _reader}
    del readers[missing]
    with pytest.raises(TypeError):
        origin.AttestationReaders(**readers)


def test_the_reader_bundle_defaults_the_launcher_the_age_limit_and_reattest_only():
    defaults = {f.name: f.default for f in dataclasses.fields(origin.AttestationReaders)}
    assert defaults == {'resolve_owner': dataclasses.MISSING,
                        'read_process': dataclasses.MISSING,
                        'clock': dataclasses.MISSING,
                        'launcher': None,
                        'max_age_s': None,
                        'reattest': False}


# ── the signature defaults of the transport gate (origin.py:129-130) ──

def test_the_gate_answers_a_bootstrap_request_on_the_tunnel_at_its_defaults():
    """Neither signature default was ever read: every existing caller spells both
    `credential_origin` and `tunnel_route`, so flipping `tunnel_route=True`
    (origin.py:130) to False would have quietly kept every route off the tunnel."""
    tunnel = _evidence(path=origin.PathClass.REGISTERED_TUNNEL)
    assert origin.authorize_transport(tunnel, local_host=False, remote_host='host') is True


def test_the_gate_answers_a_bootstrap_request_on_the_local_host_at_its_defaults():
    """The same untouched `credential_origin=None` (origin.py:129) on the direct
    local path, where a non-local credential is the refusal: T-234 feeds this
    default too, and it is the only side the default can be read from."""
    assert origin.authorize_transport(_evidence(), local_host='host',
                                      remote_host=False) is True


def test_the_gate_refuses_that_same_default_request_without_a_remote_host():
    """The edge of the permission above: the defaults never carry a connection that
    is not on a configured remote host."""
    tunnel = _evidence(path=origin.PathClass.REGISTERED_TUNNEL)
    assert origin.authorize_transport(tunnel, local_host=False, remote_host='') is False
    assert origin.authorize_transport(tunnel, local_host=True, remote_host='') is False

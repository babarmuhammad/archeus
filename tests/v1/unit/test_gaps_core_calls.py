"""T-732: the branches of `archeus/core/calls.py` that no test in tests/v1 reached
— the fail-closed and denial paths first, then the boundary values, then the
error paths.

The rig is the one tests/v1/unit/test_own_call_no_tools.py built for this module
(real `OwnCalls` over a real database of real rows, scripted `FakeCaller`s) and
the seams tests/v1/integration/test_routing.py already uses for the ADR-0021
second check (`monkeypatch.setattr(C, 'terms', ...)`) — nothing here needs a
CLI, a provider, an account, a process, the network or Windows. The e-stop
branch is driven through `OC.stop_sentinel` itself, pointed at the test's own
`tmp_path`, so no test depends on what the machine running the suite has under
its real ARCHEUS_HOME. An adapter that is not a `FakeCaller` is the one input
that makes the provider-terms gates close (class identity, ADR-0021), so the
`Real`/`Scripted`/`Crasher` subclasses below are how these tests stand in for a
real adapter without touching one.
"""

import pytest

from archeus.core import calls as OC
from archeus.core import ports
from archeus.core.application import calls as C
from archeus.core.application import commands, lifecycle, resources
from archeus.core.domain import entities
from archeus.core.domain.values import Ref
from archeus.harnesses import base
from archeus.harnesses.fake import FakeCaller
from archeus.infra.db import Database, rows

_OK = {'*': [{'parsed': {'ok': True}}]}


@pytest.fixture
def db():
    d = Database.open()
    yield d
    d.close()


class Real(FakeCaller):
    """A real-looking own-call adapter (not FakeCaller itself): gated by the
    provider terms, like the registry's real adapters (test_routing's I_T3)."""


class Scripted(FakeCaller):
    """Hands out prepared CallResults in turn, keeping the last: the only way
    to script figures on an *error* result, which FakeCaller's `{'error': ...}`
    replies cannot carry."""

    def __init__(self, id, results):
        super().__init__(id)
        self.results = list(results)

    def call(self, spec):
        self.sent.append((spec, spec.prompt))
        return self.results.pop(0) if len(self.results) > 1 else self.results[0]


class Crasher(FakeCaller):
    """An adapter bug: `call()` raises, which must end the call `failed`,
    never crash the Core (calls.py: `an adapter bug is a failed call`)."""

    def call(self, spec):
        self.sent.append((spec, spec.prompt))
        raise RuntimeError('boom')


def _actors(db):
    def reg(kind, scopes):
        return Ref(kind, db.writer.execute(commands.register_principal, {
            'kind': kind, 'scopes': scopes})['id'])
    return reg('system', ('system',)), reg('user_device', ('observe', 'control', 'approve',
                                                            'admin'))


def _own(db, system, callers, harness='pi'):
    return OC.OwnCalls(db, actor=system, callers=callers,
                       preference=ports.FixedOwnCallPreference(harness=harness))


def _ask(own, **kw):
    one = dict(purpose='knowledge_extraction', workspace_id='ws_global',
               source={'kind': 'mission', 'id': 'msn_x'}, project_id=None, prompt='p',
               schema=None, check=lambda p: [], workdir='.')
    return own.run(**dict(one, **kw))


def _decisions(db):
    with db.read() as c:
        return [r.entity for r in rows.where(c, entities.RouteDecision)]


def _ledgers(db):
    with db.read() as c:
        return [r.entity for r in rows.where(c, entities.UsageLedger)]


def _permit(db, user, harness):
    db.writer.execute(C.decide_provider_terms, {'actor': user, 'harness_id': harness,
                                                'headless': 'permitted'})


def _register(db, user, harness):
    a = db.writer.execute(resources.register_account, {
        'actor': user, 'harness_id': harness, 'label': 'Main', 'auth_kind': 'api_key',
        'auth': {'ok': True, 'detail': 'probe'}})
    return a['id']


def _fire_health(db, user, account_id, trigger):
    db.writer.execute(lambda tx, actor: lifecycle.fire(tx, entities.Account, account_id,
                                                        trigger, actor=actor,
                                                        reason='test'), {'actor': user})


# ── fail-closed and denial paths ─────────────────────────────────────────────

def test_the_e_stop_ends_the_call_with_nothing_spawned(db, tmp_path, monkeypatch):
    """calls.py:109-111: disarmed (P11 §13) — even a preferred, capable, terms-
    exempt harness runs nothing once the sentinel exists, and the decision
    records why. Consumes nothing: no usage row beside the decision."""
    stop = tmp_path / 'STOP'
    monkeypatch.setattr(OC, 'stop_sentinel', lambda: str(stop))
    caller = FakeCaller('pi', replies=_OK)
    own = _own(db, _actors(db)[0], [caller])

    assert _ask(own).state == 'ok'                     # armed: the same call runs
    sent_before = len(caller.sent)
    stop.write_bytes(b'')                              # the e-stop engages

    got = _ask(own)
    assert (got.state, got.detail, got.attempts, got.parsed, got.usage,
            got.account_ref) == ('unavailable', 'emergency stop', 0, None, None, None)
    assert len(caller.sent) == sent_before               # disarmed: nothing more ran
    rd = _decisions(db)[-1]
    assert rd.result == 'selected' and rd.outcome == {'reason': 'emergency stop',
                                                      'state': 'unavailable'}
    assert _ledgers(db) == []                          # the ok call is not ended here;
                                                       # this one never ran


def test_terms_refused_between_routing_and_the_spawn_gate_the_call(db, monkeypatch):
    """calls.py:112-117 (ADR-0021): permitted when routed, refused at the call —
    the second read is the one that stops the spawn (test_routing I_T3's seam)."""
    system, user = _actors(db)
    _permit(db, user, 'pi')
    real, reads = Real('pi', replies=_OK), []
    real_terms = C.terms

    def flip(conn):
        reads.append(1)
        got = real_terms(conn)
        if len(reads) > 1:                             # revoked after the route
            got['pi'] = entities.ProviderTerms(id='pi', headless='refused')
        return got
    monkeypatch.setattr(C, 'terms', flip)

    got = _ask(_own(db, system, [real]))
    assert (got.state, got.detail, got.attempts, got.usage,
            got.account_ref) == ('gated', 'provider terms refused', 0, None, None)
    assert real.sent == []
    (rd,) = _decisions(db)
    assert rd.result == 'selected'                     # it was routed; it never ran
    assert rd.outcome == {'reason': 'provider terms refused', 'state': 'gated'}
    assert _ledgers(db) == []                          # nothing consumed, no row


def test_terms_answered_by_nobody_at_the_spawn_gate_the_call(db, monkeypatch):
    """calls.py:112-117 + 49: a terms row that disappears between the two reads
    is unknown, and unknown is never permitted (fail-closed)."""
    system, user = _actors(db)
    _permit(db, user, 'pi')
    real, reads = Real('pi', replies=_OK), []
    real_terms = C.terms

    def flip(conn):
        reads.append(1)
        return real_terms(conn) if len(reads) <= 1 else {}
    monkeypatch.setattr(C, 'terms', flip)

    got = _ask(_own(db, system, [real]))
    assert got.state == 'gated' and got.detail == 'provider terms unknown'
    assert real.sent == [] and _ledgers(db) == []


def test_the_terms_reading_names_unknown_for_an_unanswered_harness():
    """calls.py:48-49: no row is 'unknown', never a missing key or a None."""
    assert OC._terms_state({}, 'pi') == 'unknown'
    answered = {'pi': entities.ProviderTerms(id='pi', headless='refused')}
    assert OC._terms_state(answered, 'pi') == 'refused'


def test_unanswered_terms_end_the_call_gated_without_anything_run(db):
    """calls.py:93-96: a blocked election whose candidate fell at provider_terms
    is a refusal (gated), not an absence — and it is the reason, not the
    generic one, that the record keeps only for protection-shaped eliminations."""
    real = Real('pi', replies=_OK)
    got = _ask(_own(db, _actors(db)[0], [real]))       # never answered: terms unknown
    assert (got.state, got.detail, got.attempts) == ('gated', 'no eligible harness', 0)
    assert real.sent == []
    (rd,) = _decisions(db)
    assert rd.result == 'blocked'
    assert rd.candidates[0]['eliminated_at_step'] == 'provider_terms'
    assert rd.outcome == {'reason': 'no eligible harness', 'state': 'gated'}
    assert _ledgers(db) == []


def test_a_forbidden_harness_is_named_by_the_restriction_reason(db):
    """calls.py:98-103: the furthest candidate fell at a named step
    (`restriction`), so the record answers "why is my call waiting" exactly."""
    caller = FakeCaller('pi', replies=_OK)
    got = _ask(_own(db, _actors(db)[0], [caller]), forbidden={'harnesses': ['pi']})
    assert (got.state, got.detail) == ('unavailable', 'is forbidden for this work')
    assert caller.sent == []
    (rd,) = _decisions(db)
    assert rd.candidates[0]['eliminated_at_step'] == 'restriction'
    assert rd.outcome['reason'] == 'is forbidden for this work'


def test_an_open_account_is_named_by_the_health_reason(db):
    """calls.py:98-103: the named-step reason again (`health`), decided over
    the real rows: OPEN is not routable and not fallbackable."""
    system, user = _actors(db)
    acc = _register(db, user, 'pi')
    _fire_health(db, user, acc, 'error_storm')         # AVAILABLE -> DEGRADED
    _fire_health(db, user, acc, 'errors_persist')      # DEGRADED  -> OPEN
    caller = FakeCaller('pi', replies=_OK)
    got = _ask(_own(db, system, [caller]))
    assert (got.state, got.detail, got.attempts) == ('unavailable', 'account is OPEN', 0)
    assert caller.sent == []
    (rd,) = _decisions(db)
    assert rd.result == 'blocked' and rd.candidates[0]['eliminated_at_step'] == 'health'
    assert rd.outcome['reason'] == 'account is OPEN'


def test_a_degraded_ask_account_never_runs_and_says_its_call_never_asks(db):
    """calls.py:104-105: `ask` is an answer for a task and a refusal for an own
    call — the recorded reason must say so, and nothing may run."""
    system, user = _actors(db)
    acc = _register(db, user, 'pi')
    _fire_health(db, user, acc, 'error_storm')         # AVAILABLE -> DEGRADED
    db.writer.execute(resources.set_resource_policy, {'actor': user, 'account_id': acc,
                                                      'fallback': 'ask'})
    caller = FakeCaller('pi', replies=_OK)
    got = _ask(_own(db, system, [caller]))
    assert got.state == 'unavailable'
    assert got.detail == ('account is DEGRADED; only your approval could use it, which an '
                          'own call never asks')
    assert caller.sent == [] and got.attempts == 0
    (rd,) = _decisions(db)
    assert rd.result == 'ask' and _ledgers(db) == []


def test_a_workdir_that_cannot_be_made_fails_the_call_with_nothing_spawned(db):
    """calls.py:123-129 (K-O2): the directory is made only once the call is
    about to run, and an OSError there ends it `failed` before the adapter is
    asked for anything — with a usage row (`failed` may have run elsewhere:
    basis none, never a hidden absence)."""
    caller = FakeCaller('pi', replies=_OK)

    def workdir(_rd):
        raise OSError('no space left on device')
    got = _ask(_own(db, _actors(db)[0], [caller]), workdir=workdir)
    assert (got.state, got.attempts, got.account_ref) == ('failed', 0, None)
    assert got.detail.startswith('no working directory for the call: ')
    assert 'no space left on device' in got.detail
    assert caller.sent == []
    (rd,) = _decisions(db)
    assert rd.outcome['state'] == 'failed'              # nothing ran: no attempt is claimed
    assert 'attempts' not in rd.outcome
    assert rd.outcome['reason'] == got.detail
    (led,) = _ledgers(db)
    assert led.basis == 'none'


def test_a_bug_in_the_workdir_maker_is_never_softened_into_a_failed_call(db):
    """calls.py:126: only an OSError is a missing directory; anything else is
    a programmer bug and must surface, not be filed as `failed`."""
    caller = FakeCaller('pi', replies=_OK)

    def workdir(_rd):
        raise ValueError('wrong caller')
    with pytest.raises(ValueError):
        _ask(_own(db, _actors(db)[0], [caller]), workdir=workdir)
    assert caller.sent == []


def test_an_adapter_that_raises_ends_failed_and_never_crashes_the_call(db):
    """calls.py:136-138: the exception is named in the record (`RuntimeError:
    boom`), the attempt that raised is the attempt recorded, and no second
    attempt follows an error."""
    system, user = _actors(db)
    _permit(db, user, 'pi')                            # a Real is terms-gated
    crasher = Crasher('pi')
    got = _ask(_own(db, system, [crasher]))
    assert (got.state, got.detail, got.attempts) == ('failed', 'RuntimeError: boom', 1)
    assert len(crasher.sent) == 1                      # an error returns at once
    (rd,) = _decisions(db)
    assert rd.outcome['state'] == 'failed' and rd.outcome['reason'] == 'RuntimeError: boom'
    (led,) = _ledgers(db)
    assert led.basis == 'none'


def test_an_unavailable_answer_ledgers_nothing(db):
    """calls.py:140-142: no binary meant nothing ran, so no usage row is
    written — a row here would invent consumption for a call that never was."""
    caller = FakeCaller('pi', replies={'*': [{'error': 'unavailable',
                                              'detail': 'no binary'}]})
    got = _ask(_own(db, _actors(db)[0], [caller]))
    assert (got.state, got.detail, got.attempts) == ('unavailable', 'no binary', 1)
    (rd,) = _decisions(db)
    assert rd.outcome['state'] == 'unavailable' and rd.outcome['reason'] == 'no binary'
    assert _ledgers(db) == []


def test_a_failed_answer_with_figures_is_ledgered_as_partial(db):
    """calls.py:139-145: figures an attempt reported travel to the ledger even
    when the attempt errored, and a `failed` end is never a reported total."""
    system, user = _actors(db)
    _permit(db, user, 'pi')
    scripted = Scripted('pi', [base.CallResult(error='failed', detail='rate limited',
                                               usage={'tokens_in': 7, 'tokens_out': 3})])
    got = _ask(_own(db, system, [scripted]))
    assert (got.state, got.detail, got.attempts) == ('failed', 'rate limited', 1)
    assert got.usage == {'tokens_in': 7, 'tokens_out': 3}
    (rd,) = _decisions(db)
    assert rd.outcome['state'] == 'failed' and rd.outcome['attempts'] == 1
    (led,) = _ledgers(db)
    assert (led.basis, led.tokens_in, led.tokens_out) == ('partial', 7, 3)


# ── boundary values ──────────────────────────────────────────────────────────

def test_the_workdir_maker_is_handed_the_route_decision_id_of_the_call_that_runs(db):
    """calls.py:123-124 (K-O2): a callable workdir is called once, with `rd`,
    and its answer is what reaches the adapter — a fresh directory per call,
    none for a call that never runs."""
    seen = []

    def workdir(rd):
        seen.append(rd)
        return 'calls/%s' % rd
    caller = FakeCaller('pi', replies=_OK)
    got = _ask(_own(db, _actors(db)[0], [caller]), workdir=workdir)
    assert got.state == 'ok' and seen == [got.route_decision_id]
    (spec, _prompt) = caller.sent[0]
    assert spec.workdir == 'calls/%s' % got.route_decision_id
    assert spec.limits == {'timeout_s': OC.DEFAULT_TIMEOUT_S}


def test_two_invalid_answers_end_invalid_at_the_attempts_cap(db):
    """calls.py:146-152 (ADR-0006): invalid is retried once and only once —
    ATTEMPTS is a ceiling, and both attempts' figures reach one total row."""
    caller = FakeCaller('pi', replies={'*': [{'text': 'nope'}]})
    got = _ask(_own(db, _actors(db)[0], [caller]))
    assert (got.state, got.detail, got.attempts) == (
        'invalid', 'the answer carried no JSON', 2)   # ADR-0006: retried ONCE
    assert len(caller.sent) == 2                        # never a third attempt
    assert got.parsed is None
    (rd,) = _decisions(db)
    assert rd.outcome['state'] == 'invalid' and rd.outcome['attempts'] == 2
    (led,) = _ledgers(db)
    assert (led.basis, led.tokens_in, led.tokens_out) == ('reported_total', 20, 10)


def test_only_the_first_five_problems_are_recorded(db):
    """calls.py:149-151: the cap at five (boundary: five survive whole, a
    sixth and beyond never reach the record or the caller)."""
    caller = FakeCaller('pi', replies=_OK)
    nine = ['p%d' % n for n in range(9)]
    five = ['q%d' % n for n in range(5)]
    got = _ask(_own(db, _actors(db)[0], [caller]), check=lambda p: nine)
    assert (got.state, got.detail) == ('invalid', 'p0; p1; p2; p3; p4')
    assert 'p5' not in got.detail
    got = _ask(_own(db, _actors(db)[0], [caller]), check=lambda p: five)
    assert (got.state, got.detail) == ('invalid', '; '.join(five))


def test_a_planner_never_runs_on_a_small_model(db):
    """calls.py:42 + 93-107 (plan §12): the tier floor is enforced by the
    router's `model` step — a planner with no large offer is unavailable with
    nothing spawned, and with one it runs on exactly that model."""
    small = FakeCaller('pi', replies=_OK, models=(base.ModelInfo('tiny', 'small', 1000),))
    got = _ask(_own(db, _actors(db)[0], [small]), purpose='planner')
    assert (got.state, got.detail, got.attempts) == ('unavailable', 'no eligible harness', 0)
    assert small.sent == []
    (rd,) = _decisions(db)
    assert rd.candidates[0]['eliminated_at_step'] == 'model'

    large = FakeCaller('pi', replies=_OK)              # FAKE_MODEL is `large`
    got = _ask(_own(db, _actors(db)[0], [large]), purpose='planner')
    assert (got.state, got.attempts) == ('ok', 1)
    assert large.sent[0][0].model == base.ModelInfo('fake-model', 'large',
                                                    200000).id


# ── error paths of the validation itself ─────────────────────────────────────

def test_an_invalid_answer_is_retried_once_and_the_retry_may_answer(db):
    """calls.py:146-148 (ADR-0006): the first answer carrying no JSON is a
    problem, not an end; the second answers, both attempts' figures are the
    total, and `ok` leaves the outcome for the caller to write."""
    caller = FakeCaller('pi', replies={'*': [{'text': 'not json at all'},
                                             {'parsed': {'ok': True}}]})
    got = _ask(_own(db, _actors(db)[0], [caller]))
    assert (got.state, got.detail, got.attempts, got.parsed) == (
        'ok', '', 2, {'ok': True})
    assert got.usage == {'tokens_in': 20, 'tokens_out': 10}   # both attempts summed
    assert len(caller.sent) == 2
    (rd,) = _decisions(db)
    assert rd.outcome is None                          # `ok`: the caller ends it


def test_a_schema_violation_ends_invalid_with_the_validator_reason(db):
    """calls.py:169-173: the schema is Core's, the model's answer is not
    trusted, and the validator's own words are what the record keeps."""
    caller = FakeCaller('pi', replies={'*': [{'parsed': {'ok': 'yes'}}]})
    schema = {'type': 'object', 'properties': {'ok': {'type': 'boolean'}}}
    got = _ask(_own(db, _actors(db)[0], [caller]), schema=schema)
    assert (got.state, got.detail, got.attempts) == (
        'invalid', 'ok: must be a boolean', 2)
    assert len(caller.sent) == 2                        # the schema tried too is retried
    (rd,) = _decisions(db)
    assert rd.outcome['state'] == 'invalid' and rd.outcome['reason'] == \
        'ok: must be a boolean'


def test_a_check_that_returns_none_is_no_problem(db):
    """calls.py:174: a caller's `check` may return None as well as [] — `list
    (None)` would crash the call on a caller that simply had nothing to say."""
    caller = FakeCaller('pi', replies=_OK)
    got = _ask(_own(db, _actors(db)[0], [caller]), check=lambda p: None)
    assert (got.state, got.parsed) == ('ok', {'ok': True})


def test_add_sums_only_figures_both_attempts_reported(db):
    """calls.py:155-163 (ADR-0048 §3): a figure one attempt reported and the
    other did not is dropped — a part is never ledgered as the whole."""
    assert OC._add({}, {'tokens_in': 5, 'note': 'x', 'ok': True, 'gone': None},
                   first=True) == {'tokens_in': 5}     # non-numbers and bools are out
    assert OC._add({'tokens_in': 5, 'tokens_out': 2}, {'tokens_in': 4},
                   first=False) == {'tokens_in': 9}    # tokens_out: unknown, not 2
    assert OC._add({'tokens_in': 5}, {'tokens_out': 2}, first=False) == {}

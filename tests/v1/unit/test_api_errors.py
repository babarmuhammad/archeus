"""The error translator is the §5.5 table (p3.5b design gate §5.5, D3, §10 D1).

Every row is asserted here, including the ones no P3.5b route can reach
(409 has no route taking an expected version; 423 is raised only on the
engine's path), so the mapping exists before P9 makes them reachable."""

import concurrent.futures

import pytest

from archeus.api.routes import Refused
from archeus.api.schemas import Invalid
from archeus.api.server import translate
from archeus.core.application import errors
from archeus.core.domain import ids
from archeus.core.domain.actions import Action
from archeus.core.domain.entities import PolicyDecision
from archeus.core.domain.guards import GuardResult


def _denied():
    d = PolicyDecision(id=ids.new_id('policy_decision'), decision='DENY',
                       action=Action(action_class='destructive', target='task:t1'),
                       reason='locked on prod')
    return errors.PolicyDenied(d, 't1')


ROWS = [
    (Invalid('title', 'is required'), 400, 'invalid_request',
     {'field': 'title', 'why': 'is required'}),
    (Invalid(None, 'the body is not JSON'), 400, 'invalid_request',
     {'why': 'the body is not JSON'}),
    (ValueError('bad value'), 400, 'invalid_request', {'why': 'bad value'}),
    (errors.IdempotencyConflict('reused'), 400, 'invalid_request',
     {'field': 'idempotency_key', 'why': 'reused'}),
    (Refused(401, 'unauthenticated'), 401, 'unauthenticated', {}),
    (Refused(403, 'scope_required', {'scope': 'control'}), 403, 'scope_required',
     {'scope': 'control'}),
    (errors.NotFound('msn_x'), 404, 'not_found', {'id': 'msn_x'}),
    (errors.VersionConflict('msn_x', 3, 4), 409, 'version_conflict', {'current': 4}),
    (errors.CursorExpired(3, 'pruned', 10, 20), 410, 'cursor_expired',
     {'reason': 'pruned', 'floor': 10, 'head': 20}),
    (errors.IllegalTrigger('mission', 'CREATED', 'pause'), 422, 'invalid_transition',
     {'machine': 'mission', 'from': 'CREATED', 'to': 'PAUSED', 'trigger': 'pause'}),
    (errors.InvalidTransition('mission', 'CREATED', 'COMPLETED'), 422, 'invalid_transition',
     {'machine': 'mission', 'from': 'CREATED', 'to': 'COMPLETED'}),
    (errors.GuardFailed('mission', 'EXECUTING', 'VERIFYING', 'all_tasks_done',
                        GuardResult('all_tasks_done', False, 'tasks not done: t1')),
     422, 'guard_failed', {'machine': 'mission', 'from': 'EXECUTING', 'to': 'VERIFYING',
                           'trigger': 'all_tasks_done', 'guard': 'all_tasks_done',
                           'reason': 'tasks not done: t1'}),
    (_denied(), 423, 'policy_denied', {'task': 't1', 'action_class': 'destructive',
                                       'decision': 'DENY', 'reason': 'locked on prod'}),
    (errors.WriterBusy('full'), 503, 'busy', {}),
    (concurrent.futures.TimeoutError(), 503, 'busy', {}),
    (errors.WriterClosed('closed'), 503, 'core_stopping', {}),
]


@pytest.mark.parametrize('exc,status,code,detail', ROWS, ids=lambda x: getattr(
    x, '__name__', None) or type(x).__name__ if not isinstance(x, (int, str, dict)) else str(x))
def test_every_row_of_the_table(exc, status, code, detail):
    got = translate(exc)
    assert got[:3] == (status, code, detail)
    if code == 'busy':
        assert got[3] == {'Retry-After': '1'}


def test_policy_denied_carries_no_decision_id_until_p9():
    """D3: absent, not null — so no client grows code around an id that does
    not exist yet."""
    _s, _c, detail, _h = translate(_denied())
    assert 'policy_decision_id' not in detail and 'id' not in detail


def test_anything_else_is_500_with_a_reference_and_no_traceback():
    status, code, detail, _h = translate(RuntimeError('secret internals'))
    assert (status, code, list(detail)) == (500, 'internal', ['ref'])
    assert 'secret' not in str(detail)


def test_the_guarded_subclasses_are_checked_before_value_error():
    """InvalidTransition IS a ValueError: the order in translate is the table."""
    assert issubclass(errors.InvalidTransition, ValueError)
    assert translate(errors.IllegalTrigger('mission', 'CREATED', 'pause'))[0] == 422

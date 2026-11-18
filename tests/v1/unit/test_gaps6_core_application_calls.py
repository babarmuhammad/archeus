"""T-1260: the uncovered branches of archeus/core/application/calls.py lines 24-83
(end_call and decide_provider_terms), denial and fail-closed first.

Selected branches, with the source line each test is built to catch:
- 61  a non-user actor is refused before tx.get and every write
- 71  invalid headless/rotation on existing terms is refused before tx.update
- 65  rotation=None keeps the prior rotation; an explicit value replaces it
- 67  new terms are inserted, read back and announced; two harnesses stay apart
- 31  an already-ended decision refuses a second outcome before any write
- 29  a missing decision wins over a malformed outcome
- 33  an unknown outcome state refuses; every supported state is a control
- 37  gated/unavailable with usage=None writes no ledger; usage={} means it ran
- 39  known zero figures are kept, None and unexpected keys are dropped; basis follows the state
- 50  a failed ledger insert prevents the ended event; the event scope is the decision's

Rig: a fake transaction holding synthetic rows and recording every call in
order, real entity validation and real event construction, deterministic ids.
No database, no adapter, no subprocess, no network, no Windows-specific call.
"""

import dataclasses
from types import SimpleNamespace as NS

import pytest

from archeus.core.application import calls as C
from archeus.core.application import lifecycle
from archeus.core.domain import ids
from archeus.core.domain import entities
from archeus.core.domain.values import Ref


class Row:
    def __init__(self, entity, version=1):
        self.entity = entity
        self.version = version
        self.created_at = None
        self.updated_at = None


class FakeTx:
    def __init__(self, *rows, fail_insert=None):
        self.store = {}
        self.log = []
        self.fail_insert = fail_insert
        self.conn = None
        for cls, row in rows:
            self.store[(cls, row.entity.id)] = row

    def get(self, cls, entity_id):
        self.log.append(('get', cls.__name__))
        return self.store.get((cls, entity_id))

    def update(self, cls, entity_id, fields, *, actor):
        self.log.append(('update', cls.__name__))
        old = self.store[(cls, entity_id)]
        if dataclasses.is_dataclass(old.entity):
            new = dataclasses.replace(old.entity, **fields)
        else:
            new = NS(**dict(vars(old.entity), **fields))
        self.store[(cls, entity_id)] = Row(new, old.version + 1)
        return self.store[(cls, entity_id)]

    def insert(self, entity, *, actor):
        self.log.append(('insert', type(entity).__name__, entity))
        if self.fail_insert is not None:
            raise self.fail_insert
        self.store[(type(entity), entity.id)] = Row(entity)
        return self.store[(type(entity), entity.id)]

    def append(self, event):
        self.log.append(('append', event.type, event))

    def ops(self):
        return [entry[0] for entry in self.log]

    def inserted(self):
        return [entry[2] for entry in self.log if entry[0] == 'insert']

    def events(self):
        return [entry[2] for entry in self.log if entry[0] == 'append']


@pytest.fixture(autouse=True)
def _deterministic_ids(monkeypatch):
    monkeypatch.setattr(C.ids, 'new_id', lambda kind: ids.PREFIXES[kind] + '_01ARZ3NDEKTSV4RRFFQ69G5FAV')


SYS = Ref('system', 'prn_01ARZ3NDEKTSV4RRFFQ69G5FAV')
USER = Ref('user_device', 'prn_01ARZ3NDEKTSV4RRFFQ69G5FAW')
RD_ID = 'rte_01ARZ3NDEKTSV4RRFFQ69G5FAV'


def _decision(**kw):
    fields = dict(id=RD_ID, outcome=None, subject=NS(kind='archeus_call'),
                  account_id='acc_01ARZ3NDEKTSV4RRFFQ69G5FAV', account_ref='acct_ref', purpose='titles',
                  workspace_id='ws_01ARZ3NDEKTSV4RRFFQ69G5FAV',
                  project_id='prj_01ARZ3NDEKTSV4RRFFQ69G5FAV')
    fields.update(kw)
    return NS(**fields)


def _terms(harness='pi', **kw):
    fields = dict(id=harness, headless='permitted', rotation='unknown', note='')
    fields.update(kw)
    return entities.ProviderTerms(**fields)


# ── end_call ────────────────────────────────────────────────────────────────

def test_an_ended_decision_refuses_a_second_outcome_before_any_write():
    tx = FakeTx((entities.RouteDecision, Row(_decision(outcome={'state': 'ok'}))))
    with pytest.raises(ValueError, match='already has its outcome'):
        C.end_call(tx, actor=SYS, route_decision_id=RD_ID, outcome={'state': 'failed'},
                   usage={'tokens_in': 5})
    assert tx.ops() == ['get']
    assert tx.store[(entities.RouteDecision, RD_ID)].entity.outcome == {'state': 'ok'}


def test_a_missing_decision_wins_over_a_malformed_outcome():
    tx = FakeTx()
    with pytest.raises(lifecycle.NotFound):
        C.end_call(tx, actor=SYS, route_decision_id='rd_missing', outcome='not a mapping',
                   usage={'tokens_in': 5})
    assert tx.log == [('get', 'RouteDecision')]


@pytest.mark.parametrize('state', C.OUTCOMES)
def test_every_supported_outcome_state_is_accepted(state):
    tx = FakeTx((entities.RouteDecision, Row(_decision())))
    out = C.end_call(tx, actor=SYS, route_decision_id=RD_ID, outcome={'state': state})
    assert out == {'route_decision_id': RD_ID, 'state': state}
    assert tx.ops()[:2] == ['get', 'update']


def test_an_unknown_outcome_state_refuses_without_update_or_usage():
    tx = FakeTx((entities.RouteDecision, Row(_decision())))
    with pytest.raises(ValueError, match='an own call ends as one of'):
        C.end_call(tx, actor=SYS, route_decision_id=RD_ID, outcome={'state': 'done'},
                   usage={'tokens_in': 1})
    assert tx.ops() == ['get']
    assert tx.store[(entities.RouteDecision, RD_ID)].entity.outcome is None


def test_gated_without_usage_writes_no_ledger_row():
    tx = FakeTx((entities.RouteDecision, Row(_decision())))
    C.end_call(tx, actor=SYS, route_decision_id=RD_ID, outcome={'state': 'gated'}, usage=None)
    assert tx.inserted() == []
    assert tx.ops() == ['get', 'update', 'append']


def test_an_explicit_empty_usage_on_a_gated_call_records_basis_none():
    tx = FakeTx((entities.RouteDecision, Row(_decision())))
    C.end_call(tx, actor=SYS, route_decision_id=RD_ID, outcome={'state': 'gated'}, usage={})
    (ledger,) = tx.inserted()
    assert isinstance(ledger, entities.UsageLedger)
    assert ledger.basis == 'none'
    assert ledger.route_decision_id == RD_ID


def test_known_zero_figures_are_kept_and_unexpected_keys_dropped():
    tx = FakeTx((entities.RouteDecision, Row(_decision())))
    usage = {'tokens_in': 0, 'tokens_out': None, 'cache_read': 7, 'cost_usd': None,
             'surprise': 9}
    C.end_call(tx, actor=SYS, route_decision_id=RD_ID, outcome={'state': 'ok'}, usage=usage)
    (ledger,) = tx.inserted()
    assert ledger.tokens_in == 0
    assert ledger.cache_read == 7
    assert ledger.tokens_out is None
    assert ledger.cost_usd is None
    assert not hasattr(ledger, 'surprise')
    assert ledger.basis == 'reported_total'


def test_a_timeout_with_figures_is_a_partial_total_not_a_reported_one():
    tx = FakeTx((entities.RouteDecision, Row(_decision())))
    C.end_call(tx, actor=SYS, route_decision_id=RD_ID, outcome={'state': 'timeout'},
               usage={'tokens_in': 3})
    (ledger,) = tx.inserted()
    assert ledger.basis == 'partial'
    assert ledger.tokens_in == 3


def test_a_failed_ledger_insert_prevents_the_ended_event():
    tx = FakeTx((entities.RouteDecision, Row(_decision())),
                fail_insert=RuntimeError('disk full'))
    with pytest.raises(RuntimeError, match='disk full'):
        C.end_call(tx, actor=SYS, route_decision_id=RD_ID, outcome={'state': 'ok'},
                   usage={'tokens_in': 1})
    assert 'append' not in tx.ops()


def test_the_ended_event_takes_scope_from_the_decision_not_the_outcome():
    tx = FakeTx((entities.RouteDecision, Row(_decision(workspace_id=None))))
    C.end_call(tx, actor=SYS, route_decision_id=RD_ID,
               outcome={'state': 'ok', 'workspace_id': 'ws_other', 'project_id': 'prj_other'},
               usage={'tokens_in': 1})
    (event,) = tx.events()
    assert event.type == 'archeus_call.ended'
    assert event.workspace == ids.GLOBAL_WORKSPACE
    assert event.project == 'prj_01ARZ3NDEKTSV4RRFFQ69G5FAV'
    assert event.payload['purpose'] == 'titles'


# ── decide_provider_terms ───────────────────────────────────────────────────

def test_a_non_user_actor_is_refused_before_any_read_or_write():
    tx = FakeTx()
    with pytest.raises(ValueError, match='only the user answers'):
        C.decide_provider_terms(tx, actor=SYS, harness_id='pi', headless='maybe')
    assert tx.log == []


def test_invalid_headless_on_existing_terms_leaves_the_row_unchanged():
    before = _terms(headless='permitted', rotation='permitted', note='kept')
    tx = FakeTx((entities.ProviderTerms, Row(before)))
    with pytest.raises(ValueError):
        C.decide_provider_terms(tx, actor=USER, harness_id='pi', headless='maybe')
    assert 'update' not in tx.ops()
    assert tx.store[(entities.ProviderTerms, 'pi')].entity == before


def test_rotation_none_keeps_the_prior_rotation_and_the_event_reports_it():
    tx = FakeTx((entities.ProviderTerms, Row(_terms(rotation='permitted'))))
    out = C.decide_provider_terms(tx, actor=USER, harness_id='pi', headless='refused')
    stored = tx.store[(entities.ProviderTerms, 'pi')].entity
    assert stored.headless == 'refused'
    assert stored.rotation == 'permitted'
    assert out['provider_terms']['rotation'] == 'permitted'
    assert tx.events()[-1].payload == {'harness_id': 'pi', 'headless': 'refused',
                                       'rotation': 'permitted'}


def test_an_explicit_rotation_value_replaces_the_prior_one_including_refused():
    tx = FakeTx((entities.ProviderTerms, Row(_terms(rotation='permitted'))))
    C.decide_provider_terms(tx, actor=USER, harness_id='pi', headless='permitted',
                            rotation='refused')
    assert tx.store[(entities.ProviderTerms, 'pi')].entity.rotation == 'refused'
    assert tx.events()[-1].payload['rotation'] == 'refused'


def test_new_terms_are_inserted_then_read_back_then_announced():
    tx = FakeTx()
    out = C.decide_provider_terms(tx, actor=USER, harness_id='pi', headless='permitted',
                                  note='asked')
    assert tx.ops() == ['get', 'insert', 'get', 'append']
    (row,) = tx.inserted()
    assert (row.id, row.headless, row.rotation, row.note) == ('pi', 'permitted', 'unknown', 'asked')
    assert out['provider_terms']['headless'] == 'permitted'
    assert tx.events()[-1].payload == {'harness_id': 'pi', 'headless': 'permitted',
                                       'rotation': 'unknown'}


def test_a_decision_for_one_harness_does_not_touch_another():
    tx = FakeTx()
    C.decide_provider_terms(tx, actor=USER, harness_id='a', headless='permitted')
    C.decide_provider_terms(tx, actor=USER, harness_id='b', headless='refused')
    C.decide_provider_terms(tx, actor=USER, harness_id='a', headless='refused')
    assert tx.store[(entities.ProviderTerms, 'a')].entity.headless == 'refused'
    assert tx.store[(entities.ProviderTerms, 'b')].entity.headless == 'refused'
    assert tx.ops().count('update') == 1
    assert tx.store[(entities.ProviderTerms, 'b')].version == 1

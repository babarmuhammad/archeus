"""P21 slice B (ADR-0043 §2-§4, ADR-0048 D-25.4; orchestration G6, G8, G12,
G13; R13-06): own calls in flight in `live_work`, each account's consumption
and effective policy in `/v1/accounts`, and the `status` verb in words. Fake
adapters and the real database only."""

import json
import time

import pytest

from archeus.api import schemas
from archeus.cli.tui import present as P
from archeus.core.application import calls as C, conversation as CV, live, queries, resources
from archeus.core.domain import entities
from archeus.harnesses import base
from archeus.harnesses.fake import FakeCaller
from archeus.infra.db import rows

from v1.integration.test_account_protection import snapshot_call
from v1.integration.test_routing import Rig


@pytest.fixture
def r(db):
    return Rig(db)


def call(r, purpose='planner', max_run_s=1200, source=None):
    """An own call recorded and not ended: in flight until its maximum run."""
    req, snap, _ = snapshot_call(r, [FakeCaller('fake')])
    return r.do(resources.record_call_route, who=r.system, purpose=purpose,
                source=source or {'kind': 'mission', 'id': 'msn_x'}, workspace_id='ws_global',
                project_id=None, requirements=dict(req, max_run_s=max_run_s),
                snapshot=snap)['route_decision_id']


def read(r, fn, *a, **kw):
    with r.db.read() as conn:
        return fn(conn, *a, **kw)


def views(r, now=None):
    """Every account's view, as `/v1/accounts` serves it, read at *now*."""
    now = time.time() if now is None else now
    with r.db.read() as conn:
        work = live.live_work(conn, now=now)
        return {row.entity.id: resources.account_view(conn, row, work, now)
                for row in rows.where(conn, entities.Account)}


# ── G6: one live derivation ─────────────────────────────────────────────────

def test_g6_live_work_is_the_live_executions_then_the_own_calls_without_an_outcome(r):
    a = r.account('A')
    mid = r.ready(title='Ship it')
    r.dispatch(mid)                                     # an INTENT execution
    (e,) = r.all(entities.Execution, mission_id=mid)
    flying = call(r, source={'kind': 'mission', 'id': mid})
    done = call(r, purpose='brain')
    r.do(C.end_call, who=r.system, route_decision_id=done, outcome={'state': 'ok'})
    within = call(r, purpose='planner', max_run_s=600)
    lapsed = call(r, purpose='lesson', max_run_s=1)
    later = time.time() + 5                             # past the lesson's maximum run only
    work = read(r, live.live_work, now=later)
    assert [(w['kind'], w['id']) for w in work] == [
        ('execution', e.id), ('own_call', flying), ('own_call', within)]
    for w in work:
        schemas.validate(w, schemas.TYPES['LiveItem'])
    own = work[1]
    assert (own['purpose'], own['account_id'], own['mission_id'], own['mission_title']) == (
        'planner', a, mid, 'Ship it')
    assert (own['state'], own['task_id'], own['attempt'], own['context']) == (None,) * 4
    assert lapsed not in [w['id'] for w in work]
    assert within in [w['id'] for w in read(r, live.live_work)]   # still within its run, read now
    assert read(r, live.live_work, project_id='prj_none', now=later) == []
    # the account's count is the same derivation (ledger_totals.running)
    assert views(r, later)[a]['ledger']['running'] == len(work)


def test_g6_the_status_verb_names_exactly_what_status_live_lists(r):
    r.account('A')
    mid = r.ready()
    r.dispatch(mid)
    call(r, purpose='knowledge_extraction')
    text, links = r.do(lambda tx, actor: CV._status(tx, None))
    work = read(r, live.live_work)
    said = text.split(' Running now: ')[1].rstrip('.').split('; ')
    assert len(said) == len(work) == 2
    assert said[1] == 'an own call for the knowledge extraction (%s)' % work[1]['account_id']
    assert [x['ref']['id'] for x in links if x['ref']['kind'] == 'execution'] == [work[0]['id']]


# ── G8: own calls visible, still ────────────────────────────────────────────

def test_g8_an_own_call_in_flight_is_listed_and_counted_on_its_account(r):
    a = r.account('A', priority=1)
    b = r.account('B', priority=2)
    flying = call(r)
    v = views(r)
    schemas.validate(v[a], schemas.TYPES['Account'])
    assert [c['id'] for c in v[a]['consumers']] == [flying] and v[a]['ledger']['running'] == 1
    assert (v[b]['consumers'], v[b]['ledger']['running']) == ([], 0)   # only its own account
    v = v[a]
    assert [set(c) for c in v['consumers']] == [set(resources.CONSUMER_FIELDS)]   # summary only
    assert P.consumers_text(v['consumers']) == 'an own call for the planner'
    r.do(C.end_call, who=r.system, route_decision_id=flying, outcome={'state': 'ok'})
    v = views(r)[a]
    assert (v['consumers'], v['ledger']['running']) == ([], 0)
    assert P.consumers_text(v['consumers']) == 'nothing'
    # it animates nothing: no execution frame is ever written for an own call
    assert read(r, lambda c: c.execute("SELECT COUNT(*) FROM events WHERE type LIKE "
                                       "'execution.%'").fetchone()[0]) == 0


# ── G12: unknown stays unknown ──────────────────────────────────────────────

def test_g12_a_reading_that_is_missing_is_said_unknown_never_a_number(r):
    a = r.account('A')
    v = views(r)[a]
    assert v['usage'] is None                           # no window observed: no number
    assert P.consumption_text(v['ledger']) == '0 tokens · $0.00'   # nothing ran: a known 0
    call(r, purpose='brain', max_run_s=1)               # ran, never wrote its row
    v = views(r, time.time() + 5)[a]
    assert v['ledger']['complete'] == {'tokens': False, 'cost': False}
    assert P.consumption_text(v['ledger']) == 'tokens unknown · cost unknown'


def test_g12_work_in_flight_is_unknown_not_a_zero_and_accounts_lists_the_same(r):
    a = r.account('A')
    r.dispatch(r.ready())                               # an execution whose usage is not written yet
    v = views(r)[a]
    schemas.validate(v, schemas.TYPES['Account'])
    assert v['ledger'] == {'tokens_today': 0, 'cost_today': 0, 'running': 1,
                           'complete': {'tokens': False, 'cost': False}}
    assert P.consumption_text(v['ledger']) == 'tokens unknown (1 running) · cost unknown (1 running)'
    with r.db.read() as conn:
        listed = {x['id']: x for x in resources.accounts(conn)}
    assert (listed[a]['ledger'], [c['id'] for c in listed[a]['consumers']]) == (
        v['ledger'], [c['id'] for c in v['consumers']])


def test_r13_06_the_status_says_how_many_more_run_past_the_ten_it_names(r):
    r.account('A')
    for _ in range(11):
        call(r)
    text, _links = r.do(lambda tx, actor: CV._status(tx, None))
    assert text.endswith(' (+1 more).')
    assert text.count('an own call for the planner') == 10


# ── G13: effective policy parity (P21 half) ─────────────────────────────────

def test_g13_the_effective_policy_read_is_what_the_router_decided_from(r):
    a = r.account('A', priority=3, budgets={'concurrency': 2}, fallback='deny')
    b = r.account('B', consumption='last_resort')
    mid = r.ready()
    r.dispatch(mid)
    (task_rd,) = r.rds(mission_id=mid)
    own_rd = r.one(entities.RouteDecision, id=call(r))
    v = views(r)
    for rd in (task_rd, own_rd):
        fed = {x['id']: x['policy'] for x in rd.input_snapshot['accounts'] if x.get('registered')}
        assert fed == {a: v[a]['policy'], b: v[b]['policy']}
    assert (v[a]['policy']['priority'], v[a]['policy']['budgets'], v[b]['policy']['consumption']) \
        == (3, {'concurrency': 2}, 'last_resort')


# ── R13-06: `status` in words ───────────────────────────────────────────────

def test_r13_06_status_says_each_state_in_the_words_the_clients_show(r):
    r.account('A')
    mid = r.ready(title='Ship the fix')
    r.dispatch(mid)
    text, _links = r.do(lambda tx, actor: CV._status(tx, None))
    assert 'Ship the fix (Executing)' in text and 't1 attempt 1 (Starting, context' in text
    assert 'EXECUTING' not in text and 'INTENT' not in text


def test_s3_core_never_imports_the_tui_and_says_the_same_words():
    """Core says the state words from its own generated copy; the TUI's copy is the same table."""
    import pathlib
    import re
    from archeus.cli.tui import _tables
    from archeus.core.domain import words
    core = pathlib.Path(resources.__file__).resolve().parents[2] / 'core'
    assert [p.name for p in core.rglob('*.py')
            if re.search(r'from \.+cli\b|archeus\.cli\b', p.read_text(encoding='utf-8'))] == []
    assert words.LABELS == _tables.LABELS


def _keys(x):
    if isinstance(x, dict):
        for k, v in x.items():
            yield k
            yield from _keys(v)
    elif isinstance(x, list):
        for v in x:
            yield from _keys(v)


def _strings(x):
    if isinstance(x, dict):
        for v in x.values():
            yield from _strings(v)
    elif isinstance(x, list):
        for v in x:
            yield from _strings(v)
    elif isinstance(x, str):
        yield x


def test_owner_2026_10_21_the_accounts_view_never_shows_an_account_home(r, tmp_path):
    """An account's home is a path on this machine: no form of it reaches the view."""
    home = str(tmp_path / 'Work-Claude')
    a = r.account('A', home_ref=home)
    with r.db.read() as conn:
        listed = resources.accounts(conn)
        one = resources.account_view(conn, rows.get(conn, entities.Account, a))
    shown = list(_strings([listed, one]))       # every string value, unescaped
    for form in (home, str(tmp_path), base.canonical_home(home)):
        assert not any(form in v for v in shown), form
    assert all(k not in x for x in listed + [one] for k in resources.HOME_FIELDS)


def test_owner_2026_10_21_route_decision_reads_show_no_account_home(r, tmp_path):
    """GET /v1/route-decisions and /{id} strip the home at the read (review F1); the row keeps it."""
    home = str(tmp_path / 'Work-Claude')
    r.account('A', home_ref=home)
    rid = call(r)
    with r.db.read() as conn:
        listed = queries.route_decisions(conn)
        one = queries.get_route_decision(conn, rid)
        stored = rows.get(conn, entities.RouteDecision, rid).entity.input_snapshot
    shown = list(_strings([listed, one]))
    for form in (home, str(tmp_path), base.canonical_home(home)):
        assert not any(form in v for v in shown), form
    assert not {'home_ref', 'home_key'} & set(_keys([listed, one]))
    assert any(a.get('home_ref') == home for a in stored['accounts'])     # the row keeps it
    # a default account names its home in its ref (harness:canonical home): the home is said as its home
    default = {'id': None, 'ref': 'fake:' + base.canonical_home(home), 'home_ref': home}
    got = queries._public_decision({'input_snapshot': {'accounts': [default]}, 'account_ref': default['ref']})
    assert got['input_snapshot']['accounts'] == [{'id': None, 'ref': 'fake:its home'}]
    assert got['account_ref'] == 'fake:its home'
    # a registered account's ref is its home itself: that value goes, exactly
    reg = {'input_snapshot': {'accounts': [{'id': 'acc_1', 'ref': home, 'home_ref': home}]},
           'account_ref': home}
    assert queries._public_decision(reg)['account_ref'] is None


def test_owner_2026_10_21_live_work_and_every_read_body_name_no_registered_home(r, tmp_path):
    """Strip at read (owner, 2026-10-21): an own call in flight names no home, and the
    net every observe body passes through (`queries.public_body`) holds for any surface."""
    home = str(tmp_path / 'Work-Claude')
    a = r.account('A', home_ref=home)
    flying = call(r)
    with r.db.read() as conn:
        work = live.live_work(conn)
        body = {'performed_by': {'account_id': a, 'account_ref': home,
                                 'reviewer': {'account': home}}, 'home_ref': home}
        netted = queries.public_body(conn, body)
        said = queries.public_body(conn, {'text': 'kept in ' + home})
    assert said == {'text': 'kept in its home'}
    (item,) = work
    assert item['id'] == flying and 'account_ref' not in item
    assert home not in json.dumps(work) and base.canonical_home(home) not in json.dumps(work)
    assert netted == {'performed_by': {'account_id': a, 'account_ref': None,
                                       'reviewer': {'account': None}}}
    assert netted['performed_by']['account_id'] == a          # ids are not homes: kept


"""P10, the pure half (p10-design-gate §6, §17: U-*): the resource router as a
function of (requirements, snapshot) — elimination, ordering, model and effort
vocabulary, structured output, allocation ceilings, continuity, provider
terms, fallback, determinism and replay, the generated explanation. No
database, no adapter, no process: every input is the JSON a decision records.

Each test states the invariant that makes a selection right, not only which
resource came out."""

import calendar
import copy
import json
import os
import random
import subprocess
import sys
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from archeus.core.application import resources
from archeus.core.domain import entities, instants
from archeus.core.routing import router as R

POL = {'priority': 1, 'allocation_pct': 80, 'reserve_pct': 10, 'brain_reserve_pct': 10,
       'fallback': 'ask', 'budgets': {}, 'project_allow': [], 'project_deny': []}


def harness(id_, *caps, installed=True, structured='native', models=('m-large:large',),
            enforcement='hook', efforts=(), exempt=True):
    ms = []
    for m in models:
        mid, _, tier = m.partition(':')
        ms.append({'id': mid, 'tier': tier or None, 'context_window': None})
    caps = caps or ('code_edit', 'shell')
    return {'id': id_, 'installed': installed, 'capabilities': sorted(set(caps) | {'headless'}),
            'enforcement': enforcement, 'structured_output': structured,
            'efforts': list(efforts), 'models': ms, 'exempt': exempt}


def own(harness_id, why=None):
    """A harness's own account (no registration: P6's implicit account)."""
    return {'id': None, 'ref': '%s:default' % harness_id, 'harness': harness_id,
            'label': harness_id, 'registered': False, 'health': None, 'why_not': why,
            'policy': None, 'usage': None, 'ledger': None}


def acct(id_, harness_id, *, priority=1, usage=0.0, age=0, health='AVAILABLE',
         auth='api_key', resets=None, **pol):
    return {'id': id_, 'ref': id_, 'harness': harness_id, 'label': id_.upper(),
            'auth_kind': auth, 'registered': True, 'health': health, 'why_not': None,
            'policy': dict(POL, priority=priority, **pol),
            'usage': None if usage is None else {
                'windows': {'5h': usage}, 'age_s': age,
                'resets_at': {'5h': instants.written(resets)} if resets else {}},
            'ledger': {'tokens_today': 0, 'cost_today': 0, 'running': 0}}


def snap(harnesses, accounts, **kw):
    return dict({'now': '2026-09-26T10:00:00.000Z', 'harnesses': harnesses,
                 'accounts': accounts, 'terms': {}, 'affinity': None,
                 'approved_fallbacks': []}, **kw)


def call(**kw):
    return dict({'subject': 'archeus_call', 'purpose': 'brain', 'capabilities': ['headless'],
                 'structured_output': True, 'min_model_tier': None, 'models': {},
                 'preferred': {}, 'forbidden': {}, 'required': {}, 'size': None,
                 'policy': None}, **kw)


def task(items=(('write_repo', 'ALLOW', None),), **kw):
    return dict({'subject': 'task', 'capabilities': ['code_edit'], 'structured_output': False,
                 'min_model_tier': None, 'models': {}, 'preferred': {}, 'forbidden': {},
                 'required': {}, 'size': 'M', 'mission_id': 'msn_x', 'task_id': 'tsk_x',
                 'project_id': None,
                 'policy': {'decision_id': 'pdc_x', 'outcome': 'covered',
                            'items': [{'class': c, 'decision': d, 'boundary': b}
                                      for c, d, b in items]}}, **kw)


def steps(d):
    return {c['resource']: c['eliminated_at_step'] for c in d['candidates']}


# ── U-B basic selection ─────────────────────────────────────────────────────

def test_one_capable_harness_is_selected_on_its_own_account():
    d = R.route(call(), snap([harness('h')], [own('h')]))
    assert (d['result'], d['selected'], d['account_id'], d['account_ref']) == (
        'selected', 'h', None, 'h:default')


def test_an_incapable_harness_is_never_selected_even_alone():
    d = R.route(task(), snap([harness('shell_only', 'shell')], [own('shell_only')]))
    assert d['result'] == 'blocked' and steps(d) == {'shell_only': 'capability'}


def test_with_several_capable_harnesses_the_winner_is_fixed_by_the_ordering_not_by_input():
    hs = [harness('b'), harness('a'), harness('c')]
    d = R.route(call(), snap(hs, [own('c'), own('a'), own('b')]))
    assert d['selected'] == 'a'
    assert steps(d) == {'a': None, 'b': 'election', 'c': 'election'}


def test_a_preferred_harness_wins_when_valid_and_is_ignored_when_incapable():
    hs = [harness('a'), harness('b', installed=True, structured=None)]
    s = snap(hs, [own('a'), own('b')])
    assert R.route(call(preferred={'harnesses': ['a']}), s)['selected'] == 'a'
    got = R.route(call(preferred={'harnesses': ['b']}), s)
    assert got['selected'] == 'a' and steps(got)['b'] == 'capability'   # capability first


def test_a_preferred_or_required_harness_lacking_a_capability_is_still_eliminated():
    hs = [harness('a'), harness('b_pref', 'shell')]
    s = snap(hs, [own('a'), own('b_pref')])
    d = R.route(task(preferred={'harnesses': ['b_pref']}), s)
    assert d['selected'] == 'a' and steps(d)['b_pref'] == 'capability'
    d = R.route(task(required={'harnesses': ['b_pref']}), s)
    assert d['result'] == 'blocked' and steps(d)['b_pref'] == 'capability'


def test_a_preferred_account_wins_over_priority_when_valid():
    # priority runs against id order, so neither the id nor input order can pass for it
    s = snap([harness('h')], [acct('acc_a', 'h', priority=2), acct('acc_b', 'h', priority=1)])
    assert R.route(task(), s)['selected'] == 'acc_b'
    assert R.route(task(preferred={'accounts': ['acc_a']}), s)['selected'] == 'acc_a'


def test_a_preferred_account_over_its_ceiling_loses_to_a_fallback_account_under_it():
    s = snap([harness('h')], [acct('acc_a', 'h', priority=1, usage=75),
                              acct('acc_b', 'h', priority=2, usage=10)])
    d = R.route(task(preferred={'accounts': ['acc_a']}), s)
    assert d['selected'] == 'acc_b' and steps(d)['acc_a'] == 'allocation'


# ── U-M multi-harness: no hidden Claude dependency ─────────────────────────

@pytest.mark.parametrize('installed,expect', [
    ({'claude_code', 'pi'}, 'claude_code'),      # both: first by id, not by name
    ({'claude_code'}, 'claude_code'),
    ({'pi'}, 'pi'),                              # pi available without Claude
    (set(), None),                               # neither capable
])
def test_claude_and_pi_route_by_the_same_rules(installed, expect):
    hs = [harness(h, installed=h in installed) for h in ('claude_code', 'pi')]
    d = R.route(call(), snap(hs, [own(h) for h in sorted(installed)]))
    assert d['selected'] == expect


def test_no_harness_is_preferred_by_name():
    """Rename the harnesses and the ordering moves with the ids: nothing in the
    router names Claude Code (the pre-router's rule is gone, ADR-0022)."""
    for ids_ in (('claude_code', 'zz_other'), ('aa_other', 'claude_code')):
        hs = [harness(i) for i in ids_]
        assert R.route(call(), snap(hs, [own(i) for i in ids_]))['selected'] == min(ids_)


def test_claude_unavailable_routes_to_pi_and_records_why():
    hs = [harness('claude_code'), harness('pi')]
    d = R.route(call(), snap(hs, [own('claude_code', why='account rate-limited'), own('pi')]))
    assert d['selected'] == 'pi' and steps(d)['claude_code'] == 'health'


# ── U-S structured output (ADR-0022: native OR prompted) ───────────────────

@pytest.mark.parametrize('mechanism,ok', [('native', True), ('prompted', True), (None, False)])
def test_structured_output_is_met_natively_or_in_the_prompt(mechanism, ok):
    d = R.route(call(), snap([harness('h', structured=mechanism)], [own('h')]))
    assert (d['result'] == 'selected') is ok
    assert R.route(call(structured_output=False),
                   snap([harness('h', structured=mechanism)], [own('h')]))['selected'] == 'h'


def test_native_unavailable_but_prompted_available_selects_the_prompted_one():
    hs = [harness('a_native_missing', structured=None), harness('b_prompted', structured='prompted')]
    d = R.route(call(), snap(hs, [own('a_native_missing'), own('b_prompted')]))
    assert d['selected'] == 'b_prompted'
    assert [c['structured_output'] for c in d['candidates']
            if c['resource'] == 'b_prompted'] == ['prompted']


# ── U-V model and effort vocabulary ────────────────────────────────────────

def test_a_valid_preferred_model_is_used_in_its_own_harness():
    s = snap([harness('pi', models=('local/qwen', 'other'))], [own('pi')])
    assert R.route(call(models={'pi': 'local/qwen'}), s)['model'] == 'local/qwen'


def test_a_model_that_is_not_an_offer_is_dropped_never_translated():
    s = snap([harness('pi', models=('local/qwen',))], [own('pi')])
    d = R.route(call(models={'pi': 'claude-opus-5-5'}), s)
    assert (d['selected'], d['model']) == ('pi', None)
    req = call(models={'pi': 'claude-opus-5-5'}, model_required=True)
    assert steps(R.route(req, s)) == {'pi': 'model'}


def test_switching_harness_never_carries_the_previous_harness_model():
    hs = [harness('claude_code', models=('opus:large',)), harness('pi', models=('local/m',))]
    s = snap(hs, [own('claude_code', why='limited'), own('pi')])
    d = R.route(call(models={'claude_code': 'opus'}), s)
    assert (d['harness_id'], d['model']) == ('pi', None)
    d = R.route(call(models={'claude_code': 'opus', 'pi': 'local/m'}), s)
    assert (d['harness_id'], d['model']) == ('pi', 'local/m')


def test_a_tier_minimum_picks_the_smallest_offer_that_meets_it_and_excludes_unknown():
    s = snap([harness('h', models=('big:large', 'small1:small', 'mid1:mid', 'local'))],
             [own('h')])
    assert R.route(call(min_model_tier='mid'), s)['model'] == 'mid1'
    assert R.route(call(min_model_tier='large'), s)['model'] == 'big'
    only_unknown = snap([harness('h', models=('local/x',))], [own('h')])
    assert steps(R.route(call(min_model_tier='mid'), only_unknown)) == {'h': 'model'}
    assert R.route(call(min_model_tier='small'), only_unknown)['model'] == 'local/x'


def test_a_preferred_model_below_the_tier_loses_to_one_that_meets_it():
    s = snap([harness('claude_code', models=('haiku:small', 'opus:large'))], [own('claude_code')])
    d = R.route(call(models={'claude_code': 'haiku'}, min_model_tier='large'), s)
    assert d['model'] == 'opus'


def test_effort_is_kept_only_when_declared_and_eliminates_only_when_required():
    s = snap([harness('h', efforts=('low', 'high'))], [own('h')])
    assert R.route(call(effort='high'), s)['effort'] == 'high'
    assert R.route(call(effort='max'), s)['effort'] is None
    assert steps(R.route(call(effort='max', effort_required=True), s)) == {'h': 'model'}


# ── U-A allocation: a ceiling, never a quota ────────────────────────────────

@pytest.mark.parametrize('usage,ok', [(0, True), (56.9, True), (57, False), (60, False),
                                      (95, False)])
def test_a_task_starts_only_under_the_ceiling_minus_the_projected_bump(usage, ok):
    """ceiling = 80 - 10 - 10 = 60 for tasks; an M task projects +3."""
    d = R.route(task(), snap([harness('h')], [acct('acc_a', 'h', usage=usage)]))
    assert (d['result'] == 'selected') is ok


def test_an_own_call_may_use_the_brain_reserve_a_task_may_not():
    s = snap([harness('h')], [acct('acc_a', 'h', usage=65)])
    assert R.route(task(), s)['result'] != 'selected'
    assert R.route(call(), s)['selected'] == 'acc_a'           # 65 < 70


def test_the_allocation_is_a_ceiling_not_a_share_that_must_be_used():
    """A lower priority account with room is not chosen to 'use up' its
    allocation while the priority-1 account is under its own ceiling."""
    s = snap([harness('h')], [acct('acc_b', 'h', priority=1, usage=50, allocation_pct=80),
                              acct('acc_a', 'h', priority=2, usage=0, allocation_pct=100)])
    assert R.route(task(), s)['selected'] == 'acc_b'


def test_stale_usage_carries_the_penalty():
    fresh = snap([harness('h')], [acct('acc_a', 'h', usage=53, age=10)])
    stale = snap([harness('h')], [acct('acc_a', 'h', usage=53, age=R.STALE_S + 1)])
    assert R.route(task(), fresh)['result'] == 'selected'
    assert R.route(task(), stale)['result'] != 'selected'      # 53 + 5 + 3 >= 60


def test_an_exhausted_window_is_health_not_allocation_and_never_a_fallback():
    s = snap([harness('h')], [acct('acc_a', 'h', usage=100, fallback='allow')])
    d = R.route(task(), s)
    assert d['result'] == 'blocked' and steps(d) == {'acc_a': 'health'}


def test_unknown_usage_is_never_zero():
    s = snap([harness('h')], [acct('acc_a', 'h', usage=None)])
    assert steps(R.route(task(), s)) == {'acc_a': 'allocation'}
    budgeted = snap([harness('h')], [acct('acc_a', 'h', usage=None,
                                          budgets={'tokens_per_day': 100})])
    assert R.route(task(), budgeted)['selected'] == 'acc_a'
    spent = copy.deepcopy(budgeted)
    spent['accounts'][0]['ledger']['tokens_today'] = 100
    assert steps(R.route(task(), spent)) == {'acc_a': 'allocation'}


def test_multiple_accounts_at_the_same_priority_break_ties_by_id():
    accts = [acct('acc_c', 'h'), acct('acc_a', 'h'), acct('acc_b', 'h')]
    assert R.route(task(), snap([harness('h')], accts))['selected'] == 'acc_a'


# ── U-F fallback (resource-router §7) ──────────────────────────────────────

@pytest.mark.parametrize('fallback,result', [('allow', 'fallback'), ('ask', 'ask'),
                                             ('deny', 'blocked')])
def test_fallback_follows_the_account_policy(fallback, result):
    s = snap([harness('h')], [acct('acc_a', 'h', usage=100, priority=1),
                              acct('acc_b', 'h', usage=79, priority=2, fallback=fallback)])
    d = R.route(task(), s)
    assert d['result'] == result
    if result != 'blocked':
        assert d['account_id'] == 'acc_b'
    assert d['selected'] == ('acc_b' if result == 'fallback' else None)


def test_an_approved_fallback_runs_without_asking_again():
    s = snap([harness('h')], [acct('acc_b', 'h', usage=79, fallback='ask')],
             approved_fallbacks=['acc_b'])
    assert R.route(task(), s)['result'] == 'fallback'


def test_fallback_is_never_skipped_while_one_is_allowed():
    s = snap([harness('h')], [acct('acc_a', 'h', usage=70, fallback='ask', priority=1),
                              acct('acc_b', 'h', usage=70, fallback='allow', priority=2)])
    d = R.route(task(), s)
    assert (d['result'], d['selected']) == ('fallback', 'acc_b')


def test_a_blocked_decision_names_the_earliest_reset():
    # the router's input is written instants (ms, Z: instants.ahead, T-106 r4); raw text is the builder's
    s = snap([harness('h')], [acct('acc_a', 'h', usage=100, resets='2026-09-26T16:05:00.000Z'),
                              acct('acc_b', 'h', usage=100, resets='2026-09-26T14:30:00.000Z')])
    assert R.route(task(), s)['unblock_at'] == '2026-09-26T14:30:00.000Z'


_POLICY = {'priority': 1, 'allocation_pct': 80, 'reserve_pct': 10, 'brain_reserve_pct': 10,
           'fallback': 'ask', 'budgets': {}, 'project_allow': [], 'project_deny': [],
           'consumption': None}


def _live(monkeypatch, raw):
    """The accounts the snapshot builder writes for raw provider resets ({account: text})."""
    now = datetime(2026, 9, 26, 10, tzinfo=timezone.utc)
    accounts = [SimpleNamespace(id=i, harness_id='h', home_ref=None, label=i.upper(),
                                auth_kind='api_key', health='AVAILABLE') for i in raw]

    def where(conn, cls, **kw):
        if cls is entities.Account:
            return [SimpleNamespace(entity=a) for a in accounts]
        return [SimpleNamespace(entity=SimpleNamespace(account_id=a.id, **_POLICY))
                for a in accounts]

    feed = SimpleNamespace(read=lambda ref: {
        'windows': {'5h': 100}, 'resets_at': {'5h': raw[ref['id']]},
        'observed_at': now.timestamp(), 'source': 'feed'})
    monkeypatch.setattr(resources.rows, 'where', where)
    monkeypatch.setattr(resources, 'ledger_totals',
                        lambda conn, aid, today, at: {'tokens_today': 0, 'cost_today': 0, 'running': 0})
    out, _readings = resources._registered(None, ['h'], feed, now.timestamp())
    return out


def _raw(id_, reset):
    """An account whose snapshot carries a provider's text, as a legacy decision does."""
    a = acct(id_, 'h', usage=100)
    a['usage']['resets_at'] = {'5h': reset}
    return a


# ({account: the provider's reset text}, the unblock_at 533e3e9 wrote for it). Cases A
# and B are the offset readings the router ordered wrong (T-106 r8, review of d684947).
_RESET_CASES = [
    ({'acc_a': '2026-09-26T12:00:00+02:00'}, None),                       # equal to now
    ({'acc_a': '2026-09-26T10:00:00Z'}, None),                            # equal to now, no ms
    ({'acc_a': 'soon'}, None),                                            # unreadable
    ({'acc_a': '2026-09-26T14:30:00Z'}, '2026-09-26T14:30:00.000Z'),
    ({'acc_a': '2026-09-26T16:00:00+02:00'}, '2026-09-26T16:00:00.000+02:00'),
    ({'acc_a': '2026-09-26T13:00:00+02:00', 'acc_b': '2026-09-26T12:00:00Z'},   # A: 11:00Z first
     '2026-09-26T13:00:00.000+02:00'),
    ({'acc_a': '2026-09-26T09:30:00-01:00', 'acc_b': '2026-09-26T14:00:00Z'},   # B: 10:30Z, ahead
     '2026-09-26T09:30:00.000-01:00'),
    ({'acc_a': '2026-09-26T12:00:00+02:00', 'acc_b': '2026-09-26T14:30:00Z'},   # equal to now, beside a wait
     '2026-09-26T14:30:00.000Z'),
]


@pytest.mark.parametrize('raw, unblock_at', _RESET_CASES)
def test_T106r8_the_router_orders_readings_by_instant_not_by_text(raw, unblock_at):
    s = snap([harness('h')], [acct(i, 'h', usage=100, resets=r) for i, r in raw.items()])
    assert R.route(task(), s)['unblock_at'] == unblock_at


@pytest.mark.parametrize('raw, unblock_at', _RESET_CASES)
def test_T106r8_the_builder_keeps_each_reset_an_instant_the_router_orders(monkeypatch, raw, unblock_at):
    assert R.route(task(), snap([harness('h')], _live(monkeypatch, raw)))['unblock_at'] == unblock_at


def test_T106r8_the_builder_writes_raw_resets_as_instants_and_names_the_earliest(monkeypatch):
    """The original assertion on raw provider text: the snapshot builder writes each
    reset as an instant (ms, Z), and the router names the earliest of them."""
    out = _live(monkeypatch, {'acc_a': '2026-09-26T16:05:00Z', 'acc_b': '2026-09-26T14:30:00Z'})
    assert R.route(task(), snap([harness('h')], out))['unblock_at'] == '2026-09-26T14:30:00.000Z'


@pytest.mark.parametrize('raw, unblock_at', _RESET_CASES)
def test_T106r8_a_decision_recorded_with_raw_resets_replays_as_it_was_decided(raw, unblock_at):
    """A decision recorded before the router compared written instants holds the
    providers' text. Its replay decides as the router that recorded it did (533e3e9)."""
    s = snap([harness('h')], [_raw(i, r) for i, r in raw.items()])
    d = resources.replay(SimpleNamespace(requirements=task(), input_snapshot=s))
    assert (d['result'], d['unblock_at']) == ('blocked', unblock_at)


@pytest.mark.parametrize('raw, unblock_at', _RESET_CASES)
def test_T106r8_a_decision_recorded_in_the_written_form_replays_the_same(monkeypatch, raw, unblock_at):
    """A decision recorded by the builder holds {at, key} resets; its replay keeps them."""
    s = snap([harness('h')], _live(monkeypatch, raw))
    d = resources.replay(SimpleNamespace(requirements=task(), input_snapshot=s))
    assert (d['result'], d['unblock_at']) == ('blocked', unblock_at)


# ── U-C continuity ─────────────────────────────────────────────────────────

def test_the_same_account_is_kept_when_it_is_still_valid():
    accts = [acct('acc_a', 'h', priority=1), acct('acc_b', 'h', priority=2)]
    s = snap([harness('h')], accts, affinity={'harness': 'h', 'account': 'acc_b'})
    d = R.route(task(), s)
    assert d['selected'] == 'acc_b' and 'already running there' in d['why']


def test_continuity_never_overrides_capability_or_allocation():
    accts = [acct('acc_a', 'h', priority=1), acct('acc_b', 'h', priority=2, usage=90)]
    s = snap([harness('h')], accts, affinity={'harness': 'h', 'account': 'acc_b'})
    assert R.route(task(), s)['selected'] == 'acc_a'
    s = snap([harness('h'), harness('shell', 'shell')], [acct('acc_a', 'h'), own('shell')],
             affinity={'harness': 'shell', 'account': 'shell:default'})
    assert R.route(task(), s)['selected'] == 'acc_a'


def test_after_the_previous_account_becomes_unavailable_the_fallback_is_deterministic():
    accts = [acct('acc_c', 'h', priority=3), acct('acc_b', 'h', priority=2),
             acct('acc_a', 'h', priority=1, health='DISABLED')]
    s = snap([harness('h')], accts, affinity={'harness': 'h', 'account': 'acc_a'})
    assert {R.route(task(), s)['selected'] for _ in range(5)} == {'acc_b'}


# ── U-E enforcement (resource-router §3 over P9's decision record) ─────────

@pytest.mark.parametrize('mode,items,ok', [
    ('none', [('write_repo', 'ALLOW', None)], True),
    ('none', [('write_repo', 'ASK', None)], False),
    ('none', [('write_repo', 'ALLOW_WITHIN_BOUNDARY', {'paths': ['src/**']})], False),
    ('sandbox', [('write_repo', 'ALLOW_WITHIN_BOUNDARY', {'paths': ['src/**']})], True),
    ('sandbox', [('git_push', 'ALLOW_WITHIN_BOUNDARY', {'branches': ['feat/*']})], False),
    ('sandbox', [('write_repo', 'ASK', None)], False),
    ('hook', [('git_push', 'ASK', None)], True),
])
def test_enforcement_follows_the_authorised_items(mode, items, ok):
    d = R.route(task(items=items), snap([harness('h', enforcement=mode)], [own('h')]))
    assert (d['result'] == 'selected') is ok


def test_an_own_call_needs_no_enforcement():
    d = R.route(call(), snap([harness('pi', enforcement='none')], [own('pi')]))
    assert d['selected'] == 'pi'


# ── U-T provider terms, first check (ADR-0021) ─────────────────────────────

@pytest.mark.parametrize('answer,ok', [('permitted', True), ('refused', False),
                                       ('unknown', False), (None, False)])
def test_a_real_harness_needs_permitted_terms_and_a_scripted_one_never_does(answer, ok):
    terms = {} if answer is None else {'pi': {'headless': answer, 'rotation': 'unknown'}}
    real = snap([harness('pi', exempt=False)], [own('pi')], terms=terms)
    assert (R.route(call(), real)['result'] == 'selected') is ok
    scripted = snap([harness('pi', exempt=True)], [own('pi')], terms=terms)
    assert R.route(call(), scripted)['selected'] == 'pi'


def test_rotation_across_subscriptions_needs_its_own_permission():
    accts = [acct('acc_a', 'h', priority=1, auth='subscription_oauth', usage=90),
             acct('acc_b', 'h', priority=2, auth='subscription_oauth'),
             acct('acc_k', 'h', priority=3)]                # an API key is not rotation
    terms = {'h': {'headless': 'permitted', 'rotation': 'unknown'}}
    d = R.route(call(), snap([harness('h', exempt=False)], accts, terms=terms))
    assert steps(d)['acc_b'] == 'provider_terms' and d['selected'] == 'acc_k'
    terms['h']['rotation'] = 'permitted'
    assert R.route(call(), snap([harness('h', exempt=False)], accts,
                                terms=terms))['selected'] == 'acc_b'


# ── U-R restrictions ───────────────────────────────────────────────────────

def test_forbidden_and_required_resources_and_project_rules():
    s = snap([harness('h')], [acct('acc_a', 'h', project_deny=['prj_x']),
                              acct('acc_b', 'h', priority=2, project_allow=['prj_y'])])
    assert steps(R.route(task(project_id='prj_x'), s)) == {'acc_a': 'restriction',
                                                           'acc_b': 'restriction'}
    assert R.route(task(project_id='prj_y'), s)['selected'] == 'acc_a'    # priority
    assert steps(R.route(task(), s))['acc_b'] == 'restriction'     # reserved for prj_y
    assert R.route(task(project_id='prj_y', preferred={'accounts': ['acc_b']}),
                   s)['selected'] == 'acc_b'
    assert R.route(task(forbidden={'accounts': ['acc_a']}), s)['result'] == 'blocked'
    assert R.route(call(required={'accounts': ['acc_b']}, project_id='prj_y'),
                   s)['selected'] == 'acc_b'


def test_a_disabled_or_unverified_account_is_never_routed_and_degraded_only_by_fallback():
    for health in ('DISABLED', 'UNVERIFIED', 'UNAUTHENTICATED', 'OPEN', 'LIMITED'):
        s = snap([harness('h')], [acct('acc_a', 'h', health=health, fallback='allow')])
        assert R.route(task(), s)['result'] == 'blocked', health
    s = snap([harness('h')], [acct('acc_a', 'h', health='DEGRADED', fallback='allow')])
    assert R.route(task(), s)['result'] == 'fallback'


def test_O7_an_open_start_breaker_takes_the_harness_out_and_half_open_lets_it_try():
    """T-106: the breaker is a fact of the snapshot; open stops the harness at
    `breaker` with its last error and says when it may try again, half-open
    (and a snapshot recorded before the field) routes as before."""
    until = '2026-09-26T10:05:00.000Z'
    hs = [harness('a'), harness('b')]
    hs[0]['breaker'] = {'state': 'open', 'until': until, 'error': 'no process'}
    d = R.route(task(), snap(hs, [own('a'), own('b')]))
    assert (d['result'], d['harness_id'], steps(d)['a']) == ('selected', 'b', 'breaker')
    assert next(c['reason'] for c in d['candidates'] if c['harness'] == 'a') == (
        'cannot start: no process')
    d = R.route(task(), snap(hs[:1], [own('a')]))
    assert (d['result'], d['unblock_at']) == ('blocked', until)
    assert R.explain(d, task()).startswith('Nothing could run this until %s.' % until)
    hs[0]['breaker'] = {'state': 'half_open', 'until': None, 'error': 'no process'}
    assert R.route(task(), snap(hs[:1], [own('a')]))['harness_id'] == 'a'
    del hs[0]['breaker']
    assert R.route(task(), snap(hs[:1], [own('a')]))['harness_id'] == 'a'


# ── U-D determinism, replay, explanation ───────────────────────────────────

def _world(seed):
    rnd = random.Random(seed)
    hs = [harness('h%d' % i, 'code_edit' if rnd.random() < .8 else 'shell',
                  structured=rnd.choice(['native', 'prompted', None]),
                  installed=rnd.random() < .9) for i in range(3)]
    accts = []
    for i in range(rnd.randint(0, 5)):
        accts.append(acct('acc_%02d' % i, rnd.choice(hs)['id'], priority=rnd.randint(1, 3),
                          usage=rnd.choice([None, 0, 30, 58, 61, 99, 100]),
                          fallback=rnd.choice(['allow', 'ask', 'deny']),
                          age=rnd.choice([0, 500]),
                          health=rnd.choice(['AVAILABLE', 'CONSTRAINED', 'DEGRADED',
                                             'DISABLED'])))
    have = {a['harness'] for a in accts}
    accts += [own(h['id']) for h in hs if h['installed'] and h['id'] not in have]
    return hs, accts


@pytest.mark.parametrize('seed', range(40))
def test_P_properties_over_generated_worlds(seed):
    """Property tests (resource-router §11): ordering of the input never
    changes the decision; a selected account is under its ceiling; nothing
    DENY-authorised is routed (the router is never asked); replay is equal."""
    hs, accts = _world(seed)
    req = task() if seed % 2 else call()
    base = R.route(req, snap(hs, accts))
    rnd = random.Random(seed)
    for _ in range(3):
        h2, a2 = hs[:], accts[:]
        rnd.shuffle(h2)
        rnd.shuffle(a2)
        assert R.route(req, snap(h2, a2)) == base
    assert R.replay({'requirements': json.loads(json.dumps(req)),
                     'input_snapshot': json.loads(json.dumps(snap(hs, accts)))}) == base
    if base['result'] == 'selected' and base['account_id']:
        (c,) = [c for c in base['candidates'] if c['resource'] == base['selected']]
        assert c['usage'] + R.PROJECTED.get(req['size'], 0) < c['ceiling']
    for c in base['candidates']:
        assert (c['eliminated_at_step'] is None) == (c['resource'] == base['selected']
                                                     and base['result'] == 'selected')
        if c['eliminated_at_step'] not in (None, 'election'):
            assert c['reason']


def test_rejected_candidates_carry_deterministic_reasons():
    s = snap([harness('a', 'shell'), harness('b', installed=False)], [own('a')])
    d1, d2 = R.route(task(), s), R.route(task(), s)
    assert d1['candidates'] == d2['candidates']
    assert [(c['resource'], c['eliminated_at_step'], c['reason']) for c in d1['candidates']] == [
        ('a', 'capability', 'lacks code_edit'), ('b', 'installed', 'not installed')]


def test_the_explanation_is_generated_from_the_record_and_names_priority_and_label():
    s = snap([harness('fake')], [acct('acc_w', 'fake', priority=1, usage=42),
                                 acct('acc_x', 'fake', priority=2, usage=90)])
    d = R.route(task(), s)
    text = R.explain(d, task())
    assert text.startswith('I used ACC_W (fake, its default model) because it is your '
                           'priority-1 account, at 42% of its window against a 60% ceiling.')
    assert 'ACC_X — usage at 90%' in text
    assert R.explain(d, task()) == text


def test_the_router_reads_nothing_but_its_arguments():
    """Pure: the same JSON in gives the same JSON out, and the inputs are not
    modified (the decision is built beside them)."""
    s = snap([harness('h')], [acct('acc_a', 'h')])
    req = task()
    before = json.dumps([req, s], sort_keys=True)
    R.route(req, s)
    assert json.dumps([req, s], sort_keys=True) == before


# ── Correction r4 (review of 58b5743) ───────────────────────────────────────

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))

# A naive provider reset is UTC by the router's rule. Run under TZ values of the
# opposite signs, the router's string and route_wait must still name the same
# instant (10:02Z): before the fix route_wait read the naive string in local time.
_ZONE_PROBE = r'''
import calendar, json
from datetime import datetime, timezone
from types import SimpleNamespace
from archeus.core.domain import instants
from archeus.core.application import resources
from archeus.infra.db import rows
now = datetime(2026, 9, 26, 10, 0, tzinfo=timezone.utc)
ahead = instants.ahead('2026-09-26T10:02:00', now)['at']
class _Conn:
    def execute(self, sql, args=()):
        return self
    def fetchone(self):
        return {'x': 1}
rows.decode = lambda cls, rec: SimpleNamespace(entity=SimpleNamespace(
    result='blocked', unblock_at=ahead, candidates=[{'eliminated_at_step': 'breaker'}]))
wait = resources.route_wait(_Conn(), 'task', now.timestamp())
local = datetime(2026, 9, 26, 10).timestamp() - calendar.timegm((2026, 9, 26, 10, 0, 0))
print(json.dumps({'local_offset': local, 'unblock_at': ahead, 'wait': wait}))
'''


@pytest.mark.parametrize('tz', ['XYZ-2', 'XYZ+5'])   # the CRT reads TZ: UTC+2 (east), UTC-5 (west)
def test_T106r4_a_naive_reset_names_the_same_instant_in_every_local_zone(tz):
    env = dict(os.environ, TZ=tz, PYTHONPATH=ROOT)
    out = subprocess.run([sys.executable, '-c', _ZONE_PROBE], cwd=ROOT, env=env,
                         capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr[-2000:]
    got = json.loads(out.stdout.strip().splitlines()[-1])
    assert got['local_offset'] != 0                     # the probe really ran off UTC
    assert got['wait'] == calendar.timegm((2026, 9, 26, 10, 2, 0))


def test_T106r4_a_naive_reset_is_an_aware_instant_on_every_platform():
    """Platform-independent: no timestamp() on a naive value (OSError on Windows
    outside 1970-2038), and the value that leaves the router is aware."""
    now = datetime(2026, 9, 26, 10, tzinfo=timezone.utc)
    assert instants.instant('9999-12-31T23:59:59').tzinfo is not None
    assert instants.ahead('9999-12-31T23:59:59', now)['at'] == '9999-12-31T23:59:59.000Z'
    assert instants.ahead('1960-01-01T00:00:00', now) is None


def test_T106r8_an_offset_reset_is_written_as_given_and_keyed_in_utc():
    """The text keeps the reset's own offset (533e3e9's replay text); the key is the same
    instant in UTC, the form the router sorts by. A reset whose UTC form is past the
    platform's range is no wait, not an error (it would stop Core)."""
    now = datetime(2026, 9, 26, 10, tzinfo=timezone.utc)
    assert instants.ahead('2026-09-26T13:00:00+02:00', now) == {
        'at': '2026-09-26T13:00:00.000+02:00', 'key': '2026-09-26T11:00:00.000Z'}
    assert instants.ahead('9999-12-31T23:59:59-01:00', now) is None


def test_T106r4_resets_that_are_not_a_mapping_are_no_wait_and_no_error():
    a = acct('acc_a', 'h', usage=100.0)                # at the allocation: eliminated there
    a['usage']['resets_at'] = 'soon'
    d = R.route(task(), snap([harness('h')], [a]))
    assert (d['result'], d['unblock_at']) == ('blocked', None)


def test_T106r5_a_reset_within_a_millisecond_of_now_is_no_wait():
    """The check and the written text use one instant: a reset 0.5 ms after now is
    not after it, so it is not written as now and waited on (one extra pass)."""
    now = datetime(2026, 9, 26, 10, tzinfo=timezone.utc)
    assert instants.ahead('2026-09-26T10:00:00.000500', now) is None

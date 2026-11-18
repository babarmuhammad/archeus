"""T-1435 - authorization.py 437-478 (first_denial, record_plan_denial), round-15
gap probes. Early returns for a denial no longer in force and the PLANNING
wait-in-place arm are already asserted elsewhere and are not repeated here.

Selected branches, in rank order:
  1 record_plan_denial refuses a mission that is not planning, writing nothing  (455-457)
  2 REASONING: _fire plan_denied with facts.denial and planning_blocked extra    (467-471)
  3 blocked payload: DENY items only, judged order, round_seq and decision id    (462-466)
  4 the DENY decision: outcome denied, stage plan, reasons joined with '; '     (462-463)
  5 the returned state is re-read after the move                                (477-478)
  6 REPLANNING is a planning state and takes the in-place arm                   (455, 472-476)
  7 first_denial with no specs returns ([], None) and judges nothing            (437-445)
  8 first_denial accumulates items in spec order and returns the last ctx       (440-444)
  9 first_denial passes actor and now through to evaluate_task                  (441-443)
 10 first_denial defaults missing keys to ()                                   (441-443)
"""

from dataclasses import dataclass
from types import SimpleNamespace

from archeus.core.application import authorization as A

NOW = 'NOW'


@dataclass
class Facts:
    denial: object = None
    tag: str = 'base'


class Missions:
    def __init__(self, facts=None):
        self.fired = []
        self._facts = facts or Facts()
        self.on_fire = None

    def facts(self, tx, row):
        return self._facts

    def _fire(self, tx, mission_id, trigger, *, actor, facts, reason, extra):
        self.fired.append(dict(trigger=trigger, actor=actor, facts=facts, reason=reason,
                               extra=extra))
        if self.on_fire:
            self.on_fire()


def _mission(state, mid='m1'):
    return SimpleNamespace(id=mid, state=state, workspace_id='w', project_id='p')


def _tx(calls):
    return SimpleNamespace(conn=object(), now=NOW,
                           update=lambda *a, **k: calls.append(('update', a, k)),
                           append=lambda ev: calls.append(('append', ev)))


def _install(monkeypatch, mission, items_by_key):
    """Fakes the lifecycle load, the judge, the decision writer and the event."""
    judged, records = [], []
    monkeypatch.setattr(A.lifecycle, 'load',
                        lambda tx, cls, mid: SimpleNamespace(entity=mission))

    def evaluate(policy, conn, m, key, classes, **kw):
        judged.append((key, kw))
        return items_by_key.get(key, ([], None))

    monkeypatch.setattr(A, 'evaluate_task', evaluate)

    def record(tx, **kw):
        records.append(kw)
        return SimpleNamespace(id='dec_1')

    monkeypatch.setattr(A, 'record', record)
    monkeypatch.setattr(A, 'new_event', lambda *a, **k: ('EV', a, k))
    return judged, records


def _item(task, cls, decision, rule='r0', reason='why'):
    return {'task': task, 'class': cls, 'decision': decision, 'deciding_rule': rule,
            'reason': reason}


def test_a_mission_not_in_planning_is_refused_and_nothing_is_written(monkeypatch):
    """authorization.py:455-457 - the state guard: an EXECUTING mission gets
    recorded False with the state in the reason, and neither the judge nor the
    decision writer nor the fire runs. Removed, a denial would be written onto
    a mission that is already running."""
    mission = _mission('EXECUTING')
    judged, records = _install(monkeypatch, mission, {})
    missions = Missions()
    calls = []
    out = A.record_plan_denial(_tx(calls), actor='a', policy=object(), missions=missions,
                               mission_id='m1', specs=[{'key': 't1'}])
    assert out == {'recorded': False, 'why': 'the mission is EXECUTING, not planning'}
    assert judged == [] and records == [] and missions.fired == [] and calls == []


def test_a_reasoning_denial_fires_plan_denied_with_the_denial_on_the_facts(monkeypatch):
    """authorization.py:467-471 - the REASONING arm: plan_denied with the decision id
    set on a replaced copy of the facts and the blocked payload as extra, reason
    naming the first denied item. Removed, the mission would not record why it was
    blocked, and the facts would not reach the guard."""
    mission = _mission('REASONING')
    _install(monkeypatch, mission,
             {'t1': ([_item('t1', 'destructive', 'DENY', 'r9', 'no')], None)})
    missions = Missions(Facts(tag='kept'))
    A.record_plan_denial(_tx([]), actor='a', policy=object(), missions=missions,
                         mission_id='m1', specs=[{'key': 't1'}], round_seq=4)
    (fire,) = missions.fired
    assert fire['trigger'] == 'plan_denied' and fire['actor'] == 'a'
    assert fire['facts'] == Facts(denial='dec_1', tag='kept')
    assert fire['reason'] == 'policy denies the plan: no'
    assert fire['extra']['planning_blocked']['policy_decision_id'] == 'dec_1'


def test_the_blocked_payload_lists_only_denials_in_judged_order_with_the_round(monkeypatch):
    """authorization.py:464-466 - denied is the DENY items only, each with task,
    class and the deciding rule, in judged order; ALLOW and ASK are absent and
    round_seq rides along. Removed or filtered wrong, the mission shows a denial
    for an action that was never refused."""
    items = {'t1': ([_item('t1', 'deploy', 'ALLOW'), _item('t1', 'destructive', 'DENY', 'r9')],
                    None),
             't2': ([_item('t2', 'deploy', 'ASK'), _item('t2', 'read', 'DENY', 'r8')], None)}
    mission = _mission('REASONING')
    _install(monkeypatch, mission, items)
    missions = Missions()
    A.record_plan_denial(_tx([]), actor='a', policy=object(), missions=missions,
                         mission_id='m1', specs=[{'key': 't1'}, {'key': 't2'}], round_seq=4)
    blocked = missions.fired[0]['extra']['planning_blocked']
    assert blocked == {'kind': 'policy', 'policy_decision_id': 'dec_1', 'round_seq': 4,
                       'denied': [{'task': 't1', 'class': 'destructive', 'rule': 'r9'},
                                  {'task': 't2', 'class': 'read', 'rule': 'r8'}]}


def test_the_decision_is_a_plan_deny_whose_reason_joins_every_denial(monkeypatch):
    """authorization.py:462-463 - record is called with DENY, outcome denied, stage
    plan, and the reasons of all denied items joined with '; '. Removed or joined
    with the wrong separator, the decision row would not explain every denial."""
    items = {'t1': ([_item('t1', 'destructive', 'DENY', reason='no'),
                     _item('t1', 'delete', 'DENY', reason='nope')], None)}
    mission = _mission('PLANNING')
    _judged, records = _install(monkeypatch, mission, items)
    A.record_plan_denial(_tx([]), actor='a', policy=object(), missions=Missions(),
                         mission_id='m1', specs=[{'key': 't1'}])
    (rec,) = records
    assert (rec['decision'], rec['outcome'], rec['stage']) == ('DENY', 'denied', 'plan')
    assert rec['reason'] == 'no; nope'


def test_the_returned_state_is_read_again_after_the_move(monkeypatch):
    """authorization.py:477-478 - the state is loaded after the fire, so a move
    that changes it is what the caller sees. Removed, the pre-move state would be
    returned and the caller would believe the mission never left REASONING."""
    mission = _mission('REASONING')
    _install(monkeypatch, mission, {'t1': ([_item('t1', 'x', 'DENY')], None)})
    missions = Missions()

    def move():
        mission.state = 'BLOCKED'

    missions.on_fire = move
    out = A.record_plan_denial(_tx([]), actor='a', policy=object(), missions=missions,
                               mission_id='m1', specs=[{'key': 't1'}])
    assert out == {'recorded': True, 'policy_decision_id': 'dec_1', 'state': 'BLOCKED'}


def test_a_replanning_mission_waits_in_place_with_the_block_recorded(monkeypatch):
    """authorization.py:455, 472-476 - REPLANNING is in PLANNING_STATES, so it is
    judged, and it takes the in-place arm: planning_blocked is updated and no fire
    runs. Removed from PLANNING_STATES, a replanning mission is refused as not
    planning and the denial is lost."""
    mission = _mission('REPLANNING')
    _install(monkeypatch, mission, {'t1': ([_item('t1', 'x', 'DENY')], None)})
    missions = Missions()
    calls = []
    out = A.record_plan_denial(_tx(calls), actor='a', policy=object(), missions=missions,
                               mission_id='m1', specs=[{'key': 't1'}])
    assert out['recorded'] is True and out['state'] == 'REPLANNING'
    assert missions.fired == []
    assert [c[0] for c in calls] == ['update', 'append']


def test_first_denial_with_no_specs_judges_nothing_and_returns_no_context(monkeypatch):
    """authorization.py:437-445 - an empty spec list returns ([], None) and never
    calls evaluate_task. Removed, an empty plan would be judged with no context."""
    called = []
    monkeypatch.setattr(A, 'evaluate_task', lambda *a, **k: called.append(a) or ([], None))
    assert A.first_denial(object(), object(), _mission('PLANNING'), [], now=NOW) == ([], None)
    assert called == []


def test_first_denial_accumulates_items_in_spec_order_and_returns_the_last_context(
        monkeypatch):
    """authorization.py:440-444 - items from each spec are appended in spec order and
    the returned context is the last spec's. Removed or reordered, the denial
    list would name tasks out of plan order."""
    results = {'k1': ([_item('k1', 'a', 'ALLOW')], 'ctx1'),
               'k2': ([_item('k2', 'b', 'DENY')], 'ctx2')}
    monkeypatch.setattr(A, 'evaluate_task', lambda p, c, m, key, cl, **kw: results[key])
    items, ctx = A.first_denial(object(), object(), _mission('PLANNING'),
                                [{'key': 'k1'}, {'key': 'k2'}], now=NOW)
    assert [i['task'] for i in items] == ['k1', 'k2'] and ctx == 'ctx2'


def test_first_denial_passes_the_actor_and_the_time_to_the_judge(monkeypatch):
    """authorization.py:441-443 - actor and now go to evaluate_task as keywords.
    Removed, the judge would evaluate without who is acting and at what time."""
    seen = []
    monkeypatch.setattr(A, 'evaluate_task',
                        lambda p, c, m, key, cl, **kw: seen.append(kw) or ([], None))
    A.first_denial(object(), object(), _mission('PLANNING'), [{'key': 'k1'}], now=NOW,
                   actor='alice')
    assert seen[0]['now'] == NOW and seen[0]['actor'] == 'alice'


def test_first_denial_defaults_missing_spec_keys_to_empty_tuples(monkeypatch):
    """authorization.py:441-443 - a spec with only a key passes (), () and () for
    action classes, capabilities and touches. Removed, the judge would receive
    None and fail on iteration for a bare spec."""
    seen = []
    monkeypatch.setattr(A, 'evaluate_task', lambda p, c, m, key, cl, **kw: (
        seen.append((key, cl, kw['capabilities'], kw['touches'])) or ([], None)))
    A.first_denial(object(), object(), _mission('PLANNING'), [{'key': 'k1'}], now=NOW)
    assert seen == [('k1', (), (), ())]

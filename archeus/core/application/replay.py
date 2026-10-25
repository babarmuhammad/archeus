"""Replay & Recovery read: durable rows, with event-only settlement attribution."""

import json

from ...infra.db import rows
from ...infra.db.writer import NotFound
from ...infra.eventlog import outbox, retention
from ..domain import entities, ids, states
from . import queries
from .public import system_value

ANSWER = ('INTENDED', 'AUTHORIZED', 'RECORDED', 'MAY-HAVE-TAKEN-EFFECT',
          'UNCERTAIN', 'SUSPENDED', 'RECONCILED', 'NONE')

# T-147 Part A; ENDED_REJECTED is RECORDED (owner clarification, 2026-10-25).
CATEGORIES = (
    ('idea', 'CAPTURED UNDERSTOOD SCHEDULED PARKED EXPLORED PLANNED VALIDATED DISCARDED CONCEPT IMPLEMENTING', 'INTENDED'),
    ('idea', 'COMPLETED LEARNED', 'RECORDED'),
    ('mission', 'CREATED UNDERSTANDING CONTEXT_GATHERING REASONING PLANNING REPLANNING RESUMED', 'INTENDED'),
    ('mission', 'BLOCKED APPROVAL_REQUIRED PAUSED REVIEWING', 'SUSPENDED'),
    ('mission', 'APPROVED', 'AUTHORIZED'),
    ('mission', 'CANCELLED FAILED COMPLETED', 'RECORDED'),
    ('mission', 'EXECUTING VERIFYING', 'MAY-HAVE-TAKEN-EFFECT'),
    ('plan', 'DRAFT PROPOSED', 'INTENDED'),
    ('plan', 'APPROVED REJECTED', 'AUTHORIZED'),
    ('plan', 'SUPERSEDED', 'RECORDED'),
    ('task', 'PENDING READY', 'INTENDED'),
    ('task', 'SKIPPED', 'NONE'),
    ('task', 'ROUTING RUNNING VERIFYING', 'MAY-HAVE-TAKEN-EFFECT'),
    ('task', 'BLOCKED AWAITING_APPROVAL PAUSED', 'SUSPENDED'),
    ('task', 'FAILED SUCCEEDED CANCELLED', 'RECORDED'),
    ('execution', 'INTENT', 'INTENDED'),
    ('execution', 'STARTING RUNNING PAUSING HANDING_OFF STOPPING', 'MAY-HAVE-TAKEN-EFFECT'),
    ('execution', 'ABANDONED', 'NONE'),
    ('execution', 'LOST', 'UNCERTAIN'),
    ('execution', 'AWAITING_APPROVAL PAUSED', 'SUSPENDED'),
    ('execution', 'ENDED_HANDOFF ENDED_OK ENDED_ERROR ENDED_REJECTED', 'RECORDED'),
    ('execution', 'ENDED_KILLED', 'RECONCILED'),
    ('session', 'OPEN', 'UNKNOWN'),
    ('session', 'CLOSED', 'RECORDED'),
    ('session', 'LOST', 'UNCERTAIN'),
    ('approval', 'PENDING', 'SUSPENDED'),
    ('approval', 'APPROVED REJECTED', 'AUTHORIZED'),
    ('approval', 'EXPIRED', 'UNCERTAIN'),
    ('approval', 'SUPERSEDED CONSUMED', 'RECORDED'),
    ('verification', 'PENDING', 'INTENDED'),
    ('verification', 'RUNNING', 'MAY-HAVE-TAKEN-EFFECT'),
    ('verification', 'PASSED FAILED', 'RECORDED'),
    ('verification', 'ERROR', 'UNCERTAIN'),
    ('verification', 'AWAITING_HUMAN', 'SUSPENDED'),
    ('review', 'PENDING', 'SUSPENDED'),
    ('review', 'IN_REVIEW', 'UNKNOWN'),
    ('review', 'ACCEPTED CHANGES_REQUESTED REJECTED', 'RECORDED'),
    ('automation', 'DRAFT', 'INTENDED'),
    ('automation', 'PENDING_APPROVAL SUSPENDED', 'SUSPENDED'),
    ('automation', 'ENABLED', 'AUTHORIZED'),
    ('automation', 'DISABLED ARCHIVED', 'RECORDED'),
    ('automation_run', 'CLAIMED POLICY_CHECK', 'INTENDED'),
    ('automation_run', 'SKIPPED', 'NONE'),
    ('automation_run', 'ESCALATED', 'SUSPENDED'),
    ('automation_run', 'MISSION_CREATED', 'AUTHORIZED'),
    ('automation_run', 'SUCCEEDED FAILED', 'RECORDED'),
    ('account_health', 'UNVERIFIED', 'UNKNOWN'),
    ('account_health', 'AVAILABLE UNAUTHENTICATED CONSTRAINED LIMITED DEGRADED OPEN DISABLED', 'RECORDED'),
    ('repository_inspection', 'SCHEDULED', 'INTENDED'),
    ('repository_inspection', 'RUNNING', 'UNKNOWN'),
    ('repository_inspection', 'COMPLETED FAILED', 'RECORDED'),
    ('architecture', 'UNKNOWN', 'UNKNOWN'),
    ('architecture', 'CONSISTENT DRIFTED STALE', 'RECORDED'),
    ('knowledge_item', 'CANDIDATE SUPERSEDED EXPIRED', 'RECORDED'),
    ('knowledge_item', 'CONFIRMED RETRACTED', 'RECONCILED'),
    ('device', 'PAIRING', 'INTENDED'),
    ('device', 'ACTIVE REVOKED', 'AUTHORIZED'),
    ('execution_node', 'ONLINE OFFLINE', 'RECORDED'),
    ('execution_node', 'GRACE', 'UNCERTAIN'),
    ('execution_node', 'RETIRED', 'RECONCILED'),
    ('integration', 'PENDING', 'INTENDED'),
    ('integration', 'MERGING', 'MAY-HAVE-TAKEN-EFFECT'),
    ('integration', 'MERGED', 'RECORDED'),
    ('integration', 'CONFLICT', 'SUSPENDED'),
    ('integration', 'ABANDONED', 'RECONCILED'),
    ('harness', 'AVAILABLE MISSING MISCONFIGURED', 'RECORDED'),
)
_CATEGORY = {(machine, state): answer for machine, names, answer in CATEGORIES
             for state in names.split()}
_OWN = (entities.Plan, entities.Task, entities.Execution, entities.Session,
        entities.Approval, entities.Review)
_SETTLEMENT = {'execution': ('reconciled_kill', 'adopted'),
               'integration': ('user_abandons',), 'execution_node': ('retire',),
               'knowledge_item': ('confirm', 'reject', 'retract')}


def category(machine, state):
    return _CATEGORY.get((machine, state), 'UNKNOWN')


def _binding(source, revision):
    return {'source': source, 'revision': revision,
            'answer': 'RECORDED' if revision is not None else 'UNKNOWN',
            'reason': 'existing_commit_binding' if revision is not None else 'starting_state_not_recorded'}


def _record(conn, entity, machine, state, floor):
    answer = category(machine, state)
    reason = 'state_meaning_undeclared' if answer == 'UNKNOWN' else 'durable_row'
    settled_by, settlement_seq = 'unknown', None
    settlement_reason = 'retained_event_prefix_pruned' if floor else 'no_retained_transition'
    event = conn.execute('SELECT * FROM events WHERE subject_kind = ? AND subject_id = ? '
                         'AND type = ? ORDER BY seq DESC LIMIT 1',
                         (ids.kind_of(entity.id), entity.id, machine + '.state_changed')).fetchone()
    payload = json.loads(event['payload']) if event else {}
    edge = (payload.get('from'), payload.get('to'), payload.get('trigger'))
    matches = event is not None and payload.get('to') == state and any(
        edge == (frm, to, trigger) for frm, to, trigger, _ in states.edges(machine))
    if matches:
        settlement_reason = 'transition_does_not_reconcile'
        if payload.get('trigger') in _SETTLEMENT.get(machine, ()):
            answer, reason = 'RECONCILED', 'recorded_settlement_edge'
            actor = event['actor_kind']
            settled_by = ({'system': 'core', 'user_device': 'device'}.get(actor, 'unknown')
                          if ids.is_id(event['actor_id'], 'principal') else 'unknown')
            settlement_seq = event['seq']
            settlement_reason = 'event_actor' if settled_by != 'unknown' else 'unreadable_event_actor'
        elif answer == 'RECONCILED':
            answer, reason = 'RECORDED', 'recorded_non_reconciliation_edge'
    elif answer == 'RECONCILED':
        answer, reason = 'UNKNOWN', settlement_reason
    if machine == 'execution' and state == 'LOST':
        settled_by, settlement_seq = 'unknown', None
        settlement_reason = 'unsettled_lost_awaiting_core_sweep'
    return {'ref': {'kind': ids.kind_of(entity.id), 'id': entity.id},
            'machine': machine, 'state': state, 'answer': answer, 'reason': reason,
            'settled_by': settled_by, 'settlement_reason': settlement_reason,
            'settlement_seq': settlement_seq}


def _files(checkpoint, execution):
    files = list(checkpoint.files_changed)
    # A successful seeded import is the durable source of A/M/D paths; isolated alone is a decision.
    paths = execution is not None and execution.seed_revision is not None and execution.import_revision is not None
    shape = 'paths' if paths else 'summary' if execution is not None and execution.isolated is False else 'unknown'
    if not files or any(not isinstance(f, str) or f.startswith('(not measured:') for f in files):
        shape = 'unknown'
    return {'id': checkpoint.id, 'execution_id': checkpoint.execution_id,
            'task_id': checkpoint.task_id, 'files_changed': files,
            'files_are': shape, 'complete': False, 'item_limit': 30,
            'reason': 'checkpoint_is_a_clipped_summary'}


def replay(conn, mission_id, *, homes=None):
    mission = rows.get(conn, entities.Mission, mission_id)
    if mission is None:
        raise NotFound(mission_id)
    homes = queries._homes(conn, homes)
    floor, head = outbox.floor(conn), outbox.head(conn)
    owned = {cls: rows.where(conn, cls, mission_id=mission_id) for cls in _OWN}
    tasks = {r.entity.id: r.entity for r in owned[entities.Task]}
    executions = {r.entity.id: r.entity for r in owned[entities.Execution]}
    verifications = queries.list_verifications(conn, mission_id, homes=homes)['verifications']
    records = [_record(conn, mission.entity, 'mission', mission.entity.state, floor)]
    for rs in owned.values():
        for r in rs:
            e = r.entity
            records.append(_record(conn, e, e._STATE[1], e.state, floor))
            if isinstance(e, entities.Task) and e.integration_state is not None:
                records.append(_record(conn, e, 'integration', e.integration_state, floor))
    for v in verifications:
        e = rows.get(conn, entities.Verification, v['id']).entity
        records.append(_record(conn, e, 'verification', e.state, floor))
    checkpoints = [_files(r.entity, executions.get(r.entity.execution_id))
                   for r in rows.where(conn, entities.Checkpoint, mission_id=mission_id)
                   if r.entity.task_id in tasks and r.entity.execution_id in executions
                   and executions[r.entity.execution_id].task_id == r.entity.task_id]
    artifacts = [queries.view(r) for tid in tasks
                 for r in rows.where(conn, entities.ArtifactRecord, task_id=tid)
                 if r.entity.mission_id in (None, mission_id)]
    validation = [{**v, 'validation_recorded': v['state'] in ('PASSED', 'FAILED'),
                   'passed': v['state'] == 'PASSED'
                   and all(c.get('result') == 'pass' for c in v['checks'])
                   and all(c.get('result') == 'satisfied' for c in v['criteria']),
                   'starting_state': _binding('Verification.base_revision', v['base_revision'])}
                  for v in verifications]
    retained = conn.execute('SELECT MIN(at) FROM events').fetchone()[0]
    result = {
        'mission_id': mission_id, 'records': records,
        'starting_state': _binding('Mission.integration_head', mission.entity.integration_head),
        'tasks': [{'id': t.id, 'scope': {k: getattr(t, k) for k in
                   ('objective', 'expected_output', 'boundaries', 'acceptance')}} for t in tasks.values()],
        'executions': [{'id': e.id, 'task_id': e.task_id, 'exit_reason': e.exit_reason,
                        'charged': e.charged,
                        'starting_state': _binding('Execution.seed_revision', e.seed_revision)}
                       for e in executions.values()],
        'policy_decisions': queries.list_policy_decisions(conn, mission_id),
        'approvals': [queries.view(r) for r in owned[entities.Approval]],
        'checkpoints': checkpoints, 'artifacts': artifacts, 'verifications': validation,
        'external_effects': {'answer': 'UNKNOWN', 'reason': 'external_effects_not_recorded'},
        'history': {'answer': 'UNKNOWN' if floor or retained is None else 'RECORDED',
                    'reason': 'retained_event_prefix_pruned' if floor else
                              'no_retained_events' if retained is None else 'retained_range_only',
                    'floor': floor, 'head': head, 'oldest_retained_at': retained,
                    'event_days': retention.EVENT_DAYS, 'open_mission_extension': False,
                    'gap': 'open_mission_retention_extension_not_built'},
    }
    return system_value(result, homes)

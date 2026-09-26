"""Ids, entities, action classes and events: invariants and serialisation."""

import dataclasses
import json

import pytest

from archeus.core.domain import actions, entities as E, events, ids, states
from archeus.core.domain.values import Ref

# ── ids ─────────────────────────────────────────────────────────────────────


def test_a_ulid_is_26_crockford_chars_and_carries_its_time():
    u = ids.new_ulid(at_ms=1_700_000_000_123, entropy=42)
    assert len(u) == 26 and ids.is_ulid(u)
    assert ids.ulid_ms(u) == 1_700_000_000_123
    assert u == ids.new_ulid(at_ms=1_700_000_000_123, entropy=42)   # pinned = repeatable


def test_ulids_sort_by_time_as_plain_strings():
    early = ids.new_ulid(at_ms=1_000, entropy=(1 << 80) - 1)
    late = ids.new_ulid(at_ms=1_001, entropy=0)
    assert early < late


def test_ids_minted_in_one_millisecond_still_sort_in_creation_order():
    batch = [ids.new_ulid() for _ in range(2000)]
    assert batch == sorted(batch) and len(set(batch)) == len(batch)


def test_prefixed_ids_name_their_kind():
    m = ids.new_id('mission')
    assert m.startswith('msn_') and ids.is_id(m, 'mission') and not ids.is_id(m, 'task')
    assert ids.kind_of(m) == 'mission' and ids.kind_of('msn_nope') is None
    assert ids.is_id(ids.GLOBAL_WORKSPACE, 'workspace')
    assert len(set(ids.PREFIXES.values())) == len(ids.PREFIXES)
    with pytest.raises(ValueError):
        ids.encode(-1, 0)

def test_an_execution_id_and_an_execution_token_cannot_be_confused():
    """`exe_` was once both the Execution id prefix and the execution token
    prefix. One prefix, one semantic type: ids and tokens share none."""
    import secrets
    assert not set(ids.TOKEN_PREFIXES.values()) & set(ids.PREFIXES.values())
    exe = ids.new_id('execution')
    hook = '%s_%s' % (ids.TOKEN_PREFIXES['execution'], secrets.token_urlsafe(32))
    assert ids.kind_of(exe) == 'execution' and ids.token_kind(exe) is None
    assert ids.token_kind(hook) == 'execution' and ids.kind_of(hook) is None
    assert not ids.is_id(hook, 'execution')
    for kind in ids.TOKEN_PREFIXES:            # every credential kind, every id kind
        tok = '%s_%s' % (ids.TOKEN_PREFIXES[kind], secrets.token_urlsafe(32))
        assert ids.kind_of(tok) is None, kind


def test_the_documented_token_prefixes_are_the_declared_ones():
    """The API doc lists the typed tokens; it may not drift from ids.py, and no
    architecture document may call an `exe_` string a token again."""
    import os
    import re
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))))
    arch = os.path.join(root, 'docs', 'architecture')
    api = open(os.path.join(arch, 'api-and-realtime.md'), encoding='utf-8').read()
    typed = re.search(r'Tokens are typed \(([^)]*)\)', api).group(1)
    assert set(re.findall(r'`([a-z]+)_…`', typed)) == set(ids.TOKEN_PREFIXES.values())
    stale = []
    for name in os.listdir(arch):
        if name.endswith('.md'):
            text = open(os.path.join(arch, name), encoding='utf-8').read()
            for line in text.splitlines():
                if 'token' in line.lower() and re.search(r'typed[^.]*`exe_', line):
                    stale.append('%s: %s' % (name, line.strip()[:80]))
    assert not stale, stale

# ── entities ────────────────────────────────────────────────────────────────


def _ws():
    return ids.GLOBAL_WORKSPACE


def _sample(cls):
    """The smallest valid instance of every entity class."""
    i = ids.new_id
    ref = Ref('task', i('task'))
    action = actions.Action(action_class='read', target='README.md')
    samples = {
        E.User: dict(id=i('user'), display_name='Ada'),
        E.Identity: dict(id=i('identity'), user_id=i('user')),
        E.Principal: dict(id=i('principal'), kind='user_device', scopes=('observe', 'approve')),
        E.Device: dict(id=i('device'), principal_id=i('principal'), name='phone', platform='ios'),
        E.Workspace: dict(id=i('workspace'), name='Work'),
        E.Organization: dict(id=i('organization'), workspace_id=_ws(), name='K2K'),
        E.Person: dict(id=i('person'), workspace_id=_ws(), name='Lin'),
        E.Project: dict(id=i('project'), workspace_id=_ws(), name='archeus', root_paths=['D:/x']),
        E.Repository: dict(id=i('repository'), workspace_id=_ws(), project_id=i('project'),
                           path='D:/x', path_key='d:/x'),
        E.RepositoryInspection: dict(id=i('repository_inspection'),
                                     repository_id=i('repository'), extractor_version=1),
        E.System: dict(id=i('system'), workspace_id=_ws(), name='api', environment='prod'),
        E.Idea: dict(id=i('idea'), workspace_id=_ws(), text='weekly digest'),
        E.Meeting: dict(id=i('meeting'), workspace_id=_ws(), name='Planning',
                        held_at='2026-09-20T10:00:00Z'),
        E.Decision: dict(id=i('decision'), workspace_id=_ws(), statement='dark-first'),
        E.KnowledgeItem: dict(id=i('knowledge_item'), workspace_id=_ws(), type='LESSON',
                              title='retry once'),
        E.ContextPackage: dict(id=i('context_package'), workspace_id=_ws(),
                               subject_kind='mission', subject_id=i('mission')),
        E.Relation: dict(id=i('relation'), src_kind=ref.kind, src_id=ref.id, rel='depends_on',
                         dst_kind='task', dst_id=i('task')),
        E.ProviderTerms: dict(id='claude_code'),
        E.Conversation: dict(id=i('conversation'), kind='primary'),
        E.Message: dict(id=i('message'), conversation_id=i('conversation'), author='user',
                        text='hi'),
        E.Intent: dict(id=i('intent'), message_id=i('message'), utterance='hi', kind='question'),
        E.Mission: dict(id=i('mission'), workspace_id=_ws(), title='T', objective='O'),
        E.Plan: dict(id=i('plan'), mission_id=i('mission')),
        E.Task: dict(id=i('task'), plan_id=i('plan'), mission_id=i('mission'), key='t1',
                     title='do', kind='code_change', action_classes=('write_repo',)),
        E.Execution: dict(id=i('execution'), task_id=i('task'), mission_id=i('mission')),
        E.Session: dict(id=i('session'), harness_id='fake', account_id=i('account')),
        E.Checkpoint: dict(id=i('checkpoint'), execution_id=i('execution'),
                           mission_id=i('mission'), trigger='pressure'),
        E.Verification: dict(id=i('verification'), subject=ref, verifier='code'),
        E.Review: dict(id=i('review'), mission_id=i('mission'), reviewer='brain'),
        E.Feedback: dict(id=i('feedback'), subject=Ref('mission', i('mission')),
                         signal='positive'),
        E.Artifact: dict(id='ab' * 32, media_type='text/markdown', size=10),
        E.Harness: dict(id='generic_cli:aider'),
        E.Account: dict(id=i('account'), harness_id='claude_code', label='Work',
                        auth_kind='api_key', node_id=i('execution_node')),
        E.Model: dict(id='claude-opus-5-5', family='opus', tier='large',
                      context_window=1_000_000),
        E.ModelOffer: dict(account_id=i('account'), model_id='claude-opus-5-5'),
        E.ResourcePolicy: dict(id=i('resource_policy'), account_id=i('account'),
                               allocation_pct=80, reserve_pct=10, brain_reserve_pct=10),
        E.UsageSnapshot: dict(id=i('usage_snapshot'), account_id=i('account'), window='5h',
                              utilisation_pct=42.5, source='usage_api'),
        E.UsageLedger: dict(id=i('usage_ledger'), execution_id=i('execution'),
                            account_id=i('account'), tokens_in=5),
        E.RouteDecision: dict(id=i('route_decision'), subject=ref),
        E.ExecutionNode: dict(id=i('execution_node'), name='this-pc'),
        E.PolicyRule: dict(id=i('policy_rule'), scope_level='GLOBAL', action_class='deploy',
                           decision='ASK', source='builtin'),
        E.PolicyDecision: dict(id=i('policy_decision'), action=action, decision='ALLOW'),
        E.Approval: dict(id=i('approval'), subject=Ref('plan', i('plan')),
                         action_hash=actions.action_hash('plan', _bind(), [
                             actions.item('t1', action)]),
                         requested_by=i('principal')),
        E.Automation: dict(id=i('automation'), workspace_id=_ws(), name='docs on new model'),
        E.AutomationRun: dict(id=i('automation_run'), automation_id=i('automation'),
                              triggering_event_seq=7),
    }
    return cls(**samples[cls])


@pytest.mark.parametrize('cls', E.ENTITIES, ids=lambda c: c.__name__)
def test_every_entity_builds_validates_and_round_trips_through_json(cls):
    obj = _sample(cls)
    wire = json.loads(json.dumps(obj.to_dict()))
    assert cls.from_dict(wire) == obj
    with pytest.raises(dataclasses.FrozenInstanceError):
        obj.__setattr__(dataclasses.fields(obj)[0].name, 'x')
    with pytest.raises(ValueError):
        cls.from_dict(dict(wire, not_a_field=1))


def test_the_entity_list_covers_domain_model_md():
    names = {c.__name__ for c in E.ENTITIES} | {'Event'}
    for noun in ('User', 'Identity', 'Principal', 'Device', 'Workspace', 'Organization',
                 'Person', 'Project', 'Repository', 'RepositoryInspection', 'System', 'Idea',
                 'Meeting', 'Decision', 'KnowledgeItem', 'Relation', 'Conversation', 'Message',
                 'Intent', 'Mission', 'Plan', 'Task', 'Execution', 'Session', 'Checkpoint',
                 'Verification', 'Review', 'Feedback', 'Artifact', 'Harness', 'Account',
                 'Model', 'ModelOffer', 'ResourcePolicy', 'UsageSnapshot', 'UsageLedger',
                 'RouteDecision', 'ExecutionNode', 'PolicyRule', 'PolicyDecision', 'Approval',
                 'Automation', 'AutomationRun', 'Event'):
        assert noun in names, noun


def test_a_new_row_starts_in_its_machines_initial_state():
    assert _sample(E.Mission).state == 'CREATED'
    assert _sample(E.Execution).state == 'INTENT'
    assert _sample(E.Account).health == 'UNVERIFIED'
    assert _sample(E.Repository).architecture_state == 'UNKNOWN'
    assert _sample(E.Plan).state == 'DRAFT'


def test_no_entity_carries_a_provider_concept():
    """domain-model §1 rule 7: provider ids live in adapter_state, never in fields."""
    for cls in E.ENTITIES:
        for f in dataclasses.fields(cls):
            assert not any(p in f.name for p in ('claude', 'codex', 'resume')), (cls, f.name)


@pytest.mark.parametrize('cls,bad', [
    (E.Mission, dict(state='LEARNED')),
    (E.Mission, dict(id='tsk_01J00000000000000000000000')),
    (E.Mission, dict(title='  ')),
    (E.Mission, dict(workspace_id='not-a-workspace')),
    (E.Mission, dict(project_id='prj_bad')),
    (E.Principal, dict(kind='brain', scopes=('approve',))),
    (E.Principal, dict(kind='execution', scopes=('create_mission',))),
    (E.Task, dict(action_classes=('teleport',))),
    (E.Task, dict(depends_on=('t1',))),
    (E.Task, dict(max_attempts=0)),
    (E.Execution, dict(attempt=True)),
    (E.KnowledgeItem, dict(body='x' * 2049)),
    (E.ResourcePolicy, dict(allocation_pct=50, reserve_pct=30, brain_reserve_pct=30)),
    (E.ResourcePolicy, dict(allocation_pct=120)),
    (E.PolicyRule, dict(decision='DENY', locked=False)),
    (E.Approval, dict(action_hash='abc')),
    (E.Artifact, dict(id='not-a-sha')),
    (E.Harness, dict(id='Claude Code')),
    (E.Conversation, dict(kind='mission')),
    (E.Verification, dict(subject=Ref('plan', 'pln_x'))),
])
def test_invalid_values_are_refused(cls, bad):
    good = _sample(cls).to_dict()
    with pytest.raises(ValueError):
        cls.from_dict(dict(good, **bad))


def test_a_deny_rule_is_locked_without_being_told():
    rule = E.PolicyRule(id=ids.new_id('policy_rule'), scope_level='GLOBAL',
                        action_class='destructive', decision='DENY', source='builtin')
    assert rule.locked is True
    assert _sample(E.PolicyRule).locked is False

# ── actions ─────────────────────────────────────────────────────────────────


def test_the_action_vocabulary_is_the_closed_list_of_plan_section_13():
    assert actions.ACTION_CLASSES == (
        'read', 'web', 'write_repo', 'exec', 'git_commit', 'git_push', 'deploy',
        'external_comm', 'destructive', 'spend', 'personal_data', 'install', 'credential')
    assert actions.DECISIONS == ('ALLOW', 'ASK', 'ALLOW_WITHIN_BOUNDARY', 'DENY')


def _bind(**kw):
    b = dict(mission_id='msn_a', plan_id='pln_a', plan_version=2, plan_digest='d' * 64)
    b.update(kw)
    return actions.binding(**b)


def test_an_approval_hash_binds_the_exact_identity_and_not_the_policy():
    """p9-design-gate §7.2, D7 (U-H1, U-H2). Every binding field, the kind and
    each item change the hash; the policy version is not an input at all — it
    is recorded beside the hash and re-evaluated at every use."""
    push = actions.Action(action_class='git_push', target='origin/main',
                          argv=['git', 'push', 'origin', 'main'])
    same = actions.Action(argv=('git', 'push', 'origin', 'main'), target='origin/main',
                          action_class='git_push')
    h = actions.action_hash('action', _bind(), [actions.item('t1', push)])
    assert h == actions.action_hash('action', _bind(), [actions.item('t1', same)])
    assert len(h) == 64
    for change in (dict(mission_id='msn_b'),            # plan v2 of ANOTHER mission
                   dict(plan_id='pln_b'), dict(plan_version=3),
                   dict(plan_digest='e' * 64),
                   dict(task_id='tsk_x'), dict(task_key='t2'),
                   dict(execution_id='exe_x')):
        assert h != actions.action_hash('action', _bind(**change),
                                        [actions.item('t1', push)]), change
    assert h != actions.action_hash('task', _bind(), [actions.item('t1', push)])
    assert h != actions.action_hash('action', _bind(), [actions.item('t2', push)])
    assert h != actions.action_hash('action', _bind(), [
        actions.item('t1', dataclasses.replace(push, target='origin/dev'))])
    items = [actions.item('t1', push), actions.item('t2', same)]
    assert (actions.action_hash('plan', _bind(), items)
            == actions.action_hash('plan', _bind(), items[::-1]))     # order-free
    with pytest.raises(ValueError):
        actions.action_hash('plan', dict(_bind(), policy_version=7), items)
    with pytest.raises(ValueError):
        actions.action_hash('plan', _bind(plan_digest=None), items)
    with pytest.raises(ValueError):
        actions.Action(action_class='teleport', target='x')


def test_paths_are_part_of_the_canonical_action_only_when_known():
    a = actions.Action(action_class='write_repo', target='task:t1')
    assert 'paths' not in a.canonical()
    b = actions.Action(action_class='write_repo', target='task:t1', paths=['src/**'])
    assert b.canonical_dict()['paths'] == ['src/**'] and a.canonical() != b.canonical()

# ── events ──────────────────────────────────────────────────────────────────


def _event(**kw):
    kw.setdefault('subject', Ref('mission', ids.new_id('mission')))
    kw.setdefault('actor', Ref('user_device', ids.new_id('principal')))
    return events.new_event(kw.pop('type', 'mission.state_changed'),
                            payload=kw.pop('payload', {'from': 'CREATED', 'to': 'UNDERSTANDING'}),
                            **kw)


def test_an_event_has_the_envelope_of_api_section_3_1():
    ev = _event()
    env = ev.to_envelope()
    assert set(env) == {'seq', 'id', 'type', 'at', 'actor', 'cause_chain', 'subject',
                        'scope', 'visibility', 'payload'}
    assert env['seq'] is None                    # the P2 writer assigns it
    assert ids.is_ulid(env['id']) and env['at'].endswith('Z')
    assert env['visibility'] == 'user'           # the registry's default
    assert events.Event.from_envelope(json.loads(json.dumps(env))) == ev


def test_the_registry_declares_each_type_once_with_a_known_subject():
    kinds = set(ids.PREFIXES) | {'harness', 'model', 'provider_terms'}
    for type_, subject, vis, notify, desc in events.TYPES:
        assert subject in kinds and vis in events.VISIBILITIES
        assert isinstance(notify, bool) and desc


@pytest.mark.parametrize('bad', [
    dict(type='mission.learned'),                                  # unregistered
    dict(subject=Ref('task', 'tsk_x')),                            # wrong subject kind
    dict(actor=Ref('robot', 'x')),                                 # not a principal kind
    dict(actor=Ref('execution', ids.new_id('execution'))),         # exe_ is not a principal
    dict(actor=Ref('user_device', ids.new_id('device'))),          # nor is a device id
    dict(cause_chain=[ids.new_ulid() for _ in range(17)]),         # chain too long
    dict(cause_chain=['msn_notanevent']),
    dict(payload={'when': object()}),                              # not JSON
    dict(visibility='public'),
    dict(seq=0),
    dict(project='ws_global'),
    dict(id='nope'),
])
def test_invalid_events_are_refused(bad):
    with pytest.raises(ValueError):
        _event(**bad)


#: Machines whose host column is documented but belongs to a later phase.
LATER_COLUMNS = {'integration': ('Task', 'integration_state', 'P13')}


def test_every_machine_has_exactly_one_host():
    """A machine's state lives in a column of an entity (domain-model §1 rule 2).
    Integration is Task.integration_state, not an entity of its own."""
    hosts = {}
    for cls in E.ENTITIES:
        if cls._STATE:
            field, machine = cls._STATE
            hosts.setdefault(machine, []).append((cls.__name__, field))
    for machine, (cls, field, _phase) in LATER_COLUMNS.items():
        assert machine not in hosts
        hosts[machine] = [(cls, field)]
    for machine in states.MACHINES:
        assert len(hosts.get(machine, ())) == 1, (machine, hosts.get(machine))
    assert not hasattr(E, 'Integration')


def test_the_documents_say_where_the_integration_machine_lives():
    import os
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))))
    arch = os.path.join(root, 'docs', 'architecture')
    dm = open(os.path.join(arch, 'domain-model.md'), encoding='utf-8').read()
    sm = open(os.path.join(arch, 'state-machines.md'), encoding='utf-8').read()
    task = dm[dm.index('### 7.3 Task'):dm.index('### 7.4')]
    assert '| `integration_state` |' in task and 'Integration is not an entity' in task
    assert '`Task.integration_state`' in sm[sm.index('## 13. Integration'):]


def test_every_machine_state_used_by_an_entity_exists():
    for cls in E.ENTITIES:
        if cls._STATE:
            field, machine = cls._STATE
            assert machine in states.MACHINES or machine in states.STATE_SETS

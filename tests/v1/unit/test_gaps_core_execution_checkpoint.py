"""T-740: the highest-risk branches of `archeus/core/execution/checkpoint.py` the
other tests never reached — the fail-closed rendering first (`text_of` reporting an
unreadable artifact instead of inventing one: §18, C14), then what a checkpoint is
earned by (`ran`, D5) and why it ended (§8.1), then the limits (`MAX_ITEMS`, the
300-character cut that must come AFTER the redaction: §12.1, D6), then the lines
that may never enter history (a hook answer that was not a denial, an unconfirmed
decision, another subject's verification), then the boundary values of the end
(`exit_code`, `failure`, the no-progress reason) and the identity fields a
continuation is built from.

Everything runs on the seams the module's own tests use: a real database through
`Database.open()` (the world builder is the style of
tests/v1/unit/test_gaps_core_application_executions.py, the entity fixtures those of
tests/v1/unit/test_session_units.py), the real artifact store and `Homes`, under the
per-test `ARCHEUS_HOME` tests/v1/conftest.py gives every test. No process, no
network, no installed runtime, no OS call the fake cannot answer: the one account
home is spelled without a drive letter so `Homes` never probes for an 8.3 alias,
every text is written here by hand with explicit bytes, and nothing asserts on a
path, a case or an OS message, so the file judges the same way on Linux and Windows.

Three things are said plainly here rather than hidden: `_clip` and `_text` are the
module's private helpers and are called as such, because reaching them only through
`derive` lets one cap or one `str()` hide behind the other; `_hooks` is reached only
through `derive`, with a second execution of its own to stand for the attempt before;
and `text_of` handed NO checkpoint is not asserted at all, because `render.checkpoint`
has no `cp is None` branch (render.py:30-40 dereferences it straight away) and the
`except` at checkpoint.py:137 does not catch `AttributeError` — both readers check
`of_execution` first, so no caller can be in that state.
"""

import pytest

from archeus.core.application import queries
from archeus.core.domain import entities, ids
from archeus.core.domain.events import new_event
from archeus.core.domain.values import Ref
from archeus.core.execution import checkpoint
from archeus.core.homes import Homes
from archeus.core.sessions import render
from archeus.infra.artifacts import store as artifacts
from archeus.infra.db import Database, rows
from archeus.infra.eventlog import outbox

#: an account home, spelled the same on both platforms (no drive letter, so
#: `Homes` builds its pattern without asking the OS for an 8.3 short name)
HOME = '/t740/live-home'
#: one of the shapes `core/redact.py` swears never leaves a process
SECRET = 'sk-' + 'k' * 30


def _e(state, stop_reason=None, process_seq=1):
    """An execution as `trigger_of`/`ran` are handed one (test_session_units.py:15)."""
    return entities.Execution(id=ids.new_id('execution'), task_id=ids.new_id('task'),
                              mission_id=ids.new_id('mission'), state=state,
                              stop_reason=stop_reason, process_seq=process_seq)


# ── the world: one ended execution on a real database ──────────────────────

def _seed(tx, *, actor, rows_, events_):
    for r in rows_:
        tx.insert(r, actor=actor)
    for ev in events_:
        tx.append(ev)
    return len(rows_)


def _derive_command(tx, *, actor, eid, facts=None, context_package_id=None):
    """`checkpoint.derive` as `_finish` calls it (executions.py:604): the execution
    is loaded from the rows, already terminal, the facts come from outside the
    transaction."""
    e = rows.get(tx.conn, entities.Execution, eid).entity
    return checkpoint.derive(tx, actor=actor, execution=e, facts=facts,
                             context_package_id=context_package_id)


def _world(**over):
    """One execution in its terminal state under a mission, a plan and a task,
    with whatever else the test asks for and nothing else.

    Defaults: it ran (`process_seq` 1) and ended in error with exit code 1; the
    plan holds `t1` (its task) and `t2`, and a second plan holds `a0` — inserted
    BEFORE the plan's own tasks, so both the `plan_id` filter and the sort of
    checkpoint.py:71 have something to get wrong. `hooks` are `execution.hook`
    events of this execution, `knowledge` is (type, state, scope) with scope in
    same|other|none, `checks` is (verifier, state, scope) with scope in
    task|other|mission.
    """
    p = dict(state='ENDED_ERROR', stop_reason=None, process_seq=1, exit_code=1,
             failure=None, usage=None, session=False, plan=True, objective='the objective',
             constraints=(), boundaries=(), acceptance=(), criteria=(), mission_package=None,
             hooks=(), foreign_hooks=(), knowledge=(), checks=(), account_home=None)
    p.update(over)
    db = Database.open()
    who = Ref('system', ids.new_id('principal'))
    pid, eid = ids.new_id('plan'), ids.new_id('execution')
    prjid, sid, ctxid = ids.new_id('project'), ids.new_id('session'), ids.new_id('context_package')
    other_pid, other_prjid = ids.new_id('plan'), ids.new_id('project')
    # this run's task and its sibling, minted so that their ids sort the OPPOSITE way
    # to their keys and to the order the rows are inserted in (t2 first, then t1)
    tid, other_tid = ids.new_id('task', at_ms=2), ids.new_id('task', at_ms=0)
    t2id = ids.new_id('task', at_ms=1)
    mid = ids.new_id('mission')

    # in dependency order (every connection runs `PRAGMA foreign_keys = ON`):
    # projects, mission, plans, tasks, the execution, then what it reads
    kno = [entities.KnowledgeItem(id=ids.new_id('knowledge_item'),
                                  workspace_id=ids.GLOBAL_WORKSPACE, state=s, origin='inferred',
                                  title='decision %d' % i, type=t,
                                  project_id={'same': prjid, 'other': other_prjid,
                                              'none': None}[scope])
           for i, (t, s, scope) in enumerate(p['knowledge'])]
    rows_ = [entities.Project(id=prjid, workspace_id=ids.GLOBAL_WORKSPACE, name='the project')]
    if any(k.project_id == other_prjid for k in kno):
        rows_.append(entities.Project(id=other_prjid, workspace_id=ids.GLOBAL_WORKSPACE,
                                      name='the other project'))
    rows_.append(entities.Mission(id=mid, workspace_id=ids.GLOBAL_WORKSPACE, title='the mission',
                                  objective='o', state='EXECUTING', project_id=prjid,
                                  constraints=p['constraints'], success_criteria=p['criteria'],
                                  context_package_id=p['mission_package']))
    rows_ += [entities.Plan(id=pid, mission_id=mid, state='APPROVED', plan_version=3),
              entities.Plan(id=other_pid, mission_id=mid, state='APPROVED', plan_version=1)]
    rows_ += [entities.Task(id=other_tid, plan_id=other_pid, mission_id=mid, key='a0',
                            title='Other plan', kind='research', state='PENDING'),
              entities.Task(id=t2id, plan_id=pid, mission_id=mid, key='t2',
                            title='Task two', kind='research', state='PENDING'),
              entities.Task(id=tid, plan_id=pid, mission_id=mid, key='t1', title='Task one',
                            kind='code_change', state='RUNNING', objective=p['objective'],
                            boundaries=p['boundaries'], acceptance=p['acceptance'])]
    rows_.append(entities.Execution(id=eid, task_id=tid, mission_id=mid,
                                    plan_id=pid if p['plan'] else None, attempt=1,
                                    state=p['state'], stop_reason=p['stop_reason'],
                                    process_seq=p['process_seq'], exit_code=p['exit_code'],
                                    failure=p['failure'], usage=p['usage'],
                                    session_id=sid if p['session'] else None))
    other_eid = None
    if p['foreign_hooks']:
        other_eid = ids.new_id('execution')      # the retry of the same task, attempt 2
        rows_.append(entities.Execution(id=other_eid, task_id=tid, mission_id=mid,
                                        plan_id=pid if p['plan'] else None, attempt=2,
                                        state='ENDED_ERROR', process_seq=1, exit_code=1))
    rows_ += kno
    for verifier, state, scope in p['checks']:
        subject = {'task': Ref('task', tid), 'other': Ref('task', other_tid),
                   'mission': Ref('mission', mid)}[scope]
        rows_.append(entities.Verification(id=ids.new_id('verification'), subject=subject,
                                           verifier=verifier, state=state, plan_id=pid,
                                           criterion=1 if scope == 'mission' else None))
    if p['account_home'] is not None:
        rows_.append(entities.Account(id=ids.new_id('account'), harness_id='fake_harness',
                                      label='the account', auth_kind='api_key',
                                      home_ref=p['account_home'], home_key=p['account_home']))
    events_ = [new_event('mission.created', Ref('mission', mid), who, payload={'title': 'M'},
                        workspace=ids.GLOBAL_WORKSPACE, project=prjid)]
    events_ += [new_event('execution.hook', Ref('execution', eid), who,
                         payload={'decision': d, 'reason': r},
                         workspace=ids.GLOBAL_WORKSPACE, project=prjid)
                for d, r in p['hooks']]
    events_ += [new_event('execution.hook', Ref('execution', other_eid), who,
                         payload={'decision': d, 'reason': r},
                         workspace=ids.GLOBAL_WORKSPACE, project=prjid)
                for d, r in p['foreign_hooks']]
    db.writer.execute(_seed, {'actor': who, 'rows_': rows_, 'events_': events_})
    k = {'mid': mid, 'pid': pid, 'tid': tid, 'eid': eid, 'prjid': prjid, 'sid': sid,
         'ctxid': ctxid, 'other_tid': other_tid, 'other_eid': other_eid,
         'kno': [r.id for r in kno], 'head': len(events_)}
    return db, who, k


@pytest.fixture
def world():
    """Build as many worlds as a test needs; every database is closed after it."""
    opened = []

    def build(**over):
        w = _world(**over)
        opened.append(w[0])
        return w

    yield build
    for db in opened:
        db.close()


def _derive(w, facts=None, context_package_id=None):
    """The command's own answer (`derive` returns the Checkpoint it wrote)."""
    db, who, k = w
    return db.writer.execute(_derive_command, {'actor': who, 'eid': k['eid'], 'facts': facts,
                                               'context_package_id': context_package_id})


def _cp(w):
    """The row, through the module's own reader — the one `manager._continuation`
    (manager.py:445) and `application/live.py:135` call."""
    db, _, k = w
    with db.read() as r:
        return checkpoint.of_execution(r, k['eid'])


def _stored(w, facts=None, context_package_id=None):
    _derive(w, facts, context_package_id)
    return _cp(w)


def _payloads(w, type_):
    with w[0].read() as r:
        return [ev['payload'] for ev in queries.events(r) if ev['type'] == type_]


def _envelopes(w, type_):
    with w[0].read() as r:
        return [ev for ev in queries.events(r) if ev['type'] == type_]


# ── fail closed: an unreadable rendering is reported, never invented ────────

@pytest.mark.parametrize('broken', ['corrupt', 'not-text', 'no-sha', 'wrong-type'],
                         ids=['corrupt', 'not-utf8', 'no-sha', 'wrong-type'])
def test_a_checkpoint_whose_rendering_cannot_be_read_says_so(world, broken):
    """checkpoint.py:137-139 — `except (OSError, ValueError, TypeError): return
    '[checkpoint … is unavailable …]'`. Only the missing-file arm is pinned today
    (tests/v1/unit/test_t144_checkpoint_consumption.py:42-44 hands over a sha with no blob).
    A handler narrowed to `except FileNotFoundError` lets store.get's
    `ValueError('corrupt on disk')` (infra/artifacts/store.py:45-51), a blob that is
    not UTF-8 and a nonsense sha raise straight through `manager._continuation`
    (manager.py:453) and kill the hand-off that only wanted a suffix — §18 and C14
    promise that what Core cannot read is *reported*, never invented, never fatal."""
    w = world()
    cp = _stored(w)
    sha = cp.artifact_sha
    if broken == 'corrupt':                            # bytes that no longer match their address
        with open(artifacts.path_for(sha), 'wb') as f:
            f.write(b'not the rendering any more')
    elif broken == 'not-text':
        sha = artifacts.put(b'\xff\xfe\x00checkpoint')
    elif broken == 'no-sha':
        sha = None
    else:
        sha = 17
    text = checkpoint.text_of(entities.Checkpoint(**dict(cp.to_dict(), artifact_sha=sha)),
                              Homes())
    assert 'unavailable' in text and cp.id in text and cp.execution_id in text
    assert not text.startswith('# Checkpoint')          # never a rendering of its own


def test_the_rendering_without_homes_is_the_stored_bytes_and_nothing_else(world):
    """checkpoint.py:136 — `return render.checkpoint(cp, homes) if homes is not
    None else text`. Both arms are load-bearing and opposite: `manager._continuation`
    asks for the no-homes answer (homes=None when the binding is not bound) and must
    get the stored artifact, while a reader that hands over homes must be shown the
    RENDERING OF THE ROW it holds, not the file. Which is why the two directions are
    tested against a row whose text differs from the artifact it was written from —
    always rendering would ignore the artifact (so a deleted one could not be told
    from an intact one), and always returning the text would show a reader a stale
    rendering and, with no homes at all, the raw account home."""
    w = world(account_home=HOME)
    cp = _stored(w, facts={'files_changed': ['read ' + HOME + '/settings.json']})
    assert checkpoint.text_of(cp) == artifacts.get(cp.artifact_sha).decode('utf-8')
    assert HOME not in checkpoint.text_of(cp)                       # the stored half is projected
    assert HOME not in checkpoint.text_of(cp, Homes([HOME], shorts=lambda _: None))
    assert HOME in cp.files_changed[0]                              # the row stays raw
    stale = entities.Checkpoint(**dict(cp.to_dict(), objective='the row says this now'))
    assert 'the row says this now' in checkpoint.text_of(stale, Homes())
    assert 'the row says this now' not in checkpoint.text_of(stale)


# ── what earns a checkpoint (D5) and why it ended (§8.1) ───────────────────

@pytest.mark.parametrize('state', ['ENDED_OK', 'ENDED_ERROR', 'ENDED_KILLED',
                                   'ENDED_HANDOFF'], ids=['ok', 'error', 'killed', 'handoff'])
def test_an_execution_that_never_had_a_process_earns_no_checkpoint(state):
    """checkpoint.py:49 — `e.process_seq >= 1 and e.state not in ('ABANDONED',
    'ENDED_REJECTED')`. tests/v1/unit/test_session_units.py:29-30 asks the question
    of the STATES (ABANDONED and ENDED_REJECTED never earn one, ENDED_KILLED always
    does) but only ever with `process_seq=1`, hard-coded in its fixture at :18, so
    the whole first term of the conjunction is unpinned: `>= 0`, or the term dropped
    (the caller's half of the same promise is the catalogued mutant Y20,
    tools/mutate_p12.py:143), hands an execution whose spawn never
    returned a checkpoint — and its successor is then continued from the "history"
    of a run that never was (D5; the module's own "one per ended execution that
    ran"). Each half has to hold on its own, which is why the states are asked again
    below with a process, and every terminal state is asked here both ways."""
    assert not checkpoint.ran(_e(state, process_seq=0))
    assert checkpoint.ran(_e(state, process_seq=1))


@pytest.mark.parametrize('state', ['ABANDONED', 'ENDED_REJECTED'],
                         ids=['abandoned', 'p9-rejected'])
def test_a_run_that_was_never_allowed_to_have_a_process_earns_no_checkpoint(state):
    """checkpoint.py:49 — the other half of the conjunction, with the two terms in
    tension: an ABANDONED execution, or one P9 rejected, handed the `process_seq` of
    1 that test_session_units.py's fixture always gives. That is what the manager
    stores when the spawn answered before the abandonment landed, and what a stray
    process left behind by a kill really is; neither earns a checkpoint (D5, P9).
    Delete either term of the line and one of these two tests is the one that
    notices."""
    assert not checkpoint.ran(_e(state, process_seq=1))
    assert checkpoint.ran(_e('ENDED_ERROR', process_seq=1))


@pytest.mark.parametrize('reason', ['cancel', 'estop', 'workspace', 'disarmed'],
                         ids=['cancel', 'estop', 'workspace', 'disarmed'])
def test_a_hand_off_for_a_cause_no_trigger_exists_for_is_a_pressure_one(reason):
    """checkpoint.py:41 — `_TRIGGER.get(e.stop_reason, 'pressure')`. The four named
    hand-off causes are pinned by tests/v1/unit/test_session_units.py:22-25; what is
    not pinned is the default, and an `ENDED_HANDOFF` can carry any other stop
    reason (§8.1). With `.get` replaced by `[]` this raises KeyError in the end
    transaction, and with any other default the value is outside
    `entities.CHECKPOINT_TRIGGERS` (entities.py:1137), so the row is refused where it
    is built (checkpoint.py:95) — or, for a default of `user`, the checkpoint blames
    the user for a hand-off Core itself decided on."""
    assert checkpoint.trigger_of(_e('ENDED_HANDOFF', reason)) == 'pressure'


# ── the caps: a summary, not a log (§12.1, MAX_ITEMS, 300) ─────────────────

def test_every_list_is_a_summary_of_at_most_MAX_ITEMS_items():
    """checkpoint.py:57 — `list(items)[:MAX_ITEMS]` inside `_clip`, the one cap
    every list of the checkpoint passes (checkpoint.py:98-104). Dropped or widened,
    a `git diff --stat` of 300 files arrives as 300 lines in the next execution's
    prompt, which is the whole reason the constant exists ("a checkpoint is a
    summary, not a log", checkpoint.py:31). `iter(items)` is the generator the
    constraints argument really is (checkpoint.py:98)."""
    items = ['line %d' % i for i in range(2 * checkpoint.MAX_ITEMS + 1)]
    assert checkpoint._clip(items, Homes()) == tuple(items[:checkpoint.MAX_ITEMS])
    assert len(checkpoint._clip(iter(items), Homes())) == checkpoint.MAX_ITEMS


def test_an_item_is_cut_at_300_and_the_redaction_comes_first():
    """checkpoint.py:57 — `cut_safe(redact(str(i)), homes, 300)`: the redaction is
    INSIDE the cut. Reversed, the cut falls in the middle of a secret and the
    readable prefix of the secret survives into the artifact, the row and the next
    prompt (D6/C10: a checkpoint holds no secret). The `cut_safe` primitive has its
    own test (tests/v1/unit/test_homes.py:381-390); nothing but this pins the 300 or
    the order of the two."""
    assert len(checkpoint._clip(['x' * 4000], Homes())[0]) == 300
    secret_line = 'y' * 289 + ' ' + SECRET              # 300 falls inside the secret
    out = checkpoint._clip([secret_line], Homes())[0]
    assert 'sk-' not in out and '[redacted]' in out and len(out) <= 300


def test_a_constraint_keeps_only_its_text_and_a_plain_item_keeps_its_own(world):
    """checkpoint.py:52-53 — `_text`: `x.get('text') if isinstance(x, dict) else x`,
    the only thing standing between the next execution's prompt and the mission's
    constraint RECORD ({text, origin, source_ref}, entities §Mission). Printing the
    dict leaks the provenance (and any path in it) the projection never sees — and
    constraints ARE one of the authored fields `application/executions.py:1307-1317`
    declines to project; the `else x` half is what every task boundary has to be
    kept with — a plain string, an int, anything that is not a record — and dropping
    it turns them all into `None`."""
    assert checkpoint._text({'text': 'no new dependency', 'origin': 'inferred',
                             'source_ref': 'msg_01ABCDEFGHJKMNPQRST12345'}) == 'no new dependency'
    assert checkpoint._text('its own workdir only') == 'its own workdir only'
    assert checkpoint._text(7) == '7'                     # the str() is the whole of it
    w = world(constraints=[{'text': 'no new dependency', 'origin': 'inferred',
                            'source_ref': 'msg_01ABCDEFGHJKMNPQRST12345'}],
              boundaries=['its own workdir only', 7],
              criteria=[{'text': 'the tests pass', 'check': 'automatic', 'origin': 'explicit'}],
              acceptance=[{'text': 'the seam is used', 'check': 'human'}])
    _derive(w, {'files_changed': []})
    cp = _cp(w)
    assert cp.constraints == ('no new dependency', 'its own workdir only', '7')
    # and the same for the criteria: the mission's own, then this task's (:99-100)
    assert cp.success_criteria == ('the tests pass', 'the seam is used')
    joined = ' '.join(cp.constraints + cp.success_criteria)
    assert 'source_ref' not in joined and 'inferred' not in joined and 'automatic' not in joined


def test_a_cut_never_leaves_the_readable_start_of_an_account_home():
    """checkpoint.py:57 — `cut_safe(…, homes, 300)`, not `text[:300]`.
    `cut_safe` (core/homes.py:197-207, itself tested at test_homes.py:381-390) keeps
    the text raw but moves the cut back to the start of any home it would split,
    because a cut home no longer matches the scrub patterns and its readable prefix
    would survive into the projected artifact (§12.1; the manager's facts are the
    same guarantee, test_t144_cut_and_consumption.py:82). The `Homes()` column is
    what a lost homes argument gets."""
    item = 'z' * (300 - len(HOME) + 5) + ' ' + HOME + '/settings.json'    # the 300 falls inside
    protected = checkpoint._clip([item], Homes([HOME], shorts=lambda _: None))[0]
    naive = checkpoint._clip([item], Homes())[0]
    probe = HOME[:6]                                          # '/t740/': the readable half
    assert probe in naive                                     # what a scrub can no longer match
    assert len(protected) < 300 and probe not in protected


# ── what may never become an open problem, a decision or a verification ────

def test_only_a_denied_or_halted_hook_is_an_open_problem(world):
    """checkpoint.py:74-76 — the `if ev.payload.get('decision') in ('deny', 'halt')`
    filter over this execution's `execution.hook` events, and the `_hooks` query
    behind them (checkpoint.py:121-123): `subject_id = ?` and `ORDER BY seq`. Drop
    the filter and every ALLOW the hook gave — and the ASK the user then approved —
    reads to the next execution as a problem this one died of; drop the subject
    filter and the retry inherits the denials of the attempt before it (the events
    are the same table, the same mission); drop the order and the list shuffles."""
    w = world(hooks=[('allow', 'read ok'), ('ask', 'needs your approval'),
                     ('deny', 'outside the workdir'), ('halt', 'not on the allowlist')],
              foreign_hooks=[('deny', 'a denial of the attempt before this one')],
              exit_code=None)
    _derive(w)
    assert _cp(w).open_problems == ('deny: outside the workdir', 'halt: not on the allowlist')
    assert [p['decision'] for p in _payloads(w, 'execution.hook')] \
        == ['allow', 'ask', 'deny', 'halt', 'deny']       # all five are still on the log


def test_only_a_confirmed_decision_of_this_project_is_a_decision(world):
    """checkpoint.py:86-89 — `type == 'DECISION' and state == 'CONFIRMED' and
    project_id == m.project_id`. A CANDIDATE the user never confirmed, a RETRACTED
    one, a FACT, another project's decision or one with no project at all is not a
    decision of this mission; past this filter it is written into immutable history
    (§8.3: never updated, read as fact by the continuation and by the replan of §8.4),
    which is how a model's guess becomes authorisation."""
    spec = [('DECISION', 'CONFIRMED', 'same'), ('DECISION', 'CANDIDATE', 'same'),
            ('DECISION', 'CONFIRMED', 'other'), ('DECISION', 'RETRACTED', 'same'),
            ('FACT', 'CONFIRMED', 'same'), ('DECISION', 'CONFIRMED', 'none')]
    w = world(knowledge=spec)
    _derive(w, {'decisions': ['DECISION: use the seam']})
    decisions = _cp(w).decisions
    assert decisions == ('DECISION: use the seam', 'decision 0 (knowledge %s)' % w[2]['kno'][0])


def test_the_stream_decisions_come_first_and_the_list_ends_at_MAX_ITEMS(world):
    """checkpoint.py:85-89 with :103 — the stream's own `DECISION:` lines lead, the
    project's confirmed decisions follow in row order, and the whole is capped at
    `MAX_ITEMS`. Without the cap a project that has accumulated 35 decisions sends
    all of them to every later execution as one prompt suffix (§12.1), and a
    reordered union buries what this execution actually decided under them."""
    w = world(knowledge=[('DECISION', 'CONFIRMED', 'same')] * (checkpoint.MAX_ITEMS + 5))
    _derive(w, {'decisions': ['DECISION: first', 'DECISION: second']})
    decisions = _cp(w).decisions
    assert len(decisions) == checkpoint.MAX_ITEMS
    assert decisions[:2] == ('DECISION: first', 'DECISION: second')
    assert decisions[2].startswith('decision 0 (knowledge ')
    assert decisions[-1].startswith('decision %d (knowledge ' % (checkpoint.MAX_ITEMS - 3))
    assert not any(d.startswith('decision %d ' % (checkpoint.MAX_ITEMS - 2)) for d in decisions)


def test_only_this_task_s_own_verifications_are_reported(world):
    """checkpoint.py:90-92 — `v.entity.subject.kind == 'task' and v.entity.subject.id
    == t.id`, both halves. Dropped, another task's PASSED or a verification of the
    MISSION is reported as this task's, and the next execution — and the replan that
    reads these lines (§8.4) — believes work nobody verified of it (§8.2: "the
    task's latest Verification rows"). The other task is deliberately a task of
    ANOTHER plan under the same mission: the one subject in the world that is a
    task, is not this task, and would otherwise pass a kind-only filter."""
    w = world(checks=[('code', 'PASSED', 'task'), ('code', 'FAILED', 'other'),
                      ('research', 'PASSED', 'mission')])
    _derive(w)
    assert _cp(w).verification == ('code: PASSED',)


# ── the end it records: the boundary values of what went wrong ─────────────

@pytest.mark.parametrize('code', [0, None, 1, 129], ids=['exit-0', 'no-exit-code', 'exit-1',
                                                         'exit-129'])
def test_the_exit_that_proves_nothing_went_wrong_is_never_an_open_problem(world, code):
    """checkpoint.py:79-80 — `if e.exit_code not in (None, 0)`. `None` (never
    reported) and `0` (clean) must add nothing; a line for either tells the next
    execution this one failed when its own harness says it did not, and a guard
    written as `if e.exit_code is not None` puts the literal word "None" into the
    history as an exit code."""
    w = world(exit_code=code)
    _derive(w)
    lines = _cp(w).open_problems
    assert tuple(x for x in lines if 'exited with code' in x) \
        == (() if code in (None, 0) else ('the process exited with code %s' % code,))
    assert 'code None' not in ' '.join(lines)


def test_the_failure_the_manager_measured_and_the_no_progress_reason_are_recorded(world):
    """checkpoint.py:77-84 — the four appends that make `open_problems`, in their
    one order: the hook lines (none here), the harness `failure` the manager read
    from the stream, the exit code (not here: it is None, which is the point of the
    previous test), the stream's last error, and the no-progress guard's own
    sentence (`facts['context_insufficient']`, ADR-0047 §5). That last must arrive
    VERBATIM and must arrive at all: it is the only thing telling the continuation
    that this execution was stopped for making no progress, and rewriting it — or
    prefixing it like its neighbours — is a lie about what the guard said."""
    w = world(failure='resource', exit_code=None)
    _derive(w, {'last_error': 'boom: no such file',
                'context_insufficient': 'the workdir did not change',
                'files_changed': ['src/a.py | 2 +']})
    cp = _cp(w)
    assert cp.open_problems == ('the harness reported a resource failure',
                                'last error: boom: no such file',
                                'the workdir did not change')
    assert cp.files_changed == ('src/a.py | 2 +',)


# ── the identity the continuation is built from (§8.2) ─────────────────────

def test_a_checkpoint_of_an_execution_with_no_plan_says_so_and_lists_no_steps(world):
    """checkpoint.py:68, :70 and :96 — `… if e.plan_id else None`, the
    `if plan is not None` guard, and `plan.id if plan else None` /
    `plan.plan_version if plan else None`. Without the guard a conversation
    execution, which has no plan, dies on `AttributeError: 'NoneType' … plan_version`
    inside the end transaction, and a fallback to any other plan hands the next
    execution a plan version this one never ran."""
    w = world(plan=False)
    assert _derive(w)['trigger'] == 'failure'
    cp = _cp(w)
    assert (cp.plan_id, cp.plan_version, cp.completed_steps) == (None, None, ())


def test_the_steps_are_the_plan_s_own_tasks_in_key_order(world):
    """checkpoint.py:71-73 — `sorted(rows.where(…, plan_id=plan.id), key=…key)`.
    `rows.where` answers in insertion order (rows.py:110-119, `ORDER BY rowid`) and
    this world is built against both that and the ids: `a0` of the OTHER plan is
    inserted first, then `t2`, then `t1`, and the two keys' ULIDs are minted the
    wrong way round (`t1` above `t2`), so key order is the only thing left that can
    order the list. Drop the filter and the checkpoint lists another plan's task as
    this mission's step; drop the sort, or sort by id, and it lists them in the order
    the planner's JSON happened to arrive in, not the order of the plan (§8.2: "the
    plan's tasks and their states" — and `completed_steps` is what Y01,
    tools/mutate_p12.py:39, tempts a reader to treat as a task's state)."""
    w = world()
    _derive(w)
    cp = _cp(w)
    assert cp.completed_steps == ('t1 Task one: RUNNING', 't2 Task two: PENDING')
    assert (cp.plan_id, cp.plan_version, cp.trigger) == (w[2]['pid'], 3, 'failure')


def test_the_objective_is_the_task_s_own_and_never_a_secret(world):
    """checkpoint.py:97 — `redact(t.objective or t.title)`. Both halves matter.
    An objective-less task falls back to its title, or the continuation reads "(none)"
    (render.py:40) where it should read what it is for. And the key the agent pasted
    into the objective is redacted IN THE ROW, not only in the rendering, because the row is
    what `application/executions.py:1307-1317` hands out — where `objective`,
    `constraints` and `success_criteria` are the AUTHORED fields, the three it
    deliberately does not project. The write is the last place a secret in them can
    be stopped (§8.2 "never in a checkpoint"; D6/C10)."""
    w = world(objective='ship it ' + SECRET)
    _derive(w)
    assert '[redacted]' in _cp(w).objective and SECRET not in _cp(w).objective
    assert _stored(world(objective='')).objective == 'Task one'


@pytest.mark.parametrize('case', ['arg', 'mission', 'neither'],
                         ids=['arg-wins', 'mission-fallback', 'no-package'])
def test_the_package_the_continuation_was_given_wins_over_the_mission_s(world, case):
    """checkpoint.py:105 — `context_package_id or m.context_package_id`. §8.2 and
    §11: the checkpoint names the package THIS execution's prompt was given, and
    `application/live.py` reads it back to judge freshness. Recording the mission's
    current package instead dates a hand-off against material it never saw; the
    fallback is what keeps the plain end (`_finish` passes no package) honest
    instead of writing None."""
    mission_pkg = ids.new_id('context_package')
    w = world(mission_package=mission_pkg) if case != 'neither' else world()
    if case == 'arg':
        assert _derive(w, context_package_id=w[2]['ctxid'])['context_package_id'] == w[2]['ctxid']
    else:
        assert _derive(w)['context_package_id'] == (mission_pkg if case == 'mission' else None)


@pytest.mark.parametrize('usage', [None, {}, {'input_tokens': 10}],
                         ids=['no-usage-row', 'empty-usage', 'reported'])
def test_the_usage_is_what_the_execution_reported_or_nothing_at_all(world, usage):
    """checkpoint.py:106 — `dict(e.usage) if e.usage else None`. An execution that
    reported nothing keeps None, which every reader of §8.2 renders as "the harness
    said nothing"; an empty dict is a claim of measured zeroes, and a missing `if`
    writes one for the run that reported no figures at all."""
    w = world(usage=usage, state='ENDED_OK', stop_reason=None)
    got = _derive(w)
    assert got['trigger'] == 'task_boundary'
    if usage:
        assert got['usage'] == usage and _cp(w).usage == usage
    else:
        assert got['usage'] is None and _cp(w).usage is None


# ── the artifact, the record and the event the end owes (§8.2, §12.1, D6) ──

def test_the_stored_rendering_loses_the_account_home_the_row_keeps_raw(world):
    """checkpoint.py:65 and :107-108 — `homes = resources.bound_homes(tx.conn,
    tx.live)`, `data = render.checkpoint(cp, homes).encode('utf-8')`, then
    `artifacts.put(data)`. Rendered WITHOUT the homes (mutation of the one
    argument), the artifact Core stores — and the text the next execution's prompt
    ends with — carries where an account lives, which D6 forbids outright; the row
    keeping the same text raw is deliberate (T-144), so only the artifact half is
    projected and this is the test that says which half."""
    w = world(account_home=HOME)
    got = _derive(w, {'last_error': 'cannot read ' + HOME + '/settings.json',
                      'decisions': ['DECISION: use ' + HOME],
                      'files_changed': [HOME + '/a.py | 1 +']})
    cp = _cp(w)
    stored = artifacts.get(cp.artifact_sha).decode('utf-8')
    assert HOME not in stored and 'its home' in stored
    assert HOME in ' '.join(cp.open_problems + cp.decisions + cp.files_changed)
    assert got['artifact_sha'] == cp.artifact_sha
    assert artifacts.get(cp.artifact_sha) \
        == render.checkpoint(cp, Homes([HOME], shorts=lambda _: None)).encode('utf-8')
    assert 'never from a transcript' in stored              # the provenance footer, §12.1


def test_the_end_records_the_artifact_row_and_one_checkpoint_created_event(world):
    """checkpoint.py:110-116 — the insert, `record_artifact(…, kind='checkpoint',
    label=cp.id)` (executions.py:1259) and the `checkpoint.created` event carrying
    `execution`, `trigger` and `task_id` in the mission's workspace and project.
    §16 Event model (p12-design-gate.md:535) gives it the checkpoint as its subject,
    `system` visibility and a payload of execution and trigger — the code adds the
    `task_id` the UI groups by. The event is how a reader learns a checkpoint exists
    at all: with the payload read off the wrong entity, or the subject built from the
    execution rather than the checkpoint, or the scope lost, the hand-off is
    attributed to nothing and drops out of the mission's grouping."""
    w = world(state='ENDED_HANDOFF', stop_reason='pressure', exit_code=None, session=True)
    got = _derive(w)
    cp = _cp(w)
    assert (got['id'], got['trigger'], got['session_id']) == (cp.id, 'pressure', w[2]['sid'])
    assert _payloads(w, 'checkpoint.created') == [{'execution': w[2]['eid'],
                                                   'trigger': 'pressure', 'task_id': w[2]['tid']}]
    assert [(ev['subject']['kind'], ev['subject']['id'], ev['scope'])
            for ev in _envelopes(w, 'checkpoint.created')] \
        == [('checkpoint', cp.id, {'workspace': ids.GLOBAL_WORKSPACE,
                                   'project': w[2]['prjid']})]
    with w[0].read() as r:
        recs = [x.entity for x in rows.where(r, entities.ArtifactRecord, task_id=w[2]['tid'])]
        arts = [x.entity for x in rows.where(r, entities.Artifact, id=cp.artifact_sha)]
    assert [(a.kind, a.label, a.artifact_id) for a in recs if a.kind == 'checkpoint'] \
        == [('checkpoint', cp.id, cp.artifact_sha)]
    assert [a.media_type for a in arts] == ['text/markdown']
    assert [a.size for a in arts] == [len(artifacts.get(cp.artifact_sha))]
    assert cp.next_action == ''                       # the renderer's own default, §8.2


def test_the_head_it_was_derived_at_is_the_log_before_its_own_events(world):
    """checkpoint.py:97 — `as_of_seq=outbox.head(tx.conn)` (infra/eventlog/outbox.py:32-35).
    It is the "Derived by Archeus at event N" footer of §12.1 and the freshness
    answer of §11; `0`, a row count, or `head()` read after `tx.append` date the
    checkpoint at a moment the log never had, and every reader that compares it
    with its own cursor is wrong by the events the checkpoint itself wrote."""
    w = world(hooks=[('deny', 'no')])
    with w[0].read() as r:
        before = outbox.head(r)
    _derive(w)
    cp = _cp(w)
    assert before == 2 and cp.as_of_seq == before          # mission.created + the hook
    assert 'at event %d' % before in artifacts.get(cp.artifact_sha).decode('utf-8')


def test_its_own_events_come_after_the_head_it_records(world):
    """checkpoint.py:97 with :110-116 — the two events this write appends
    (`artifact.recorded`, `checkpoint.created`) must both sit ABOVE `as_of_seq`,
    which is the whole meaning of "the head it was derived at", while the rows the
    world was seeded with sit at or below it. `head()` taken after `tx.append`, or
    a `+1` here, leaves a reader that believes it is current still short of the
    checkpoint it is being handed."""
    w = world()
    _derive(w)
    as_of = _cp(w).as_of_seq
    with w[0].read() as r:
        own = [row[0] for row in r.execute(
            "SELECT seq FROM events WHERE type IN ('checkpoint.created', 'artifact.recorded')")]
        seeded = [row[0] for row in r.execute("SELECT seq FROM events WHERE type = "
                                              "'mission.created'")]
    assert len(own) == 2 and len(seeded) == 1
    assert all(s > as_of for s in own) and all(s <= as_of for s in seeded)


def test_no_checkpoint_row_means_no_rendering_and_no_invention(world):
    """checkpoint.py:126-128 — `got[0].entity if got else None`. Both readers branch
    on this being None: `manager._continuation` gives the prompt back with no suffix
    at all (manager.py:451-453) and the live surface of §16 prints its "What was
    preserved: checkpoint …" line only when there is one to count
    (application/live.py:135-140); `got[0]` without the guard is an IndexError inside
    the prompt build, and a fabricated checkpoint is the §18 failure in the reader's
    half — an execution that never ran continued from a history nobody wrote, above a
    line counting steps nobody did. The other end of it is left unasserted on purpose,
    for the reason in the header."""
    w = world()
    assert _cp(w) is None
    _derive(w)
    assert _cp(w) is not None
    with w[0].read() as r:
        assert checkpoint.of_execution(r, ids.new_id('execution')) is None

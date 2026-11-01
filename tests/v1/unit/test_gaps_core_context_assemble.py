"""T-311: the highest-risk uncovered branches of archeus/core/context/assemble.py.

`select()`'s pure half is pinned by test_context_units.py and the recorded
package by the integration tests; this file sits on the gaps between them: the
refusals (which subject kinds, which levels, which budgets, which missing
rows), the read-only freshness verdict `fresh()` (p12-design-gate §11.2, called
by nothing else in the suite), the fail-closed knowledge and history reads, the
two truncations (`RECENT_TURNS`, `HISTORY_CANDIDATES`) and the budget carry
past a disabled level.

Database-backed tests run in-process on a seeded database, no harness, no
model, no process, no network (the rig style of test_hook_mailbox_origin.py);
the pure tests copy the `cand`/`gathered` style of test_context_units.py.
"""

import pytest

from archeus.core.context import assemble as A
from archeus.core.context import levels as P
from archeus.core.domain import entities, events, ids
from archeus.core.domain.events import new_event
from archeus.core.domain.values import Ref
from archeus.infra.db import Database

AS_OF = '2026-09-25T12:00:00.000Z'             # the snapshot: the last event's `at`
SINCE = '2026-09-18T12:00:00.000Z'             # one window before AS_OF, as `_history` computes it
TOO_OLD = '2026-09-18T11:59:59.999Z'           # a hair outside that window


@pytest.fixture
def db():
    d = Database.open()               # ARCHEUS_HOME is the test's own (v1/conftest.py)
    yield d
    d.close()


# ── seeding helpers (every mutating command must append at least one event) ──

def _do(db, write):
    who = Ref('user_device', ids.new_id('principal'))
    db.writer.execute(lambda tx, **_: write(tx, who), {})
    return who


def _project(pid, state='ACTIVE'):
    return entities.Project(id=pid, workspace_id=ids.GLOBAL_WORKSPACE, name='P ' + pid[-4:],
                            state=state)


def _mission(mid, project_id=None, **kw):
    return entities.Mission(id=mid, workspace_id=ids.GLOBAL_WORKSPACE, title='M', objective='o',
                           project_id=project_id, **kw)


def _knowledge(kid, project_id, kind='FACT', state='CONFIRMED', **kw):
    return entities.KnowledgeItem(id=kid, workspace_id=ids.GLOBAL_WORKSPACE, type=kind,
                                  title='t ' + kid[-4:], text='body', project_id=project_id,
                                  state=state, **kw)


def _conversation(cid):
    return entities.Conversation(id=cid, kind='primary')


def _message(mid, conversation_id, text='hello'):
    return entities.Message(id=mid, conversation_id=conversation_id, author='user', text=text)


def _event(type_, subject, actor, at=AS_OF, project=None, payload=None):
    return new_event(type_, Ref(subject[0], subject[1]), actor, payload=payload or {}, at=at,
                     project=project)


def _head(db):
    """The log's head: the AUTOINCREMENT counter, which deletions never lower."""
    with db.read() as conn:
        r = conn.execute("SELECT seq FROM sqlite_sequence WHERE name = 'events'").fetchone()
    return r['seq'] if r else 0


def _forget(db):
    """Remove the whole event log the way retention does (raw DELETE: not a
    mutation, so it needs no event of its own)."""
    def drop(tx, **_):
        tx.execute('DELETE FROM events')
    db.writer.execute(drop, {})


# ── the pure helpers of test_context_units.py, copied for the budget gaps ──

def cand(id_, level='L1', store='knowledge', text='x', authority='confirmed', stale=False,
         observed_at=AS_OF, kind='knowledge_item', **extra):
    return A._cand({'kind': kind, 'id': id_}, level, store, 'FACT', kind, id_, observed_at,
                   text, authority, 'because', stale=stale, **extra)


def gathered(cands, excluded=(), query='', missing=()):
    return {'query': query, 'as_of_at': AS_OF, 'candidates': list(cands),
            'excluded': list(excluded), 'missing_information': list(missing)}


def pinned(id_, package, version, at):
    return cand(id_, constraint={'kind': 'framework_pinned',
                                 'spec': {'package': package, 'version': version}},
                created_at=at)


# ── 1. refusals: a subject kind that is not one of the three ─────────────────

def test_assemble_refuses_any_subject_kind_that_is_not_one_of_the_three(db):
    """Mutation: deleting the final `else: raise ValueError` of `gather` makes
    an unknown kind fall through to UnboundLocalError (or worse, a package)."""
    with db.read() as conn:
        for kind in ('task', '', 'mission '):
            with pytest.raises(ValueError, match='a context subject is one of'):
                A.assemble(conn, kind, ids.new_id('mission'))


def test_gather_refuses_a_subject_whose_row_does_not_exist(db):
    """Fail-closed: a wrong id is NotFound for all three subject kinds, never
    an empty-but-valid package. Mutation: dropping any `raise NotFound` gives
    an AttributeError on None or a silent empty gather."""
    for kind in ('mission', 'message', 'project'):
        with pytest.raises(A.NotFound), db.read() as conn:
            A.gather(conn, kind, ids.new_id(kind))


@pytest.mark.parametrize('levels', [('L5',), ('L1', 'L9'), ('l1',)],
                         ids=['unknown', 'one-bad', 'lowercase'])
def test_assemble_refuses_levels_outside_the_five(db, levels):
    """Mutation: deleting `if not set(levels) <= set(P.LEVELS): raise` lets an
    unanswerable level reach `select`, where `P.LEVELS.index(level)` explodes
    far from the caller's argument."""
    with db.read() as conn:
        with pytest.raises(ValueError, match='levels are'):
            A.assemble(conn, 'project', ids.new_id('project'), levels=levels)


@pytest.mark.parametrize('bad', [True, False, 0, -5, 1.0, '12000', None],
                         ids=['true', 'false', 'zero', 'negative', 'float', 'str', 'none'])
def test_assemble_refuses_a_limit_tokens_that_is_not_a_positive_integer(db, bad):
    """The `isinstance(limit_tokens, bool)` half is the live one: `True` is an
    int >= 1 to Python. Mutation: deleting it makes `True` a 1-token budget
    (a silent truncation), `False` a ValueError from a deeper place."""
    with db.read() as conn:
        with pytest.raises(ValueError, match='limit_tokens is an integer'):
            A.assemble(conn, 'project', ids.new_id('project'), limit_tokens=bad)


# ── 2. fresh(): called by nothing in the suite besides these ─────────────────

def _package(mid, pid, as_of_seq):
    return entities.ContextPackage(id=ids.new_id('context_package'),
                                   workspace_id=ids.GLOBAL_WORKSPACE, subject_kind='mission',
                                   subject_id=mid, project_id=pid, as_of_seq=as_of_seq)


def _scope(db):
    """A project, the mission a package describes, another mission, and one
    task of each (the indirection `_mission_of` reads through)."""
    w = {'pid': ids.new_id('project'), 'mid': ids.new_id('mission'),
         'mid_other': ids.new_id('mission'), 'tsk_own': ids.new_id('task'),
         'tsk_other': ids.new_id('task')}

    def write(tx, who):
        tx.insert(_project(w['pid']), actor=who)
        tx.insert(_mission(w['mid'], project_id=w['pid']), actor=who)
        tx.insert(_mission(w['mid_other'], project_id=w['pid']), actor=who)
        for tsk, mid in ((w['tsk_own'], w['mid']), (w['tsk_other'], w['mid_other'])):
            pln = ids.new_id('plan')
            tx.insert(entities.Plan(id=pln, mission_id=mid, plan_version=1,
                                    state='DRAFT'), actor=who)
            tx.insert(entities.Task(id=tsk, plan_id=pln, mission_id=mid,
                                    key='t', title='T', kind='code_change', state='PENDING',
                                    max_attempts=2), actor=who)
        tx.append(_event('project.created', ('project', w['pid']), who, project=w['pid']))
    _do(db, write)
    return w


def test_fresh_cannot_be_proven_below_the_retained_log(db):
    """A snapshot older than what the log still holds returns False, never an
    assumed True (`if package.as_of_seq < outbox.floor(conn): return False`).
    The events are deleted the way retention deletes them; AUTOINCREMENT keeps
    `head`, so floor() jumps to it."""
    w = _scope(db)
    who = _do(db, lambda tx, a: tx.append(
        _event('project.changed', ('project', w['pid']), a, project=w['pid'])))
    assert who is not None
    assert _head(db) == 2                      # project.created + project.changed
    with db.read() as conn:
        assert A.fresh(conn, _package(w['mid'], w['pid'], 2)) is True
    _forget(db)
    assert _head(db) == 2                      # seqs are never reused
    with db.read() as conn:
        assert A.fresh(conn, _package(w['mid'], w['pid'], 1)) is False   # under the floor
        assert A.fresh(conn, _package(w['mid'], w['pid'], 2)) is True    # AT the floor is fine


FRESH_CASES = {
    # (event type, subject kind chosen by name, event's project, want): every
    # case is scoped so that only the rule it names can decide it.
    'bookkeeping': ('session.created', 'session', 'pid', True),
    'project-event': ('project.changed', 'project', 'pid', False),
    'knowledge-event': ('knowledge_item.state_changed', 'knowledge_item', None, False),
    'own-mission': ('mission.updated', 'mid', None, False),
    'other-mission': ('mission.updated', 'mid_other', None, True),
    'own-task': ('task.state_changed', 'tsk_own', None, False),
    'other-task': ('task.state_changed', 'tsk_other', None, True),
}


@pytest.mark.parametrize('case', sorted(FRESH_CASES), ids=sorted(FRESH_CASES))
def test_fresh_is_conservative_about_what_stales_a_package(db, case):
    """`session.*` is bookkeeping and must not stale what it just recorded
    (the _NOT_NEWS skip); a user event of the package's project, of its
    workspace's knowledge, or of its mission's work (directly or through a
    task) must."""
    type_, subject_key, project, want = FRESH_CASES[case]
    w = _scope(db)
    as_of = _head(db)
    if subject_key == 'session':
        subject = ('session', ids.new_id('session'))
    elif subject_key == 'project':
        subject = ('project', w['pid'])
    elif subject_key == 'knowledge_item':
        subject = ('knowledge_item', ids.new_id('knowledge_item'))
    elif subject_key in ('mid', 'mid_other'):
        subject = ('mission', w[subject_key])
    else:
        subject = ('task', w[subject_key])

    def write(tx, who):
        tx.append(new_event(type_, Ref(*subject), who, payload={'from': 'a', 'to': 'b'},
                            project=w['pid'] if project else None))
    _do(db, write)
    with db.read() as conn:
        assert A.fresh(conn, _package(w['mid'], w['pid'], as_of)) is want


# ── 3. knowledge: what may be a candidate at all ─────────────────────────────

def test_unconfirmed_knowledge_is_never_a_candidate_and_the_imported_decision_is_labelled(db):
    """Three source branches at once: `_NOT_CONFIRMED[k.state]` (line 92) for
    RETRACTED/EXPIRED on a project subject, the same gate refusing the imported
    DECISION candidate outside P7 (`message=False` skips lines 79-86), the P7
    candidate itself entering only at the `candidate` authority and never
    presented as confirmed, and the out-of-scope `continue` (line 75) for
    another project's plain fact."""
    kid = {n: ids.new_id('knowledge_item') for n in
           ('ok', 'retracted', 'expired', 'imported', 'foreign')}
    pid1, pid2, mtg = ids.new_id('project'), ids.new_id('project'), ids.new_id('meeting')
    conv, msg = ids.new_id('conversation'), ids.new_id('message')

    def write(tx, who):
        tx.insert(_project(pid1), actor=who)
        tx.insert(_project(pid2), actor=who)
        tx.insert(_knowledge(kid['ok'], pid1), actor=who)
        tx.insert(_knowledge(kid['retracted'], pid1, state='RETRACTED'), actor=who)
        tx.insert(_knowledge(kid['expired'], pid1, state='EXPIRED'), actor=who)
        tx.insert(_knowledge(kid['imported'], pid1, kind='DECISION', state='CANDIDATE',
                             source_kind='import', source_ref=Ref('meeting', mtg)), actor=who)
        tx.insert(_knowledge(kid['foreign'], pid2), actor=who)
        tx.insert(_conversation(conv), actor=who)
        tx.insert(_message(msg, conv, text='what should we build'), actor=who)
        tx.append(_event('project.created', ('project', pid1), who, project=pid1))
    _do(db, write)

    with db.read() as conn:
        g = A.gather(conn, 'project', pid1)
    cands = {c['ref']['id']: c for c in g['candidates'] if c['store'] == 'knowledge'}
    excl = {e['ref']['id']: e['reason'] for e in g['excluded'] if e['ref']['kind']
            == 'knowledge_item'}
    assert list(cands) == [kid['ok']]
    assert excl[kid['retracted']] == 'retracted'
    assert excl[kid['expired']] == 'expired (its validity ended)'
    assert excl[kid['imported']] == 'not confirmed (a candidate)'      # never a candidate here
    assert kid['foreign'] not in cands and kid['foreign'] not in excl  # out of scope entirely

    with db.read() as conn:
        gm = A.gather(conn, 'message', msg)
    mcands = {c['ref']['id']: c for c in gm['candidates']}
    imp = mcands[kid['imported']]
    assert (imp['level'], imp['authority']) == ('L2', 'candidate')
    assert imp['reason'].startswith('DECISION candidate from meeting %s' % mtg)
    assert 'not confirmed' in imp['reason']
    assert kid['imported'] not in {e['ref']['id'] for e in gm['excluded']}
    assert kid['ok'] not in mcands                 # a plain FACT is not challengeable material


@pytest.mark.parametrize('moved', [True, False], ids=['moved-past', 'still-at'])
def test_a_knowledge_item_read_from_an_inspection_is_stale_only_when_the_repo_moved(db, moved):
    """`_moved_past` (lines 107-121): the item cites the inspection, the
    repository moved past that revision. Mutation: always returning '' makes a
    description of a stale world read as current; never returning '' labels an
    item that still matches."""
    pid, rep, rin, kid = (ids.new_id(k) for k in ('project', 'repository',
                                                  'repository_inspection', 'knowledge_item'))

    def write(tx, who):
        tx.insert(_project(pid), actor=who)
        tx.insert(entities.Repository(id=rep, workspace_id=ids.GLOBAL_WORKSPACE,
                                      project_id=pid, path='repo', path_key='repo',
                                      last_revision='rev-2' if moved else None), actor=who)
        tx.insert(entities.RepositoryInspection(id=rin, repository_id=rep, extractor_version=1,
                                                 revision='rev-1', state='COMPLETED',
                                                 inspected_at=AS_OF), actor=who)
        tx.insert(_knowledge(kid, pid, source_kind='inspection',
                             source_ref=Ref('repository_inspection', rin)), actor=who)
        tx.append(_event('project.created', ('project', pid), who, project=pid))
    _do(db, write)
    with db.read() as conn:
        g = A.gather(conn, 'project', pid)
    (k,) = [c for c in g['candidates'] if c['ref']['id'] == kid]
    assert k['stale'] is moved
    assert ('stale: read at rev-1, the repository is at rev-2' in k['reason']) is moved
    (insp,) = [c for c in g['candidates'] if c['type'] == 'INSPECTION']
    assert insp['stale'] is False                  # the inspection itself is the latest one


# ── 4. history: the window, the visibility gate, the bound, the empty log ────

def test_history_is_user_events_in_the_window_never_more_than_the_bound(db):
    """Four filters of the one `_history` SELECT (lines 200-204) at once:
    visibility='user' (a system event is never history), `at >= since` with
    its exact boundary, `subject_id != ?`, and `LIMIT HISTORY_CANDIDATES`
    keeping the NEWEST bound rows (ORDER BY seq DESC). Mutations: any filter
    deleted, the DESC inverted, or the LIMIT dropped fails an assertion here."""
    pid, mid, rep = ids.new_id('project'), ids.new_id('mission'), ids.new_id('repository')
    many = [ids.new_id('idea') for _ in range(P.HISTORY_CANDIDATES + 5)]
    boundary, gone = ids.new_id('idea'), ids.new_id('idea')

    def write(tx, who):
        tx.insert(_project(pid), actor=who)
        tx.insert(_mission(mid, project_id=pid,
                           success_criteria=({'text': 'dark ships', 'check': 'automatic'},)),
                  actor=who)
        tx.append(_event('project.created', ('project', pid), who, project=pid,
                         at='2026-01-01T00:00:00.000Z'))                 # far outside: not hist
        for i, iid in enumerate(many):
            tx.append(_event('idea.created', ('idea', iid), who, project=pid,
                             at='2026-09-25T10:%02d:00.000Z' % i, payload={'title': 'i%d' % i}))
        tx.append(_event('idea.created', ('idea', boundary), who, project=pid, at=SINCE))
        tx.append(_event('idea.created', ('idea', gone), who, project=pid, at=TOO_OLD))
        tx.append(_event('mission.created', ('mission', mid), who, project=pid, at=AS_OF))
        # newest of all, still inside the window: only the visibility filter keeps it out
        tx.append(_event('repository.registered', ('repository', rep), who, project=pid,
                         at=AS_OF))
    _do(db, write)
    with db.read() as conn:
        g = A.gather(conn, 'mission', mid)
    (mission,) = [c for c in g['candidates'] if c['type'] == 'MISSION']
    assert 'dark ships' in mission['text']             # success criteria are in the L0 text
    hist = [c for c in g['candidates'] if c['store'] == 'history']
    seen = {c['source_ref'] for c in hist}
    assert len(hist) == P.HISTORY_CANDIDATES           # the bound, not 56
    assert all(c['level'] == 'L3' and c['observed_at'] >= SINCE for c in hist)
    assert boundary in seen                            # at exactly `since` counts
    assert gone not in seen                            # one millisecond outside does not
    assert rep not in seen                             # system visibility: never history
    assert many[5] not in seen and many[6] in seen     # DESC: the newest bound rows are kept
    assert 'mission.created' not in {c['type'] for c in hist}   # the subject is not its history


def test_a_snapshot_older_than_every_event_and_an_empty_log_produce_no_history(db):
    """`if as_of_at is None: return` (line 194): with no events at all there is
    no "now", so no history — and the empty project states its gap. The events
    are removed the way retention removes them."""
    pid = ids.new_id('project')

    def write(tx, who):
        tx.insert(_project(pid), actor=who)
        tx.append(_event('project.created', ('project', pid), who, project=pid))
    _do(db, write)
    _forget(db)
    with db.read() as conn:
        g = A.gather(conn, 'project', pid)
    assert g['as_of_at'] is None
    assert [c for c in g['candidates'] if c['store'] == 'history'] == []
    assert g['missing_information'] == ['project %s has no repository registered' % pid]
    pkg = A.assemble(conn, 'project', pid)             # the same input assembles, empty
    assert [i['type'] for i in pkg['items']] == ['PROJECT']
    assert pkg['missing_information'] == g['missing_information']


def test_a_workspace_without_any_project_says_so_for_a_message(db):
    """The stated gap at line 259, and its mission twin (line 285): deleting
    either silently hands a package that resolves names to nothing."""
    conv, msg = ids.new_id('conversation'), ids.new_id('message')
    mid = ids.new_id('mission')

    def write(tx, who):
        tx.insert(_conversation(conv), actor=who)
        tx.insert(_message(msg, conv), actor=who)
        tx.insert(_mission(mid), actor=who)                     # names no project
        tx.append(_event('message.created', ('message', msg), who))
    _do(db, write)
    with db.read() as conn:
        g = A.gather(conn, 'message', msg)
    assert g['missing_information'] == [
        'no project is registered, so nothing can be resolved to one']
    with db.read() as conn:
        gm = A.gather(conn, 'mission', mid)
    assert any('names no project' in m for m in gm['missing_information'])


# ── 5. the message truncation and its closed-row skips ───────────────────────

def test_a_message_reads_only_its_last_turns_and_never_ones_after_it(db, monkeypatch):
    """`[-RECENT_TURNS:]` (line 225) and the `created_at <= mrow.created_at`
    half of the same line: fifteen earlier turns are twelve, and a turn the
    snapshot does not contain yet is never quoted. Mutations: `[-13:]`, `[:12]`
    or dropping the time filter all fail here."""
    conv = ids.new_id('conversation')
    ms = [ids.new_id('message') for _ in range(15)]

    def write(tx, who):
        tx.insert(_conversation(conv), actor=who)
        for m in ms:
            tx.insert(_message(m, conv, text='turn'), actor=who)
        tx.append(_event('message.created', ('message', ms[-1]), who))
    _do(db, write)
    monkeypatch.setattr(events, 'now_iso', lambda: '2027-01-01T00:00:00.000Z')
    later = ids.new_id('message')

    def future(tx, who):
        tx.insert(_message(later, conv, text='the future'), actor=who)
        tx.append(_event('message.created', ('message', later), who,
                         at='2027-01-01T00:00:00.000Z'))
    _do(db, future)
    with db.read() as conn:
        g = A.gather(conn, 'message', ms[-1])
    earlier = [c['ref']['id'] for c in g['candidates'] if 'an earlier turn' in c['reason']]
    assert earlier == ms[2:-1]                          # turns 3..14: the last twelve
    (cur,) = [c for c in g['candidates'] if c['reason'] == 'the message being interpreted']
    assert cur['ref']['id'] == ms[-1]


def test_message_context_skips_archived_projects_and_finished_rows(db):
    """The three skips of `_message`: `p.state != 'ACTIVE'`, the terminal
    mission states, and the DISCARDED/COMPLETED/LEARNED ideas. Inverting any
    test brings a dead row into a live package."""
    conv, msg = ids.new_id('conversation'), ids.new_id('message')
    pid_on, pid_off = ids.new_id('project'), ids.new_id('project')
    msn_on, msn_done = ids.new_id('mission'), ids.new_id('mission')
    ida_on, ida_off = ids.new_id('idea'), ids.new_id('idea')

    def write(tx, who):
        tx.insert(_conversation(conv), actor=who)
        tx.insert(_message(msg, conv), actor=who)
        tx.insert(_project(pid_on), actor=who)
        tx.insert(_project(pid_off, state='ARCHIVED'), actor=who)
        tx.insert(_mission(msn_on, state='EXECUTING'), actor=who)
        tx.insert(_mission(msn_done, state='COMPLETED'), actor=who)
        tx.insert(entities.Idea(id=ida_on, workspace_id=ids.GLOBAL_WORKSPACE, text='live',
                                state='CAPTURED'), actor=who)
        tx.insert(entities.Idea(id=ida_off, workspace_id=ids.GLOBAL_WORKSPACE, text='dead',
                                state='DISCARDED'), actor=who)
        tx.append(_event('message.created', ('message', msg), who))
    _do(db, write)
    with db.read() as conn:
        g = A.gather(conn, 'message', msg)
    got = {t: sorted(c['ref']['id'] for c in g['candidates'] if c['type'] == t)
           for t in ('PROJECT', 'MISSION', 'IDEA')}
    assert got['PROJECT'] == [pid_on] and got['MISSION'] == [msn_on] and got['IDEA'] == [ida_on]


def test_a_meeting_whose_notes_cannot_be_read_still_gathers_its_name(db):
    """`except OSError: notes = ''` (line 136): a missing artifact is a soft
    gap in one candidate's text, never a failed gather. Without the catch the
    FileNotFoundError escapes `assemble`."""
    pid, mtg = ids.new_id('project'), ids.new_id('meeting')

    def write(tx, who):
        tx.insert(_project(pid), actor=who)
        tx.insert(entities.Meeting(id=mtg, workspace_id=ids.GLOBAL_WORKSPACE, name='Sync',
                                   project_id=pid, notes_artifact_id='a' * 64), actor=who)
        # a meeting of no project is not this project's past either (line 131)
        tx.insert(entities.Meeting(id=ids.new_id('meeting'),
                                   workspace_id=ids.GLOBAL_WORKSPACE, name='Global'), actor=who)
        tx.append(_event('meeting.imported', ('meeting', mtg), who, project=pid))
    _do(db, write)
    with db.read() as conn:
        g = A.gather(conn, 'project', pid)
    (m,) = [c for c in g['candidates'] if c['type'] == 'MEETING']
    assert m['text'] == 'Sync\n'                       # the name survives, the notes do not
    assert ' undated,' in m['reason']                  # dated when it was held, not on import


# ── 6. the budget gaps select() never had a test for ─────────────────────────

def test_a_disabled_levels_whole_share_flows_into_the_next_level():
    """`carry = quota` after a disabled level (line 391): the excluded level's
    share must keep travelling, not evaporate. With the carry dropped, L2 gets
    150 and the 151-token item is excluded."""
    pkg = A.select(gathered([cand('kno_big', 'L2', text='a' * 604)]),
                   levels=('L0', 'L2', 'L3', 'L4'), limit_tokens=1000)
    assert [i['ref']['id'] for i in pkg['items']] == ['kno_big']
    b = pkg['budget']['levels']
    assert b['L1'] == {'limit_tokens': 0, 'used_tokens': 0}
    assert b['L2'] == {'limit_tokens': 850, 'used_tokens': 151}    # 150 + (400 + 300) carried
    assert pkg['budget']['used_tokens'] == 151


def test_a_level_with_no_quota_left_excludes_everything_naming_the_quota():
    """The else branch of the fit test (lines 398-401): the reason must state
    the need and what was left. Deleting the else includes an over-budget item."""
    pkg = A.select(gathered([cand('kno_z', 'L4', text='x')]), limit_tokens=1)
    assert pkg['items'] == []
    (cut,) = pkg['excluded']
    assert cut['reason'] == 'over the L4 budget: needs 1 tokens, 0 left'
    assert pkg['budget']['levels']['L4'] == {'limit_tokens': 0, 'used_tokens': 0}
    assert pkg['budget']['used_tokens'] == 0


def test_equal_creation_times_are_broken_by_the_larger_id_whatever_the_input_order():
    """`sorted(..., key=lambda c: (c['created_at'], c['ref']['id']))` (line
    344): with one created_at the id decides, so the verdict cannot depend on
    the order the candidates arrived in. Drop the id from the key and the
    reversed input prefers the other item."""
    at = '2026-09-24T10:00:00.000Z'
    a = pinned('kno_a', 'pydantic', '1.10', at)
    b = pinned('kno_b', 'pydantic', '2.7', at)
    (c,) = A.select(gathered([b, a]))['conflicts']
    assert (c['items'], c['preferred']) == (['kno_a', 'kno_b'], 'kno_b')


def test_recency_is_clamped_at_the_top_and_a_missing_now_is_zero():
    """`min(1.0, ...)` (line 322) and the `as_of_at is None` half of line 319:
    an item observed after the snapshot is 1.0, not 1.14; without a "now"
    nothing is recent. Remove the clamp and the future scores over 1."""
    assert A._recency('2026-10-05T12:00:00.000Z', AS_OF) == 1.0
    assert A._recency(AS_OF, None) == 0.0

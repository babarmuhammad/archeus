"""T-1130 · the ten highest-risk uncovered branches of
archeus/core/knowledge/passes.py lines 269-338 inclusive (HEAD 56d53504, 2026-11-10):
the review findings of the lessons pass (88feb23b) and the consolidation pass
(a94cc3a7). Nothing outside this one file is edited.

Fail-closed and denial first, then boundaries, then error paths, then one
concurrency ordering forced with a seam and `threading.Event`s (never a sleep):

1. passes.py:307-311 with 320-321 — the three eligibility filters and the refusal:
   an item that is not a CONFIRMED item read from a repository inspection never enters
   the prompt or `shown`, and when none of them is eligible the pass makes no own call,
   records nothing, opens no route decision and reads no payload.
2. passes.py:314-315, 318 — an item whose inspection row is gone is dropped: the
   model is never told it was re-checked, and it is never in `shown`.
3. passes.py:322, 336-338 x knowledge.py:452-453 — the facts are keyed per
   inspection, so a quote taken from another source's facts cannot replace an item.
4. passes.py:311 — the item bound is `(observed_at or '', id)` and cuts before the
   sources are grouped, so a whole source can fall out of the call.
5. passes.py:313-318, 322-327, 336-337 — two items read from one inspection are ONE
   fact extraction (one payload read), one call, both ids shown, no context package.
6. passes.py:334-335 — a consolidation call that did not answer records no
   candidate, and its open call is never ended as a success.
7. passes.py:280-281 — a review finding carrying a keyed secret and a bound account
   home is redacted and scrubbed BEFORE the FINDING_CHARS cut, so the cut cannot
   leave a secret or home prefix behind.
8. passes.py:280-281 — FINDINGS_MAX and FINDING_CHARS boundaries keep each line's
   category, the (review, list, item) order, and cut the tail.
9. passes.py:280-281 with 290 and 297 — what a reviewer put in `requirements_met`
    or `follow_up` is not a finding: no findings header, and no `reviewed` opt-in
    even when the model says `from_review`.
10. passes.py:319-337 — the items shown are exactly the single snapshot read at 319:
    a concurrent commit cannot join the prompt or `shown` (ordering forced by the
    artifact seam plus Events).
Same rig as the landed passes tests: a real database on the test's own ARCHEUS_HOME,
the real artifact store, the real writer and the real `end_call`, with only the two
seams a pass has answered here — its own call, and the artifact read its facts come
from. `_win_short` is faked so no Windows DLL is ever loaded, the account home is a
directory under `tmp_path`, and nothing reads an environment value, a real process,
a real model or the clock.
"""

import itertools
import json
import threading
from collections import namedtuple

import pytest

from archeus.core.application import commands
from archeus.core.application import knowledge as K
from archeus.core.calls import Called
from archeus.core.domain import entities, ids
from archeus.core.domain.events import new_event
from archeus.core.domain.values import Ref
from archeus.core.knowledge import passes
from archeus.infra.artifacts import store as artifacts
from archeus.infra.db import Database, rows

WS = ids.GLOBAL_WORKSPACE
#: A repository path naming no drive and holding no reserved character: prompt text only.
REPO_PATH = 'repo/under/t1130'
#: What the fake model quotes back (one line `_facts` really prints).
QUOTE_TWO = 'Package dependencies: beta-dep'
LESSONS = {'lessons': [{'title': 'Pin the formatter', 'text': 'it drifts',
                        'outcome': 'failed', 'from_review': True}]}
F_CHAR = passes.FINDING_CHARS
F_MAX = passes.FINDINGS_MAX
_SEQ = itertools.count(1)
#: The three lists a finding may come from, spelled out rather than read from the
#: source: `passes.FINDING_LISTS` is the contract this asserts, not its input.
LABELS = ('requirements_missing', 'regressions', 'risks')
AccountRef = namedtuple('AccountRef', 'account_id home_ref')


@pytest.fixture
def db():
    d = Database.open()
    yield d
    d.close()


@pytest.fixture(autouse=True)
def no_short_name_probe(monkeypatch):
    """`Homes` probes an 8.3 short name through kernel32 for a drive-rooted home.
    It is faked for the whole file, so a bound home never loads a real DLL."""
    monkeypatch.setattr('archeus.core.homes._win_short', lambda path: None)


@pytest.fixture
def actor(db):
    return Ref('system', db.writer.execute(commands.register_principal, {
        'kind': 'system', 'scopes': ['system']})['id'])


# ── seeding: what a pass is asked about ─────────────────────────────────────

def _insert(db, who, entity, etype):
    """One row plus the event that says it appeared (the writer refuses a command
    that mutates and records no event), written by the pass's own actor."""
    def put(tx, *, actor):
        tx.insert(entity, actor=actor)
        tx.append(new_event(etype, Ref(ids.kind_of(entity.id), entity.id), actor))
    db.writer.execute(put, {'actor': who})
    return entity.id


def project(db, who, name='layered-python'):
    return _insert(db, who, entities.Project(id=ids.new_id('project'), workspace_id=WS,
                                             name=name), 'project.created')


def _payload(files=(), deps=()):
    return json.dumps({'files': list(files), 'edges': [],
                       'dependencies': [{'name': d} for d in deps]}).encode('utf-8')


def source(db, who, pid, *, payload=None, revision='rev-1', path=None):
    """A repository of *pid* and one COMPLETED inspection of it: (inspection id, sha).
    Its path is unique per call: the path key is unique per workspace, and a test
    that seeds two inspections of one project seeds two repositories."""
    where = path or '%s/r%03d' % (REPO_PATH, next(_SEQ))
    rid = _insert(db, who, entities.Repository(id=ids.new_id('repository'), workspace_id=WS,
                                               project_id=pid, path=where,
                                               path_key=where), 'repository.registered')
    sha = None if payload is None else artifacts.put(payload)
    iid = _insert(db, who, entities.RepositoryInspection(
        id=ids.new_id('repository_inspection'), repository_id=rid, extractor_version=1,
        revision=revision, state='COMPLETED', languages=(('python', 4),), frameworks=(),
        payload_sha256=sha), 'repository_inspection.state_changed')
    return iid, sha


def kno_id(entropy):
    """A knowledge item id pinned to a fixed moment and entropy: two of these order
    by id as strings, which is what the item-bound tie-break has to sort on."""
    return 'kno_' + ids.encode(1700000000000, entropy)


def item(db, who, pid, iid, *, title, text='the text', state='CONFIRMED', origin='inferred',
         observed_at='2026-01-01T00:00:00Z', kind='repository_inspection', entity_id=None):
    src = None if iid is None else Ref(kind, iid)
    k = entities.KnowledgeItem(id=entity_id or ids.new_id('knowledge_item'), workspace_id=WS,
                               project_id=pid, type='ENTITY', title=title, text=text,
                               state=state, origin=origin, source_ref=src, observed_at=observed_at)
    return _insert(db, who, k, 'knowledge_item.created')


def mission(db, who, *, reviews=()):
    """One ended mission with its own context package and one review per entry of
    `reviews` (a dict of finding lists, or {} for a plain verdict)."""
    pid = project(db, who)
    mid = _insert(db, who, entities.Mission(id=ids.new_id('mission'), workspace_id=WS,
                                            title='Ship it', objective='dark first',
                                            project_id=pid), 'mission.created')
    ctx = _insert(db, who, entities.ContextPackage(id=ids.new_id('context_package'),
                                                   workspace_id=WS, subject_kind='mission',
                                                   subject_id=mid, query='q'),
                  'context_package.created')
    plan = _insert(db, who, entities.Plan(id=ids.new_id('plan'), mission_id=mid,
                                          plan_version=1, summary='the first plan'),
                   'plan.created')

    def bind(tx, *, actor):
        tx.update(entities.Mission, mid, {'context_package_id': ctx}, actor=actor)
        tx.append(new_event('mission.updated', Ref('mission', mid), actor))
    db.writer.execute(bind, {'actor': who})
    for found in reviews:
        _insert(db, who, entities.Review(id=ids.new_id('review'), mission_id=mid,
                                         reviewer='model', verdict='changes_requested',
                                         plan_id=plan, **found), 'review.requested')
    return {'mission_id': mid, 'project_id': pid, 'context_package_id': ctx}


def open_call(db, who, purpose, source_ref):
    """A committed own-call decision with no outcome yet, as `OwnCalls.run` leaves
    one before its adapter runs: the real `end_call` needs the real row."""
    rd = ids.new_id('route_decision')

    def put(tx, *, actor):
        tx.insert(entities.RouteDecision(
            id=rd, subject=Ref('archeus_call', purpose), purpose=purpose, decided_by='router',
            source=source_ref, selected='fake', harness_id='fake', result='selected'),
            actor=actor)
        tx.append(new_event('route.decided', Ref('route_decision', rd), actor))
    db.writer.execute(put, {'actor': who})
    return rd


def answer(state='ok', parsed=None, rd='rte_x', usage=None, attempts=1, account='fake:fake'):
    """One own call's answer: the very tuple `OwnCalls.run` returns."""
    return Called(route_decision_id=rd, state=state, parsed=parsed, usage=usage or {},
                  detail='', attempts=attempts, account_ref=account)


# ── the rig: the pass's own call and its artifact read, everything else real ──

class Rig:
    """`Passes` over a real database with only what it reaches through answered
    here: its own call, the artifact its facts read, and its recording command.
    `real_record=True` lets the real `record_consolidation` run, so what the pass
    handed it is judged by the command's own contract."""

    def __init__(self, db, who, monkeypatch, *, answers=(), real_record=False):
        self.asked, self.recorded, self.reads = [], [], []
        self.answers = list(answers) or [answer()]
        self.real_record = real_record
        self.hook = None
        monkeypatch.setattr(passes, 'artifacts', type('Artifacts', (), {'get': self._get}))
        monkeypatch.setattr(passes, 'K', type('K', (), {
            'record_knowledge_pass': self._refused('knowledge'),
            'record_decisions': self._refused('decisions'),
            'record_lessons': self._recording('lessons'),
            'record_consolidation': self._recording('consolidation')}))
        self.passes = passes.Passes(db, actor=who, calls=self)

    def _get(self, sha, home=None):
        self.reads.append(sha)
        if self.hook is not None:
            self.hook(len(self.reads))
        return artifacts.get(sha)

    def _refused(self, which):
        def command(tx, *, actor, **kw):
            raise AssertionError('the lessons/consolidation card must not run %s' % which)
        return command

    def _recording(self, which):
        def command(tx, *, actor, **kw):
            self.recorded.append(dict(kw, command=which, actor=actor))
            if self.real_record:
                return getattr(K, 'record_' + which)(tx, actor=actor, **kw)
            return {'which': which}
        command.__qualname__ = 'record_' + which
        return command

    def run(self, **kw):
        self.asked.append(kw)
        return self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]

    def prompt(self, n=-1):
        return self.asked[n]['prompt']


def _rows(db, cls, **eq):
    with db.read() as conn:
        return rows.where(conn, cls, **eq)


def _count(db, cls, **eq):
    return len(_rows(db, cls, **eq))


def _items(db, pid=None):
    """Every knowledge item, optionally of one project, as entities (in row order).
    `supersedes_id` is never asked of `rows.where`: SQL `= NULL` matches nothing."""
    with db.read() as conn:
        got = rows.where(conn, entities.KnowledgeItem) if pid is None else \
            rows.where(conn, entities.KnowledgeItem, project_id=pid)
    return [r.entity for r in got]


def _outcome(db, rd):
    with db.read() as conn:
        return rows.get(conn, entities.RouteDecision, rd).entity


def _lines(text):
    return text.split('\n')


def _blocks(prompt):
    """The consolidate prompt as {inspection id: ['<id> <title>: <text>', ...]}."""
    out, cur = {}, None
    for ln in _lines(prompt):
        if ln.startswith('Facts from inspection '):
            cur = ln[len('Facts from inspection '):].rstrip(':')
            out[cur] = []
        elif cur is not None and ln.startswith('- '):
            out[cur].append(ln[2:])
    return out


def _finding_lines(prompt):
    return [ln for ln in _lines(prompt) if ln.startswith('Review finding')]


def _states(seed):
    """What the items of case `seed` were before the pass ran: the control that says
    a refusal to call the model also refused to write anything."""
    return {'no-items': [], 'candidate': ['CANDIDATE'], 'no-source': ['CONFIRMED'],
            'meeting-source': ['CONFIRMED'], 'retracted': ['RETRACTED']}[seed]


# ── 1: nothing eligible means no call ───────────────────────────────────────

@pytest.mark.parametrize('seed', ['no-items', 'candidate', 'no-source', 'meeting-source',
                                  'retracted'],
                         ids=['no-items', 'candidate', 'no-src', 'meeting', 'retracted'])
def test_no_eligible_inspected_confirmed_item_makes_no_call_at_all(db, actor, monkeypatch,
                                                                    seed):
    """passes.py:320-321 over the filters at 307-311. Invert `state == 'CONFIRMED'`,
    drop `source_ref is not None`, drop `source_ref.kind == 'repository_inspection'`
    or remove the `if not items` guard, and the pass puts an item the model must not
    judge into a call whose answer is allowed to add CANDIDATEs."""
    pid = project(db, actor)
    iid, _ = source(db, actor, pid, payload=_payload(files=['app/core/store.py']))
    if seed == 'candidate':
        item(db, actor, pid, iid, title='draft', state='CANDIDATE')
    elif seed == 'no-source':
        item(db, actor, pid, None, title='from-the-user', origin='explicit')
    elif seed == 'meeting-source':
        # the same real inspection, reached as a meeting note: the item is about
        # something that was inspected, but it was not read from that inspection
        item(db, actor, pid, iid, title='from-a-meeting', kind='meeting', origin='explicit')
    elif seed == 'retracted':
        item(db, actor, pid, iid, title='taken-back', state='RETRACTED')
    r = Rig(db, actor, monkeypatch)
    assert r.passes.consolidate(pid, 5) == 'nothing to consolidate'
    assert r.asked == []                                    # no model call was made
    assert r.recorded == []                                 # nothing was recorded
    assert r.reads == []                                    # no payload was opened
    assert _count(db, entities.RouteDecision) == 0          # no call was opened either
    assert [k.state for k in _items(db)] == _states(seed)   # nothing was added or changed


# ── 1b: another project's item, and every non-inspection source, stay out ─────

def test_another_projects_item_and_every_other_source_never_enter_the_prompt(
        db, actor, monkeypatch):
    """passes.py:307-310, 326-327 and 337. Widen the `project_id=project_id` filter
    and another project's title, text and inspection go into this project's model
    call and into `shown`, which is what `record_consolidation` trusts as "what the
    model was actually given"; widen the source filter and a meeting-derived item is
    re-checked against repository facts that never produced it."""
    mine, theirs = project(db, actor, 'mine'), project(db, actor, 'theirs')
    my_iid, payload_sha = source(db, actor, mine, payload=_payload(files=['app/core/store.py']))
    their_iid, their_sha = source(db, actor, theirs, payload=_payload(
        files=['secret/vault.py'], deps=['vault-dep']))
    keep = item(db, actor, mine, my_iid, title='alpha-fact', text='api above core')
    item(db, actor, theirs, their_iid, title='beta-other-project', text='the-key-of-vault')
    item(db, actor, mine, my_iid, title='gamma-draft', state='CANDIDATE')
    item(db, actor, mine, None, title='delta-user-word')
    item(db, actor, mine, my_iid, title='epsilon-meeting', kind='meeting', origin='explicit')
    r = Rig(db, actor, monkeypatch,
           answers=[answer(parsed={'items': [{'id': keep, 'verdict': 'keep'}]})])
    assert r.passes.consolidate(mine, 5) == 'ok'
    prompt = r.prompt()
    assert _blocks(prompt) == {my_iid: ['%s alpha-fact: api above core' % keep]}
    for hidden in ('beta-other-project', 'the-key-of-vault', 'vault-dep', 'secret/vault',
                   'gamma-draft', 'delta-user-word', 'epsilon-meeting'):
        assert hidden not in prompt
    assert r.reads == [payload_sha]                         # only my own payload was opened
    assert their_sha not in r.reads                         # theirs was never even opened
    (got,) = r.recorded
    assert got['command'] == 'consolidation'
    assert got['shown'] == (keep,)
    assert got['project_id'] == mine and got['called']['context_package_id'] is None
    assert _count(db, entities.ContextPackage) == 0         # consolidation assembles none
    kw = r.asked[-1]
    assert (kw['purpose'], kw['no_tools'], kw['workdir']) == (
        'knowledge_extraction', True, passes.paths.fresh_call_dir)
    assert kw['source'] == {'kind': 'project', 'id': mine}
    assert kw['workspace_id'] == WS and kw['project_id'] == mine
    assert kw['schema'] is passes.CONSOLIDATE_SCHEMA
    assert kw['check'] is passes.check_consolidation
    assert kw.get('context_package_id') is None             # nothing was assembled for it


# ── 2: an item whose inspection is gone is dropped, never claimed verified ───

def test_an_item_whose_inspection_row_is_gone_is_dropped_and_never_claimed(
        db, actor, monkeypatch):
    """passes.py:314-315 and 318. Remove `if i is not None` and the pass shows a model
    facts for an inspection it never read (`None.entity` raises first), and the item
    stays in `shown`, so `record_consolidation` accepts a supersede of an item that
    was never re-checked against anything; remove the trailing filter at 318 and the
    same item is offered to the model with no facts above it, in a call that then
    records it as seen."""
    pid = project(db, actor)
    good, sha = source(db, actor, pid, payload=_payload(files=['app/core/store.py'],
                                                         deps=['alpha-dep']))
    gone = ids.new_id('repository_inspection')
    kept = item(db, actor, pid, good, title='kept-item')
    item(db, actor, pid, gone, title='orphan-item', text='what nobody verified')
    r = Rig(db, actor, monkeypatch, answers=[answer(parsed={'items': []})])
    assert r.passes.consolidate(pid, 5) == 'ok'
    assert _blocks(r.prompt()) == {good: ['%s kept-item: the text' % kept]}
    assert gone not in r.prompt() and 'orphan-item' not in r.prompt()
    assert r.reads == [sha]                                 # the dead source read nothing
    (got,) = r.recorded
    assert got['shown'] == (kept,)                          # never "shown" => never applied
    assert list(got['sources']) == [good]
    assert [k.state for k in _items(db, pid)] == ['CONFIRMED'] * 2

    # and when EVERY item is like that, the pass refuses to ask at all
    pid2 = project(db, actor, 'orphans')
    dead = ids.new_id('repository_inspection')
    item(db, actor, pid2, dead, title='only-orphan')
    r2 = Rig(db, actor, monkeypatch)
    assert r2.passes.consolidate(pid2, 5) == 'nothing to consolidate'
    assert (r2.asked, r2.recorded, r2.reads) == ([], [], [])
    assert [k.state for k in _items(db, pid2)] == ['CONFIRMED']   # the orphan is left alone


# ── 3: a quote from another source's facts cannot replace an item ───────────

def test_a_quote_from_another_sources_facts_is_flagged_not_applied(db, actor, monkeypatch):
    """passes.py:322 and 336-338 against knowledge.py:452-453 (`quote not in
    sources.get(old.source_ref.id, '')`). Build `sources` as one merged blob, or key
    it by something other than the inspection the item was read from, and a model
    that quotes the facts of source B replaces an item that was read from source A:
    the fail-closed check stops working because the facts it checks against are no
    longer the facts that produced the item."""
    pid = project(db, actor)
    one, _ = source(db, actor, pid, payload=_payload(files=['app/one/x.py'],
                                                      deps=['alpha-dep']))
    two, _ = source(db, actor, pid, payload=_payload(files=['app/two/y.py'],
                                                     deps=['beta-dep']))
    a = item(db, actor, pid, one, title='alpha-item', observed_at='2026-01-01T00:00:00Z')
    b = item(db, actor, pid, two, title='beta-item', observed_at='2026-01-02T00:00:00Z')
    result = {'items': [{'id': a, 'verdict': 'supersede', 'title': 'wrong source',
                         'text': 'quoted from the other repository', 'quote': QUOTE_TWO},
                        {'id': b, 'verdict': 'supersede', 'title': 'right source',
                         'text': 'quoted from its own repository', 'quote': QUOTE_TWO}]}
    rd = open_call(db, actor, 'knowledge_extraction', Ref('project', pid))
    r = Rig(db, actor, monkeypatch, real_record=True,
            answers=[answer(parsed=result, rd=rd, usage={'tokens_in': 5})])
    assert r.passes.consolidate(pid, 5) == 'ok'
    (got,) = r.recorded
    # the facts are keyed per inspection and never carry another's words
    assert sorted(got['sources']) == sorted([one, two])
    assert 'beta-dep' not in got['sources'][one] and 'app/one/x.py' not in got['sources'][two]
    assert _blocks(r.prompt()) == {one: ['%s alpha-item: the text' % a],
                                   two: ['%s beta-item: the text' % b]}
    # ... so only the item whose own source carries the quote is replaced
    new = [k for k in _items(db, pid) if k.supersedes_id]
    assert [(k.title, k.state, k.source_ref.id) for k in new] == [
        ('right source', 'CANDIDATE', two)]
    assert [(k.id, k.state, k.title) for k in _items(db, pid) if not k.supersedes_id] == [
        (a, 'CONFIRMED', 'alpha-item'), (b, 'CONFIRMED', 'beta-item')]
    d = _outcome(db, rd)
    assert (d.outcome['state'], d.outcome['items'], d.outcome['flagged'],
            d.outcome['dropped']) == ('ok', 1, [a], 0)
    assert _count(db, entities.Relation) == 1               # only the one supersedes edge
    (rel,) = _rows(db, entities.Relation)
    assert (rel.entity.rel, rel.entity.dst_kind, rel.entity.dst_id) == ('supersedes',
                                                                        'knowledge_item', b)


# ── 4: the item bound is observed_at, then id, and cuts before grouping ─────

def test_the_item_bound_sorts_observed_at_then_id_before_the_sources_are_grouped(
        db, actor, monkeypatch):
    """passes.py:311. Drop `or ''` and an item with no observed_at raises (or sorts
    last, depending on the mix) instead of taking the oldest place the docstring
    promises ("oldest CONFIRMED items"); drop `, k.id` and two items seen at the same
    instant are ordered by insertion, so the same project consolidates differently
    on two runs; and check that the cut happens HERE, before 312-317: a source whose
    only item fell outside the bound is never read and never named."""
    pid = project(db, actor)
    one, sha1 = source(db, actor, pid, payload=_payload(files=['app/one/x.py']))
    two, sha2 = source(db, actor, pid, payload=_payload(files=['app/two/y.py']))
    late = kno_id(4)
    item(db, actor, pid, two, title='late-from-two', entity_id=late,
         observed_at='2026-03-01T00:00:00Z')
    high = kno_id(2)
    item(db, actor, pid, one, title='high-id', entity_id=high,
         observed_at='2026-01-01T00:00:00Z')
    none = kno_id(3)
    item(db, actor, pid, one, title='no-observed-at', entity_id=none, observed_at=None)
    low = kno_id(1)
    item(db, actor, pid, one, title='low-id', entity_id=low, observed_at='2026-01-01T00:00:00Z')
    r = Rig(db, actor, monkeypatch, answers=[answer(parsed={'items': []})])
    assert r.passes.consolidate(pid, 3) == 'ok'
    (got,) = r.recorded
    assert got['shown'] == (none, low, high)                # None first, then the id tie-break
    assert _blocks(r.prompt()) == {one: ['%s no-observed-at: the text' % none,
                                         '%s low-id: the text' % low,
                                         '%s high-id: the text' % high]}
    assert 'late-from-two' not in r.prompt() and two not in r.prompt()
    assert r.reads == [sha1]                                # the cut source was never opened
    assert sha2 not in r.reads


# ── 5: two items, one inspection: one fact extraction, both ids shown ───────

def test_two_items_of_one_inspection_are_one_fact_extraction_and_one_call(
        db, actor, monkeypatch):
    """passes.py:313-318 with 322-327 and 336-337: what `seen` decides is how many fact
    extractions one own call carries, and `shown` is what `record_consolidation`
    later accepts as "the model saw this". Drop the per-source grouping (the
    `if k.source_ref.id == iid` at 326-327) and every item of the project is shown under
    every facts block, so an item is "re-checked" against facts that never mention
    it. Pinned here, from two items of one inspection: ONE facts block, ONE payload
    read (the `not in seen` guard at 315 is what keeps `seen` one entry per
    inspection, and one entry is what 322 turns into one read), ONE own call, and
    BOTH ids in `shown`, which is the batch the answer may be applied to."""
    pid = project(db, actor)
    iid, sha = source(db, actor, pid, payload=_payload(files=['app/one/x.py', 'app/two/y.py'],
                                                        deps=['alpha-dep']), path=REPO_PATH)
    old = item(db, actor, pid, iid, title='older-item', observed_at='2026-01-01T00:00:00Z')
    new = item(db, actor, pid, iid, title='newer-item', observed_at='2026-02-01T00:00:00Z')
    r = Rig(db, actor, monkeypatch, answers=[answer(parsed={'items': []})])
    assert r.passes.consolidate(pid, 10) == 'ok'
    assert len(r.asked) == 1                                # one call for the whole batch
    assert r.reads == [sha]                                 # read once, not once per item
    assert r.prompt().count('Facts from inspection %s:' % iid) == 1
    assert _blocks(r.prompt()) == {iid: ['%s older-item: the text' % old,
                                          '%s newer-item: the text' % new]}
    assert [ln for ln in _lines(r.prompt()) if ln.startswith('Repository: ')] == [
        'Repository: %s at rev-1' % REPO_PATH]              # the facts block, once
    (got,) = r.recorded
    assert got['shown'] == (old, new) and got['sources'] == {iid: got['sources'][iid]}
    assert got['called'] == {'route_decision_id': 'rte_x', 'attempts': 1,
                             'account_ref': 'fake:fake', 'usage': {},
                             'context_package_id': None}
    assert _count(db, entities.ContextPackage) == 0


# ── 6: a call that did not answer records nothing and never ends ok ─────────

@pytest.mark.parametrize('state', ['gated', 'unavailable', 'timeout', 'model_unavailable',
                                   'failed', 'invalid'],
                         ids=['gated', 'unavailable', 'timeout', 'model', 'failed', 'invalid'])
def test_a_consolidation_call_that_did_not_answer_records_nothing_and_never_ends_ok(
        db, actor, monkeypatch, state):
    """passes.py:334-335. Remove the guard and an answer the call never gave becomes
    CANDIDATEs naming real items as superseded, and `_record` writes an `ok` outcome
    over a call that was gated, so the worker's daily cap counts a call that reached
    no model and the retry of a gated pass is lost."""
    pid = project(db, actor)
    iid, _ = source(db, actor, pid, payload=_payload(files=['app/one/x.py'],
                                                     deps=['beta-dep']))
    kept = item(db, actor, pid, iid, title='only-item')
    rd = open_call(db, actor, 'knowledge_extraction', Ref('project', pid))
    hostile = {'items': [{'id': kept, 'verdict': 'supersede', 'title': 'invented',
                          'quote': QUOTE_TWO}]}
    r = Rig(db, actor, monkeypatch, answers=[answer(state=state, parsed=hostile, rd=rd,
                                                    usage={'tokens_in': 3})])
    assert r.passes.consolidate(pid, 5) == state
    assert r.recorded == []                                 # the recording command never ran
    assert len(r.asked) == 1                                # it asked, then stopped
    assert [k for k in _items(db, pid) if k.supersedes_id] == []
    assert [k.title for k in _items(db, pid)] == ['only-item']   # no candidate was added
    assert _outcome(db, rd).outcome is None                 # never ended, above all not ok
    assert _count(db, entities.UsageLedger, route_decision_id=rd) == 0


# ── 7: a finding is redacted and scrubbed before it is cut ──────────────────

class _HomeCaller:
    """What `application/resources.py:831-834` reads as `db.writer.live`: the pair
    `(registry, callers)` that `bound_homes` turns into homes, here with one adapter
    whose default account lives at a temporary home."""

    id = 'fake-t1130'

    def __init__(self, home):
        self.ref = AccountRef('acct-t1130', home)

    def default_account(self):
        return self.ref


def test_a_lesson_finding_is_redacted_and_scrubbed_before_it_is_cut(db, actor, monkeypatch,
                                                                     tmp_path):
    """passes.py:280-281, the `scrub_text(redact(x), homes)[:FINDING_CHARS]` order.
    Move the cut outside `redact`/`scrub_text` and a secret or an account home that
    starts near FINDING_CHARS is cut to a fragment its matcher no longer recognises,
    so the prompt carries the readable prefix of a credential or of where an account
    lives. The existing findings test uses no bound home and a secret that ends well
    before the cut, so neither ordering is visible there."""
    home = str(tmp_path / 'T1130-LiveHome')
    (tmp_path / 'T1130-LiveHome').mkdir()
    db.writer.live = (None, [_HomeCaller(home)])
    s = mission(db, actor, reviews=[{
        'regressions': ['a' * (F_CHAR - 4) + 'sk-' + 'q' * 30],
        'requirements_missing': ['b' * (F_CHAR - 10) + ' ' + home + '/secrets/id-key'],
        'risks': ['read %s/settings.json' % home]}])
    r = Rig(db, actor, monkeypatch, answers=[answer(parsed=LESSONS)])
    assert r.passes.lessons(s['mission_id']) == 'ok'
    assert _finding_lines(r.prompt()) == [
        # the home is a word-boundary match: the cut falls ten characters into it,
        # where the raw path would still be recognisable if it had been cut first
        'Review finding (requirements_missing): ' + 'b' * (F_CHAR - 10) + ' its home/',
        'Review finding (regressions): ' + 'a' * (F_CHAR - 4) + '[red',
        'Review finding (risks): read its home/settings.json']
    prompt = r.prompt()
    assert home not in prompt and 'secrets/id-key' not in prompt
    assert 'sk-' not in prompt and 'q' * 6 not in prompt
    assert 'q' * 30 not in prompt
    assert r.recorded[0]['reviewed'] is True


# ── 8: the two caps keep category, order and the tail ───────────────────────

def test_the_findings_cap_and_the_per_finding_cut_keep_category_and_order(db, actor,
                                                                           monkeypatch):
    """passes.py:280-281, `[:FINDINGS_MAX]` and `[:FINDING_CHARS]` together. Drop the
    outer cap and a review with hundreds of findings puts them all in one call; drop
    the inner one and one giant finding is carried whole; and iterate `reviews` in an
    unstable order (or the two comprehensions swapped) and which finding survives the
    cap, and under which category label it is named, is no longer (review, list, item)
    order."""
    long_fit, long_over = 'y' * F_CHAR, 'z' * (F_CHAR + 1)
    first = {'requirements_missing': ('m1', 'm2'), 'regressions': ('r1', 'r2'),
             'risks': ('k1', 'k2')}
    second = {'requirements_missing': tuple('n%d' % i for i in range(7)),
              'regressions': tuple('s%d' % i for i in range(4)),
              'risks': (long_fit, long_over, 'tail-kept', 'tail-dropped')}
    s = mission(db, actor, reviews=[first, second])
    r = Rig(db, actor, monkeypatch, answers=[answer(parsed=LESSONS)])
    assert r.passes.lessons(s['mission_id']) == 'ok'
    # what the reviewer filed, in (review, list, item) order, uncapped and uncut:
    # one finding over the cap, so the tail is what must fall away.
    raw = ['Review finding (%s): %s' % (label, x)
           for found in (first, second) for label in LABELS for x in found[label]]
    assert len(raw) == F_MAX + 1
    expected = raw[:F_MAX]
    over = expected.index('Review finding (risks): ' + long_over)
    expected[over] = 'Review finding (risks): ' + long_over[:F_CHAR]
    got = _finding_lines(r.prompt())
    assert got == expected                                  # every label and every byte
    assert len(got) == F_MAX                                # the tail, and only it, is gone
    assert 'tail-dropped' not in r.prompt() and 'tail-kept' in r.prompt()
    assert ('z' * (F_CHAR + 1)) not in r.prompt()           # the extra byte did not survive
    assert ('y' * F_CHAR) in r.prompt()                     # the exact fit is not cut at all


# ── 9: what a reviewer filed elsewhere is not a finding ────────────────────

def test_a_reviewers_met_list_and_follow_up_are_not_findings_and_give_no_opt_in(
        db, actor, monkeypatch):
    """passes.py:280-281 (`for f in FINDING_LISTS`) with 290 and 297. Fold
    `requirements_met` or `follow_up` into the findings and the lessons prompt is
    told to set `from_review` on lessons drawn from what a reviewer said went FINE,
    and `reviewed=bool(found)` opts the project into review-sourced lessons that no
    reviewer ever reported. The landed findings tests only ever seed the three lists
    they name, together with a `reviewed` they read back, never this combination."""
    s = mission(db, actor, reviews=[{'requirements_met': ('the tests all pass',),
                                     'follow_up': ('file a card for the docs',),
                                     'summary': 'looked good'}])
    r = Rig(db, actor, monkeypatch, answers=[answer(parsed=LESSONS)])
    assert r.passes.lessons(s['mission_id']) == 'ok'
    assert _finding_lines(r.prompt()) == []
    assert passes.LESSONS_FINDINGS not in r.prompt()        # no findings header at all
    assert r.prompt().startswith(passes.LESSONS_PREFIX + 'Mission: ')
    assert 'the tests all pass' not in r.prompt() and 'file a card' not in r.prompt()
    assert 'Review: PENDING' in r.prompt()                  # the verdict is still shown
    (got,) = r.recorded
    assert got['reviewed'] is False                         # no provenance opt-in
    assert got['result'] == LESSONS                         # the model's claim changes nothing


# ── 10: what is shown is exactly the one snapshot the pass read ─────────────

def test_a_commit_after_the_snapshot_cannot_join_the_call(db, actor, monkeypatch):
    """passes.py:319-337. `shown` is what `record_consolidation` accepts as "the
    model saw this item" (knowledge.py:444). Re-read the items while the prompt is
    being built (or when `shown` is assembled) and an item some other thread confirmed
    in between is applied by its answer without ever having been in the prompt. The
    ordering is forced at the artifact seam with Events, never a sleep: the pass waits
    inside its first facts read until the other thread has committed."""
    pid = project(db, actor)
    one, sha1 = source(db, actor, pid, payload=_payload(files=['app/one/x.py']))
    two, sha2 = source(db, actor, pid, payload=_payload(files=['app/two/y.py']))
    shown = item(db, actor, pid, one, title='in-the-snapshot',
                 observed_at='2026-01-01T00:00:00Z')
    reached, committed = threading.Event(), threading.Event()

    def hook(n):
        if n == 1:
            reached.set()                             # the snapshot has been read
            assert committed.wait(5), 'the concurrent commit never happened'

    def late_committer():
        try:
            if reached.wait(5):
                item(db, actor, pid, two, title='committed-too-late',
                     observed_at='2026-01-02T00:00:00Z')
        finally:
            committed.set()

    r = Rig(db, actor, monkeypatch, answers=[answer(parsed={'items': []})])
    r.hook = hook
    thread = threading.Thread(target=late_committer, name='t1130-late-committer')
    thread.start()
    try:
        assert r.passes.consolidate(pid, 10) == 'ok'
    finally:
        thread.join(5)
    assert not thread.is_alive()
    assert reached.is_set() and committed.is_set()
    assert _blocks(r.prompt()) == {one: ['%s in-the-snapshot: the text' % shown]}
    assert 'committed-too-late' not in r.prompt() and two not in r.prompt()
    assert r.reads == [sha1] and sha2 not in r.reads        # one source, the snapshot's
    (got,) = r.recorded
    assert got['shown'] == (shown,)                         # never shown, so never applied
    assert got['sources'] == {one: got['sources'][one]}

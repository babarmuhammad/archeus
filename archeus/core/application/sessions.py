"""Session commands (P12, p12-design-gate §7, §9, §10.2, §14): every function
is ONE writer transaction. A Session is a provider conversation; nothing here
moves a mission, a plan, a task or an execution, and nothing here authorises
anything (§16): a user's own session is the user's.

What an adapter has to find out about the world — is the provider session
still there, what does the target harness offer — is found out by the caller
(core/sessions/service.py) before the command and passed in as plain data;
launching a terminal happens after the command commits.

Only a user device changes a session; only Core (system) records what it
observed of one (`vanished`, `reappeared`, `observe`, a launch's outcome) and
writes the headless session an execution ran in.
"""

import time

from ...infra.artifacts import store as artifacts
from ...infra.eventlog import outbox
from ..domain import entities, ids
from ..domain.events import new_event
from ..domain.values import Ref
from ..sessions import continuity, render
from . import authorization, lifecycle


def _now():
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


def _user(actor):
    if actor.kind != 'user_device':
        raise authorization.NotPermitted('only a user device changes a session')


def _core(actor):
    if actor.kind != 'system':
        raise authorization.NotPermitted('only Core records what it observed of a session')


def _event(tx, type_, s, actor, payload):
    return tx.append(new_event(type_, Ref('session', s.id), actor, payload=payload,
                               workspace=s.workspace_id, project=s.project_id))


def _fire(tx, s, trigger, actor, reason, fields=None):
    row, _ev = lifecycle.fire(tx, entities.Session, s.id, trigger, actor=actor, reason=reason,
                              fields=fields)
    return row.entity


def _mission_in_scope(tx, mission_id, workspace_id, project_id):
    """A session may continue a mission of its own workspace and project only (§17)."""
    m = lifecycle.load(tx, entities.Mission, mission_id).entity
    if m.workspace_id != workspace_id or m.project_id != project_id:
        raise authorization.NotPermitted(
            'mission %s is not of this session\'s workspace and project' % mission_id)
    return m


def _account_of(tx, account_id, harness_id):
    if account_id is None:
        return None
    a = lifecycle.load(tx, entities.Account, account_id).entity
    if a.harness_id != harness_id:
        raise ValueError('account %s is not a %s account' % (account_id, harness_id))
    if a.health == 'DISABLED':
        raise ValueError('account %s is disabled' % account_id)
    return a


def _vocabulary(value, offered, what, harness_id):
    """ADR-0022: a value the harness does not know is refused when asked for
    explicitly — never translated."""
    if value and value not in offered:
        raise ValueError('%s does not offer %s %r' % (harness_id, what, value))
    return value or None


# ── creating a session ──────────────────────────────────────────────────────

def open_session(tx, *, actor, harness_id, cwd, mode, workspace_id=ids.GLOBAL_WORKSPACE,
                 project_id=None, mission_id=None, account_id=None, provider_session_ref=None,
                 transcript_path=None, model=None, effort=None, models=(), efforts=(),
                 launch=False):
    """A new Session: `manual` (the user registers one they started),
    `interactive_attached` with `launch` (Archeus opens it in a terminal after
    this commits). Its cursor starts at now: it has seen nothing before."""
    _user(actor)
    if mode not in ('manual', 'interactive_attached'):
        raise ValueError('a user registers or launches a manual or interactive session')
    if project_id is not None:
        lifecycle.load(tx, entities.Project, project_id)
    if mission_id is not None:
        _mission_in_scope(tx, mission_id, workspace_id, project_id)
    _account_of(tx, account_id, harness_id)
    s = entities.Session(
        id=ids.new_id('session'), harness_id=harness_id, workspace_id=workspace_id, cwd=cwd,
        mode=mode, account_id=account_id, project_id=project_id, mission_id=mission_id,
        provider_session_ref=provider_session_ref, transcript_path=transcript_path,
        model=_vocabulary(model, models, 'model', harness_id) if launch else model,
        effort=_vocabulary(effort, efforts, 'effort', harness_id) if launch else effort,
        last_seen_seq=outbox.head(tx.conn), launch_seq=1 if launch else 0,
        started_at=_now(), last_active_at=_now())
    tx.insert(s, actor=actor)
    _event(tx, 'session.created', s, actor, {'mode': mode, 'harness_id': harness_id,
                                             'account_id': account_id, 'mission_id': mission_id,
                                             'handoff_from': None})
    return view_of(s)


def headless_session(tx, *, actor, execution, provider_session_ref=None):
    """The session an execution ran in, written at its end (§6): OPEN and then
    closed in the same transaction, so nothing can resume a session an
    execution owned — its work continues by checkpoint hand-off (§10.1)."""
    _core(actor)
    m = lifecycle.load(tx, entities.Mission, execution.mission_id).entity
    source = None
    if execution.handoff_from is not None:
        prev = tx.get(entities.Execution, execution.handoff_from)
        source = prev.entity.session_id if prev else None
    s = entities.Session(
        id=ids.new_id('session'), harness_id=execution.harness_id or 'unknown',
        workspace_id=m.workspace_id, cwd=execution.workdir or '.', mode='headless',
        account_id=execution.account_id, project_id=m.project_id, mission_id=m.id,
        provider_session_ref=provider_session_ref, model=execution.model,
        effort=execution.effort, handoff_from_session_id=source, execution_id=execution.id,
        last_seen_seq=outbox.head(tx.conn), started_at=execution.started_at or _now(),
        last_active_at=_now())
    tx.insert(s, actor=actor)
    _event(tx, 'session.created', s, actor, {'mode': 'headless', 'harness_id': s.harness_id,
                                             'account_id': s.account_id, 'mission_id': m.id,
                                             'handoff_from': source})
    s = _fire(tx, s, 'close', actor, 'the execution ended', {'closed_reason': 'execution ended'})
    tx.update(entities.Execution, execution.id, {'session_id': s.id}, actor=actor)
    return s


# ── lifecycle ───────────────────────────────────────────────────────────────

def close(tx, *, actor, session_id, reason='closed by the user'):
    _user(actor)
    s = lifecycle.load(tx, entities.Session, session_id).entity
    s = _fire(tx, s, 'close', actor, reason, {'closed_reason': reason})
    return view_of(s)


def reopen(tx, *, actor, session_id):
    _user(actor)
    s = lifecycle.load(tx, entities.Session, session_id).entity
    s = _fire(tx, s, 'reopen', actor, 'reopened by the user', {'closed_reason': None})
    return view_of(s)


def vanished(tx, *, actor, session_id, reason):
    """Core looked for the provider session and it is gone."""
    _core(actor)
    s = lifecycle.load(tx, entities.Session, session_id).entity
    return view_of(_fire(tx, s, 'vanished', actor, reason))


def reappeared(tx, *, actor, session_id, transcript_path=None):
    _core(actor)
    s = lifecycle.load(tx, entities.Session, session_id).entity
    return view_of(_fire(tx, s, 'reappeared', actor, 'the provider session is there again',
                         {'transcript_path': transcript_path or s.transcript_path}))


def link(tx, *, actor, session_id, mission_id):
    """Continue a mission in this session (§17: its own workspace and project)."""
    _user(actor)
    s = lifecycle.load(tx, entities.Session, session_id).entity
    if mission_id is not None:
        _mission_in_scope(tx, mission_id, s.workspace_id, s.project_id)
    if s.mission_id == mission_id:
        return view_of(s)
    tx.update(entities.Session, s.id, {'mission_id': mission_id}, actor=actor)
    _event(tx, 'session.linked', s, actor, {'from': s.mission_id, 'to': mission_id})
    return view_of(lifecycle.load(tx, entities.Session, s.id).entity)


def observe(tx, *, actor, session_id, provider_session_ref=None, transcript_path=None):
    """What Core found of a session it could not name before (a pi session,
    §13.3): recorded once, never overwritten."""
    _core(actor)
    s = lifecycle.load(tx, entities.Session, session_id).entity
    got = {}
    if provider_session_ref and not s.provider_session_ref:
        got['provider_session_ref'] = provider_session_ref
    if transcript_path and transcript_path != s.transcript_path:
        got['transcript_path'] = transcript_path
    if got:
        tx.update(entities.Session, s.id, got, actor=actor)
        _event(tx, 'session.observed', s, actor, dict(got))
    return view_of(lifecycle.load(tx, entities.Session, s.id).entity)


# ── launches (§14.4) ────────────────────────────────────────────────────────

def launched(tx, *, actor, session_id, launch_seq, provider_session_ref=None, error=None):
    """The outcome of launch *launch_seq*: settled once. A stale or repeated
    report changes nothing."""
    _core(actor)
    s = lifecycle.load(tx, entities.Session, session_id).entity
    if launch_seq != s.launch_seq or s.launched_seq >= launch_seq:
        return view_of(s)
    got = {'launched_seq': launch_seq, 'launch_error': error}
    if provider_session_ref and not s.provider_session_ref:
        got['provider_session_ref'] = provider_session_ref
    tx.update(entities.Session, s.id, got, actor=actor)
    _event(tx, 'session.observed', s, actor, {'launch_seq': launch_seq, 'error': error,
                                              'provider_session_ref': got.get(
                                                  'provider_session_ref')})
    return view_of(lifecycle.load(tx, entities.Session, s.id).entity)


def expire_launches(tx, *, actor):
    """Boot (D21): a launch asked of a previous Core is settled as expired,
    never replayed — a restarted Core opens no terminal nobody asks for now."""
    _core(actor)
    out = []
    for r in tx.where(entities.Session):
        s = r.entity
        if s.launch_seq > s.launched_seq:
            tx.update(entities.Session, s.id, {'launched_seq': s.launch_seq,
                                               'launch_error': 'launch_expired'}, actor=actor)
            _event(tx, 'session.observed', s, actor, {'launch_seq': s.launch_seq,
                                                      'error': 'launch_expired'})
            out.append(s.id)
    return {'expired': out}


# ── resume (§9) ─────────────────────────────────────────────────────────────

def resume(tx, *, actor, session_id, request_id, models=(), efforts=(), model=None,
           effort=None):
    """Resume a user's session: reopen it if closed, read the world now, the
    brief since its own cursor, a fresh context package, and ask for a launch.
    The same request id twice changes nothing (D10)."""
    _user(actor)
    if not request_id:
        raise ValueError('a resume names its request id')
    s = lifecycle.load(tx, entities.Session, session_id).entity
    if s.last_request == request_id:
        return dict(view_of(s), duplicate=True, brief=None, artifact_sha=None)
    if s.mode == 'headless':
        raise lifecycle.IllegalTrigger('session', s.state, 'resume',
                                       'an execution\'s session continues by hand-off, '
                                       'not by resume')
    if s.state == 'LOST':
        raise lifecycle.IllegalTrigger('session', s.state, 'resume',
                                       'its provider session is gone')
    if s.state == 'CLOSED':
        s = _fire(tx, s, 'reopen', actor, 'resumed by the user', {'closed_reason': None})
    model = _vocabulary(model, models, 'model', s.harness_id) or s.model
    effort = _vocabulary(effort, efforts, 'effort', s.harness_id) or s.effort
    head = outbox.head(tx.conn)
    ctx = continuity.package(tx, actor, s)
    b = continuity.brief(tx.conn, s, ctx, head=head)
    sha = artifacts.put(render.brief(b).encode('utf-8'))
    tx.update(entities.Session, s.id, {
        'last_seen_seq': head, 'context_package_id': ctx['package_id'],
        'last_active_at': _now(), 'model': model, 'effort': effort,
        'launch_seq': s.launch_seq + 1, 'last_request': request_id}, actor=actor)
    _event(tx, 'session.resumed', s, actor, {
        'request': request_id, 'model': model, 'effort': effort,
        'package': ctx['package_id'], 'rebuilt': ctx['rebuilt'],
        'changes': b['changes']['count'], 'brief': sha})
    s = lifecycle.load(tx, entities.Session, s.id).entity
    return dict(view_of(s), duplicate=False, brief=b, artifact_sha=sha)


# ── hand-off (§10.2) ────────────────────────────────────────────────────────

def handoff(tx, *, actor, source_session_id, request_id, harness_id, account_id=None,
            model=None, effort=None, reason='', turns=None, models=(), efforts=()):
    """A new Session on *harness_id* that continues *source_session_id*, with a
    Core-rendered artifact; the source row is not written (ADR-0023). `turns`
    are the source's text turns, read by the source's adapter — used only when
    the source continues no mission. The same request id twice makes one
    target (D10)."""
    _user(actor)
    if not request_id:
        raise ValueError('a hand-off names its request id')
    src = lifecycle.load(tx, entities.Session, source_session_id).entity
    got = tx.where(entities.Session, handoff_from_session_id=src.id, handoff_request=request_id)
    if got:
        return dict(view_of(got[0].entity), duplicate=True)
    _account_of(tx, account_id, harness_id)
    same = harness_id == src.harness_id
    model = _vocabulary(model, models, 'model', harness_id) or (
        src.model if same and src.model in models else None)
    effort = _vocabulary(effort, efforts, 'effort', harness_id) or (
        src.effort if same and src.effort in efforts else None)
    head = outbox.head(tx.conn)
    if src.mission_id is not None:
        ctx = continuity.package(tx, actor, src)
        text = render.handoff(view_of(src), continuity.handoff_state(tx.conn, src, ctx, head),
                              None)
    elif turns:
        ctx = continuity.package(tx, actor, src)
        text = render.handoff(view_of(src), None, [tuple(t) for t in turns])
    else:
        raise lifecycle.IllegalTrigger('session', src.state, 'handoff',
                                       'it continues no mission and has no readable '
                                       'transcript: there is nothing to hand over')
    sha = artifacts.put(text.encode('utf-8'))
    t = entities.Session(
        id=ids.new_id('session'), harness_id=harness_id, workspace_id=src.workspace_id,
        cwd=src.cwd, mode='interactive_attached', account_id=account_id,
        project_id=src.project_id, mission_id=src.mission_id, model=model, effort=effort,
        handoff_from_session_id=src.id, handoff_request=request_id, handoff_artifact_sha=sha,
        context_package_id=ctx['package_id'], last_seen_seq=head, launch_seq=1,
        started_at=_now(), last_active_at=_now())
    tx.insert(t, actor=actor)
    _event(tx, 'session.created', t, actor, {'mode': t.mode, 'harness_id': harness_id,
                                             'account_id': account_id,
                                             'mission_id': t.mission_id, 'handoff_from': src.id})
    _event(tx, 'session.handed_off', t, actor, {'from': src.id, 'to': t.id,
                                                'reason': reason[:500], 'artifact': sha})
    return dict(view_of(t), duplicate=False)


# ── reads ───────────────────────────────────────────────────────────────────

def view_of(s):
    """A session as the API shows it: its identity, cursor and lineage. The
    transcript path stays inside Core."""
    d = s.to_dict()
    d.pop('transcript_path', None)
    return d


def view(conn, session_id):
    from ...infra.db import rows
    row = rows.get(conn, entities.Session, session_id)
    if row is None:
        raise lifecycle.NotFound(session_id)
    out = view_of(row.entity)
    out['version'] = row.version
    out['targets'] = [r.entity.id for r in rows.where(
        conn, entities.Session, handoff_from_session_id=session_id)]
    lineage, cur = [], row.entity
    while cur.handoff_from_session_id is not None and len(lineage) < 50:
        lineage.append(cur.handoff_from_session_id)
        prev = rows.get(conn, entities.Session, cur.handoff_from_session_id)
        if prev is None:
            break
        cur = prev.entity
    out['lineage'] = lineage
    return out


def listing(conn, *, project_id=None, mission_id=None, state=None):
    from ...infra.db import rows
    eq = {k: v for k, v in (('project_id', project_id), ('mission_id', mission_id),
                            ('state', state)) if v is not None}
    got = [r.entity for r in rows.where(conn, entities.Session, **eq)]
    got.sort(key=lambda s: (s.last_active_at or '', s.id), reverse=True)
    return [view_of(s) for s in got]


def preview_brief(conn, session_id):
    """The brief now, without moving the cursor or recording a package."""
    from ...infra.db import rows
    from ..context import assemble as C
    row = rows.get(conn, entities.Session, session_id)
    if row is None:
        raise lifecycle.NotFound(session_id)
    s = row.entity
    ctx = {'package_id': None, 'as_of_seq': None, 'rebuilt': False}
    if s.context_package_id is not None:
        p = rows.get(conn, entities.ContextPackage, s.context_package_id)
        if p is not None:
            ctx = {'package_id': p.entity.id, 'as_of_seq': p.entity.as_of_seq,
                   'rebuilt': False, 'fresh': C.fresh(conn, p.entity)}
    return continuity.brief(conn, s, ctx)

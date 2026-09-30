"""The session service (p12-design-gate §9, §10.2, §14): what surrounds each
session command, outside any transaction.

    before   ask the harness's session adapter what the world says — is the
             provider session still there, what does the target offer, what
             are the source's text turns — and pass the answers in as data
    command  one writer transaction (core/application/sessions.py)
    after    the launcher: write the delivery copy, build the argv through the
             adapter, open the terminal through the node, record the outcome

A restarted Core runs `sweep()` once: launches a previous Core was asked for
are settled as expired, never replayed (D21), and every OPEN session's
provider session is looked for.
"""

import logging
import os
import time

from ...harnesses import sessions as SA
from ...infra.artifacts import store as artifacts
from ...infra.db import rows
from ..application import sessions as S
from ..application.world import Conflict
from ..domain import entities

log = logging.getLogger('archeus.sessions')


class Refused(Conflict):
    """A session operation the world does not allow now (409): the reason says why."""


def delivery_path(cwd, session_id):
    """`<cwd>/.archeus/sessions/<id>.md`: the delivery copy of a session's
    artifact (D15). Per session, never overwritten, never read back, inside the
    `.archeus/` directory whose `.gitignore` is `*`."""
    from claude_sessions import store
    return os.path.join(store.workdir(cwd), 'sessions', '%s.md' % session_id)


def opening(session_id, path, what):
    return ('Before anything else, read %s: it is %s, rendered by Archeus for session %s. '
            'It describes the work as it is now; it grants no permission.' % (path, what,
                                                                               session_id))


class SessionService:
    def __init__(self, db, *, system, adapters, node):
        self.db, self.system, self.node = db, system, node
        self.adapters = {a.id: a for a in adapters}

    def _do(self, command, actor, key=None, **kw):
        return self.db.writer.execute(command, dict(kw, actor=actor), idempotency_key=key)

    def _session(self, session_id):
        with self.db.read() as r:
            row = rows.get(r, entities.Session, session_id)
            if row is None:
                from ..application.lifecycle import NotFound
                raise NotFound(session_id)
            s = row.entity
            home = None
            if s.account_id is not None:
                a = rows.get(r, entities.Account, s.account_id)
                home = a.entity.home_ref if a else None
        return s, home

    def _home(self, account_id):
        if account_id is None:
            return None
        with self.db.read() as r:
            a = rows.get(r, entities.Account, account_id)
        return a.entity.home_ref if a else None

    def adapter(self, harness_id, need=('interactive',)):
        a = self.adapters.get(harness_id)
        if a is None or not a.discover().installed:
            raise Refused('%s is not installed' % harness_id)
        caps = a.capabilities(None)
        missing = [c for c in need if c not in caps.capabilities]
        if missing:
            raise Refused('%s does not declare %s' % (harness_id, ', '.join(missing)))
        models = [m if isinstance(m, str) else m.id for m in caps.models]
        return a, models, list(caps.efforts)

    # ── the world, before a command ──

    def _locate(self, s, home, adapter):
        """The provider session's transcript, finding a ref the harness chose
        itself (pi) when none is recorded; None when it cannot be found."""
        ref = s.provider_session_ref
        if ref is None:
            ref = adapter.find(home, s.cwd, _epoch(s.started_at))
            if ref is None:
                return None
            self._do(S.observe, self.system, session_id=s.id, provider_session_ref=ref)
        got = adapter.locate(ref, home, s.cwd)
        if got is not None and got.transcript_path != s.transcript_path:
            self._do(S.observe, self.system, session_id=s.id,
                     transcript_path=got.transcript_path)
        return got

    # ── operations ──

    def register(self, actor, key=None, **kw):
        a, models, efforts = self.adapter(kw['harness_id'], need=())
        return self._do(S.open_session, actor, key, mode='manual', **kw)

    def launch(self, actor, key=None, **kw):
        """A new interactive session in a terminal."""
        a, models, efforts = self.adapter(kw['harness_id'])
        out = self._do(S.open_session, actor, key, mode='interactive_attached', launch=True,
                       models=models, efforts=efforts, **kw)
        return dict(out, launch=self._launch(out['id']))

    def resume(self, actor, *, session_id, request_id, model=None, effort=None,
               deliver_brief=False, key=None):
        s, home = self._session(session_id)
        a, models, efforts = self.adapter(s.harness_id, need=('interactive', 'resume'))
        if s.mode != 'headless' and s.last_request != request_id:
            got = self._locate(s, home, a)
            if got is None:
                if s.provider_session_ref is None:
                    raise Refused('the provider session of %s is not known yet' % session_id)
                if s.state == 'OPEN':
                    self._vanish(s, 'the provider session could not be found')
                raise Refused('the provider session of %s is gone' % session_id)
            if s.state == 'LOST':                 # found again: a remounted drive
                self._do(S.reappeared, self.system, session_id=s.id,
                         transcript_path=got.transcript_path)
        out = self._do(S.resume, actor, key, session_id=session_id, request_id=request_id,
                       models=models, efforts=efforts, model=model, effort=effort)
        if out['duplicate']:
            return out
        sha = out['artifact_sha'] if deliver_brief else None
        return dict(out, launch=self._launch(session_id, sha, 'the brief of what changed '
                                             'since this session was last used'))

    def handoff(self, actor, *, source_session_id, request_id, harness_id, account_id=None,
                model=None, effort=None, reason='', key=None):
        src, home = self._session(source_session_id)
        a, models, efforts = self.adapter(harness_id)
        turns = None
        if src.mission_id is None:
            # read-only: a hand-off never writes its source (invariant 6), not
            # even what Core found out about it on the way
            sa = self.adapters.get(src.harness_id)
            got = sa.locate(src.provider_session_ref, home, src.cwd) \
                if sa is not None and src.provider_session_ref else None
            turns = [list(t) for t in sa.turns(got.transcript_path, 400)] if got else None
        out = self._do(S.handoff, actor, key, source_session_id=source_session_id,
                       request_id=request_id, harness_id=harness_id, account_id=account_id,
                       model=model, effort=effort, reason=reason, turns=turns, models=models,
                       efforts=efforts)
        if out['duplicate']:
            return out
        return dict(out, launch=self._launch(out['id'], out['handoff_artifact_sha'],
                                             'the context handed over from session %s'
                                             % source_session_id))

    def _vanish(self, s, why):
        try:
            self._do(S.vanished, self.system, session_id=s.id, reason=why)
        except Exception as err:               # already LOST: nothing to record
            log.info('session %s: %s', s.id, err)

    # ── the launcher (§14.4) ──

    def _launch(self, session_id, artifact_sha=None, what=''):
        s, home = self._session(session_id)
        if s.launched_seq >= s.launch_seq:
            return {'launched': False, 'reason': 'nothing to launch'}
        a = self.adapters[s.harness_id]
        first = None
        if artifact_sha:
            path = delivery_path(s.cwd, s.id)
            if not os.path.exists(path):
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, 'wb') as f:
                    f.write(artifacts.get(artifact_sha))
            first = opening(s.id, path, what)
        # a session is launched new exactly once, when it is created; every later
        # launch follows a resume, which is what `last_request` records
        spec = SA.SessionSpec(session_id=s.id, cwd=s.cwd, home=home, model=s.model,
                              effort=s.effort, resume_ref=s.provider_session_ref
                              if s.last_request else None, opening=first)
        try:
            got = a.launch_argv(spec)
            _proc, err = self.node.open_terminal(got.argv, cwd=s.cwd, env=got.env,
                                                 title='Archeus session %s' % s.id)
        except Exception as e:                  # a launch is reported, never raised past here
            got, err = None, '%s: %s' % (type(e).__name__, e)
        self._do(S.launched, self.system, session_id=s.id, launch_seq=s.launch_seq,
                 provider_session_ref=got.ref if got else None, error=err or None)
        return {'launched': not err, 'error': err or None, 'launch_seq': s.launch_seq}

    # ── boot ──

    def sweep(self):
        """After a restart: expire unsettled launches (never replay them), and
        look for every OPEN or LOST user session's provider session."""
        expired = self._do(S.expire_launches, self.system)['expired']
        with self.db.read() as r:
            live = [x.entity for x in rows.where(r, entities.Session)
                    if x.entity.mode != 'headless' and x.entity.state in ('OPEN', 'LOST')
                    and x.entity.provider_session_ref]
        moved = []
        for s in live:
            a = self.adapters.get(s.harness_id)
            if a is None or not a.discover().installed:
                continue                # a harness we cannot ask is not evidence
            got = a.locate(s.provider_session_ref, self._home(s.account_id), s.cwd)
            if got is None and s.state == 'OPEN':
                self._vanish(s, 'the provider session is gone')
                moved.append((s.id, 'LOST'))
            elif got is not None and s.state == 'LOST':
                self._do(S.reappeared, self.system, session_id=s.id,
                         transcript_path=got.transcript_path)
                moved.append((s.id, 'OPEN'))
        return {'expired': expired, 'moved': moved}


def _epoch(iso):
    if not iso:
        return 0.0
    try:
        return time.mktime(time.strptime(iso, '%Y-%m-%dT%H:%M:%SZ')) - time.timezone
    except ValueError:
        return 0.0

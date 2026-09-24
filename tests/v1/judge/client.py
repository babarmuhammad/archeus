"""The `CoreClient` contract the acceptance judge is written against
(testing-strategy §1.1).

The judge never imports Core internals, and it is written before the API
exists, so this Protocol is the surface it may use: exactly the operations the
scenarios need, mirroring the command/query surface of api-and-realtime §2.
Commands return dicts shaped like the API's responses; `events(after_seq)`
returns envelopes (api-and-realtime §3.1).

Bindings:
- `InProcessClient` (P1–P3.5) calls the application layer directly. An
  operation whose phase has not arrived raises `NotImplementedError` — loudly,
  never a silent `None` a scenario could mistake for an answer — so each judge
  function that needs it is an expected failure tagged with its phase.
- `HttpClient` (P3.5 onward) speaks HTTP + SSE; every scenario then runs
  against both bindings.
"""

import inspect
import os
from typing import Optional, Protocol, Sequence, runtime_checkable

from archeus.core import engine, ports
from archeus.core.application import commands, queries, work
from archeus.core.application.lifecycle import GuardFailed, IllegalTrigger
from archeus.core.application.work import PolicyDenied
from archeus.core.domain import ids
from archeus.core.domain.values import Ref
from archeus.harnesses.fake import FakeHarness
from archeus.harnesses.registry import AdapterRegistry
from archeus.infra import discovery, paths
from archeus.infra.db import Database, connection
from archeus.infra.db.writer import (IdempotencyConflict, InvalidTransition, NotFound,
                                     VersionConflict)
from archeus.infra.eventlog.outbox import CursorExpired


class CoreClientError(Exception):
    """A typed API error (api-and-realtime §1.5): `status` + `code`, e.g.
    422 invalid_transition, 423 policy_denied, 409 version_conflict."""

    def __init__(self, status, code, detail=None):
        super().__init__('%s %s: %s' % (status, code, detail))
        self.status, self.code, self.detail = status, code, detail or {}


@runtime_checkable
class CoreClient(Protocol):
    # ── conversation, missions ──
    def submit_message(self, text: str, *, conversation_id: Optional[str] = None,
                       idempotency_key: Optional[str] = None) -> dict: ...
    def create_mission(self, *, title: str, objective: str,
                       project_id: Optional[str] = None,
                       success_criteria: Sequence[dict] = (),
                       idempotency_key: Optional[str] = None) -> dict: ...
    def get_mission(self, mission_id: str) -> dict: ...
    def list_missions(self, *, state: Optional[str] = None,
                      project_id: Optional[str] = None) -> list: ...
    # ── control ──
    def decide_approval(self, approval_id: str, decision: str, *,
                        note: Optional[str] = None, step_up: Optional[str] = None,
                        idempotency_key: Optional[str] = None) -> dict: ...
    def pause(self, target: str) -> dict: ...
    def resume(self, target: str) -> dict: ...
    def stop(self, target: str) -> dict: ...
    # ── questions ──
    def route_why(self, subject_id: str) -> dict: ...
    def status(self, *, project_id: Optional[str] = None) -> dict: ...
    def digest(self) -> dict: ...
    def ack(self, up_to_seq: int) -> dict: ...
    # ── world, resources ──
    def import_meeting(self, path: str, *, project_id: Optional[str] = None) -> dict: ...
    def register_account(self, *, harness_id: str, label: str, auth_kind: str,
                         home_ref: Optional[str] = None) -> dict: ...
    def set_resource_policy(self, account_id: str, *, priority: Optional[int] = None,
                            allocation_pct: Optional[int] = None,
                            reserve_pct: Optional[int] = None,
                            brain_reserve_pct: Optional[int] = None,
                            fallback: Optional[str] = None,
                            expected_version: Optional[int] = None) -> dict: ...
    # ── the event stream ──
    def events(self, after_seq: int = 0, *, limit: Optional[int] = None) -> list: ...


#: The operation names, in contract order — what every binding must implement.
OPERATIONS = tuple(name for name in CoreClient.__dict__
                   if not name.startswith('_') and callable(CoreClient.__dict__[name]))


def _pending(op):
    def method(self, *args, **kwargs):
        raise NotImplementedError(
            'CoreClient.%s: not implemented in this binding yet; it arrives with '
            'the phase that owns it' % op)
    method.__name__ = op
    return method


class InProcessClient:
    """The P1–P3.5 binding: a Core in this process, on an ARCHEUS_HOME.

    It implements the operations the passing scenarios need (`IMPLEMENTED`)
    over the database and the application layer; every other one still fails
    loudly. The client registers itself as a `user_device` principal on first
    use and keeps that identity across `_restart()`, as a paired device would;
    Core's engine acts as its own `system` principal. Both registrations are
    bootstraps only: the HTTP binding gets its principal from the auth layer
    (commands.register_principal).

    P3.5: Core runs the walking-skeleton engine (archeus/core/engine.py) on the
    stub ports and the fake harness. In process there is no Core loop, so the
    engine is pumped by `_idle()` — a scenario waiting for a state is exactly
    the moment Core would be working. It hosts an engine, so it takes the
    home's core.lock exactly as the Core runtime does: two engine hosts on one
    home fail loudly instead of reconciling each other's children (p3.5b A1).
    """

    def __init__(self, home):
        self.home = str(home)
        self._db = self._lock = None
        self._engine = None
        self._principal = self._system = None
        # the stub ports every phase runs on until P9/P10/P13 swap them
        self._policy = ports.AllowAllPolicy()
        self._missions = commands.Missions(policy=self._policy)

    # ── binding plumbing (not part of the contract) ──

    def _core(self):
        if self._db is None:
            assert (os.path.normcase(os.path.abspath(paths.archeus_home()))
                    == os.path.normcase(os.path.abspath(self.home))), 'the lock is per home'
            self._lock = discovery.acquire()
            self._db = Database.open(connection.db_path(self.home))
            if self._principal is None:
                self._principal = self._db.writer.execute(commands.register_principal, {
                    'kind': 'user_device',
                    'scopes': ('observe', 'control', 'approve', 'admin')})['id']
                self._system = self._db.writer.execute(commands.register_principal, {
                    'kind': 'system', 'scopes': ('system',)})['id']
            registry = AdapterRegistry(self._policy)
            registry.register(FakeHarness())
            self._engine = engine.Engine(
                self._db, actor=Ref('system', self._system),
                work=work.Work(missions=self._missions,
                               router=ports.FixedCandidateRouter('fake')),
                brain=ports.FixedPlanBrain(engine.SKELETON_PLAN), registry=registry,
                verifier=ports.ScriptedVerifier(), reviewer=ports.ScriptedReview())
        return self._db

    def _actor(self):
        self._core()
        return Ref('user_device', self._principal)

    def _call(self, fn):
        """Run *fn*, translating Core errors into the API's typed errors."""
        try:
            return fn()
        except NotFound as e:
            raise CoreClientError(404, 'not_found', {'id': str(e)}) from e
        except CursorExpired as e:
            raise CoreClientError(410, 'cursor_expired', {'reason': e.reason}) from e
        except VersionConflict as e:
            raise CoreClientError(409, 'version_conflict', {'current': e.current}) from e
        except GuardFailed as e:
            raise CoreClientError(422, 'guard_failed', {
                'machine': e.machine, 'from': e.frm, 'to': e.to, 'trigger': e.trigger,
                'guard': e.result.guard, 'reason': e.result.reason}) from e
        except InvalidTransition as e:          # before ValueError: it is one
            detail = {'machine': e.machine, 'from': e.frm, 'to': e.to}
            if isinstance(e, IllegalTrigger):
                detail['trigger'] = e.trigger
            raise CoreClientError(422, 'invalid_transition', detail) from e
        except PolicyDenied as e:               # D3: no decision id until P9 persists one
            raise CoreClientError(423, 'policy_denied', {
                'task': e.task_key, 'action_class': e.decision.action.action_class,
                'decision': e.decision.decision, 'reason': e.decision.reason}) from e
        except IdempotencyConflict as e:
            raise CoreClientError(400, 'invalid_request', {'field': 'idempotency_key',
                                                           'why': str(e)}) from e
        except ValueError as e:
            raise CoreClientError(400, 'invalid_request', {'why': str(e)}) from e

    def _idle(self):
        """One engine step for every mission that is not settled; True when
        none of them changed — then nothing in this Core can change on its own."""
        db = self._core()
        with db.read() as conn:
            live = [m['id'] for m in queries.list_missions(conn)
                    if m['state'] not in engine.SETTLED]
        return not any([self._engine.step(mid)['changed'] for mid in live])

    def close(self, *, drain=True):
        if self._db is not None:
            self._db.close(drain=drain)
            self._db = self._engine = None      # its processes are orphans now
            self._lock.release()
            self._lock = None

    def _restart(self, *, kill=True):
        """Core stops (kill: queued commands are dropped) and starts again on
        the same home."""
        self.close(drain=not kill)
        self._core()

    # ── the contract ──

    def create_mission(self, *, title: str, objective: str,
                       project_id: Optional[str] = None,
                       success_criteria: Sequence[dict] = (),
                       idempotency_key: Optional[str] = None) -> dict:
        return self._call(lambda: self._core().writer.execute(
            commands.create_mission,
            {'actor': self._actor(), 'title': title, 'objective': objective,
             'project_id': project_id,
             'success_criteria': [dict(c) for c in success_criteria]},
            idempotency_key=idempotency_key))

    def get_mission(self, mission_id: str) -> dict:
        def read():
            with self._core().read() as conn:
                return queries.get_mission(conn, mission_id)
        return self._call(read)

    def list_missions(self, *, state: Optional[str] = None,
                      project_id: Optional[str] = None) -> list:
        if project_id is not None:
            raise NotImplementedError('CoreClient.list_missions: a project filter arrives '
                                      'with projects (P4)')

        def read():
            with self._core().read() as conn:
                return queries.list_missions(conn, state)
        return self._call(read)

    def _control(self, verb, target):
        if ids.kind_of(target) != 'mission':
            raise NotImplementedError('CoreClient.%s: only mission targets until the '
                                      'execution orchestrator (P11)' % verb)
        return self._call(lambda: self._core().writer.execute(
            getattr(self._missions, verb), {'actor': self._actor(), 'mission_id': target}))

    def pause(self, target: str) -> dict:
        return self._control('pause', target)

    def resume(self, target: str) -> dict:
        return self._control('resume', target)

    def events(self, after_seq: int = 0, *, limit: Optional[int] = None) -> list:
        def read():
            with self._core().read() as conn:
                return queries.events(conn, after_seq, limit=limit)
        return self._call(read)


#: Operations with a real body in both bindings (P2: G1, G4; P3: the mission
#: control verbs; P3.5: listing missions, which the SPA's two lists read).
IMPLEMENTED = ('create_mission', 'get_mission', 'list_missions', 'events', 'pause', 'resume')

# Every other operation is declared and fails loudly. Later phases replace these
# with real bodies one by one; tests/v1/contract/test_core_client.py keeps every
# binding's signatures identical to the Protocol's.
for _op in OPERATIONS:
    if _op in IMPLEMENTED:
        continue
    _stub = _pending(_op)
    _stub.__signature__ = inspect.signature(getattr(CoreClient, _op))
    setattr(InProcessClient, _op, _stub)
del _op, _stub

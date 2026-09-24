"""The `CoreClient` contract the acceptance judge is written against
(testing-strategy §1.1).

The judge never imports Core internals, and it is written before the API
exists, so this Protocol is the surface it may use: exactly the operations the
scenarios need, mirroring the command/query surface of api-and-realtime §2.
Commands return dicts shaped like the API's responses; `events(after_seq)`
returns envelopes (api-and-realtime §3.1).

Bindings:
- `InProcessClient` (P1–P3) calls the application layer directly. An
  operation whose phase has not arrived raises `NotImplementedError` — loudly,
  never a silent `None` a scenario could mistake for an answer — so each judge
  function that needs it is an expected failure tagged with its phase.
- `HttpClient` (P3.5 onward) speaks HTTP + SSE; every scenario then runs
  against both bindings.
"""

import inspect
from typing import Optional, Protocol, Sequence, runtime_checkable

from archeus.core.application import commands, queries
from archeus.core.domain.values import Ref
from archeus.infra.db import Database, connection
from archeus.infra.db.writer import IdempotencyConflict, NotFound
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
            'CoreClient.%s: not implemented in the in-process binding yet; it '
            'arrives with the phase that owns it' % op)
    method.__name__ = op
    return method


class InProcessClient:
    """The P1–P3 binding: a Core in this process, on an ARCHEUS_HOME.

    P2 implements the operations its acceptance needs (`IMPLEMENTED`) over the
    database and the application layer; every other one still fails loudly.
    The client registers itself as a `user_device` principal on first use and
    keeps that identity across `_restart()`, as a paired device would. That
    self-registration is a P2 bootstrap only; the HTTP binding (P3.5) gets its
    principal from the auth layer instead (commands.register_principal).
    """

    def __init__(self, home):
        self.home = str(home)
        self._db = None
        self._principal = None

    # ── binding plumbing (not part of the contract) ──

    def _core(self):
        if self._db is None:
            self._db = Database.open(connection.db_path(self.home))
            if self._principal is None:
                self._principal = self._db.writer.execute(commands.register_principal, {
                    'kind': 'user_device',
                    'scopes': ('observe', 'control', 'approve', 'admin')})['id']
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
        except IdempotencyConflict as e:
            raise CoreClientError(400, 'invalid_request', {'field': 'idempotency_key',
                                                           'why': str(e)}) from e
        except ValueError as e:
            raise CoreClientError(400, 'invalid_request', {'why': str(e)}) from e

    def _idle(self):
        """Nothing here runs in the background: state changes only when a
        command is issued. The engine that advances missions arrives in P3.5."""
        return True

    def close(self):
        if self._db is not None:
            self._db.close()
            self._db = None

    def _restart(self, *, kill=True):
        """Core stops (kill: queued commands are dropped) and starts again on
        the same home."""
        if self._db is not None:
            self._db.close(drain=not kill)
            self._db = None
        self._core()

    # ── the contract ──

    def create_mission(self, *, title: str, objective: str,
                       project_id: Optional[str] = None,
                       success_criteria: Sequence[dict] = (),
                       idempotency_key: Optional[str] = None) -> dict:
        if success_criteria:
            raise NotImplementedError('CoreClient.create_mission: success criteria '
                                      'arrive with the plan engine')
        return self._call(lambda: self._core().writer.execute(
            commands.create_mission,
            {'actor': self._actor(), 'title': title, 'objective': objective,
             'project_id': project_id},
            idempotency_key=idempotency_key))

    def get_mission(self, mission_id: str) -> dict:
        def read():
            with self._core().read() as conn:
                return queries.get_mission(conn, mission_id)
        return self._call(read)

    def events(self, after_seq: int = 0, *, limit: Optional[int] = None) -> list:
        def read():
            with self._core().read() as conn:
                return queries.events(conn, after_seq, limit=limit)
        return self._call(read)


#: Operations with a real body in the in-process binding (P2: G1, G4).
IMPLEMENTED = ('create_mission', 'get_mission', 'events')

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

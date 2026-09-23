"""The `CoreClient` contract the acceptance judge is written against
(testing-strategy §1.1).

The judge never imports Core internals, and it is written before the API
exists, so this Protocol is the surface it may use: exactly the operations the
scenarios need, mirroring the command/query surface of api-and-realtime §2.
Commands return dicts shaped like the API's responses; `events(after_seq)`
returns envelopes (api-and-realtime §3.1).

Bindings:
- `InProcessClient` (P1–P3) calls the application layer directly. In P1 there
  is no application layer yet, so every operation raises `NotImplementedError`
  — loudly, never a silent `None` a scenario could mistake for an answer. Each
  judge function is therefore an expected failure tagged with its phase.
- `HttpClient` (P3.5 onward) speaks HTTP + SSE; every scenario then runs
  against both bindings.
"""

import inspect
from typing import Optional, Protocol, Sequence, runtime_checkable


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
            'CoreClient.%s: the in-process binding has no application layer yet '
            '(persistence arrives in P2, transitions in P3)' % op)
    method.__name__ = op
    return method


class InProcessClient:
    """The P1–P3 binding. Built on an ARCHEUS_HOME; P2/P3 give it a Core."""

    def __init__(self, home):
        self.home = str(home)


# P1: every operation is declared and fails loudly. Later phases replace these
# with real bodies one by one; tests/v1/contract/test_core_client.py keeps every
# binding's signatures identical to the Protocol's.
for _op in OPERATIONS:
    _stub = _pending(_op)
    _stub.__signature__ = inspect.signature(getattr(CoreClient, _op))
    setattr(InProcessClient, _op, _stub)
del _op, _stub

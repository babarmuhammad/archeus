"""The typed errors commands and queries raise: the one import a transport
needs to map them to its statuses (p3.5b design gate §5.5), so no transport
reaches into the lifecycle, the writer or the work module for them."""

from ...infra.db.writer import (IdempotencyConflict, InvalidTransition, NotFound,  # noqa: F401
                                VersionConflict, WriterBusy, WriterClosed)
from ...infra.eventlog.outbox import CursorExpired  # noqa: F401
from .authorization import NotEligible, NotPermitted  # noqa: F401
from .lifecycle import GuardFailed, IllegalTrigger  # noqa: F401
from .work import PolicyDenied  # noqa: F401
from .world import Conflict  # noqa: F401

#: A command refused because another command moved its row first: the engine
#: treats these as a lost race (p3.5b §3 D4), never as a failure.
LOST_RACE = (IllegalTrigger, GuardFailed, VersionConflict)

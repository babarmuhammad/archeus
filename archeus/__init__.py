"""Archeus V1 — the new control plane, growing beside `claude_sessions` (ADR-0001).

Nothing in the legacy app imports this package. It is the strangler fig's new
trunk: domain model, contracts and the fake harness first (P1), persistence and
the API after (P2, P3.5). docs/architecture/ is the design it follows.
"""

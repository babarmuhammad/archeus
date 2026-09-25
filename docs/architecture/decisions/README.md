# Architecture Decision Records — Archeus V1

Internal documents (excluded from the published manual). Status values: DECIDED, PROPOSED, OPEN, DEFERRED.

| ADR | Title | Status |
|---|---|---|
| [0001](ADR-0001.md) | Modular monolith control plane, grown beside the current package | DECIDED |
| [0002](ADR-0002.md) | SQLite with a single writer and a transactional outbox | DECIDED |
| [0003](ADR-0003.md) | Stdlib-only runtime for Core | DECIDED |
| [0004](ADR-0004.md) | Mission is the continuity abstraction; sessions are infrastructure | DECIDED |
| [0005](ADR-0005.md) | Resource router: priority, ceiling allocation, affinity, persisted decisions | DECIDED |
| [0006](ADR-0006.md) | The brain is Core-side structured-output calls; control verbs are deterministic | DECIDED |
| [0007](ADR-0007.md) | Policy engine as data + code, enforced first by capability removal | DECIDED |
| [0008](ADR-0008.md) | Execution nodes: local in-process in V1, remote contract specified | DECIDED |
| [0009](ADR-0009.md) | Realtime by SSE with ids-only events and client re-query | DECIDED |
| [0010](ADR-0010.md) | Remote access and mobile: PWA over a user-operated HTTPS tunnel | PROPOSED |
| [0011](ADR-0011.md) | One TypeScript/React SPA for desktop, web and mobile, prebuilt into the wheel | DECIDED |
| [0012](ADR-0012.md) | Knowledge as typed items with lifecycle in SQLite; no vector store in V1 | DECIDED |
| [0013](ADR-0013.md) | Graph relationships in relational tables, not a graph database | DECIDED |
| [0014](ADR-0014.md) | Information architecture: Now, Work, World, Control + Attention + command bar | DECIDED |
| [0015](ADR-0015.md) | Conversation model: one primary conversation plus mission threads with live cards | DECIDED |
| [0016](ADR-0016.md) | Spatial visualization: 2D fine-line, semantics only; 3D later | DECIDED |
| [0017](ADR-0017.md) | Design language: fixed state colours, one signature element, skins/worlds not carried | DECIDED |
| [0018](ADR-0018.md) | Internal architecture and design documents live under docs/ but are excluded from the manual | DECIDED |
| [0019](ADR-0019.md) | Data ownership during the strangler period | DECIDED |
| [0020](ADR-0020.md) | Automation as event/schedule/condition/state triggers creating missions under policy | DECIDED |
| [0021](ADR-0021.md) | Provider-terms gate before the first real headless model call | OPEN |
| [0022](ADR-0022.md) | Archeus's own model calls run on any capable harness | DECIDED |
| [0023](ADR-0023.md) | A user's own session resumes and hands off through its harness | DECIDED |

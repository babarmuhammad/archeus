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
| [0024](ADR-0024.md) | Visual DNA and event-driven motion: dark and still until Archeus acts | DECIDED |
| [0025](ADR-0025.md) | Graph edge semantics, legend, impact view and the constellation treatment | DECIDED |
| [0026](ADR-0026.md) | The thread and thread tints | DECIDED |
| [0027](ADR-0027.md) | Identity and operational presence: the mark, the orbit and the control surface | DECIDED |
| [0028](ADR-0028.md) | Colour separation, depth and transparency tokens | DECIDED |
| [0029](ADR-0029.md) | Visual evidence: deterministic regression and manual visual acceptance | DECIDED |
| [0030](ADR-0030.md) | Phase amendments for the visual architecture: P19.5, P18 A8, V1.x-3D, Core owners | DECIDED |
| [0031](ADR-0031.md) | The model catalogue is dated current state, and discovery is not authorisation to route | DECIDED |
| [0032](ADR-0032.md) | Capability evidence: four classes, method apart from class, task-family scoped, no score | DECIDED |
| [0033](ADR-0033.md) | Evidence advises routing; it orders or excludes only under an explicit rule | DECIDED |
| [0034](ADR-0034.md) | Artifact-first hand-off between the steps of a mission | DECIDED |
| [0035](ADR-0035.md) | A project's data class limits which providers and locations may receive its work | DECIDED |
| [0036](ADR-0036.md) | Availability is a per-offer state with one reason, separate from routing status | PROPOSED |
| [0037](ADR-0037.md) | The harness descriptor declares what a harness serves; orchestration never branches on a harness id | PROPOSED |
| [0038](ADR-0038.md) | Four control modes for orchestration acts; a material substitution asks | PROPOSED |
| [0039](ADR-0039.md) | Model evaluation is an approved mission over a versioned fixture suite | PROPOSED |
| [0040](ADR-0040.md) | A consumed architecture artifact binds implementation; changing it is a plan-level act | PROPOSED |
| [0041](ADR-0041.md) | Account consumption policy: protected accounts, subject limits, budgets always enforced, a readable effective policy | DECIDED |
| [0042](ADR-0042.md) | Conversational directives resolve into the same governed operations as the controls | DECIDED |
| [0043](ADR-0043.md) | Live work is executions and in-flight own calls, derived once; there is no Agent entity | DECIDED |
| [0044](ADR-0044.md) | The application theme is a per-client preference (System, Dark, Light, High Contrast); thread tints stay tints | DECIDED |
| [0045](ADR-0045.md) | Legacy context migration is per project, lossless-first and read-only; existing projects stay on legacy until their own approved cutover (P25.5) | DECIDED |
| [0046](ADR-0046.md) | The V1 write boundary: ARCHEUS_HOME, an Archeus-owned project-local namespace with per-entry ownership, and project files only through named capabilities | DECIDED |
| [0047](ADR-0047.md) | Context capacity is a governed execution resource: measured with its basis, never assumed; the only continuation is the existing checkpoint hand-off | DECIDED |
| [0048](ADR-0048.md) | D-25: account identity, usage measures, own calls as consumers, and the legacy boundary of AP-1 | DECIDED |
| [0049](ADR-0049.md) | What a V1 execution inherits from the Claude Code settings sources it runs under (account home, project, local: hooks, plugins, skills, MCP, permissions, CLAUDE.md) | DECIDED (PV-20 consequence 2026-10-07, ADR-0053 §7 A2: no account home inside the boundary; opt-ins as Core-materialised data; no MCP opt-in admitted to an isolated execution, confirmed by the owner — not implemented) |
| [0050](ADR-0050.md) | A future assistant layer is a client and modality of the conversation and mission model, never a second loop, router, memory or approval path | DECIDED |
| [0051](ADR-0051.md) | V1 execution isolation is application-level and harness-provided; an Archeus-owned OS-level sandbox is post-V1 | DECIDED (timing superseded 2026-10-07: a V1.x security remediation, ADR-0053; harness-sandbox posture changed by ADR-0053 §7 A4) |
| [0052](ADR-0052.md) | Claude Code executions get tool removal derived from action classes, beneath the per-tool hook; unmapped tools are excluded by default | DECIDED |
| [0053](ADR-0053.md) | Executions run under an isolated OS identity inside a Core-held Job, and Core bounds every privileged effect by attested origin (PV-20, a V1.x security remediation) | DECIDED (not implemented; blocker decisions A1–A6 and the A7 correction added 2026-10-07, §7) |

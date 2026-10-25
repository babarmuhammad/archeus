# V2 Replay & Recovery — 2026-10-25

Fixture-only design. Owner authorizes this prototype, not the proposed V1 implementation.
Sources: REPLAY-coverage.md, CITATION-check-T145-147.md, CARD-DRAFT-T-148-replay.md,
V2-feedback-Federico-2026-10-21.md, V2-chatbar-design-codex.md, prototype README and Mission code.
No account home, credential store, network, runtime or browser access.
Requested design and final handoff are explicit exceptions to the prototype-only edit scope.
Skills stored under account homes cannot be opened under this task's restriction.

## Placement and scene

Replay is an inspection mode of a Mission within its project. Keep existing deep link
`#/replay/m-date` and Mission Replay link; no new top-level destination.
Back returns to that Mission. Project context appears in the inspector.
Reuse existing constellation art, materials, labels and tokens. Do not change text weights.
The constellation remains visible beside the desktop inspector and above the phone sheet.
Historical selection labels the constellation as an as-of fixture; it never changes live Mission data.
Preserve the owner's preferred 02/03/06/13 direction and existing chat work-start flow.

## Evidence vocabulary and limits

Display fixture row identity, timestamp, entity/state, source and derived category separately.
Use INTENDED, AUTHORIZED, RECORDED, MAY-HAVE-TAKEN-EFFECT, UNCERTAIN,
SUSPENDED and RECONCILED only where coverage supports them. NONE means never dispatched;
UNKNOWN means indeterminate, not failure. Categories are explanatory fixture mappings, not new states.
Real integration must read durable rows first; retained transition evidence supplies order/trigger.
No claim that the proposed replay API, Core vocabulary mapping or operator command exists.
Fixture order/timestamps are authored examples, not a recovered production log.
Retention depth: NOT RECORDED in this fixture. Missing evidence never becomes zero or success.
Correction references: domain-model.md:346, writer.py:399, executions.py:472-486.
Do not rely on the unverified aggregate count of 130 states.

V2 must NOT show these as recorded facts:
- External response loss, external Effect/Attempt entities, broker/provider effect proof.
- Confirmed push/message/payment or undo/reversal of any external effect.
- A per-attempt starting-state digest; seed/base revisions are narrower bindings.
- Operator reconciliation as a standalone recorded action or invented REVERSED state.
- Full retained history, complete ordering or a reconstructed filesystem at every instant.
- Harness edges, private reasoning, complete tool transcripts or inferred intermediate file diffs.
- Harness summary as completion proof; policy isolation decision as proof of confinement.
- Missing cost as zero, or requested provenance as served/billed provenance.
Show compact NOT RECORDED disclosure naming these absences; never fabricate timeline events for them.

## Timeline and navigation

At least 12 fixture entries cover mission creation, plan proposal, approval request/decision,
execution intent/start, checkpoint, successful process exit, failed verification,
second execution intent/start/loss and mission block. Process success is not verified success.
Keep failed verification and LOST on different execution attempts.
All event detail and outcome receipts carry SIMULATED; CONCEPT FIXTURE stays visible.
No playback, timers, interpolated state or second live clock.
Native range control scrubs by pointer; arrows change one event, Home/End select endpoints.
Previous/Next buttons offer the same steps with endpoint disabling.
Tab reaches range, step controls, proposal choices and approval/cancel.
Selected event details update in a polite live region; focused range is not rebuilt.
Full timeline is a disclosure with text rows, not dozens of tiny click targets.
All new controls are at least 48 CSS px in both dimensions; desktop frame compensates scaling.
Phone uses at least 48 CSS px, exceeding existing probe's 44 CSS px minimum;
physical 44 pt remains a real-device verification item.

## Recovery

Failed verification or LOST context offers Resume, Retry with changes, Ask the owner.
Each opens a proposal card bound to selected event and mission. Selection change clears it.
Resume explains reconciliation/checkpoint eligibility must be established; never re-spawn LOST.
Retry requires a changed-instructions draft and describes a new execution identity.
Ask the owner previews an unsent question. None sends or runs anything.
Explicit Approve fixture proposal changes only a local SIMULATED receipt; Cancel discards card.
Approval does not append evidence, alter execution state or claim recovery occurred.

## Phone, terminal, reduced motion and Quiet

At 402 px, reuse constellation crop and a bounded scrolling bottom sheet.
Controls wrap and text breaks without horizontal scrolling; scene remains visible above sheet.
Terminal p opens Replay from Mission. Text shows the same selected fixture, source and gaps,
plus compact Archeus-to-Mission-to-execution/verification constellation.
Left/Right and Home/End scrub; 1/2/3 open proposal; y explicitly approves; Escape cancels first.
Terminal explains unsent draft contents, with editable retry/question drafts available in graphical Replay.
Terminal Replay text and geometry are monochrome and static.
Reduced motion and Quiet expose identical evidence and controls. Replay adds no motion.

## Acceptance and handoff

Static checks assert fixture count, required states, labels, controls and no replay timers.
New browser probe covers desktop/402, motion modes, pointer/keyboard, endpoints,
proposal cancellation/approval/invalidation, draft requirement, terminal parity,
overflow, control dimensions, console errors and external request absence.
Claude runs all requested probes under testlock on port 8819. Codex does not execute runtimes.
Open production decisions: backend read contract/retention, recovery eligibility/authorization,
source evidence visibility and real-device accessibility. None blocks this local fixture.

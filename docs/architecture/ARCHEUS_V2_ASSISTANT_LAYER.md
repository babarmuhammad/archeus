# Archeus V2 — Assistant Layer: decisions, backlog, phases and the do-not-forget index

Internal architecture document (excluded from the published manual: `mkdocs.yml` `exclude_docs: /architecture/`).
Status: **ARCHITECTURE DECIDED where marked; PLANNING ONLY for every phase.** Nothing here is
V1 except the four V1-facing decisions in §0 (XR-1, XR-12, XR-13, XR-14). Nothing here is authorised to start.

Created 2026-10-03 by the reconciliation of the 2026-10 external research. Revised the same day
with the user's answers to XR-1, XR-10, XR-11, XR-12 and XR-13.

**What this document is:**
- the **authoritative home** of the research decision register (XR-1…XR-14) and the post-V1
  backlog (PV-1…PV-22);
- the detail behind plan §31.5 (V2-A0…A5). If the plan's summary table and §2 here ever differ,
  §2 wins and the plan is the bug.

The research report
[../research/2026-10-external-research.md](../research/2026-10-external-research.md) keeps the
evidence: what each project does, pinned revisions and licences, and the findings F-1…F-56 with
their sources. **This document must be readable without it.** Where a row cites `F-n`, the line
here says what the finding is.

The governing principle is **ADR-0050** (DECIDED 2026-10-03). A future Jarvis-style assistant is
clients and device components over Archeus's existing conversations, missions, routing,
knowledge, approvals, policy, resources and execution model. It never adds:
- a second router;
- a second memory;
- a second approval path;
- a second agent loop;
- a second mission system.

Speech engines are device components, not routed models. **Archeus borrows mechanisms, not
architectural identity.**

**Tags:**
- **[A]** an Archeus fact (code or decided document);
- **[R]** a research fact (see the report for its source);
- **[DOC]** the Claude Code documentation as read on 2026-10-03 (cited in ADR-0049);
- **[I]** inference.

---

## 0. Decisions made on 2026-10-03 (the user's answers)

| Register | Decision | Record | V1-facing consequence |
|---|---|---|---|
| **XR-13** | P20 builds **no** Archeus-owned OS-level sandbox. V1 isolation is the application-level boundary plus harness-provided sandboxes; P20 specifies, tests and threat-models it, naming the OS-level gap and the future sensors. An Archeus-owned sandbox is PV-20, required before V2-A5 | **ADR-0051** (new, DECIDED) | P20 work and acceptance (plan §31.1 P20) |
| **XR-1** | All three settings sources in scope. **Exclude by default with explicit, recorded opt-in, and always record an inventory.** A per-source fallback to recorded-only if narrowing breaks the login. **Deny by exit code 2**; halt keeps `continue: false` | **ADR-0049** (DECIDED) | P20 builds PV-10 and verifies with PV-19 |
| **XR-12** | `browser` is **withdrawn from P22** and designed with its action class and boundary as a prerequisite of V2-A4 | **ADR-0037 "Amended"** (ADR still PROPOSED) | P22 adds `fs_read` and the other descriptor facts, without `browser` |
| **XR-11** | ADR-0050 **DECIDED**, amendments A1, A2, A4 and A5 folded into the decision text | **ADR-0050** | none |
| **XR-10** | **Push-to-talk only.** ADR-0050 §2 stays unconditional. A wake word is PV-21 and needs an explicit amendment of §2 | **ADR-0050 §2** | none |
| **XR-14** | P20 builds Claude Code **tool removal** beneath the hook: `--tools` (allow-form) derived from action classes, plus `--disallowedTools "mcp__*"` except opted-in servers, never `--allowedTools`. **Unmapped built-in tools are excluded by default** | **ADR-0052** (new, DECIDED) | P20 work (PV-22) and acceptance; execution-architecture §2 flag names corrected |

XR-14 was found by the reconciliation pass and decided the same day, after the analysis in
[XR-14_TOOL_ALLOWLIST_BRIEF.md](XR-14_TOOL_ALLOWLIST_BRIEF.md).

**Sequencing (the user's, 2026-10-03):** P20 does not start until P19.5 is explicitly finished.
None of the P20 items above (PV-10, PV-19, PV-22, the ADR-0051 tests) begins before then.

## 1. Do-not-forget index

Read this first when V2 starts. Every item has an authoritative record, an earliest phase, its
prerequisites and its boundary. Nothing here exists only as prose in the research report.

| # | Discovery | Why it matters | Authoritative record | Earliest phase | Prerequisite | Implementation boundary |
|---|---|---|---|---|---|---|
| 1 | Executions load the user, project and local settings sources: third-party hooks, plugins, skills, MCP servers, permissions, CLAUDE.md. Archeus's legacy hooks already stand down (P0.5) | context and code outside policy and the basis reach every execution | ADR-0049 (DECIDED) · PV-10 · PV-19 | **P20 (V1)** | P20 scheduled; ADR-0021 for PV-19 | the decided flags, inventory and opt-in only |
| 2 | Archeus denied with JSON + exit 0; how hooks' decisions combine is undocumented; exit 2 is the documented unconditional block | another hook might widen Archeus's deny | ADR-0049 §3 (exit 2 decided) · PV-10 | **P20 (V1)** | — | the deny path's form only; halt is unchanged until observed |
| 3 | `browser` was planned for P22 with no action class while `web` is ALLOW by default | a word declarable before its policy | ADR-0037 "Amended" · XR-12 (DECIDED) | V2-A4 | the browser capability ADR (§2 A4) | nothing named `browser` in V1 |
| 4 | Execution isolation in V1 is application-level and harness-provided; Claude Code's Bash network and Windows filesystem reach are not OS-confined | V1 must not be described as sandboxed; V2-A5 needs more | ADR-0051 · PV-13 · PV-20 | **P20 (V1)** test and threat-model; PV-20 post-V1 | — | P20 adds tests and threat entries, no sandbox |
| 5 | The tool allowlists specified in execution-architecture §2 were never built (P11 §18; `adapter.py:117-126`); a failed hook falls to Claude Code's permission flow; `--allowedTools` pre-approves rather than restricts | the hook was the only tool gate | ADR-0052 (DECIDED) · XR-14 · PV-22 | **P20 (V1)**, after P19.5 | P19.5 finished | removal via `--tools`/`--disallowedTools` only; never `--allowedTools` |
| 6 | Every researched assistant or agent project owns its own loop, model calls, tools and memory | adopting any as shipped means a second orchestrator | ADR-0050 §1, §6, §7 · §8 | any | — | primitives only |
| 7 | Tool-call healing (Fury) | model output becomes execution | ADR-0042 §6 · ADR-0050 §6 | never | — | rejected |
| 8 | Windows STT is feasible from components with Windows binaries or CI; none is measured on consumer hardware | a choice without measurement repeats an unmeasured claim | PV-1 · V2-A0a (§3.1) | **any time** (research) | — | a benchmark outside the product |
| 9 | Blazing's endpointing: adaptive silence 50–350 ms, pre-speech audio, 14 s forced split, split at the quietest point, generation guard, warm-up and keep-warm | parameters to benchmark and reproduce | PV-1 (§3.1) · PV-2 | V2-A0a | — | ideas only (MIT; macOS-only code) |
| 10 | Silero VAD in the browser (`ricky0123/vad`, ISC) needs `'wasm-unsafe-eval'`, which the CSP `script-src 'self'` lacks (`archeus/api/auth.py:40`); its README loads the runtime from a CDN | makes SPA-side VAD an option at a CSP cost | XR-4 option B · PV-16 (§3.3) | V2-A0c | XR-4 | no CSP change before XR-4 |
| 11 | Python's stdlib cannot capture audio on Windows; onnxruntime 1.30 has no Windows wheel for Python 3.10 | speech is never in Core; a sidecar has packaging gaps | ADR-0050 §10 · PV-1 | V2-A0a | — | speech never in Core |
| 12 | `Message` has no modality field (`entities.py:575-590`); ADR-0042 §7 requires one; ADR-0050 §9 binds the engine provenance to it | a later migration | XR-7 (OPEN) · PV-3 | V2-A1 | XR-7 | the field plus provenance, nothing else |
| 13 | Licences: Parakeet TDT v3 CC-BY-4.0 (attribution); EOU 120M NVIDIA Open Model License with no Windows path; openWakeWord models non-commercial; Porcupine needs a key | licences decide candidates before benchmarks | PV-1 acceptance · PV-21 prerequisites | V2-A0a | — | an attribution/NOTICE check is part of every production gate (§2) |
| 14 | Wake word vs a user-started microphone | an always-listening microphone is a different privacy posture | ADR-0050 §2 · XR-10 (DECIDED: push-to-talk) · PV-21 | after V2-A1 | PV-21's prerequisites + an ADR-0050 §2 amendment | push-to-talk only |
| 15 | Interruption must not become a second stop verb | barge-in vs mission control | ADR-0050 §4 · XR-8 (OPEN) · PV-4 · PV-11 | V2-A2 | XR-8 | playback stop is client-local |
| 16 | Windows desktop control (UI Automation, SendInput, PrintWindow, PowerShell) takes the foreground, captures the screen and runs code | new risk classes | XR-6 (OPEN) · PV-6 · ADR-0051 §5 | V2-A5 | XR-6, XR-9, PV-20, the desktop capability ADR | narrow typed integrations first |
| 17 | Browser Use's domain filter is navigation-only; Browser Harness attaches to the real profile | the browser boundary must be request-level and profile-isolated | XR-2 (OPEN) · PV-7 | V2-A4 | XR-2, XR-9, the browser capability ADR | CDP primitives only |
| 18 | Telemetry on by default in four projects | adoption would send data Archeus does not | XR-9 (OPEN) · PV-14 | before any adoption | XR-9 | off and verified, or not adopted |
| 19 | Installers write into agent homes (AgentMemory, OpenViking, Windows Harness, Diagram Design) | how item 1 becomes real | ADR-0049 | P20 | — | — |
| 20 | Third-party skills run scripts, install packages and call providers | skills trust is unsolved | XR-3 (OPEN) · PV-8 | V1.x-O5 | XR-3 | no third-party skill execution before XR-3 |
| 21 | Multi-size summaries (OpenViking) | only if truncation is measured | XR-5 (OPEN) · PV-9 | after P21 | P21 data | measure first |
| 22 | Windows TTS, tray and hotkey options were not researched | A2/A3 lacked evidence | PV-18 (§3.2) · PV-16 (§3.3) | V2-A0b/A0c | — | research only |
| 23 | Interrupt that keeps the partial; sentence-boundary TTS stream; mid-stream errors raised, never truncated (Fury) | reusable mechanisms for A2 and own calls | PV-4 · PV-11 · PV-12 | V2-A2 / V1.x | XR-8 | mechanisms only, not Fury's loop |

## 2. The V2 plan (plan §31.5 detail)

**Two tracks.**
- The **speech track** is A0 → A1, A2 → A3.
- The **capability track** is A4, A5. It depends on ADR-0037 and ADR-0051, not on voice.

**Research is not production.**
- **Research phases (A0a, A0b, A0c)** produce dated reports under `docs/research/`. They add no
  dependency to `pyproject.toml` and no product code, and they may run at any time, including
  before P26.
- **A production phase is "ready" only when all of the following hold:**
  1. every listed decision is DECIDED;
  2. its prerequisite phases have reported;
  3. its security boundary has a threat-model entry;
  4. the user has given an explicit go-ahead.

  That code could be written is never readiness. Approval of this plan is not a go-ahead.

**Every production phase also carries the shared gates:**
- ADR-0050 compliance: no loop, router, memory or approval path;
- licence attribution and NOTICE files for every shipped model;
- telemetry off and verified (XR-9's answer, once decided);
- the idle invariant (R1);
- **nothing of it enters V1**: every production phase starts after P26.

### V2-A0a — Windows STT/VAD benchmark (research)
- **Backlog:** PV-1 · **Design:** §3.1.
- **Output:** a dated report. It feeds XR-4, XR-7, A1's latency target, and PV-21's detector
  candidates if a wake word is ever reconsidered.

### V2-A0b — Windows TTS survey (research)
- **Backlog:** PV-18 · **Design:** §3.2.
- **Output:** a dated report. It feeds A2's engine choice and XR-8.

### V2-A0c — desktop shell probe (research)
- **Backlog:** PV-16 · **Design:** §3.3.
- **Output:** a dated report that says whether the Qt shell is suitable for the tray, the hotkey
  and microphone capture. It does not commit Archeus to Qt.

### V2-A1 — voice input (production)
- **Backlog:** PV-2, PV-3.
- **Decisions:** XR-4 (placement and privacy), XR-7 (modality timing; with voice by default),
  XR-9 (the component gate). XR-10 and XR-11 are already decided.
- **Prerequisites:** P26; A0a reported; A0c reported if XR-4 picks option B.
- **Architecture boundary:**
  - push-to-talk capture, either in a client (the SPA, under a CSP change that XR-4 option B
    would require) or in a local device sidecar, never in Core;
  - VAD and endpointing;
  - a local STT device component;
  - the transcript posted through the existing message command as a user `Message`, with its
    modality and the engine and version (ADR-0050 §2, §9);
  - no new route that bypasses the grammar.
- **Security boundary:** the microphone threat entry (ADR-0051 §3), plus a visible capture
  indicator. If XR-4 picks C, a provider rule under ADR-0035.
- **Acceptance:**
  - voice messages take the same grammar and command path as text (G1–G5 extended);
  - no approval or destructive confirmation is accepted by voice;
  - nothing is captured outside a push-to-talk act;
  - no audio leaves the device unless XR-4 permits it;
  - latency p95 within A0a's target.
- **Evidence:** test runs; a capture-indicator check; a network capture showing no audio egress;
  the A0a report cited.
- **Does not enter V1:** the modality column waits for XR-7.

### V2-A2 — voice output and interruption (production)
- **Backlog:** PV-4, PV-11.
- **Decisions:** XR-8 (interruption scope), the A0b engine choice, XR-9.
- **Prerequisites:** A0b reported.
- **What A1 is needed for:** only for a *spoken* barge-in ("stop" said aloud). Spoken output and
  key or button interruption do not depend on A1. Voice output speaks text Core already
  returned, so it can serve typed conversations too.
- **Architecture boundary:**
  - client-side TTS of messages, cards and Attention text;
  - sentence-boundary chunking;
  - half-duplex first (the microphone muted while speaking, if A1 is present);
  - interruption stops playback client-locally (ADR-0050 §4). Whether it also cancels the own
    call is XR-8.
- **Security boundary:** nothing spoken that the screen would not show.
- **Acceptance:**
  - time to first audio;
  - interruption latency;
  - CPU while speaking;
  - an interruption never changes mission state unless XR-8 says so, and then only through a
    recorded command.
- **Evidence:** measurements against A0b's baseline; grammar tests for a spoken "stop".

### V2-A3a — tray and hotkey (production; a desktop client)
- **Backlog:** PV-5.
- **Prerequisites:** A0c reported.
  - The **tray** (the mark's state from `/v1/status`, ADR-0027) needs nothing else.
  - The **push-to-talk hotkey** also needs A1.
- **Architecture boundary:**
  - a client of existing reads;
  - no new agent loop;
  - no Core change;
  - the hotkey only opens push-to-talk capture (ADR-0050 §2).
- **Acceptance:** the idle invariant for the tray process; the hotkey never opens the microphone
  without the key held or pressed.
- **Evidence:** idle CPU and wakeup measurements.

### V2-A3b — spoken Attention items (production)
- **Backlog:** PV-15.
- **Prerequisites:** A2, since speech output is required.
- **Architecture boundary:** an opt-in client rendering of Attention items. Proactive speech comes
  only from Attention and decided automations (ADR-0050 §5).
- **Acceptance:** one opt-out silences all of it; nothing is spoken that Attention does not show.

### V2-A4 — browser capability (production)
- **Backlog:** PV-7, PV-14.
- **Decisions:** XR-2 (the boundary), XR-9.
- **Prerequisites:**
  - ADR-0037 approved and implemented (P22);
  - a **browser capability ADR** that defines the `browser` word, its policy action class
    (default ASK) and the XR-2 boundary together (ADR-0037 "Amended");
  - PV-20 considered (ADR-0051 §5).
- **Security boundary:**
  - an isolated profile, never the user's real one;
  - a request-level domain filter (navigation-only is insufficient: F-5);
  - credentials only as placeholders;
  - page text is never a command (ADR-0042 §6).
- **Acceptance:**
  - domain-filter escape tests (`fetch`/XHR to an unlisted host is blocked);
  - a profile-isolation test;
  - a telemetry-off proof;
  - the Browser Use `Agent` is not used.
- **Evidence:** a test suite plus a network capture.

### V2-A5 — desktop-control capability (production)
- **Backlog:** PV-6, PV-14.
- **Decisions:** XR-6 (a capability word or narrow integrations only), XR-9.
- **Prerequisites:**
  - ADR-0037 implemented;
  - a **desktop capability ADR** (the word, the action class, and the screen-capture retention
    sub-choice);
  - **PV-20 built** (ADR-0051 §5).

  It follows the action-class pattern A4 establishes, or establishes it if A5 goes first.
- **Security boundary:**
  - screen-capture and input-injection threat entries;
  - visible and interruptible input takeover;
  - UI Automation reads before SendInput writes;
  - PowerShell only under policy;
  - narrow typed integrations preferred.
- **Acceptance:**
  - a fixed Windows task suite run under approval;
  - foreground-collision handling;
  - screenshots handled under the data class;
  - a telemetry-off proof.
- **Evidence:** suite results; a threat-model review.

## 3. Research phase designs

### 3.1 V2-A0a — what the STT/VAD benchmark evaluates (no winner chosen)

**Candidates** (sources [R] unless marked):
- **VAD:**
  - Silero VAD v6 (MIT) natively;
  - Silero through whisper.cpp's VAD C API;
  - Silero in the browser via `ricky0123/vad`;
  - webrtcvad (the Jarvis baseline).
- **STT:**
  - whisper.cpp (CPU, OpenBLAS, CUDA binaries);
  - faster-whisper / CTranslate2;
  - Parakeet TDT v3 via sherpa-onnx, onnx-asr and NeMo-Speech.cpp;
  - Windows' built-in speech recognition as a baseline [I: not researched; include only if
    available on the test machines].
- **Endpointing:** Blazing's parameters (§1 item 9).
- **Capture:** sounddevice/WASAPI, and `getUserMedia` in Chromium.

**Dimensions** (each per candidate, CPU-only and GPU separately):

| Dimension | Measure |
|---|---|
| Latency | end of speech to final text, p50 / p95 / p99; time to first partial |
| Accuracy | WER and CER on a fixed recorded set: clean, noisy, accented, developer vocabulary, Italian |
| Resources | peak RAM and VRAM; CPU while listening and while transcribing; installed size; cold and warm load |
| Offline / online | fully offline operation; any network call at load or run (a network capture) |
| Streaming | whether partial results exist; their stability (how often a partial is revised); the forced-split behaviour on long speech |
| Punctuation | punctuation and casing on the fixed set, natively or via post-processing |
| Interruption | cost and correctness of aborting mid-utterance (the generation guard); recovery after a device change |
| VAD quality | false-start, false-stop and clipped-onset rates; cost per chunk |
| Provenance and licensing | the licence of code and weights; attribution and NOTICE duties; whether the engine reports its own version |
| Windows integration | Python 3.10 wheel availability; native binaries; WASAPI device swaps and Bluetooth headsets; behaviour inside QtWebEngine (with A0c) |

**Hardware:**
- a low-end laptop (4-core U-series, 8 GB);
- a mainstream laptop (8-core H-series, 16 GB);
- Snapdragon X;
- an NVIDIA GPU with 6–8 GB;
- an AMD or Intel GPU;
- an NPU where a backend exists.

**Rule:** a macOS result predicts nothing on Windows.

**What the report must answer, by decision:**
- **XR-4:** the cost of native vs browser VAD and capture, plus the latency and egress facts for
  option C if measured.
- **XR-7:** whether every engine can report a stable engine and version string.
- **PV-21:** the detector candidates and their licences, recorded, not chosen.
- **A1:** the latency target.

### 3.2 V2-A0b — what the TTS survey evaluates

**Candidates:**
- Windows' built-in speech synthesis [I: not researched];
- local neural TTS engines found by the survey itself;
- MeloTTS (Jarvis, Apple-oriented) as a reference only.

| Dimension | Measure |
|---|---|
| Latency | time to first audio for a sentence; streaming by sentence chunk |
| Quality | a listening test on a fixed text set, English and Italian |
| Interruption and cancellation | time to silence on cancel; clean stop mid-word; resume behaviour |
| Streaming | incremental synthesis from a growing text |
| Offline / online | fully offline operation; network calls (a capture) |
| Resources | CPU and RAM while speaking; installed size |
| Windows APIs / engines | the API surface used; Python 3.10 availability; packaging |
| Provenance and licensing | the licence of code and voices; attribution |

**Output:** an engine shortlist for A2 and the cancellation facts XR-8 needs.

### 3.3 V2-A0c — what the shell probe determines

**Questions** (in a scratch build, never the product CSP or the product shell):
1. Does QtWebEngine grant `getUserMedia` microphone access through a permission handler, and how
   is that shown to the user?
2. Does Silero WASM run under a test CSP that has `'wasm-unsafe-eval'`, and at what cost?
3. Does `QSystemTrayIcon` meet the idle invariant? [I]
4. Can a Win32 global hotkey (`RegisterHotKey`) be bound from the shell, and what happens on a
   collision? [I]
5. Packaging size and start-up cost.

**Output:** whether Qt is suitable for A1 option B, A3a and the tray. Alternatives are noted, not
chosen. The existing legacy Qt shell (`gui_qt.py`) and its P19 S7 attach are evidence, not a
commitment.

## 4. Decision register (XR) — authoritative

Unresolved decisions stay unresolved until the user decides them. A recommendation is not a
decision.

**XR-1 — what an execution inherits from its settings sources** — **DECIDED 2026-10-03** (ADR-0049)
- **Decision:**
  - all three sources are in scope;
  - exclude by default with an explicit, recorded opt-in;
  - the inventory is always on;
  - a per-source fallback to recorded-only;
  - deny by exit code 2.
- **Open within it (verification, not choice):**
  - what each flag excludes;
  - whether the login survives each narrowing;
  - how a halt combines with exit code 2.

  PV-19 observes all three.
- **Phase:** P20 (PV-10, PV-19).

**XR-2 — what declaring `browser` requires** — OPEN (plan §33 Q18)
- **Evidence:** F-2 (CDP primitives without model calls), F-4 (snapshot, placeholders), F-5
  (navigation-only filter), F-6 (telemetry).
- **Options:**
  - **(a)** an action class + an isolated profile + a request-level filter + telemetry off:
    complete, and the most work;
  - **(b)** an action class only, the rest per harness: uneven;
  - **(c)** keep it undefined until A4.
- **Owner:** user · **Phase:** written as the browser capability ADR before A4.
- **Depends on:** ADR-0037, XR-12 (decided), XR-9.
- **Blocks V1:** no (`browser` withdrawn) · **Blocks V2:** A4 · **Safe to stay open:** yes, until A4.

**XR-3 — trust model for executable or third-party skill content** — OPEN
- **Evidence:** F-10, F-56.
- **Options:** a review gate; pinning by hash; a CI scan; allowed-tools declarations; no script
  execution. Combinations are possible, each trading safety for coverage.
- **Owner:** user · **Phase:** V1.x-O5 · **Depends on:** XR-1 (decided; skills may arrive through
  the sources).
- **Blocks:** O5 · **Safe to stay open:** yes.

**XR-4 — where speech becomes text, and its privacy rule** — OPEN (plan §33 Q17)
- **Evidence:** F-31, F-33, F-34, F-35, F-37.
- **Options:**
  - **(A) native sidecar:** shell and tray friendly; packaging gaps; no PWA.
  - **(B) SPA capture and VAD, local STT:** one capture path; a CSP `'wasm-unsafe-eval'` change and
    a vendored runtime; QtWebEngine permission unverified.
  - **(C) external provider:** audio leaves the device; an ADR-0035 provider rule and a terms
    check.
  - **Privacy sub-choices:** raw-audio retention; what is recorded.
- **Owner:** user · **Phase:** A1 · **Depends on:** A0a (A0c for B).
- **Blocks:** A1 · **Safe to stay open:** yes.

**XR-5 — derived summaries in context assembly** — OPEN
- **Evidence:** F-20.
- **Options:** none; own-call summaries with provenance (ADR-0022).
- **Phase:** after P21 (PV-9) · **Safe to stay open:** indefinitely, unless truncation is measured.

**XR-6 — desktop-control capability word and action class** — OPEN (plan §33 Q18)
- **Evidence:** F-8, F-51.
- **Options:**
  - **(a)** a word + an action class + screen-capture handling;
  - **(b)** narrow typed integrations only;
  - **(c)** defer.
  - **Sub-choice:** retention of screenshots and UI Automation trees.
- **Owner:** user · **Phase:** the desktop capability ADR before A5.
- **Depends on:** ADR-0037, XR-9, PV-20.
- **Blocks:** A5 · **Safe to stay open:** yes.

**XR-7 — when `Message.modality` lands, with its provenance** — OPEN
- **Evidence:** F-32; ADR-0042 §7; ADR-0050 §9.
- **Options:**
  - **(a)** a V1 nullable column now: no later migration; a field without a writer;
  - **(b)** with A1: one small migration then.
- **Recommendation (not a decision):** (b).
- **Phase:** V1 or A1 · **Blocks:** A1 · **Safe to stay open:** yes.

**XR-8 — what "interrupt" means for streamed or spoken output** — OPEN
- **Evidence:** F-41, F-47, F-48.
- **Options:**
  - **(a)** client-local playback stop only;
  - **(b)** also cancel the producing own call, as a recorded command distinct from mission
    `stop` (ADR-0042 §1).
- **Phase:** A2 · **Depends on:** A0b's cancellation facts.
- **Blocks:** A2, PV-11 · **Safe to stay open:** yes.

**XR-9 — "telemetry off and verified" as a precondition for adopting any third-party component or harness** — OPEN (plan §33 Q19)
- **Evidence:** F-6.
- **Options:**
  - **(a)** a uniform gate: some components become unadoptable;
  - **(b)** case by case: inconsistent.
- **Scope note:** XR-9 is the component-trust gate. Skills trust is XR-3, and execution context
  is XR-1.
- **Phase:** before the first adoption (A1, A2, A4, A5).
- **Blocks:** those phases · **Safe to stay open:** yes, until the first adoption.

**XR-10 — activation for voice input** — **DECIDED 2026-10-03** (ADR-0050 §2)
- **Decision:** push-to-talk only.
- **Wake word:** PV-21. Reopening it requires an explicit amendment of ADR-0050 §2.
- **Scope note:** together with XR-4, it forms "the speech input architecture".

**XR-11 — ADR-0050** — **DECIDED 2026-10-03.** Approved with A1, A2, A4 and A5 folded in; A3
resolved by XR-10.

**XR-12 — does `browser` ship in P22?** — **DECIDED 2026-10-03.** No. It is withdrawn from P22
(ADR-0037 "Amended") and designed with its action class in the browser capability ADR before A4.

**XR-13 — OS-level sandbox in P20** — **DECIDED 2026-10-03** (ADR-0051)
- **Decision:** no Archeus-owned sandbox in P20. P20 tests the application and harness boundary
  and threat-models the gap.
- **Later work:** PV-20, required before A5.

**XR-14 — Claude Code tool allowlists** — **DECIDED 2026-10-03** (ADR-0052; plan §33 Q22)
- **Decision:** option (a). Tool removal in P20 by `--tools` (allow-form) from action classes;
  `--disallowedTools "mcp__*"` except opted-in servers; never `--allowedTools`; unmapped
  built-in tools excluded by default.
- **Phase:** P20 (PV-22), after P19.5.
- The evidence and options at decision time are kept below for the record.
- **Evidence [A]:**
  - execution-architecture §2 specifies `--allowedTools` / `--disallowedTools` derived from action
    classes (e.g. no `Bash` for a pure `document` task);
  - p11-design-gate §18, the execution environment as built, lists only the environment and
    credential removal;
  - `adapter.py:117-126` passes no tool allowlist and no `--add-dir`;
  - only own calls disallow write tools (`archeus/harnesses/calls.py:52`).

  The fail-closed hook is therefore the only per-tool gate for Claude Code executions.
- **Options:**
  - **(a)** P20 builds the allowlists as specified: capability removal before the hook, as
    ADR-0007 intends.
  - **(b)** P20 records the hook as the sole tool gate and amends execution-architecture §2: no
    new code, but one enforcement layer instead of two.
  - **(c)** P24's audit decides.
- **Owner:** user · **Phase:** before P20 implementation.
- **Blocks V1:** P20 acceptance (G6) · **Blocks V2:** A4 and A5 rely on capability removal.
- **Safe to stay open:** until P20 starts.
- **Decision brief (2026-10-03):** [XR-14_TOOL_ALLOWLIST_BRIEF.md](XR-14_TOOL_ALLOWLIST_BRIEF.md).
  - Hook failures fall to Claude Code's permission flow.
  - `--allowedTools` pre-approves rather than restricts; `--tools` restricts.
  - Most risky classes ride on Bash.
  - Draft ADR text exists for all three options.
  - Still OPEN.

## 5. Backlog (PV) — authoritative

**Class:**
- **V1:** a V1 phase owns it;
- **V1.x:** after V1, before V2;
- **V2:** an assistant-layer phase;
- **R:** research only.

| ID | Item | Source | Owner (subsystem) | Phase | Prerequisites | ADR first? | Class | Acceptance / evidence | Status |
|---|---|---|---|---|---|---|---|---|---|
| PV-1 | Windows STT/VAD benchmark (§3.1) | F-25…F-29, F-34, F-36 | research | V2-A0a | — | no | R | dated report covering every §3.1 dimension on the hardware matrix | ready-to-research |
| PV-2 | Voice capture + VAD + STT path | F-25, F-31, F-35 | clients + a voice device component | V2-A1 | PV-1, XR-4, XR-9 | no (ADR-0050 governs) | V2 | §2 A1 acceptance | blocked-decision |
| PV-3 | `Message.modality` + engine provenance | F-32 | Core domain, the messages command | V2-A1 (or V1 per XR-7) | XR-7 | no (ADR-0042 §7, ADR-0050 §9) | V2 | migration test; provenance on every voice message | blocked-decision |
| PV-4 | Spoken output, sentence chunking, half-duplex first | F-41, F-47, F-48 | clients | V2-A2 | PV-18, XR-8, XR-9 | no | V2 | §2 A2 acceptance | parked |
| PV-5 | Tray and push-to-talk hotkey | F-29, F-48 | desktop client | V2-A3a | PV-16; A1 for the hotkey | no | V2 | idle invariant; hotkey never opens the microphone unprompted | parked |
| PV-6 | Desktop-control capability harness | F-8, F-51 | harnesses, policy | V2-A5 | XR-6, XR-9, PV-20, ADR-0037 | **yes** (desktop capability ADR) | V2 | §2 A5 acceptance | blocked-decision |
| PV-7 | `browser` capability harness | F-2, F-4, F-5 | harnesses, policy | V2-A4 | XR-2, XR-9, ADR-0037 | **yes** (browser capability ADR) | V2 | §2 A4 acceptance | blocked-decision |
| PV-8 | Skill trust + CI scanning + review metadata | F-9…F-11, F-56 | skills | V1.x-O5 | XR-3 | no (orchestration reconciliation §25) | V1.x | scanner in CI; no unreviewed script runs | owned (O5) |
| PV-9 | Measure context truncation; summaries only if needed | F-20 | context, knowledge | after P21 | P21 data, XR-5 | no | V1.x | a truncation measurement report | parked (deferrable indefinitely) |
| PV-10 | Build the ADR-0049 rule: spawn flags, opt-in, inventory, exit-code-2 deny | F-1 | harnesses/execution | **P20** | ADR-0049 (DECIDED) | no | **V1** | G6: exclusion, inventory, fallback and deny tests | decided; waiting for P20 |
| PV-11 | Interrupting a streamed text reply | F-41 | conversation client | V2-A2 | XR-8 | no | V2 | no mission state change without a recorded command | parked (cross-ref PV-4) |
| PV-12 | Own-call retry rule for streams | F-45 | own calls (ADR-0022) | V1.x | own calls streaming | no | V1.x | retry only before the first byte; mid-stream errors raised | parked (deferrable indefinitely) |
| PV-13 | Windows OS-sandbox mechanisms study (AppContainer, Job objects, Windows Sandbox) | F-22 | research, security | before PV-20 | — | no | R | dated report: confinement achievable for a Node CLI plus its child shells | ready-to-research |
| PV-14 | Telemetry-off verification per adopted component | F-6 | security | each adoption | XR-9 | no | V2 | network capture + configuration proof | blocked-decision |
| PV-15 | Spoken Attention items | O-J | clients | V2-A3b | PV-4 | no | V2 | §2 A3b acceptance | parked |
| PV-16 | Desktop shell probe (§3.3) | F-33, F-34 | research | V2-A0c | — | no | R | dated report answering §3.3 | ready-to-research |
| PV-17 | Archeus MCP server tool design | F-24 | API | post-V1 (plan §33 Q13) | Q13 | **yes**, when scheduled | V2 | — | parked |
| PV-18 | Windows TTS survey (§3.2) | research §23 | research | V2-A0b | — | no | R | dated report answering §3.2 | ready-to-research |
| PV-19 | Observe one real execution per ADR-0049 source rule | ADR-0049 undocumented points | harnesses/execution | **P20** | ADR-0021 answered for one harness | no | **V1** | recorded inventory matches the flags; the login survives or the fallback is shown; exit-2 and halt behaviour observed | blocked (ADR-0021) |
| PV-20 | Archeus-owned OS-level sandbox for executions on Windows *(new 2026-10-03)* | F-22; ADR-0051 §5 | execution, security | post-V1; **required before V2-A5**; considered for A4 | PV-13 | **yes** | V1.x/V2 | confinement tests: filesystem outside the worktree and network denied for a Claude Code execution | parked |
| PV-21 | Wake-word activation *(new 2026-10-03)* | F-38, F-39; XR-10 | voice device component | after V2-A1 | an ADR-0050 §2 amendment; an on-device detector with a licence-clean model (PV-1's candidates); a short rolling buffer discarded unless activated; nothing before activation becomes a `Message` or is stored; a visible always-listening indicator; opt-in only | **yes** (amends ADR-0050 §2) | V2 | false-accept and false-reject rates; a no-retention proof; an indicator check | parked |
| PV-22 | Claude Code tool removal per ADR-0052: action-class → `--tools` mapping in the adapter, `mcp__*` deny, never `--allowedTools`, unmapped tools excluded *(new 2026-10-03)* | XR-14; brief §3 | harnesses (Claude Code adapter) | **P20**, after P19.5 | ADR-0052 (DECIDED); P19.5 finished; ADR-0021 for the observed run | no (ADR-0052 decides it) | **V1** | argv per class set; mapping completeness against `ACTION_CLASSES` and the canonicaliser; CLI drift test; mutations (drop a row, add `--allowedTools`, drop `mcp__*`, drop `--settings`); observed run; the effect of excluding the subagent and todo tools measured | decided; waiting for P20 |

## 6. Security and trust map

| Concern | Held by | State |
|---|---|---|
| Inherited hooks, plugins, skills, MCP servers, permissions, CLAUDE.md (user, project, local) | ADR-0049 · PV-10 · PV-19 | DECIDED; built in P20 |
| Whether another hook widens Archeus's deny | ADR-0049 §3: exit code 2 | DECIDED; observed in PV-19 |
| Legacy Archeus hooks inside executions | P0.5 guard (`ARCHEUS_EXECUTION_ID`) [A] | built |
| Managed settings | always apply [DOC]; recorded, never excluded | fact |
| Execution isolation: application-level vs OS-level | ADR-0051 · PV-13 · PV-20 | DECIDED (no OS sandbox in V1) |
| Tool removal (capability removal) | ADR-0052 · XR-14 · PV-22 | DECIDED; built in P20 (after P19.5) |
| Browser control | ADR-0037 "Amended" · XR-2 · PV-7 · §2 A4 | withdrawn from V1; OPEN for V2 |
| Desktop control, input injection, PowerShell | XR-6 · PV-6 · PV-20 · §2 A5 | OPEN |
| Microphone | ADR-0050 §2 (push-to-talk) · XR-4 privacy · ADR-0051 §3 threat entry | DECIDED (activation); OPEN (placement) |
| Wake word | PV-21 | deferred |
| Screen capture | XR-6 sub-choice · ADR-0050 §11 · ADR-0051 §3 | OPEN |
| Third-party component trust (telemetry) | XR-9 · PV-14 | OPEN |
| Skills trust | XR-3 · PV-8 | OPEN (O5) |
| Approvals and destructive confirmations never by voice | ADR-0042 §7 [A] | DECIDED |
| Fetched or model text never a command | ADR-0042 §6 [A] | DECIDED |
| CSP as a boundary (WASM) | XR-4 option B | OPEN |
| Provider credentials never in an assistant component; cloud STT is a provider | ADR-0050 §8 · ADR-0035 | DECIDED |

## 7. Reconciliation — every research finding to its record

| Findings | What they are | Classification | Where it lives | V1 impact | V2 impact | Decision |
|---|---|---|---|---|---|---|
| F-1 | executions load their settings sources | decided | ADR-0049, PV-10, PV-19 | **P20** | none | XR-1 (decided) |
| F-2, F-4, F-5 | CDP primitives; snapshot and placeholders; navigation-only filter | V2 / reference | XR-2, PV-7, §2 A4 | none (`browser` withdrawn) | A4 | XR-2 |
| F-3, F-42, F-43 | the Browser Use `Agent` loop; tool-call healing; Fury's loop and unsandboxed bash | rejected | ADR-0050 §6; ADR-0042 §6; ADR-0006, 0022 | none | must not enter | none |
| F-6 | telemetry on by default | requires decision | XR-9, PV-14 | none | A1, A2, A4, A5 | XR-9 |
| F-7, F-50 | cloud cookie sync; pickle and `torch.load` | rejected | §9 | none | none | none |
| F-8, F-51 | Windows desktop control; narrow integrations | requires decision / reference | XR-6, PV-6, PV-20; ADR-0050 §6 | none | A5 | XR-6 |
| F-9, F-11, F-56 | skills format; CI scanning and metadata; scanner evidence | V1.x | PV-8, V1.x-O5 | none | none | XR-3 |
| F-10 | third-party skill execution | requires decision | XR-3 | none | none | XR-3 |
| F-12, F-13, F-16, F-39, F-46, F-52, F-55 | `self_check` contract; scientific skills; `untrusted` marker; clap trigger; local-model shims; cloud character API; `browser-use-core` licence | reference only | §8, the research report | none | none | none |
| F-14, F-15, F-17, F-19, F-54 | cybersecurity skills; external memory stores; vector retrieval; OpenViking | rejected | §9; ADR-0012 | none | must not enter | none |
| F-18, F-21, F-23, F-37, F-40, F-53 | origin guard; CANDIDATE knowledge; handoff patterns; speech outside Core; UI vs transcript events; no notifications elsewhere | already in Archeus | ADR-0002, 0003, 0009, 0012, 0034, 0047 | none | none | none |
| F-20 | multi-size summaries | needs measurement | XR-5, PV-9 | none | none | XR-5 |
| F-22 | OS sandbox, credential proxy | decided | ADR-0051, PV-13, PV-20 | **P20 tests and threat model** | A5 needs PV-20 | XR-13 (decided) |
| F-24 | tool design for an MCP server | V2 | PV-17 | none | yes | Q13 |
| F-25…F-27, F-29, F-36 | Silero; whisper.cpp; Parakeet v3 runtimes; Blazing endpointing; Python 3.10 wheel gap | benchmark first | PV-1, §3.1 | none | A1 | none until A0a reports |
| F-28 | Parakeet EOU 120M | reference (no Windows path) | §1 item 13 | none | none | none |
| F-30, F-49 | Blazing as an app; the Jarvis persona copy | rejected | §9 | none | none | none |
| F-31, F-33, F-34, F-35 | speech placement; `getUserMedia`; WASM VAD vs CSP; `web-whisper` split | requires decision / verification | XR-4, PV-2, PV-16 | none (no CSP change) | A1 | XR-4 |
| F-32 | no modality field | requires decision (timing) | XR-7, PV-3 | only if XR-7 (a) | A1 | XR-7 |
| F-38 | wake-word licences | decided (deferred) | ADR-0050 §2, PV-21 | none | after A1 | XR-10 (decided) |
| F-41, F-47, F-48 | interrupt keeps the partial; TTS sentence stream; half-duplex | V2 | XR-8, PV-4, PV-11 | none | A2 | XR-8 |
| F-44 | compaction | rejected | ADR-0047 §6, ADR-0050 §7 | none | must not enter | none |
| F-45 | retry before the first streamed byte | reference | PV-12 | none | none | none |
| (gap) | Windows TTS not researched | research | PV-18, §3.2 | none | A2 | none |
| (gap) | `browser` word without an action class | decided | ADR-0037 "Amended" | P22 drops it | A4 | XR-12 (decided) |
| (gap) | tool allowlists specified, not built | decided | ADR-0052, PV-22 | **P20** | A4, A5 add mapping rows | XR-14 (decided) |

Every F-n appears in exactly one row.

## 8. External discoveries — the Archeus lesson, not the project

**Rule:** a project is evidence or inspiration, never an authority. Its agent loop, memory model,
routing model, permissions model and tool-execution model are not adopted unless a decision
here adopts the idea. **"Affects"** names what the lesson changes: architecture, planning,
testing, UX, security, or inspiration only.

| Source | Archeus lesson | Class | Record | Affects |
|---|---|---|---|---|
| Browser Use (X1) | The reusable layer is the CDP primitive under the loop; a domain filter must be request-level, not navigation-level; credentials go in as placeholders | V2 | XR-2, PV-7 | security, architecture |
| Browser Harness (X2) | Primitives without model calls are the right shape for a harness; never attach to the real profile | V2 | PV-7 | security |
| Windows Harness (X3) | Desktop control is a distinct risk class: foreground takeover, screen capture, PowerShell; its `install-skill` is how account homes get polluted | V2 / evidence | XR-6, PV-6, PV-20, ADR-0049 | security, architecture |
| AgentMemory (X4) | Injected memory needs a trust marker; Archeus's knowledge lifecycle already has a richer one | reference | ADR-0012 | inspiration |
| qmd (X5) | A DNS-rebinding origin guard on a local MCP server is table stakes; Archeus already has one | already in Archeus | — | — |
| Scientific Agent Skills (X6) | Scanners give false positives; the real risks are `.env` walks and generated `SKILL.md` | V1.x | XR-3, PV-8 | security, testing |
| Diagram Design (X7) | Per-skill version, compatibility and `last-reviewed` metadata; an output self-check contract | V1.x / reference | PV-8 | planning |
| Cybersecurity Skills (X8) | Dual-use skill content without behaviour tests is not adoptable | rejected | §9 | security |
| Awesome Harness Engineering (X9) | An OS sandbox plus a credential proxy around agents; handoff patterns already decided; tool design for an MCP server | V1 (test) / V2 | ADR-0051, PV-20, PV-17 | security, architecture |
| OpenViking (X10) | Summaries at several sizes for one item, only if measured; AGPL and a separate vector service rule it out as a dependency | V1.x / rejected | XR-5, PV-9 | planning |
| Blazing Transcribe (X11) | VAD-gated, endpointed STT: adaptive silence, quietest-point split, generation guard, keep-warm; macOS results predict nothing on Windows | research | PV-1, §3.1 | testing, architecture |
| Jarvis (X12) | Half-duplex (mute while speaking) is the simplest echo control; the persona is presentation, not architecture | V2 / rejected | PV-4; §9 | UX |
| Fury (X13) | Interrupt keeps the partial; a sentence-boundary stream for TTS; mid-stream errors raised, never truncated; its loop, tool-call healing and compaction are rejected | V2 / V1.x / rejected | XR-8, PV-4, PV-11, PV-12; ADR-0050 §6–§7 | architecture, UX |
| Huw Prosser's other repos (X14) | Client VAD feeding local STT works (`web-whisper`); narrow typed integrations before desktop control (`spotify-cli`); plaintext token files and `0.0.0.0` debug servers are counter-examples | V2 / reference | XR-4, ADR-0050 §6 | architecture, security |
| `ricky0123/vad` (X15) | Silero can run in the SPA, at the price of a CSP change and a vendored runtime | research | XR-4 (B), PV-16 | security, architecture |
| Windows speech components (X16) | Several runtimes have Windows binaries or CI; none is measured on consumer hardware; licences differ per model | research | PV-1, PV-21, §1 item 13 | testing, planning |

## 9. What must never enter V1 because it appeared in this research

- speech, STT, TTS, VAD, wake words, the tray and global hotkeys;
- microphone capture, screen capture, desktop input injection;
- the `Message.modality` column (unless XR-7 (a) is decided);
- any CSP change;
- the `browser` capability word, a browser harness, a desktop harness or their action classes;
- any third-party skill execution;
- any external memory store, vector or semantic retrieval, or derived summaries;
- any agent loop, tool-call parsing of model text, compaction by Archeus, or model call outside
  the router, including inside an "assistant" component;
- a second router, memory or approval path;
- any component with telemetry on;
- Jarvis or Fury code (no licence), and Blazing as an engine (macOS-only);
- persona copy and audio-reactive motion (already rejected in P16 §18.1).

**The only V1-facing work from this research:**
- P20 builds ADR-0049 (PV-10) and observes it (PV-19);
- P20 tests and threat-models the boundary ADR-0051 describes;
- P20 builds ADR-0052's tool removal (PV-22);
- P22 omits `browser`.

## 10. Dependency graph

```
research (report §1–§26)
  └─► findings F-1…F-56 (§7)
        └─► XR decisions (§4) ──► ADRs ──► PV backlog (§5) ──► phase (§2) ──► security/acceptance gate ──► go-ahead ──► implementation ──► evidence

V1 (owned by V1 phases; nothing else from this research)
  XR-1 ✔ ─► ADR-0049 ✔ ─► PV-10 (P20) ─► PV-19 observed run (needs ADR-0021) ─► G6 ─► P26
  XR-13 ✔ ─► ADR-0051 ✔ ─► P20 boundary tests + threat model ─► G6
  XR-14 ✔ ─► ADR-0052 ✔ ─► PV-22 (P20) ─► mapping, drift and mutation tests + observed run (needs ADR-0021) ─► G6
  (every P20 item above starts only after P19.5 is explicitly finished)
  XR-12 ✔ ─► ADR-0037 "Amended" ─► P22 descriptor work without `browser`

V1.x
  XR-3 ○ ─► PV-8 ─► V1.x-O5
  P21 data ─► PV-9 ─► XR-5 ○ (only if truncation measured)
  PV-12 (only if own calls stream) · PV-20 (may be pulled into V1.x by a new decision)

RESEARCH ONLY (any time, no product code)
  PV-1  ─► V2-A0a report ─┐
  PV-18 ─► V2-A0b report ─┼─► XR-4, XR-7, XR-8, A1 latency target, A2 engine, PV-21 candidates
  PV-16 ─► V2-A0c report ─┘
  PV-13 ─► Windows sandbox study ─► PV-20's ADR

STRICTLY V2 (after P26; each phase: decisions ✔ + gate + go-ahead)
  XR-11 ✔ ADR-0050 governs everything below
  speech track:
    XR-4 ○ + XR-7 ○ + XR-9 ○ + A0a ─► PV-2, PV-3 ─► V2-A1 ─► [A1 gate] ─► evidence
    XR-8 ○ + XR-9 ○ + A0b ─► PV-4, PV-11 ─► V2-A2 (spoken barge-in also needs A1)
    A0c ─► PV-5 ─► V2-A3a (hotkey also needs A1) ;  A2 ─► PV-15 ─► V2-A3b
    after A1: PV-21 wake word ─► needs an ADR-0050 §2 amendment
  capability track:
    ADR-0037 (P22) + browser capability ADR (XR-2 ○) + XR-9 ○ ─► PV-7, PV-14 ─► V2-A4
    ADR-0037 + desktop capability ADR (XR-6 ○) + XR-9 ○ + PV-20 ─► PV-6, PV-14 ─► V2-A5

✔ decided   ○ open
```

## 11. Contradiction audit (re-run 2026-10-03, after the decisions)

| # | Check | Result |
|---|---|---|
| 1 | ADR-0049 vs the P0.5 guard | **consistent.** ADR-0049 Context item 2 and execution-architecture §2's tagging row both say the legacy hooks stand down |
| 2 | Settings-source scope | **consistent.** ADR-0049 Decision 1 covers user, project and local, and plan Q15 matches |
| 3 | ADR-0050 vs wake word | **resolved.** §2 is push-to-talk only; PV-21 requires an amendment of §2 |
| 4 | `browser` vs policy | **resolved.** Withdrawn from P22 (ADR-0037 "Amended"); the orchestration plan's descriptor row is annotated; `CAPABILITIES` never had it |
| 5 | Message modality | **consistent, open.** Domain-model §6 points to XR-7, ADR-0050 §9 binds the provenance to it, and the code has no field (as expected) |
| 6 | A3 dependencies | **corrected again.** A3a's tray needs only A0c, its hotkey needs A1; A3b needs A2 |
| 7 | PV-13 scope | **resolved.** XR-13 decided (ADR-0051); PV-13 is the study, feeding PV-20 |
| 8 | Duplicate decision/backlog tables | **consistent.** The research report's §20–§21 point here. Plan §31.5 is a summary that defers to §2 here |
| 9 | XR terminology and scope | **consistent.** XR-9 and XR-10 carry scope notes; XR-14 is new and named for what it asks |
| 10 *(new)* | V2-A2 depended on A1 as a whole | **corrected.** Only a spoken barge-in needs A1 |
| 11 *(new)* | execution-architecture §2 specifies tool allowlists that P11 §18 and `adapter.py` never built | **recorded as XR-14**, not fixed. ADR-0051 §2 states the gap |
| 12 *(new)* | ADR-0007's "sandbox flags" vs ADR-0051 | **consistent.** Both refer to harness-provided sandboxes, and ADR-0051 forbids describing V1 as OS-sandboxed |
| 13 *(new)* | ADR-0042 note and conversational-orchestration notes called ADR-0050 PROPOSED | **updated** to DECIDED in this pass |
| 14 *(XR-14 decision)* | execution-architecture §2 names `--allowedTools`, which pre-approves | **amended** (dated marker in §2): removal uses `--tools`/`--disallowedTools` (ADR-0052 §8) |
| 15 *(XR-14 decision)* | plan P20 "Depends: P19" vs §31.3's chain P19 → P19.5 → P20 and the user's sequencing | **corrected** to "Depends: P19.5 (explicitly finished)" |
| 16 *(XR-14 brief, not fixed)* | execution-architecture §5 (HTTP `/v1/hook/evaluate`, 5 s) and §1 (`policy_hook.py` path) describe the hook differently from the build (file mailbox, 60 s, `archeus/harnesses/hook.py`) | **recorded**, not fixed: stale descriptions of a working hook, outside XR-14 |

## 12. Decisions still waiting for the user

| ID | Needed by | V1-facing? |
|---|---|---|
| XR-7 modality timing | before A1 (or now, if V1) | only if (a) |
| XR-2 browser boundary | the browser capability ADR, before A4 | no |
| XR-6 desktop capability | the desktop capability ADR, before A5 | no |
| XR-9 telemetry gate | before the first component adoption | no |
| XR-4 speech placement | before A1, after A0a | no |
| XR-8 interruption scope | before A2, after A0b | no |
| XR-3 skills trust | before V1.x-O5 | no |
| XR-5 summaries | only if P21 measures truncation | no |
| ADR-0037 approval itself | before P22 | yes (pre-existing; unchanged by this pass) |

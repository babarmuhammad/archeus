# External Research 2026-10 — Agent Ecosystem, Jarvis, Windows Speech

Internal document (excluded from the published manual, `mkdocs.yml` `exclude_docs: /research/`).
Archeus HEAD at research time: `0a2a3af` (branch `archeus-v1-rearchitecture`). Date: 2026-10-02.

This file consolidates three research passes (phase 1, phase 2, and a short gap-closure pass on
2026-10-02) into one durable record. Until now, the findings, the decision register and the
backlog existed only in chat transcripts. A future engineer should not need to reopen any
external repository to understand what Archeus decided about it and why.

> **Status banner (2026-10-03).** This is a dated research record. The ADR statuses and
> decision states written in its sections are those of 2026-10-02: ADR-0049 OPEN, ADR-0050
> PROPOSED, XR-1/10/11/12/13 open. For current statuses, see
> [../architecture/ARCHEUS_V2_ASSISTANT_LAYER.md](../architecture/ARCHEUS_V2_ASSISTANT_LAYER.md) §0 and §4.

**Where it landed in the architecture (2026-10-02):**
- ADR-0049 (OPEN) and ADR-0050 (PROPOSED);
- research notes on ADR-0037, 0042 and 0047;
- plan P20 entry, §31.2, §31.3, the new §31.5 (V2-A0…A5) and §33 Q15–Q19;
- orchestration reconciliation §29.
- **2026-10-03 reconciliation:** [../architecture/ARCHEUS_V2_ASSISTANT_LAYER.md](../architecture/ARCHEUS_V2_ASSISTANT_LAYER.md) is now the authoritative register (XR), backlog (PV),
  phase plan, security map and do-not-forget index; ADR-0049 was revised; ADR-0050 gained proposed amendments A1–A5.
- **2026-10-03 decisions (the user's):**
  - XR-1 → ADR-0049 DECIDED;
  - XR-13 → ADR-0051 (new, DECIDED);
  - XR-12 → ADR-0037 "Amended" (`browser` withdrawn from P22);
  - XR-11 → ADR-0050 DECIDED;
  - XR-10 → push-to-talk, wake word PV-21.

  The same pass found XR-14 (tool allowlists not built).

**What this document is not:** an implementation plan. Nothing here enters V1 unless an existing
V1 phase already owns it (§26 is the boundary). The two ADRs it proposes, ADR-0049 (OPEN) and
ADR-0050 (PROPOSED), record questions and principles. Neither one authorises work.

**Evidence tags:**
- **[S]** read in source at the pinned revision;
- **[D]** documentation, a README or a model card only;
- **[A]** Archeus documents or code at `0a2a3af`;
- **[CLI]** `claude --help`, v2.1.287;
- **[I]** inference.

Everything was read through `gh api`, raw files, PyPI JSON and HF model cards. Nothing was
cloned, installed or run, and no fetched content contained instructions aimed at an agent.

---

## 1. Executive summary

- **The scope question was settled first.** Every user message in every Claude Code transcript
  on this machine (seven account homes) was searched for a separate list of eight repositories.
  No such list exists. The only eight-repository list is the one from the Instagram reel:
  - Browser Use
  - AgentMemory
  - Scientific Agent Skills
  - Diagram Design
  - Cybersecurity Skills
  - Awesome Harness Engineering
  - OpenViking
  - Blazing Transcribe

  The user chose to consolidate rather than research a new set (2026-10-02). The other external
  lineage, R1–R7 plus BRUD, is already recorded in
  [external-references.md](external-references.md) and the design and orchestration audits.
- **Jarvis is a thin voice loop, not an architecture.** Huw Prosser's public Jarvis
  (`huwprosser/jarvis-mlx`) is a 4 KB, half-duplex, macOS-only script with no licence:
  - microphone → webrtcvad → MLX Whisper → MLX Llama-3-8B → MeloTTS;
  - no tools, no memory, no wake word, no UI.

  His maintained work is `fury-sdk`, also unlicensed: a single-agent tool loop. What makes his
  demos feel like "JARVIS" is presentation plus narrow integrations (e.g. `spotify-cli`, "a CLI
  for you and your agent"), not a novel orchestration design. **Nothing in it should replace
  Archeus's mission, router, ledger, policy or knowledge model.** Four of its patterns conflict
  with decided ADRs:
  - tool-call healing (ADR-0042 §6);
  - an agent loop in the control plane (ADR-0006, ADR-0022);
  - transcript compaction (ADR-0047 §6);
  - unconfined tools (ADR-0007).
- **Architectural knowledge worth keeping:**
  1. **One finding touches V1 as built:** executions inherit the account home's own Claude Code
     customisations (XR-1). Recorded as **ADR-0049 (OPEN)**.
  2. **A Jarvis-style assistant fits Archeus only as clients and device components over the
     existing conversation and mission model.** Recorded as a principle in
     **ADR-0050 (PROPOSED)**, so future voice and desktop work does not re-open the
     orchestration decisions.
  3. **Windows speech-to-text is feasible from components that ship Windows binaries or CI.**
     Blazing itself is macOS-only. The usable components are Silero VAD, whisper.cpp,
     sherpa-onnx, NeMo-Speech.cpp, onnx-asr, CTranslate2 and sounddevice. None is measured on
     consumer Windows hardware, so the order is benchmark first (PV-1), then decide where speech
     becomes text (XR-4).
  4. **New this pass:** `ricky0123/vad` (ISC) runs Silero VAD **inside the browser** via
     onnxruntime-web, and Huw's `web-whisper` uses exactly that split: client VAD, server STT. It
     makes "the SPA captures and segments, a local sidecar transcribes" a concrete XR-4 option.
     **It conflicts with Archeus's current CSP:** `script-src 'self'` has no
     `'wasm-unsafe-eval'` (`archeus/api/auth.py:40`), so this is a security decision, not a
     library choice.
- **The decision register is now persisted, under a new prefix.** The chat-only research
  register (D-1…D-16) collided with the repository's own D-1…D-26, which mean different things
  (orchestration plan, conversational orchestration). Research decisions are re-keyed as
  **XR-1…XR-11** (§21).
- **V1 scope is unchanged.** No new work enters P19.5–P26. ADR-0049 has an owning phase (P20),
  but its decision does not block any current slice.

## 2. Exact repositories and projects researched

**The scope check** (2026-10-02):
- Every user message in `~/.claude*/projects/*/*.jsonl` (accounts default, Affan, Federico,
  Gioele, Lorenzo, dario, personal) containing four or more GitHub URLs was enumerated.
- Four sets exist:
  - **the reel list (8):** researched in phases 1 and 2;
  - **the R1–R7 design lineage:** `external-references.md`;
  - **BRUD:** orchestration audit, 2026-09-30;
  - **the credits lineage plus four skill collections:** orchestration audit.
- None is an unresearched list of eight.

| ID | Project | Canonical URL | Role in this research |
|---|---|---|---|
| X1 | Browser Use | https://github.com/browser-use/browser-use | reel #1 |
| X2 | Browser Harness | https://github.com/browser-use/browser-harness | found from X1 |
| X3 | Windows Harness | https://github.com/browser-use/windows-harness | found from X1 (phase 2) |
| X4 | AgentMemory | https://github.com/jayzeng/agentmemory | reel #2 |
| X5 | qmd | https://github.com/tobi/qmd | X4's search engine |
| X6 | Scientific Agent Skills | https://github.com/K-Dense-AI/scientific-agent-skills | reel #3 |
| X7 | Diagram Design | https://github.com/cathrynlavery/diagram-design | reel #4 |
| X8 | Cybersecurity Skills | https://github.com/CYBERAD7/anthropic-cybersecurity-skills (fork), upstream https://github.com/mukul975/Anthropic-Cybersecurity-Skills | reel #5 |
| X9 | Awesome Harness Engineering | https://github.com/harness-engineer/awesome-harness-engineering | reel #6 |
| X10 | OpenViking | https://github.com/volcengine/OpenViking | reel #7 |
| X11 | Blazing Transcribe | https://github.com/acstener/blazing-transcribe | reel #8 |
| X12 | Jarvis (MLX) | https://github.com/huwprosser/jarvis-mlx | Huw Prosser |
| X13 | Fury SDK | https://github.com/huwprosser/fury-sdk (+ `fury-sdk-js`) | Huw Prosser |
| X14 | Huw Prosser's other public repos | `web-whisper`, `spotify-cli`, `clap-detection`, `carter-voice-assistant`, `deskgpt`, profile README | gap closure 2026-10-02 |
| X15 | Silero VAD in the browser | https://github.com/ricky0123/vad | found from X14 (`web-whisper`) |
| X16 | Windows speech components | Silero VAD, whisper.cpp, Parakeet TDT v3 / realtime EOU 120M, NeMo, NeMo-Speech.cpp, sherpa-onnx, onnx-asr, faster-whisper / CTranslate2, sounddevice, openWakeWord, Porcupine | phase 2 deep dive |
| — | huwprosser.com | https://www.huwprosser.com | site renders client-side; the posts `building-jarvis-in-real-life`, `some-thoughts-on-jarvis` and `fury` are listed in the sitemap but their content is **UNVERIFIED** |

## 3. Research versions and commits

| ID | Pin | Licence | Language | Maintained | Windows | Cloud / account needed | Handles (credentials, telemetry, profiles, FS/network, code exec) |
|---|---|---|---|---|---|---|---|
| X1 | `62a0f71b` | MIT | Python ≥3.11 | very active | install CI on Windows; functional tests Linux only [S] | no (any model provider; cloud optional) | telemetry + version check on by default; device id = hash of MAC + hostname; runs a model loop that drives a browser [S] |
| X2 | `afbcc38` | MIT | Python | active, alpha, no test CI | has Windows branches [S] | no | attaches to a real logged-in Chrome profile; CLI executes code from stdin; telemetry sends scripts and stdout [S] |
| X3 | `46a37cf1` (PyPI 0.2.2) | MIT | Python; pywin32, uiautomation | created 2026-08-23, alpha | Windows-only [S] | no | SendInput (foreground takeover), UI Automation, PrintWindow, PowerShell `script`; telemetry opt-out; `install-skill` writes into `~/.claude`, `~/.codex`, … [S] |
| X4 | `a6c256b` | MIT | Node ≥20 | single author | partial (issue #43) | no | injection hooks installed into agent homes; MCP [S] |
| X5 | `26b703c5` | MIT | Node ≥22 / Bun | active | best effort; CI Ubuntu + macOS [S] | no | downloads GGUF models on first use; HTTP MCP with DNS-rebinding guard [S] |
| X6 | `1549884` | MIT | Python skills | very active | WSL2 [D] | some skills call OpenAI / Anthropic | 177 skills; scripts with network and credential use; a parent-folder `.env` walk [S] |
| X7 | `f903933` | MIT | stdlib Python + HTML/SVG | very active | Windows CI [S] | no | packaging writes into several hosts' folders [S] |
| X8 | fork `888bbe4`; upstream `54a7988` | Apache-2.0 | Python + PowerShell | fork stale; upstream active | partial | no | 754 / 818 dual-use offensive skills; CI checks frontmatter only [S] |
| X9 | `0b14b85` | none in effect | Markdown | inactive | n/a | n/a | link corpus; the OpenAI source returns 403 [D] |
| X10 | `7e47957d` | **AGPL-3.0** | Python / Rust / C++ | very active, alpha | wheels exist [D] | embedding / vision model providers (can be local) | server with insecure defaults at HEAD; can reuse Codex credentials [S] |
| X11 | `bc97a2d` (tags v2.2.0–v2.3.2) | MIT; models CC-BY-4.0 / NVIDIA Open Model License | Swift | bursty, no CI | **none** (macOS 15+, Apple Silicon) [S] | optional cloud clean-up | analytics, update and announcement calls (every 4 h) [S] |
| X12 | `e2a0887` (code last changed 2024-06-02) | **none** | Python; MLX, PyTorch | abandoned ("very out of date") [D] | none (`mps`) [S] | no | `torch.load` without `weights_only`; pickle loads [S] |
| X13 | `bbdf07c` (v0.3.2, 2026-09-25) | **none** | Python ≥3.10; `openai`, numpy | active, 25 releases, Ubuntu CI | no platform code in `src/`; no Windows CI [S] | any OpenAI-compatible endpoint (default local llama.cpp) | bash tool with no sandbox in the examples; executes tool-call markup found in plain text [S] |
| X14 | `web-whisper` `695960c`; `spotify-cli` `0cac8bd`; `clap-detection` `983a78a` (MIT); `carter-voice-assistant` `28e2071` (MIT); `deskgpt` `1b9a36a` | mostly none | Python / HTML / Electron | 2023–2026, demos | `carter-voice-assistant` claims Windows [D] | Carter API (cloud character) for the assistant; Spotify developer app | `spotify-cli` stores OAuth tokens as plain JSON in `~/.spotify-cli.json`, runs a loopback callback server on `127.0.0.1:8888` [S]; `web-whisper` binds `0.0.0.0` with `debug=True` [S]; `clap-detection`'s model is a Google Drive download [D] |
| X15 | `2e5aca9` (pushed 2026-09-12) | **ISC** | TypeScript | active | browser (any OS) [D] | no (but its README loads onnxruntime-web from a CDN) | ships Silero VAD legacy / v5 / v6 ONNX files; runs them via onnxruntime-web (WASM) [S] |
| X16 | Silero v6.2.3 · whisper.cpp `60c0be6` (bins b5130) · NeMo-Speech.cpp v0.2.0 · sherpa-onnx v1.13.8 · onnx-asr v0.12.0 · faster-whisper v1.2.1 / CTranslate2 v4.8.2 · sounddevice 0.5.6 · Parakeet TDT v3 HF `541d1f9` · EOU 120M HF `a7e2b46` | MIT / Apache-2.0; Parakeet v3 CC-BY-4.0; EOU NVIDIA Open Model License; openWakeWord models CC BY-NC-SA; Porcupine needs AccessKey | C/C++/Python | active | see §12 | Porcupine only | local inference; none send audio by default [D] |

## 4. Huw Prosser / Jarvis findings

**What is public** [S unless noted]:
- `jarvis-mlx`: one `main.py`, with vendored MLX Whisper and MeloTTS.
- `fury-sdk` and `fury-sdk-js`.
- Demo repos: `web-whisper`, `carter-voice-assistant`, `clap-detection`, `deskgpt`.
- One agent-facing integration: `spotify-cli`.
- The profile README calls him "the guy building JARVIS from Iron Man IRL" on TikTok (80m+ views).
- The blog posts are UNVERIFIED (client-rendered site).

**Implemented, demonstrated, described and inferred:**

| | Content |
|---|---|
| **Implemented (in code)** | a half-duplex voice loop (`jarvis-mlx`: webrtcvad with a 300 ms hangover, 0.75 s minimum utterance, microphone muted while thinking and speaking, Whisper large-v3 4-bit → Llama-3-8B 4-bit → MeloTTS on `mps`; history in memory, unbounded); Fury's agent loop (streaming, parallel tools, up to 200 tool rounds, interruption keeping partial text, JSONL session log that repairs a torn last line, history trimming and compaction, 429 retry only before the first streamed byte, mid-stream errors raised); a narrow app CLI for agents (`spotify-cli`); client-side VAD with server-side Whisper (`web-whisper`); a clap classifier (`clap-detection`) |
| **Demonstrated (video or demo, not checked against code)** | TikTok and YouTube demos of a "JARVIS" persona; the Carter "Steve Jobs" demo video [D] |
| **Described only** | the README speed and model claims of `jarvis-mlx`, which do not match its code; the three blog posts (UNVERIFIED) |
| **Inferred** | that the persistent-assistant feel in the demos comes from presentation (persona, voice, a beep) plus a handful of narrow integrations, not from memory or orchestration, since none of those exist in the published code [I] |

**Phase 6 checklist:**

| Aspect | What the public material shows | Would it strengthen or compete with Archeus? |
|---|---|---|
| Persistence feel | voice persona and voice; nothing stored between runs in Jarvis; Fury keeps a JSONL log, and its memory module is now only an example | Archeus's persistence is missions and knowledge (ADR-0004, ADR-0012); a voice is a presentation over it (ADR-0050 §1) |
| Voice | half-duplex loop | strengthens as a *client* pattern only |
| Wake word / activation | none in Jarvis; a clap CNN in a separate repo | activation is a client concern (XR-10) |
| STT | MLX Whisper (Mac); `web-whisper` uses client VAD + server Whisper | evidence for the XR-4 split |
| TTS | MeloTTS; Fury has a sentence-boundary stream for TTS | V2 output path (PV-4) |
| Interruption / barge-in | Jarvis: none (mic off while speaking); Fury: interrupt that keeps the partial | pattern for PV-4 (XR-8) |
| Conversational memory | in-memory list | competes; rejected (ADR-0012) |
| Context persistence | Fury compaction | competes; rejected (ADR-0047 §6) |
| Computer / browser / desktop control | none in Huw's code; narrow CLIs instead | the narrow-integration principle supports ADR-0050 §6 |
| Notifications, proactive behaviour, scheduling, background tasks | none | Archeus already owns automations (ADR-0020) and push (P20) |
| Tool execution | Fury: unconfined; tool-call healing | competes; rejected (F-42, F-43) |
| Approval / permission boundaries | none | Archeus stronger (ADR-0007, `action_hash` approvals) |
| Credentials | env vars plus a plain JSON token file (`spotify-cli`) | Archeus stronger (P20 DPAPI path) |
| Local vs cloud | Jarvis local; Fury any endpoint; Carter cloud | the data class rule (ADR-0035) covers it |
| Model switching | per-call `model=` in Fury, no failover | Archeus router stronger (ADR-0005, 0033, 0041) |
| Failure recovery / long-running actions | Fury's mid-stream error handling only | reference (F-45) |
| Mobile / multi-device | none | Archeus PWA (ADR-0010) |
| UI / state exposure | a terminal; DeskGPT is an Electron chat wrapper | nothing new |
| **Genuinely novel** | nothing architectural; the craft is in packaging small local models into a convincing persona | — |

## 5. Repository-by-repository findings

Only categories with meaningful evidence are listed. Finding numbers (F-n) are used in §7.

- **X1 Browser Use:**
  - its own model loop (`Agent`) over a CDP tool layer (F-3);
  - DOM and accessibility snapshot, `allowed_domains`, `sensitive_data` placeholders (F-4);
  - the domain filter covers navigation and new tabs only, so page `fetch`/XHR reach any host (F-5);
  - telemetry and version check on by default (F-6);
  - `profile-use` is closed binaries that sync cookies to the vendor cloud (F-7);
  - `browser-use-core` is an optional extra whose source is MIT in `browser-use/terminal`; the
    wheel lacks licence metadata (F-55, errata to phase 1).
- **X2 Browser Harness:**
  - CDP primitives with no model calls, a daemon, a CLI that runs stdin code, MCP (F-2);
  - attaches to the real logged-in profile (F-2, F-6).
- **X3 Windows Harness:** Windows desktop control (F-8):
  - `see` (PrintWindow screenshots), `key`/`type`/`click` (SendInput, which takes the foreground);
  - `ax` (UI Automation tree), `script` (PowerShell), plus a browser;
  - telemetry opt-out, and an `install-skill` that writes into agent homes (F-1, F-6).
- **X4 AgentMemory:**
  - Markdown memory, injection hooks, MCP (F-15);
  - an `untrusted` marker on injected memory, and a nudge-to-record hook (F-16).
- **X5 qmd:**
  - BM25 + vector search + model rerank over local GGUF models (F-17);
  - a DNS-rebinding origin guard on HTTP MCP (F-18).
- **X6 Scientific Agent Skills:**
  - 177 skills in the Agent Skills format (F-9, F-13);
  - weekly CI scanning (F-11);
  - the 28 CRITICAL scanner findings are false positives on credential and network use; real
    residual risks are a parent-folder `.env` walk, screen-text OCR fed into a generated
    `SKILL.md`, and a skill telling the agent to cite the vendor's paper (F-56).
- **X7 Diagram Design:**
  - a `self_check` output contract (F-12);
  - per-skill version, compatibility and `last-reviewed`; multi-host packaging (F-11).
- **X8 Cybersecurity Skills:** dual-use offensive skills, no behaviour tests or security scan (F-14).
- **X9 Awesome Harness Engineering:**
  - handoff artifacts, compaction or reset per model, re-testing the harness on a model change,
    planner and evaluator, cheap checks first (F-23);
  - OS sandbox and credential proxy (F-22);
  - tool design for agents (workflow tools, readable ids, pagination); a stable prompt prefix (F-24).
- **X10 OpenViking:**
  - a context database server (F-19);
  - summaries at several sizes for one item (F-20);
  - offline is possible with explicit config, but the licence is still AGPL and the defaults are
    insecure (F-54).
- **X11 Blazing Transcribe:** see §13 (F-25…F-30).
- **X12 / X13 / X14:** see §4 (F-40…F-52).
- **X15 ricky0123/vad:** Silero v5/v6 in the browser via onnxruntime-web (F-34).
- **X16:** see §12 and §13 (F-25…F-28, F-36, F-38).

## 6. Cross-project patterns

1. **Every agent project ships its own loop and its own model calls:**
   - Browser Use, Fury, OpenViking, qmd and K-Dense scripts;
   - Blazing's cloud clean-up.

   In Archeus each would be a second router or orchestrator (ADR-0041 §6, ADR-0048). The
   reusable layer is always the *primitive* underneath: CDP calls, UIA calls, a VAD, an STT
   runtime.
2. **Installers write into users' agent homes:**
   - AgentMemory hooks;
   - OpenViking plugins;
   - Windows Harness `install-skill`;
   - Diagram Design packaging.

   That is the mechanism by which XR-1 becomes real for any Archeus user (ADR-0049).
3. **Telemetry on by default:** Browser Use, Browser Harness, Windows Harness, and Blazing's
   release builds. No researched project is telemetry-free by construction except the speech
   runtimes.
4. **Silero VAD is the de-facto voice detector:**
   - Blazing (via the whisper.cpp C API);
   - faster-whisper, sherpa-onnx, NeMo-Speech.cpp, onnx-asr;
   - the browser via X15.
5. **Interruption is first-class wherever output streams:** Fury, Blazing and Browser Use.
6. **No project has an approval step before tool execution, provenance on injected context,
   per-project memory isolation, or notifications.** Archeus already has the first three by
   design (ADR-0007, ADR-0012, ADR-0046); notifications are P20.
7. **The split between capture and recognition repeats:**
   - Blazing: device-local, both halves in one app;
   - `web-whisper`: browser VAD, local server STT;
   - Jarvis: one process.

## 7. Archeus comparison — every finding classified

**Classes:**
- ALREADY IMPLEMENTED (AI);
- ALREADY DECIDED / PRESERVED (AD);
- V1 FOUNDATION (V1F);
- V1.x;
- V2 / POST-V1 (V2);
- REFERENCE ONLY (REF);
- REQUIRES DECISION (RD);
- REJECTED / DO NOT ADOPT (REJ);
- NEEDS VERIFICATION (NV).

**Column key:** "ADR?" says whether the finding becomes or affects an ADR; "Backlog" names its §20 item.

| F | Source | Finding | Evidence | Archeus anchor | Archeus status | Class | Phase | ADR? | Backlog |
|---|---|---|---|---|---|---|---|---|---|
| 1 | CLI; X3, X4, X7, X10 installers | Executions inherit the hooks, plugins, skills, MCP servers, permissions and CLAUDE.md of the settings sources they run under: the account home (`CLAUDE_CONFIG_DIR`), plus the project and local sources. Archeus's own `--settings` hook is beside them. *(Corrected 2026-10-03: Archeus's legacy hooks already stand down via the P0.5 `ARCHEUS_EXECUTION_ID` guard; project and local sources are in scope)* | [A] `archeus/harnesses/claude_code/adapter.py:104-133`; [CLI] `--setting-sources`, `--strict-mcp-config`, `--disable-slash-commands`; `--bare` reads no OAuth | ADR-0047 (basis), 0007, 0019, 0045 §12, 0046 | built; unrecorded | **RD** (XR-1) | P20 | **ADR-0049 (OPEN)** | PV-10 |
| 2 | X2 | CDP primitives with no model calls as a future `browser` capability provider | [S] | ADR-0037 §2 (`browser`, PROPOSED) | not built | **V2** | after ADR-0037 + XR-2 | no (amends 0037 when decided) | PV-7 |
| 3 | X1 | `Agent` loop | [S] | ADR-0004, 0006, 0041 §6, 0043, 0048 | — | **REJ** | — | ADR-0050 §6 | — |
| 4 | X1 | DOM/a11y snapshot; `allowed_domains`; `sensitive_data` placeholders | [S] | XR-2 inputs | — | **REF** | — | no | PV-7 |
| 5 | X1 | Domain filter covers navigation only | [S] | XR-2 | — | **REF** (evidence) | — | no | PV-7 |
| 6 | X1, X2, X3, X11 | Telemetry on by default | [S] | ADR-0035 (data handling) | Archeus sends none [I] | **RD** (XR-9) | before adopting any component | no | PV-14 |
| 7 | X1 | `profile-use` cloud cookie sync | [S] | credential boundary | — | **REJ** | — | no | — |
| 8 | X3 | Windows desktop control (UIA, SendInput, PrintWindow, PowerShell) | [S] | no capability word exists (ADR-0037 has `browser`, `fs_read` only) | — | **RD** (XR-6) | V2 | no (amends 0037 when decided) | PV-6 |
| 9 | X6, X7 | Agent Skills format, staged loading | [S] | orchestration reconciliation §25; V1.x-O5 | direction decided | **V1.x** | V1.x-O5 | no | PV-8 |
| 10 | X6, X8 | Third-party skills that run scripts, install packages, use credentials | [S] | §25; ADR-0007, 0041, 0048 | — | **RD** (XR-3) | V1.x-O5 | no | PV-8 |
| 11 | X6, X7 | Skill CI scanning; per-skill version, compatibility, `last-reviewed`; multi-host packaging | [S] | legacy `skillscan.py`; O5 | legacy only | **V1.x** | V1.x-O5 | no | PV-8 |
| 12 | X7 | `self_check` output contract | [S] | — | — | **REF** | — | no | — |
| 13 | X6 | Scientific skills as content | [S] | O5 content | — | **REF** | — | no | — |
| 14 | X8 | Offensive dual-use skills | [S] | ADR-0007 | — | **REJ** | — | no | — |
| 15 | X4 | Memory store, injection, hooks | [S] | ADR-0012, 0019, 0046 | — | **REJ** | — | no | — |
| 16 | X4 | `untrusted` marker; nudge-to-record hook | [S] | ADR-0012 lifecycle | richer already | **REF** | — | no | — |
| 17 | X5 | Vector + rerank retrieval, GGUF downloads | [S] | ADR-0012; plan §33 Q12 | deferred | **REJ** (V1) | — | no | — |
| 18 | X5 | DNS-rebinding origin guard | [S] | `tests/v1/integration/test_api_auth.py` | Host + cross-site + token | **AI** | — | no | — |
| 19 | X10 | Context database as a dependency or service | [S] | ADR-0003, 0012, 0019, 0041/0048; AGPL | — | **REJ** | — | no | — |
| 20 | X10 | Summaries at several sizes for one item | [S] | ADR-0012, 0022, 0047 §6 | not built | **NV** (XR-5: measure first) | after P21 data | no | PV-9 |
| 21 | X4, X10 | Model-extracted memory | [S] | context-and-knowledge §3 (CANDIDATE) | decided | **AD** | — | no | — |
| 22 | X9 | OS-level filesystem / network sandbox; credential proxy | [D] | ADR-0007; `archeus/core/execution/manager.py` credential handling | credential half built; OS sandbox not in any phase text | **NV** (is it in P20?) | P20 / P24 | no | PV-13 |
| 23 | X9 | Handoff artifacts; reset per model; re-test on model change; planner/evaluator; cheap checks first | [D] | P12, ADR-0034, 0047, 0031, 0039, 0040 | built or decided | **AD** | — | no | — |
| 24 | X9 | Tool design for an MCP server; stable prompt prefix | [D] | plan §33 Q13 | deferred | **V2** | post-V1 | no | PV-17 |
| 25 | X11, X16 | Silero VAD as the detector | [S] | ADR-0042 §7; plan §33 Q6 | voice deferred | **V2** | post-V1 | no | PV-1, PV-2 |
| 26 | X16 | whisper.cpp: first-class Windows binaries; VAD C API | [S] | same | — | **V2** (benchmark) | post-V1 | no | PV-1 |
| 27 | X11, X16 | Parakeet TDT v3 via sherpa-onnx / onnx-asr / NeMo-Speech.cpp | [S]/[D] | same | — | **V2** (benchmark; CC-BY attribution) | post-V1 | no | PV-1 |
| 28 | X16 | Parakeet realtime EOU 120M | [D] | same | — | **REF** (no Windows path; NOTICE file and termination clauses) | — | no | — |
| 29 | X11 | Endpointing design: adaptive silence 50–350 ms, pre-speech audio, 14 s forced split, split at the quietest point, generation guard, warm-up, keep-warm | [S] | voice | — | **REF** (parameters to benchmark) | — | no | PV-1, PV-2 |
| 30 | X11 | Blazing as an application or engine | [S] | — | macOS-only | **REJ** | — | no | — |
| 31 | X11, X14, X15 | Where speech becomes text | [S]/[A] | ADR-0042 §7, 0003, 0011, 0035 | undecided | **RD** (XR-4) | post-V1 | ADR-0050 §8–9 frames it | PV-2 |
| 32 | — | `Message` has no input-modality field, which ADR-0042 §7 requires | [A] `archeus/core/domain/entities.py:575-590` | ADR-0042 §7 | missing | **RD** (XR-7: timing) | V1 foundation or with voice | no | PV-3 |
| 33 | X16 | Browser capture via `getUserMedia` (secure context: loopback, HTTPS tunnel) | [D] | ADR-0010, 0011 | — | **NV** (QtWebEngine permission handling) | post-V1 | no | PV-2 |
| 34 | X15 | Silero VAD in the SPA via onnxruntime-web (WASM) | [S] | CSP `script-src 'self'` with no `'wasm-unsafe-eval'` (`archeus/api/auth.py:40`) | conflicts as configured | **RD** (XR-4, its CSP part) | post-V1 | no | PV-2 |
| 35 | X14 | `web-whisper`: client VAD → local server Whisper | [S] | XR-4 option B | — | **REF** (evidence; its `0.0.0.0` / `debug=True` server is a counter-example) | — | no | PV-2 |
| 36 | X16 | onnxruntime 1.30 / onnxruntime-directml have no Windows wheels for Python 3.10 | [S] | `pyproject.toml` supports 3.10 | — | **NV** | before PV-2 | no | PV-1 |
| 37 | X16 | Python's stdlib cannot record audio on Windows (`winsound` plays only) | [D] | ADR-0003 | — | **AD** (speech stays out of Core) | — | ADR-0050 §9 | — |
| 38 | X16 | Wake word: openWakeWord models non-commercial; Porcupine needs a key | [D] | ADR-0042 §7 requires no wake word | — | **RD** (XR-10, non-blocking) | post-V1 | no | PV-5 |
| 39 | X14 | Clap detection as non-speech activation | [S] | XR-10 | — | **REF** | — | no | — |
| 40 | X13 | UI events separate from transcript events | [S] | ADR-0009 (ids-only events), 0015 | built differently | **AI** | — | no | — |
| 41 | X13 | Interrupt or cancel a streamed turn, keeping the partial | [S] | conversation / voice | executions stop; nothing interrupts a spoken reply | **V2** (XR-8) | post-V1 | ADR-0050 §4 | PV-4 |
| 42 | X13 | Tool-call healing: executes tool-call markup found in plain model text | [S] | ADR-0042 §6, 0022 | — | **REJ** | — | ADR-0050 §6 | — |
| 43 | X13 | Its own agent loop; an unsandboxed bash tool | [S] | ADR-0006, 0022, 0037, 0007 | — | **REJ** (as a Core loop) | — | ADR-0050 §6 | — |
| 44 | X13 | History compaction | [S] | ADR-0047 §6 | no compaction by Archeus | **REJ** | — | ADR-0050 §7 | — |
| 45 | X13 | Retry a 429 only before the first streamed byte; raise mid-stream errors, never truncate | [S] | ADR-0022 own calls | retry policy not stated | **REF** | — | no | PV-12 |
| 46 | X13 | Local-model accommodations (`extra_body`, thinking flag, `<think>` split) | [S] | harness adapters | not applicable (CLIs) | **REF** | — | no | — |
| 47 | X13 | Sentence-boundary stream feeding TTS | [S] | voice output | — | **V2** | post-V1 | no | PV-4 |
| 48 | X12 | Half-duplex loop: mic muted while speaking | [S] | voice | — | **REF** (echo-avoidance baseline; full duplex needs echo cancellation) | — | no | PV-4 |
| 49 | X12 | "Sir" persona, beep, Iron Man framing | [S] | rulebook copy rules (R8: state sentence, no greeting) | — | **REJ** | — | no | — |
| 50 | X12 | `torch.load` without `weights_only`; pickle loads | [S] | — | — | **REJ** | — | no | — |
| 51 | X14 | `spotify-cli`: a narrow, typed integration "for you and your agent" instead of desktop automation | [S] | ADR-0037 capabilities; ADR-0050 §6 | — | **REF** (principle: narrow integrations before pixel control); its plaintext token file conflicts with P20's DPAPI path | — | ADR-0050 §6 | PV-6 |
| 52 | X14 | Cloud character API (Carter) as the assistant brain | [D] | ADR-0041 §6, 0035 | — | **REF** | — | no | — |
| 53 | all | No project provides notifications, scheduling or automation with approvals | [S] | ADR-0020; P20 push | automations built | **AD** | — | no | PV-15 |
| 54 | X10 | Offline possible with explicit config | [D]/[S] | — | — | **REJ** (still AGPL, a vector store, models outside the router) | — | no | — |
| 55 | X1 | `browser-use-core`: optional extra; MIT source | [S] | — | phase-1 "probably proprietary" withdrawn | **REF** | — | no | — |
| 56 | X6 | Scanner CRITICALs are false positives; three real residual risks | [S] | XR-3 | — | **REF** (evidence) | — | no | PV-8 |

## 8. Findings already represented in Archeus

F-18, F-21, F-23, F-37, F-40 and F-53, plus the following, which Archeus already does more
strongly than any researched project:
- knowledge with provenance and a lifecycle (ADR-0012);
- a single SQLite writer with an outbox (ADR-0002);
- approvals bound to `action_hash`;
- routing, budgets and the ledger (ADR-0005, 0033, 0041, 0048);
- capability removal (ADR-0007);
- the deterministic grammar (ADR-0042);
- "nothing is flattened" continuity (legacy-context-migration §25.11) instead of summary compaction;
- the local API defence: Host check, cross-site rejection, token.

## 9. New V1 foundations

**None is added to a V1 phase by this research.** Two items are V1-adjacent:
- **XR-1 / ADR-0049** concerns V1 as built. P20 ("Security and trust hardening") is the nearest
  owner [I]. The decision is the user's, and observing the behaviour requires a real model call
  gated by ADR-0021.
- **XR-7** asks whether the `Message.modality` column ADR-0042 §7 already requires should land as
  a cheap V1 foundation, to avoid a later migration. **Recommendation: no.** V1 has one modality,
  and the field can land with its first writer. The trade-offs are in §21, and the decision is
  the user's.

## 10. V1.x opportunities

| Item | Phase | Source |
|---|---|---|
| Skills as offers, with a trust model and CI scanning | V1.x-O5 (already planned); needs XR-3 | F-9, F-10, F-11, F-56 |
| Multi-size derived summaries, only if P21 data shows context assembly truncating useful material | V1.x (after P21 measurement); XR-5 | F-20 |
| Own-call retry rule "retry before the first streamed byte, raise mid-stream" | V1.x, if own calls ever stream | F-45 |

## 11. V2 / post-V1 architecture

The rest of the opportunities are post-V1. They are mapped in **"Archeus V1.x / V2 Architecture
Opportunities"** below and backlogged in §20.

---

## Archeus V1.x / V2 Architecture Opportunities

Areas appear only where the research supports them. Long-running missions, verification,
handoffs, the model catalogue and evaluation, and evidence-informed routing got no new evidence
here beyond what ADR-0031…0040 already decide, so they are not listed.

Every block uses the same fields:
- **Purpose**
- **User-facing**
- **Components**
- **Prerequisite ADRs**
- **V1 dependencies**
- **Phase dependencies**
- **Core / API / client changes**
- **Security**
- **Data and provenance**
- **Migration**
- **New harness**
- **Model / evaluation infrastructure**
- **Measure before adoption**

### O-V1 Voice input (speech → text → the existing conversation)
- **Purpose:** talk to Archeus as you type to it.
- **User-facing:** push-to-talk (global hotkey in the desktop shell; a button in the SPA/PWA). A
  live transcript appears in the composer and is sent as a normal message.
- **Components:**
  - audio capture (sounddevice/WASAPI natively, or `getUserMedia` in the SPA);
  - VAD (Silero);
  - endpointing (Blazing's design as parameters);
  - a local STT runtime (whisper.cpp, sherpa-onnx, onnx-asr or NeMo-Speech.cpp, chosen by PV-1);
  - the transcript posted to `POST /v1/conversations/{id}/messages`.
- **Prerequisite ADRs:** ADR-0050 (PROPOSED); XR-4 decided; ADR-0042 §7 (DECIDED).
- **V1 dependencies:** the conversation pipeline (P19), the SPA (ADR-0011), the PWA tunnel
  (ADR-0010, PROPOSED).
- **Phase dependencies:** after P26; P20's threat model must cover a microphone-holding component.
- **Core / API / client changes:**
  - Core: `Message.modality` (XR-7);
  - API: the existing message command takes `modality`;
  - client: capture UI, plus VAD if XR-4 picks option B.
- **Security:**
  - The microphone is a sensor. Capture is user-initiated, visible while active, and never
    starts from an automation.
  - Audio never leaves the device unless a decided provider rule (ADR-0035) allows it.
  - Spoken text is a user message, so approvals and destructive confirmations stay non-voice
    (ADR-0042 §7).
  - Option B requires a CSP change (`'wasm-unsafe-eval'`): a deliberate security decision.
- **Data and provenance:**
  - the message records modality, plus the STT engine and version (provenance like any
    `source_kind`);
  - raw audio is not retained by default (XR-4 privacy rule).
- **Migration:** one nullable column on `messages` (XR-7).
- **New harness:** no. STT is not a harness and not an own call (ADR-0050 §8).
- **Model / evaluation infrastructure:** a speech benchmark (PV-1), not the LLM evaluation of
  ADR-0039.
- **Measure before adoption:** the PV-1 matrix (§13).

### O-V2 Voice output and barge-in
- **Purpose:** hear replies and Attention items.
- **User-facing:** replies spoken as they arrive; saying or pressing "stop" silences them.
- **Components:**
  - local TTS (not researched in depth; MeloTTS in Jarvis is macOS-oriented);
  - a sentence-boundary chunker (Fury pattern);
  - echo handling (half-duplex first, as in Jarvis).
- **Prerequisite ADRs:** ADR-0050 §3–§4; XR-8.
- **V1 dependencies:** none beyond the conversation reads.
- **Phase dependencies:** after O-V1.
- **Core / API / client changes:** client only. TTS speaks text Core already returned. Stopping
  speech is client-local and does not stop work.
- **Security:** never speaks content the screen would not show (no hidden reasoning; P16 §18.1 r8).
- **Data and provenance:** none new.
- **Migration:** no.
- **New harness:** no.
- **Model / evaluation infrastructure:** TTS latency and quality benchmark.
- **Measure before adoption:**
  - time to first audio;
  - interruption latency;
  - CPU while speaking.

### O-J Jarvis-style presence
- **Purpose:** an always-available assistant feel on Windows.
- **User-facing:**
  - a tray icon showing the mark's state (ADR-0027);
  - a global hotkey to talk;
  - spoken Attention items when the user opts in.
- **Components:** Qt shell tray and hotkey (the shell attach is P19 S7); the existing `/v1/status`
  live derivation (R7) and Attention.
- **Prerequisite ADRs:** ADR-0050; ADR-0027 (DECIDED); ADR-0020 (DECIDED) for anything proactive.
- **V1 dependencies:** `/v1/status`, Attention, automations.
- **Phase dependencies:** after O-V1; push from P20 (Q-B5).
- **Core / API / client changes:** client only.
- **Security:** proactive speech only from Attention items or decided automations; the assistant
  originates no action (ADR-0050 §5).
- **Data and provenance:** none new.
- **Migration:** no.
- **New harness:** no.
- **Model / evaluation infrastructure:** none.
- **Measure before adoption:** idle CPU and wakeups of the tray process (the idle invariant
  applies, R1).

### O-D Desktop / computer control
- **Purpose:** let an execution operate Windows applications the way a `browser` capability
  operates pages.
- **User-facing:**
  - a mission step "do X in app Y" runs under approval;
  - while it runs, input takeover is visible and interruptible.
- **Components:**
  - a harness declaring a new capability (XR-6);
  - UI Automation reads before SendInput writes;
  - PowerShell only through policy;
  - narrow typed integrations preferred over pixel control (F-51).
- **Prerequisite ADRs:** ADR-0037 decided; XR-6; ADR-0007 policy action classes; ADR-0050 §6.
- **V1 dependencies:** policy engine (P9), approvals, capability removal.
- **Phase dependencies:** after ADR-0037 is implemented (P22); P20/P24 threat model.
- **Core / API / client changes:**
  - Core: a capability word and a policy action class;
  - client: a visible "Archeus is using your desktop" state and an interrupt control.
- **Security:**
  - SendInput takes the foreground: the user's own input collides with it;
  - PowerShell is arbitrary code;
  - screenshots capture whatever is on screen, including secrets;
  - Windows Harness writes into agent homes (XR-1) and has telemetry (XR-9).
- **Data and provenance:** screenshots and UIA trees are execution artifacts under the data class.
- **Migration:** no.
- **New harness:** yes (a desktop harness, or a capability on an existing one).
- **Model / evaluation infrastructure:** capability evidence per task family (ADR-0032).
- **Measure before adoption:**
  - task success on a fixed Windows suite;
  - false-click rate;
  - foreground-collision handling.

### O-B Browser / computer-use harness
- **Purpose:** the `browser` capability that ADR-0037 names.
- **User-facing:** web tasks inside missions.
- **Components:** CDP primitives (X2 shape); an isolated profile; a request-level domain filter.
  X1's filter is navigation-only (F-5), so the request-level filter has to be built.
- **Prerequisite ADRs:** ADR-0037; XR-2.
- **V1 dependencies:** policy (`web` allowed by default in `rules.py`, which XR-2 must revisit).
- **Phase dependencies:** P22 (descriptor) at the earliest; no V1 phase owns a browser harness.
- **Core / API / client changes:** a policy action class; the descriptor word exists.
- **Security:**
  - never the user's real profile;
  - credentials only as placeholders (F-4);
  - telemetry off and verified (XR-9).
- **Data and provenance:** page content is untrusted input; text from it is never a command
  (ADR-0042 §6).
- **Migration:** no.
- **New harness:** yes.
- **Model / evaluation infrastructure:** ADR-0039 suites.
- **Measure before adoption:**
  - the domain-filter escape tests;
  - profile isolation.

### O-S Skills
Already V1.x-O5. The research adds a trust model (XR-3) and CI scanning with per-skill review
metadata (F-11). Nothing else changes.

### O-M Memory and knowledge
ADR-0012 stands. The only open item is XR-5: measure whether context assembly truncates useful
material after P21, before any derived summaries exist. Rejected here:
- vector, semantic and reranked retrieval (F-17);
- external memory stores (F-15, F-19).

### O-C Execution context provenance (evidence and provenance)
- **Purpose:** know exactly what context an execution ran with.
- **Components:** ADR-0049's options (exclude, record or both).
- **Phase:** P20.
- **Security:**
  - a third-party hook in an account home runs inside every Archeus execution on that account;
  - whether a user PreToolUse hook can widen Archeus's own deny is not established.
- **Measure:** one observed execution with an inventory of the loaded sources (needs ADR-0021).

### O-SEC Security, sandboxing and credential boundaries
- **OS sandbox (F-22):** check whether P20 includes one (XR-13; study PV-13). Windows options were not
  researched in this pass: AppContainer, Job objects, Windows Sandbox.
- **Credentials:**
  - Archeus's credential handling is stronger than every researched project;
  - adopted components must not keep plaintext token files (F-51) or sync profiles (F-7).
- **Telemetry (XR-9):** a component is adoptable only with telemetry off and verified (PV-14).

### O-N Notifications and proactivity
No researched project provides notifications. Spoken notifications are a rendering of P20 push
and Attention items (O-J).

### O-R Mobile and remote control
- Voice from the PWA is possible over the HTTPS tunnel (ADR-0010), since `getUserMedia` needs a
  secure context.
- That rests on XR-4 option B and the CSP decision.
- Nothing researched offers more.

### O-MCP Archeus as an MCP server
Plan §33 Q13 (DEFERRED). X9's tool-design guidance (workflow-shaped tools, readable ids,
pagination) is the input when it is scheduled (PV-17).

---

## 12. Windows-specific opportunities

| Topic | Confirmed on Windows (CI or official binaries) | Theoretically portable | Linux/macOS only | Unverified |
|---|---|---|---|---|
| STT runtimes | whisper.cpp (MSVC CI; CPU, OpenBLAS, CUDA 11.8/12.4, ARM64 downloads); sherpa-onnx (wheels incl. Python 3.10, CUDA archives); NeMo-Speech.cpp (CPU/CUDA/Vulkan downloads, Windows CI, very young: v0.1.0 2026-08-19); onnx-asr (Windows CI 3.10–3.14); CTranslate2 (Windows CI and wheels) | faster-whisper (its own CI is Ubuntu only); whisper.cpp Vulkan / OpenVINO (build docs only) | NeMo toolkit; Blazing (CoreML/ANE); Jarvis (MLX) | DirectML for any of them; whisper.cpp's streaming example on Windows; pywhispercpp exposing the VAD API |
| Models | Parakeet TDT v3 int8 is downloadable for sherpa-onnx (Parakeet itself not exercised in Windows CI) | Parakeet v3 via onnx-asr and NeMo-Speech.cpp | Parakeet EOU 120M (`.nemo` only) | community ONNX ports of EOU |
| VAD | Silero (Windows CI, manual dispatch) | Silero in the browser (X15, WASM) | — | X15 inside QtWebEngine |
| Audio capture | sounddevice (Windows wheels bundle PortAudio with WASAPI) | `getUserMedia` in Chromium | — | QtWebEngine microphone permission handling; WASAPI device swaps and Bluetooth headsets |
| Endpointing / latency | — | Blazing's parameters | — | every latency figure (Blazing's ~530 ms is unmeasured by its own audit) |
| GPU / CPU | CUDA optional everywhere, required by nothing listed | — | — | consumer-hardware numbers (the only Windows figures are on a Ryzen 9800X3D and an i7-12700K + RTX 3070 Ti [D]) |
| Packaging | — | — | — | onnxruntime 1.30 / -directml wheels for Python 3.10 (F-36) |
| Wake word | Porcupine lists Windows (needs a key) | openWakeWord (onnxruntime) | — | — |
| TTS | — | — | MeloTTS on `mps` in Jarvis | any Windows TTS (not researched) |
| Global hotkeys, tray | — | Qt (`QSystemTrayIcon`); Win32 `RegisterHotKey` [I] | Blazing's CGEventTap / AppKit | not researched in this pass |
| Desktop automation, accessibility, clipboard, window management | Windows Harness (UIA via `uiautomation`, SendInput, PrintWindow, PowerShell), alpha | — | Blazing's CGEvent typing | Windows Harness behaviour (never run) |
| Browser automation | X1 install CI on Windows; X2 has Windows branches | — | X1 functional CI is Linux only | X1 behaviour on Windows |
| Process launching | Archeus already: `proc.py`, `CREATE_NO_WINDOW` for headless runs [A] | — | — | — |
| Credential isolation | Archeus P20 DPAPI path [A] | — | — | — |
| Sandboxing | — | — | — | AppContainer, Job objects, Windows Sandbox (not researched) |
| Remote / mobile | Archeus PWA over an HTTPS tunnel (ADR-0010, PROPOSED) [A] | — | — | — |

**No WSL, Docker or Linux is needed** for whisper.cpp, sherpa-onnx, NeMo-Speech.cpp, onnx-asr,
CTranslate2 or Silero. K-Dense skills expect WSL2.

## 13. Voice / STT implications

**The Blazing baseline (phase 1, unchanged; not redone):**
- Silero VAD through the whisper.cpp C API;
- adaptive endpointing;
- splitting at the quietest point;
- the generation guard;
- warm-up and keep-warm;
- Parakeet TDT v3 as a possible model;
- the EOU 120M licence;
- Windows vs macOS;
- where speech becomes text (XR-4);
- the missing modality field (XR-7);
- voice is post-V1.

**What this pass adds:**
1. **Browser-side VAD exists and is maintained** (X15, ISC, Silero v5/v6 ONNX). It turns XR-4
   option B into a concrete design:
   - the SPA captures and segments;
   - only speech segments reach a local STT process;
   - nothing native is needed for capture or VAD.

   It also sidesteps the onnxruntime Python 3.10 wheel gap (F-36) for the VAD half.
2. **That option needs a CSP change.** Chromium requires `'wasm-unsafe-eval'` in `script-src` to
   compile WebAssembly, and Archeus's CSP has `script-src 'self'` only (`archeus/api/auth.py:40`).
   X15's README loads onnxruntime-web from a CDN, which Archeus's CSP and offline posture also
   exclude, so the runtime would have to be vendored [I].
3. **The same split exists in Huw's `web-whisper`** (browser VAD → server Whisper over a socket).
   That confirms the shape, and it is a counter-example on hygiene: it binds `0.0.0.0` with
   Flask `debug=True`.
4. **Activation alternatives:**
   - push-to-talk needs no model;
   - openWakeWord's pre-trained models are non-commercial;
   - Porcupine needs an account key;
   - a clap classifier exists (X14), but its model ships from Google Drive.

   The default should be push-to-talk (XR-10, a recommendation).

**XR-4 options for where speech becomes text:**

| Option | Where | Pros | Cons |
|---|---|---|---|
| A. Native sidecar does capture + VAD + STT | a separate local process (not Core, ADR-0003) | works for the Qt shell and the tray without a browser; full WASAPI control | a second native process to package (Python 3.10 wheel gaps, GPU runtimes); does not help the PWA |
| B. SPA captures + VAD (X15); local STT process transcribes | browser, plus a local process | one capture path for desktop, web and PWA; only speech segments move | CSP `'wasm-unsafe-eval'`; QtWebEngine permission unverified; the PWA still needs the STT process reachable over the tunnel |
| C. External STT provider | cloud | no local compute | audio leaves the device; needs a provider rule (ADR-0035) and a terms check; bypasses the router unless modelled as a provider |

**Benchmark before adoption (PV-1):**
- **Hardware:**
  - a low-end laptop (4-core U-series, 8 GB);
  - a mainstream laptop (8-core H-series, 16 GB);
  - Snapdragon X;
  - an NVIDIA GPU with 6–8 GB;
  - an AMD or Intel GPU;
  - an NPU where a backend exists.

  CPU-only and GPU are measured separately.
- **Metrics:**
  - end of speech to final text, p50 / p95 / p99;
  - RTFx on 5 s, 30 s and 5 min clips;
  - WER and CER on a fixed set: clean, noisy, accented, developer vocabulary, and Italian;
  - cold and warm load time;
  - peak RAM and VRAM;
  - installed size;
  - VAD cost per chunk, plus false-start, false-stop and clipped-onset rates;
  - idle CPU while listening;
  - WASAPI device swaps and Bluetooth headsets;
  - Python 3.10 wheel availability;
  - for option B, the same VAD figures inside QtWebEngine and mobile Chromium.

## 14. Security / trust implications

1. **Context entering executions (XR-1, ADR-0049):** hooks, plugins, skills and MCP servers from
   the account home run inside Archeus executions. This is the only finding that touches the
   current architecture.
2. **No researched agent loop has an approval step.** Adopting any loop as shipped would bypass:
   - ADR-0007 policy;
   - `action_hash` approvals;
   - the no-command-from-content rule (ADR-0042 §6).
3. **Telemetry by default** in four projects (XR-9).
4. **Credentials:**
   - plaintext token files (F-51);
   - cloud cookie sync (F-7);
   - real-profile attachment (X2);
   - Codex credential reuse (X10).
5. **Code execution:**
   - stdin code in X2;
   - PowerShell in X3;
   - unsandboxed bash in X13;
   - pickle and `torch.load` in X12;
   - skill scripts in X6 and X8.
6. **The microphone and the screen are new sensors.** Capture and screenshots are user-initiated
   and visible, never started by an automation or a model (ADR-0050 §2, §5).
7. **The CSP is a security boundary**, so XR-4 option B is a security decision.

## 15. Memory / knowledge implications

- **ADR-0012 stands.** Every memory system researched is weaker on provenance and lifecycle:
  - AgentMemory;
  - OpenViking;
  - qmd;
  - Fury's example.
- **XR-5:** derived multi-size summaries are considered only if P21 measurement shows truncation
  of useful material. They would be own-call outputs with provenance (ADR-0022), never a second
  store.
- **No assistant-side memory (ADR-0050 §7).** A voice session's continuity is the conversation
  and mission in Core.

## 16. Routing / model implications

- **Every researched loop chooses its own model.** Archeus keeps one router (ADR-0005, 0033,
  0041, 0048).
- **Speech engines are not routed models (ADR-0050 §8).** STT, TTS and VAD run on the device and
  make no LLM call, so they are configured device components, not catalogue offers (ADR-0031). A
  *cloud* STT would be a provider subject to the data class (ADR-0035).
- **No change to the catalogue, evidence or evaluation ADRs.**

## 17. Browser / computer-use implications

- Browser: XR-2 (what `browser` requires).
- Desktop: XR-6 (a new capability).
- **Shared principles** (ADR-0050 §6):
  - capabilities live on harnesses declared through ADR-0037, never in the assistant;
  - narrow typed integrations come before pixel or UIA control;
  - the user's real browser profile is never used;
  - an input takeover is visible and interruptible;
  - telemetry is off and verified.

## 18. Mobile / remote-control implications

- **Voice from the phone:** the PWA over the HTTPS tunnel (ADR-0010) can capture with
  `getUserMedia` (a secure context). That is XR-4 option B, with STT running on the Core
  machine.
- **Nothing else new.** No researched project has a mobile client.

## 19. ADRs to create / update

| ADR | Action | Status | Why an ADR and not a backlog item |
|---|---|---|---|
| **ADR-0049** | created | **OPEN** | It concerns V1 as built (`adapter.py`), crosses three decided ADRs (0007, 0019, 0047), and has options with real trade-offs the user must choose between |
| **ADR-0050** | created | **PROPOSED** | One principle that stops every future voice, desktop or "Jarvis" proposal re-opening the orchestration model. It is derived from decided ADRs (0003, 0006, 0007, 0012, 0022, 0035, 0042, 0043, 0047) and adds the output, proactivity and device-component rules they do not cover |
| ADR-0037 | research-input note appended (decision text unchanged) | PROPOSED | XR-2 and XR-6 are inputs to deciding it; amending its decision before approval would pre-empt that decision |
| ADR-0042 §7 | research note appended (clause unchanged) | DECIDED | already requires the modality field; XR-7 is about timing only |
| ADR-0047 | pending-question note appended (decision unchanged) | DECIDED | ADR-0049's "record" option may need a basis clause here |
| ADR-0011 / CSP | no change | DECIDED | XR-4 option B would amend the CSP, but only if chosen |

**Rejected as ADRs:** browser capability, skills trust, multi-size summaries, telemetry,
activation and barge-in. Each is a decision-register entry (§21) inside an existing ADR's scope,
or a backlog item. Creating an ADR for each would be ceremony without a decision.

## 20. V1.x / V2 architecture backlog

**Moved 2026-10-03.** The backlog (now PV-1…PV-21) lives in [../architecture/ARCHEUS_V2_ASSISTANT_LAYER.md](../architecture/ARCHEUS_V2_ASSISTANT_LAYER.md) §5, which is authoritative.
The reconciliation pass added PV-18 (Windows TTS survey) and PV-19 (observe one real execution's
loaded sources). It widened PV-16 to cover tray and hotkey, and moved PV-13's scope question to XR-13.
Keeping a second copy here would let the two drift.

## 21. New decision register entries (XR-*)

**Moved 2026-10-03.** The register (now XR-1…XR-14) lives in [../architecture/ARCHEUS_V2_ASSISTANT_LAYER.md](../architecture/ARCHEUS_V2_ASSISTANT_LAYER.md) §4, which is authoritative.
Each entry carries its question, evidence, options with trade-offs, owner, phase, dependencies,
whether it blocks V1 or V2, and whether it can stay open. The reconciliation pass added XR-12
(does `browser` ship in P22 before XR-2) and XR-13 (P20's OS sandbox scope).

**Why a new prefix (kept for the record).**
- The chat-only register used D-1…D-16. The repository already uses D-1…D-12
  (`ARCHEUS_V1_ORCHESTRATION_PLAN.md` §31) and D-13…D-26
  (`ARCHEUS_V1_CONVERSATIONAL_ORCHESTRATION.md` Part H) for other decisions.
- Research D-1…D-5 became XR-1…XR-5.
- Research D-6…D-16 were P19.5 reconciliation items, not external research, so they are not
  registered here.

## 22. Rejected ideas and why

| Idea | Source | Why |
|---|---|---|
| Browser Use `Agent` loop; Fury loop as a Core loop | X1, X13 | a second orchestrator and router (ADR-0006, 0022, 0041 §6, 0043, 0048) |
| Tool-call healing | X13 | model text becomes execution with no approval (ADR-0042 §6) |
| Transcript compaction by Archeus | X13, X9 | ADR-0047 §6; continuity is the checkpoint hand-off |
| AgentMemory, OpenViking, qmd as stores | X4, X5, X10 | ADR-0012; AGPL (X10); vector store excluded in V1 |
| Cybersecurity skills | X8 | dual-use offensive content, no behaviour tests (ADR-0007) |
| `profile-use`; real-profile attachment | X1, X2 | credentials leave the machine or are exposed to automation |
| openWakeWord pre-trained models | X16 | non-commercial licence |
| Jarvis or Fury code | X12, X13 | no licence (all rights reserved): ideas may be studied, no code copied; Jarvis is also macOS-only |
| Blazing as an application or engine | X11 | macOS-only |
| Persona copy ("Sir", greetings) | X12 | the rulebook's copy rules (no greeting; state sentence from counts) |
| Loading models via pickle or `torch.load` without `weights_only` | X12, X14 | arbitrary code execution on load |

## 23. Unverified claims requiring future investigation

- **XR-1:** the inheritance is documented by the CLI, not observed. It needs one real execution,
  which ADR-0021 gates. Not established: whether a user PreToolUse hook can widen Archeus's deny;
  whether `UserPromptSubmit` hooks (e.g. legacy recall) fire for `-p` runs [I].
- **The huwprosser.com posts:** unreadable (client-rendered).
- **Every latency figure:** Blazing's, and all Windows STT on consumer hardware (PV-1).
- **The QtWebEngine side:** microphone permission handling, and WASM VAD performance inside the
  shell (PV-16).
- **onnxruntime wheels for Python 3.10 on Windows (F-36).**
- **Runtime details:** pywhispercpp's VAD exposure; community EOU ONNX ports; DirectML backends.
- **Windows Harness and Browser Use behaviour on Windows:** never run.
- **Windows sandboxing options (PV-13) and P20's scope (XR-13).**
- **Windows TTS options:** not researched.
- **From phase 1, still open:**
  - Browser Use: page-request filtering beyond navigation;
  - OpenViking: AGPL as a separate server;
  - `krl` provenance;
  - the OpenAI harness post (403).

## 24. Dependency graph

*Superseded 2026-10-03 by the graph in [../architecture/ARCHEUS_V2_ASSISTANT_LAYER.md](../architecture/ARCHEUS_V2_ASSISTANT_LAYER.md) §9, which adds XR-12, XR-13 and the A0/A3
sub-phases. Kept as the research-time view.*

```
inherited account customisations (CLI help; X3/X4/X7/X10 installers)
  ↓ principle: an execution's context must be known (ADR-0047 basis)
  ↓ ADR-0049 (OPEN) — XR-1
  ↓ harnesses/execution (claude_code adapter)
  ↓ P20 security and trust hardening
  ↓ prerequisite: ADR-0021 answered for one harness (to observe a real run)
  ↓ acceptance: an observed execution's loaded-source inventory matches the decided rule

Jarvis / Fury / Browser Use loops
  ↓ principle: an assistant is a client and modality, never a second loop/router/memory
  ↓ ADR-0050 (PROPOSED) — XR-11
  ↓ clients, conversation pipeline (ADR-0042 §7)
  ↓ post-V1 assistant layer (O-V1, O-V2, O-J)
  ↓ prerequisite: XR-4, XR-7, XR-8, XR-10 decided
  ↓ acceptance: grammar tests show voice messages take the same path; no approval accepted by voice

Blazing + Silero + whisper.cpp / sherpa-onnx / onnx-asr / NeMo-Speech.cpp + ricky0123/vad
  ↓ principle: speech engines are device components, not routed models (ADR-0050 §8)
  ↓ XR-4 (placement; option B needs a CSP decision)
  ↓ voice sidecar and/or SPA capture
  ↓ PV-2 (post-V1)
  ↓ prerequisite: PV-1 benchmark; PV-16 (if option B); P20 threat model
  ↓ acceptance: the §13 metrics on the hardware matrix; zero audio off-device by default

Windows Harness · Browser Harness · spotify-cli
  ↓ principle: capabilities are declared by harnesses; narrow integrations before pixel control
  ↓ ADR-0037 (PROPOSED) + XR-2 / XR-6 + XR-9
  ↓ harnesses, policy (action classes)
  ↓ P22 (descriptor), then V2
  ↓ prerequisite: policy action class; isolated profile; telemetry off; foreground-collision rule
  ↓ acceptance: domain-filter escape tests; a Windows desktop task suite under approval

Skills repos (X6, X7, X8)
  ↓ XR-3 → V1.x-O5 → PV-8 → acceptance: scan in CI; scripts never call providers outside the router

OpenViking multi-size summaries
  ↓ XR-5 → P21 measurement → PV-9 → acceptance: measured truncation of useful material before any build
```

## 25. Recommended research / architecture sequence

1. **Now, at no cost to V1:** the user decides XR-11 (approve, amend or reject ADR-0050) and
   reads ADR-0049.
2. **Before P20 starts:** decide XR-1 / ADR-0049, and decide XR-13 (whether P20 includes an OS
   sandbox).
3. **When ADR-0021 is answered for one harness:** observe one real execution's loaded sources.
   That closes XR-1's unverified part.
4. **With ADR-0037's approval (P22):** decide XR-2 and XR-9. Leave XR-6 open.
5. **Any time, as an isolated experiment with no product code:** PV-1, the Windows STT benchmark,
   plus PV-16 if option B is still on the table.
6. **After P26 (V1 release):**
   - decide XR-4, XR-7, XR-8 and XR-10 in that order;
   - then PV-2 → PV-3 → PV-5 → PV-4 → PV-15;
   - desktop (PV-6) and browser (PV-7) only after their decisions.
7. **V1.x-O5:** XR-3, then PV-8.
8. **After P21:** PV-9 (measure), and XR-5 only if the measurement shows need.

## 26. Final scope boundary — what MUST NOT enter current V1

*The architecture-level copy is [../architecture/ARCHEUS_V2_ASSISTANT_LAYER.md](../architecture/ARCHEUS_V2_ASSISTANT_LAYER.md) §8.*

- Any voice, STT, TTS, VAD, wake-word, tray or hotkey work, including the `Message.modality`
  column (unless XR-7 is decided otherwise).
- Any change to the CSP (`archeus/api/auth.py:40`).
- Any browser or desktop-control harness, capability word or policy action class beyond what
  ADR-0037 already proposes for P22.
- Any third-party skill import or execution (V1.x-O5).
- Any external memory store, vector or semantic retrieval, or derived summaries.
- Any agent loop, tool-call parsing of model text, compaction by Archeus, or model call outside
  the router, including inside a future "assistant" component.
- Any third-party component with telemetry on.
- Changes to the current P19.5 implementation, to routing, or to Core behaviour.

**The only V1-relevant item is ADR-0049 (XR-1).** It is a decision, owned by P20, and it changes
no code until decided.

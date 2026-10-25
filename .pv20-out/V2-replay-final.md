# V2 Replay & Recovery handoff — 2026-10-25

Implemented fixture prototype; runtime verification pending Claude. No commit, network,
Python, Node or browser execution. No deliberate account-home or credential-store reads.
Git emitted a denied-access warning for its automatic global ignore lookup during status.
Design was written before prototype edits, under 200 lines.

## Files changed

- `.pv20-out/V2-replay-design.md`: evidence limits, placement, controls, recovery and acceptance.
- `clients/v2-prototype/app.js`: 13 shared fixture entries, cursor, source details,
  proposal binding/draft gate, simulated receipt, terminal text and keyboard paths.
- `clients/v2-prototype/index.html`: native scrubber, step controls, recovery proposal card,
  editable draft, live status, timeline disclosure, fixture/gap labels.
- `clients/v2-prototype/style.css`: Replay-only inspector/phone sheet and target sizing;
  monochrome terminal Replay. Existing text weights unchanged.
- `clients/v2-prototype/check.mjs`: static fixture/control/source/safety assertions;
  obsolete invented-evidence assertions replaced with recorded vocabulary.
- `clients/v2-prototype/sw.js`: shell cache version bumped.
- `clients/v2-prototype/README.md`: Replay paths, limitations and keys.
- `tools/v2_replay_probe.py`: Playwright acceptance probe modeled on chatbar/hit probes.
- `.pv20-out/V2-replay-final.md`: this handoff.

The two requested `.pv20-out` artifacts are explicit exceptions to the prototype-only scope.
No backend, state machine, API, isolation, credential, existing probe or production file edited.

## Decisions

Replay stays a Mission inspection mode under project context; existing route retained.
Back returns to Mission. Existing constellation art remains, desktop inspector alongside it;
402 px uses scrolling sheet below scaled constellation. No existing-screen restyle or weight edits.
As-of fixture label is separate from live Mission state; no historical filesystem reconstruction.
Thirteen authored rows include process exit success, failed verification, separate execution LOST
and blocked Mission. Entries name their row/transition evidence and derived category.
No fabricated external-response event, starting digest or operator reconciliation record.
NOT RECORDED disclosure covers evidence gaps; retained history completeness is not promised.
Resume, Retry with changes and Ask the owner create proposal cards only.
Explicit approval produces SIMULATED receipt; no execution, message or evidence mutation.
Changed cursor invalidates pending proposal. Retry requires changed instructions.
Terminal uses same fixture/cursor, static monochrome text constellation and explicit y approval.
Terminal retry/question use visible fixed drafts; graphical form permits editing.
Quiet/reduced-motion do not remove facts. No Replay autoplay/timers were added.

## Measurable checks and status

- `git diff --check`: PASS (exit 0); only normal CRLF advisory.
- Fixture entries: 13 by source inspection; >=12 asserted statically and by browser probe.
- Static facts: LOST, FAILED verification, separate execution IDs, range/step/card controls,
  mission/event binding and no-real-effects receipt. Added assertions NOT RUN.
- Browser matrix: 1440x900 and 402x900; full/reduced/Quiet; 6 cases. NOT RUN.
- Pointer scrub targets verification event 9; keyboard arrows/Home/End; both step buttons;
  disabled endpoints. Probe written, NOT RUN.
- Recovery: changed-draft requirement, approval preserving evidence, Cancel and cursor
  invalidation. Probe written, NOT RUN.
- Terminal: Mission -> p, shared 13-event cursor, proposal/cancel/approve and one text fill.
  Probe written, NOT RUN.
- New control boxes >=48 CSS px, no horizontal document overflow, constellation visible,
  console errors zero and external requests zero. Probe written, NOT RUN.
- Existing effective-hit probe remains mandatory; box checks do not prove pointer reachability.
- Physical 44 pt, real touch, keyboard/screen reader, contrast over scene, 200% zoom,
  phone safe areas/keyboard and terminal 80x24 visual QA remain manual.

## Claude commands (PowerShell; worktree root)

Use separate terminal to serve; all commands below go through shared testlock.
Do not run probes concurrently. Reuse server if 8819 already serves this worktree.

```powershell
Set-Location D:\archeus-v2-replay
py D:\Archeus\.collab\testlock.py -- py -m http.server 8819 --bind 127.0.0.1 --directory clients/v2-prototype
```

Then in probe terminal:

```powershell
Set-Location D:\archeus-v2-replay
$env:BASE = 'http://127.0.0.1:8819'
$env:OUT = 'D:\archeus-v2-replay\.pv20-out\replay-probes'
New-Item -ItemType Directory -Force -Path $env:OUT | Out-Null
py D:\Archeus\.collab\testlock.py -- node clients/v2-prototype/check.mjs
py D:\Archeus\.collab\testlock.py -- py tools/slash_probe.py
py D:\Archeus\.collab\testlock.py -- py tools/v2_chatbar_probe.py
py D:\Archeus\.collab\testlock.py -- py tools/v2_hit_probe.py
py D:\Archeus\.collab\testlock.py -- py tools/v2_replay_probe.py
```

The inspected testlock has multiple bounded slots. The server holds one slot while alive;
each sequential probe needs another eligible slot. If memory leaves only one slot eligible,
Claude should use the established server supervisor and keep every verification under testlock.
Clear/unregister an old service worker for manual inspection if shell cache appears stale.
New probe blocks service workers and aborts non-local requests; it reports attempted requests.

## Open owner questions (production only)

- Who owns Core category mapping and retained-range/source-order contract?
- Which checkpoint/reconciliation proofs permit a resume proposal, and who authorizes it?
- Should editable recovery drafts also be supported directly inside terminal text form?
- What retention/evidence detail may appear on phones without hiding uncertainty?

None requires a real-world action in this fixture. Stop after handoff; Claude owns probes.

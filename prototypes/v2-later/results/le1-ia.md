# LE-1: the three places vs V1's structure, and the responsive desktop (2026-10-05)

**Result: B and C beat V1's structure on every one of the eight questions, on every device, on
the structural proxy. C's extra panes do not make answers faster than B; they keep the evidence
beside the decision. The human 5-second test (H-1) is the gate and has not been run.**

Lab: `lab/ia.html?v=a|b|c` (A = V1's structure, a replica calibrated against the real V1
capture; B = the three places; C = B with the container-driven desktop composition). Probe:
`tools/ia_probe.py` → `results/le1/probe.json`; captures `results/le1/shots/` (every variant ×
device × route) and `results/le1/env/` (light, high contrast, forced colours, 200 % text).

## 1. The measure, and what it is not

For each question the probe starts on Now and walks the **best route each variant offers**
(`window.PATHS` in `ia.js`; for A, the route V1 actually has), then measures **clicks**,
**scroll** needed to bring the answer fully on screen (above any fixed bottom chrome), and
**words read** before the answer within its pane. "Any" questions (Q1, Q2, Q7, Q8) are answered by
the first element carrying the answer; "all" questions (Q3 needs-you list, Q5 everything running,
Q4, Q6) need every element. It is a **proxy for effort, not time-on-task.**

## 2. Results — clicks / scroll px / words before the answer

| Question | A desk 1,440 | B desk | C desk | A phone 390 | B phone | A small 360 | B small |
|---|---|---|---|---|---|---|---|
| Q1 What is Archeus doing? | 2 / 0 / 33 | **0 / 0 / 9** | **0 / 0 / 9** | 2 / 0 / 33 | **0 / 0 / 9** | 2 / 0 / 33 | **0 / 0 / 9** |
| Q2 Which mission / project? | 2 / 0 / 0 | **0 / 0 / 9** | **0 / 0 / 9** | 2 / 0 / 0 | **0 / 0 / 9** | 2 / 0 / 0 | **0 / 0 / 9** |
| Q3 What needs me? | 0 / **785** / 12 | 0 / 0 / 29 | 0 / 0 / 29 | 0 / **1,842** / 12 | 0 / 0 / 29 | 0 / **2,072** / 12 | 0 / 0 / 29 |
| Q4 What happened today? | 1 / 0 / 111 | 0 / 0 / 192 | 0 / 0 / 184 | 1 / 313 / 111 | 0 / 288 / 162 | 1 / 483 / 111 | 0 / 410 / 162 |
| Q5 What is running? | 0 / **918** / 250 | 0 / 0 / 109 | 0 / 0 / 101 | 0 / **2,017** / 250 | 0 / 7 / 95 | 0 / 2,247 / 250 | 0 / 129 / 95 |
| Q6 What changed? | 0 / **1,192** / 278 | 1 / 168 / 210 | 1 / 200 / 202 | 0 / **2,321** / 278 | 1 / 636 / 180 | 0 / 2,605 / 278 | 1 / 794 / 180 |
| Q7 Why did it stop? | **3** / 0 / 33 | 0 / 0 / 161 | 0 / 0 / 153 | **3** / 0 / 33 | 0 / 211 / 137 | **3** / 0 / 33 | 0 / 333 / 137 |
| Q8 Where is the evidence? | **3** / 0 / 33 | 1 / 0 / 52 | 1 / 0 / 194* | **3** / 0 / 33 | 1 / 42 / 54 | **3** / 0 / 33 | 1 / 253 / 54 |

Q1, Q2, Q7, Q8 shown from the first probe run; the any/all correction (§1) only lowers B's scroll
on Q1/Q2 at 360 px. *C's Q8 words count the list pane's words, because the evidence opens in the
inspector beside it; reading the inspector alone it is ≈ 50.*

Reading it:

- **V1 cannot answer Q1 or Q2 from Now at all** (its row status line is empty — V1 defect V-1 —
  and the project is never on a row): 2 clicks each, into the mission page and then the project
  page. B and C answer both in the first sentence under the verdict.
- **V1 answers Q3, Q5, Q6 only after a long scroll**: on the phone, 1,842 / 2,017 / 2,321 px — two
  to three screens. B answers Q3 and Q5 on the first phone screen.
- **V1 needs 3 clicks for Q7 and Q8** (Work → the mission → the Evidence tab). B answers Q7 on Now
  ("blocked because check “rollback” failed (exit 1)") and Q8 one click away.
- **Q4 ("what happened?") is the one question where B costs more words** than V1's Work page
  (162–192 vs 111): B answers it on Now, below the decisions and the running work, which is the
  intended order. On the phone it needs a 288 px scroll.
- **C vs B:** identical on the proxy. C's value is not speed but **co-presence**: at 1,440 the
  first decision is open beside the list ("what needs me" and "what will happen if I approve" on
  one screen) and at 1,920 the because-chain and checks sit in the inspector without a click
  once a mission is selected.

## 3. Screens

| Screen | A desk | B desk | C desk | A phone | B phone |
|---|---:|---:|---:|---:|---:|
| Now height (px) | 2,372 (2.6 screens) | 900 (1.0) | 900 (1.0) | 4,336 (5.1) | **1,206 (1.4)** |
| Now, the D-1 diagnosis state | 2,384 | 900 | — | 5,066 (6.0) — real V1: 5,590 | **844 (1.0)** |
| Decide items above the fold at 1,440 × 900 | **1** | 3 | 3 | — | — |
| Running items above the fold at 1,440 × 900 | **0** | 2 | 2 | — | — |
| The same decision offered twice on Now | **2 decisions** | 0 | 0 | 2 | 0 |
| Machine language at depth 1–2 (Now, Attention/Needs you) | ISO time, policy grammar, policy enum | none | none | same as desk | none |
| E-stop on the first screen | ✓ | ✓ | ✓ | **✗** | ✓ |

## 4. Variant terms

1. Q4's position (below the decisions and the running work) is deliberate: the verdict's order is
   *needs me → running → stopped → today*. If H-1 shows "what happened" is the first thing people
   want after an absence, K-1's handover already leads with it.
2. Desktop names (Work → Missions, Attention → Needs you) are decision D-2.
3. The Space-peek depth (O-6) is owed; C's pane stands in for it here.

## 5. Open

H-1 (the 5-second test) with A, B and C, desktop and phone.

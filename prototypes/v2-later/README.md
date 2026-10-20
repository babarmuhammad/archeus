# LV2-0 — later-V2 UI evidence lab

Prototype code only. Nothing here ships and nothing in `clients/app` or `archeus/` imports it.
The phase record is [docs/design/ARCHEUS_V2_LATER_UI_EVIDENCE.md](../../docs/design/ARCHEUS_V2_LATER_UI_EVIDENCE.md).

| Record | Concept | Lab | Probe |
|---|---|---|---|
| [results/le1-ia.md](results/le1-ia.md) | Information architecture: V1 structure (A) vs three places (B) vs responsive desktop (C) | `lab/ia.html?v=a\|b\|c` | `tools/ia_probe.py` |
| [results/le2-context.md](results/le2-context.md) | Mission / project / repository context: what V1 knows, shows and loses | `lab/ia.html?ctx=v1\|proposed` | (inventory) |
| [results/le3-days-light.md](results/le3-days-light.md) | The day's light: quiet vs lanes vs ledger vs ledger + traces | `lab/light.html?r=…` | `tools/light_probe.py` |
| [results/le4-mobile.md](results/le4-mobile.md) | The phone: strip, three tabs, decision page, e-stop, Back | `lab/ia.html?v=b` at 390 px | `tools/ia_probe.py` |
| [results/le5-motion.md](results/le5-motion.md) | The motion middle, in Qt and Chromium | `lab/motion.html` | `tools/motion_measure.py`, `tools/filmstrip.py` |
| [results/le6-budget.md](results/le6-budget.md) | Bundle cost per capability (LD-1) | — | `tools/budget.py` |
| [results/le7-colour.md](results/le7-colour.md) | Warm neutrals and state balance (LD-8) | — | `tools/colour.py` |
| [results/le8-design-pass.md](results/le8-design-pass.md) | The design pass: HIG principles + design-audit / frontend-design / web-design-guidelines / typography, presentation only (`?dp=0` = before) | `lab/polish.css` | `tools/dp_diff.py`, `tools/compare.py` |
| [results/ld9-voice.md](results/ld9-voice.md) | The language layer on V1's own strings (LD-9) | `lab/ia.html` | — |
| `results/mutate_gates.txt` | Every lab gate watched to fail on its defect | — | `tools/mutate_gates.py` |

## LV2-1 (proof phase) — switches, harness, tools

Gate: [docs/design/ARCHEUS_V2_LATER_UI_LV2_1_GATE.md](../../docs/design/ARCHEUS_V2_LATER_UI_LV2_1_GATE.md).
Results in `results/lv21/`.

| `ia.html` switch | Values (default first) | What it is |
|---|---|---|
| `type` | *(§F)* · `le8` | D-6: accepted A §F typography by default; `le8` = LE8's −1.2 % tracking, phone verdict 24/30, durations in the text face (experimental arm only) |
| `names` | `new` · `v1` | D-2: desktop names Needs you / Missions, or V1's Attention / Work (the phone tabs keep the new names) |
| `bar` | `two` · `one` | D-5 rule 1: LE8's two-row phone decision bar, or LV2-0's one-row bar |
| `hdr` | `28` · `20` | D-5 rule 2: list-header spacing above section headers |
| `ctxrow` | *(desktop pb, phone p)* · `p` · `pb` · `prb` · `pbc` | W3: the row's context line — project / + branch / + repository / + commit (known or derived only; an unknown field is left off) |
| `fx` | `1` · `2` · `3` | look-alike days: same structure and states, different names, paths, branches, commits |
| `corpus` | — · `stress` · `diag` | `stress`: three same-titled missions in one two-repository project, a long title and project, Unicode |
| `flash` | — · `5` | H-1 recall: blank the page after 5 s |
| `log` | — · `1` | on-device press/route log in localStorage; `#lablog` shows it, `#lablog-clear` empties it |
| `dp` | — · `0` | LE8 off (the pre-design-pass lab) |

| Tool | Does |
|---|---|
| `lab/harness.html` | Moderator console: counterbalanced plan per participant, 5 s flash, timers, marks, wrong-path counting, keys from the fixture, local JSON export |
| `tools/h_score.py` | Scores exported sessions (`results/lv21/sessions/lv21-*.json`) against the locked criteria, per participant; INCOMPLETE below the required participant mix |
| `tools/harness_check.py` | Proves the scorer (planted misses), the counterbalancing, the harness drive and the phone server's gate |
| `tools/serve_lan.py` | One-session phone server: `--adb` (loopback for `adb reverse`) or private-LAN mode; per-run path token + HttpOnly cookie; GET only; stops itself |
| `tools/density_probe.py` | Row height, wraps, characters, field presence and look-alike separability per `ctxrow` arm, 1,440 / 390 / 360 px, 100 / 200 % |
| `tools/pr4_le8.py` | PR-4's clipping check (its own lab and metric) for the LE8 typography arm, Chromium and Qt |
| `tools/ia_probe.py` | as before; `LV21_Q='&arm=…'` + `LV21_TAG=name` write `results/lv21/ia_<name>.json` |

Run any page: `py prototypes/v2-later/tools/shoot.py OUT "ia.html?v=b@390x844"` (serves on loopback
from `tools/serve.py`, which exposes `prototypes/` and V1's token stylesheet only). The Qt driver
opens a real, topmost window and takes the foreground for the length of a run.

`fixture.js` is synthetic and shaped like V1's reads; anything V1 does not record is marked
`proposed:` and appears only with `?ctx=proposed`. `v1-diagnosis/` holds the real V1 captures the
replica is calibrated against.

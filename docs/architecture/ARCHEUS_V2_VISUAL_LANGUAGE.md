# Archeus V2: visual language for the real app

**Status: PROPOSED (Gate 0, G0-4 of the V2 real build plan).** Written 2026-10-25 on branch `v2/real` (from 539b29a, the V1 integration candidate). Docs only: no token, gate or code file was edited to produce it. The owner decisions of 2026-10-25 are applied where they are marked; everything else is a proposal for the aimed Codex review. Like the spine and motion ADRs it does not merge to the release line before the P26 decision.

This document gives the values and rules that slice U1-a (tokens) and U1-e, U1-f (fonts, targets) will encode. Governing sources: [ADR-0017](decisions/ADR-0017.md) and [ADR-0028](decisions/ADR-0028.md) (state colours, focus), [ADR-0044](decisions/ADR-0044.md) (themes), [ADR-0054](decisions/ADR-0054.md) (spine), [ADR-0055](decisions/ADR-0055.md) (motion), the V1 design system ([ARCHEUS_V1_DESIGN_SYSTEM.md](../design/ARCHEUS_V1_DESIGN_SYSTEM.md)) and the V2 research ([ARCHEUS_V2_UI_RESEARCH.md](../design/ARCHEUS_V2_UI_RESEARCH.md) §7). The prototype (`D:\archeus-v2-f32\clients\v2-prototype`, branch `v2/final-32` at 93e9a62) is cited as input only: its `style.css` tokens and its concept art supplied the values below; none of its code or art ships.

## 1. Owner decisions applied (2026-10-25)

| Decision | What it means here |
|---|---|
| Q2 palette: take the prototype palette | The prototype's colours are the V2 base. V1's colours become "legacy" where they differ (table in §3.3). The contrast floors and `state_colours_are_told_apart` still apply and decided two of the choices (§3.3). |
| Q3 themes: Dark and Light, each standard and high contrast, plus System and forced-colors | Two token sets, `dark` and `light`, which is what ADR-0044 already says (`['dark','light']`); high contrast and System are modes over them; forced-colors always wins. The prototype has no Light, so Light is derived (§4). |
| Q4 serif display font for the state-sentence line only | One self-hosted, hashed display font; everything else stays on system fonts (§6). This amends the design-system statement "No web fonts, no CDN" (DS §4) to "no CDN, no remote font; one self-hosted display font". It is a document statement, not a gate. |
| Q5 keep the core breath | ADR-0055. |
| Q6 44 px for primary desktop controls only | A new `desktop-primary` target of 44 px; every other desktop control keeps its current 28 px floor (§7). |
| Q10 no `backdrop-filter` | Overlays use a solid material (§8). The V1 gate `no_readback_effects` stays as it is. |
| Q11 spine of six stations | ADR-0054. |

## 2. What the prototype supplies (input only)

From `style.css` `:root` (lines 5 to 33) and the concept art in `docs/design/v2-concepts/` (on `v2/final-32` only: that directory is not in this branch):

| Prototype token | Value | Use in the prototype |
|---|---|---|
| `--bg` | `#0C0811` | page ground, violet-black |
| `--rail` | `#090D15` | side rail |
| `--surface`, `--surface-2` | `#0E131C`, `#151C2A` | panels |
| `--line`, `--line-2` | ivory at 12 % and 26 % | hairlines |
| `--text`, `--text-2`, `--text-3`, `--text-muted` | `#EFE9DA`, `#BDB7A8`, `#9EA3AE`, `#ABA699` | text |
| `--ivory`, `--amber`, `--blue`, `--green`, `--slate` | `#EFE9DA`, `#F2B544`, `#6FB1FF`, `#6FD39A`, `#9AA5B8` | thread ink; needs you; running; connected; done and idle |
| `--focus` | `#FFF3CF` | focus ring (3 px) |
| `--teal`, `--rose`, `--lilac` | `#7FCFC0`, `#E7A3AE`, `#C7B2F0` | project tints |
| node cyan, stop-button red | `#6FC6FF`, `#E5585E` (text on dark `#F4A4A8`, border `#F07178`) | node fill; Stop |
| `--serif` | Libre Caslon Text 400 to 700 | wordmark, headline, lede |

The concept art, sampled by hue (a small script over `02-now.png`, `03-mission.png`, `10-phone-needs-you.png`, `08-day-attention.png`), agrees with the CSS: ground `#0A0A0E` to `#120E16`, amber `#F4B454` to `#FCCC6C`, blue `#2C9CFC` to `#84B4FC` (the CSS values are the lighter, text-safe forms of the art's blue and red), green `#34CC94`, red `#CC3C3C`. In the concept's mission frame the passed stations are green checks, the current one a blue ring and dot, and Review a hollow ring. The prototype's own state table (`app.js` line 10) paints Done in slate; the art and the V1 rule (only a completed mission is done) paint it green. §3.3 follows the art.

## 3. Colour tokens

Token names and roles are V1's (`tokens.json`); V2 changes values and adds none, except where §9 says so. Every value below was run through the same formulas as `tests/v1/design/test_design_gates.py` (WCAG relative luminance contrast; CIE76 ΔE on Lab with the gate's constants). The ratios are the minimum over the four surfaces `bg`, `surface-1`, `surface-2`, `surface-3`.

### 3.1 Dark (standard)

| Role | V2 | V1 (legacy) | Source |
|---|---|---|---|
| `bg` | `#0C0811` | `#0E1116` | prototype `--bg` |
| `surface-1` | `#0E131C` | `#141922` | prototype `--surface`; the rail uses it (the prototype's `#090D15` is not a role) |
| `surface-2` | `#151C2A` | `#1A2130` | prototype `--surface-2` |
| `surface-3` | `#1C2536` | `#202838` | derived, one step above `surface-2`; the prototype has none |
| `line` | `#292D33` | `#2A3344` | prototype ivory 12 % over `surface-1`, as an opaque hex (V1 tokens are hex-first) |
| `line-strong` | `#484B4D` | `#3A4558` | prototype ivory 26 % over `surface-1` |
| `text` | `#EFE9DA` | `#E6EAF0` | prototype |
| `text-2` | `#BDB7A8` | `#AAB3C0` | prototype |
| `text-3` | `#ABA699` | `#8A94A3` | prototype `--text-muted`; the prototype's cool `--text-3` `#9EA3AE` is dropped so there are three text roles, not four |
| `primary`, `thread` | `#EFE9DA` | `#E6EAF0`, `#F4F1EA` | prototype ivory |
| `on-primary` | `#0C0811` | `#0E1116` | the ground |
| `focus` | `#FFF3CF` | `#F4F1EA` | prototype `--focus` |
| `state.active` | `#6FB1FF` | `#5AA9FF` | prototype blue |
| `state.attention` | `#F2B544` | `#F2B544` | prototype amber (unchanged) |
| `state.blocked` | `#F07178` | `#F07178` | unchanged; see §3.3 |
| `state.paused` | `#9AA5B8` | `#A7B0BD` | prototype slate |
| `state.thinking` | `#C7B2F0` | `#B79CFF` | prototype lilac |
| `state.done` | `#6FD39A` | `#5FD08B` | prototype green |

Minimum contrast over the four surfaces: `text` 12.68, `text-2` 7.68, `text-3` 6.32, `focus` 13.88, `state.active` 6.88, `state.attention` 8.39, `state.blocked` 5.37, `state.paused` 6.18, `state.thinking` 8.09, `state.done` 8.38; `primary` on `on-primary` 16.38; `thread` on `surface-1` 15.36. Smallest ΔE among the six states 25.5 (active and thinking; V1 dark: 29.1; floor 20). Smallest ΔE of `focus` from any state 41.3 (V1: 26.3; floor 20). Hairlines against `surface-1`: `line` 1.34, `line-strong` 2.12 (V1: 1.39 and 1.82), decorative like V1's.

### 3.2 Light (derived; the prototype has none)

Rule: keep the prototype's hue and saturation, move lightness. The ground is a warm ivory paper (the prototype's ivory family, lightened), the ink is the prototype's violet-black ground lifted slightly, and each state colour keeps its dark hue and saturation (HLS) while its lightness is lowered in 0.5 % steps until it clears 4.5:1 on the darkest of the four light surfaces.

| Role | V2 Light |
|---|---|
| `bg` | `#F4EFE4` |
| `surface-1` | `#FBF9F4` |
| `surface-2` | `#EDE8DA` |
| `surface-3` | `#FFFFFF` (raised, as V1 Light) |
| `line` | `#DBD8D5` (ink 14 % over `surface-1`) |
| `line-strong` | `#B6B3B3` (ink 30 %) |
| `text`, `primary`, `thread`, `focus` | `#14101A` |
| `on-primary` | `#FBF9F4` |
| `text-2` | `#4A4452` |
| `text-3` | `#5C5666` |
| `state.active` | `#0063D8` |
| `state.attention` | `#8C5E0A` |
| `state.blocked` | `#CE1620` |
| `state.paused` | `#5B6982` |
| `state.thinking` | `#7947DB` |
| `state.done` | `#247647` |

Minimum contrast: `text` 15.33, `text-2` 7.66, `text-3` 5.76, `focus` 15.33, `state.active` 4.54, `state.attention` 4.61, `state.blocked` 4.56, `state.paused` 4.53, `state.thinking` 4.59, `state.done` 4.57; `primary` on `on-primary` 17.84. Smallest state ΔE 31.6 (active and thinking); smallest focus-from-state ΔE 40.1. The state margins on `surface-2` are 0.03 to 0.11 above the floor: a rounding change to any of the six needs the gate re-run. As in V1, focus is the thread ink in Light.

### 3.3 Where the prototype and V1 differ, and what decided it

| Role | V1 | Prototype | V2 | Reason |
|---|---|---|---|---|
| `state.blocked` | `#F07178` | Stop red `#E5585E`, border `#F07178` | `#F07178` | `#E5585E` measures 4.31:1 on `surface-3`, under the 4.5 floor. The prototype already borders Stop in `#F07178`. |
| `state.done` | green `#5FD08B` | slate (the prototype), green (the concept art) | green `#6FD39A` | Slate is the paused colour; the two would fail ΔE 20 and break "only a completed mission is done". The art's passed stations are green. **Owner question 1.** |
| `state.thinking` | `#B79CFF` | lilac `#C7B2F0` | `#C7B2F0` | ΔE against active 25.5, above the floor. |
| node cyan `#6FC6FF` | none | node fill | not adopted | ΔE 15.7 from `state.active`, under 20: a cyan node would read as an active one. Node fills stay state or neutral (§9, U1-h). |
| teal `#7FCFC0`, rose `#E7A3AE` | none | project tints | not adopted as tokens | ADR-0044 §2: tints carry no meaning and are never promoted; they stay thread tints if wanted. |

ADR-0017's rule that "state colours and glyphs are fixed across all themes" keeps its meaning: one colour, one meaning, in every theme. Its value tables are what V2 replaces, so ADR-0017 gets one line pointing here (done with this document).

## 4. High contrast (Dark and Light)

V1's high contrast is two aliases over both themes (`text-3` becomes `text-2`, `line` becomes `line-strong`, hairline 2 px) and no contrast gate. V2 keeps the aliases and adds per-theme overrides where the standard value does not reach 7:1, plus a gate (§10).

Floors in high contrast: `text`, `text-2`, `text-3` and the six states at 7:1 on every surface; `focus` 4.5:1; `line` and `line-strong` 3:1 on every surface (WCAG non-text contrast); state ΔE 20; focus-from-state ΔE 20.

| Theme | Overrides to the standard values | Minimum results |
|---|---|---|
| Dark HC | `state.active` `#74B4FF`; `state.blocked` `#F4969B`; `state.paused` `#A6B0C0`; `text-3` = `text-2` (`#BDB7A8`); `line` = `line-strong` = `#6C6F74` | `text` 12.68, `text-2` and `text-3` 7.68, active 7.11, attention 8.39, blocked 7.08, paused 7.02, thinking 8.09, done 8.38; lines 3.69 on `surface-1`; state ΔE 24.8; focus ΔE 37.3 |
| Light HC | `state.active` `#00489D`; `state.attention` `#664407`; `state.blocked` `#991018`; `state.paused` `#424C5E`; `state.thinking` `#5925BF`; `state.done` `#1A5533`; `text-3` = `text-2` (`#4A4452`); `line` = `line-strong` = `#878280` | `text` 15.33, `text-2` and `text-3` 7.66, active 7.11, attention 7.16, blocked 7.03, paused 7.07, thinking 7.03, done 7.17; lines 3.61 on `surface-1`; state ΔE 38.8; focus ΔE 27.6 |

Because the overrides differ by theme, the generator has to emit them per theme: `:root[data-theme='dark'][data-contrast='high']`, the Light counterpart, the `prefers-contrast: more` forms for each, and the System-theme forms. The existing generic block (`:root[data-contrast='high']` with the aliases) stays, so the existing `test_t6_only_the_token_sets_are_themes_and_each_has_its_attribute` still matches its patterns.

## 5. Forced colors

`forced-colors: active` always wins (ADR-0044 §1) and replaces the palette with system colours. Every V2 primitive has a form there, and none depends on a colour to be understood.

| Primitive | Forced-colors form |
|---|---|
| Spine marks | Drawn with `currentColor` and system colours: passed = solid `CanvasText` disc with a `Canvas` check; current = `Highlight` ring and dot (shape follows the presentation class: ◆ needs you, ■ blocked, ‖ paused, ✕ failed); not reached = hollow `CanvasText` ring; unknown = dotted ring. Segments differ by line style: solid, dashed, dotted. |
| Attention band | The tint is dropped (forced colours remove backgrounds). The row gets a 1 px `Highlight` line above and below and keeps its ◆ and its word. Never a left edge (the thread owns it). |
| State figures and badges | Glyph and word, as V1 (`.badge` gets `1px solid CanvasText`). |
| Core mark and breath | The breath is a transform, unaffected by colours. The static twin is a `CanvasText` outlined mark with its text. |
| Display serif line | Fonts are not changed by forced colours; the line renders in `CanvasText`. |
| Focus | `2px solid Highlight` (V1). |
| Thread rule and line | `CanvasText` and `Highlight` (V1). |

## 6. Typography

- **Body, UI and mono stay system fonts** (V1 `type.family`, `type.mono`); the scale is unchanged (body 13/20 desktop, 17/24 phone; caption 12/16 and 13/18; display 28/34).
- **Display font, Q4: Libre Caslon Text, for `.state-sentence` only** (the Now and OfflineNow state-sentence lines; `Now.tsx` lines 74 and 204). Weight 500 as the prototype's headline. Heading and wordmark use are a later decision (the plan's U1-e says "display line, headings, wordmark"; this document decides the sentence only, which is what the owner's answer named).
- **Source and cost.** Prototype `LibreCaslonText-VF.ttf` is 126,876 bytes (sha256 `c11809db...b8b3f4`, OFL, licence `OFL-LibreCaslonText.txt`). Converted to woff2 without subsetting: 57,568 bytes. Subset to Latin (U+0020 to 007E, 00A0 to 00FF, 2010 to 2027, 2190 to 2193, 2026) with `kern`, `liga`, `lnum`, `tnum`: **35,432 bytes** (measured here with fontTools; not committed). The sentence is Core's own words, so a fallback for other scripts is fine.
- **Loading.** Self-hosted as a content-hashed asset under `/assets/` (cached by the existing service worker, so offline cold start renders it; CSP `default-src 'self'` allows it). `font-display: swap`, fallback `Georgia, serif`; the swap behaviour and a metric-matched fallback are for U1-e to verify, not measured here. Not Source Sans 3, Inter or Roboto Mono, which the prototype's folder also holds (1.8 MB of ttf).
- **Gate to add (U1-e).** A font allow-list: exactly one `@font-face`, a hashed same-origin URL, an OFL notice file present, no remote URL.

## 7. Targets and density

- `tokens.json targets` gains `desktop-primary: 44` (emitted as `--target-desktop-primary`). It applies to primary actions (`.btn` marked primary, Approve, Reject), navigation items, Tell and Stop. Every other desktop control keeps `--target-desktop: 28`; phone stays 44. The plan's idea of a 32 px class for dense secondary buttons is not needed and is dropped.
- Targets are measured by effective hit extent (`elementFromPoint`), not by box size; the probe is a port of the prototype's `v2_hit_probe.py` against the real SPA (U1-f).
- **Compact density (research §7.2, 24 px rows) and the meta column are not decided here.** They pull against raising primary targets and are not in the owner's answers. Owner question 4.

## 8. Material, depth and line styles

- **Solid material.** Overlays (the chat sheet, the decision sheet, menus) are opaque `surface-3`. The prototype's `--chat-solid` `#120E1A` is its reduced-transparency fallback and is not adopted as a role. No `backdrop-filter`, `filter` or blend mode anywhere (the V1 gate stays). Elevation is surface step plus `line`, no shadows added.
- **Attention band.** A static tint of `state.attention` at 12 % over the row's surface, for rows that need you (at most three on Now); never a left edge. Dark: text, text-2 and text-3 on the band clear 4.5 (smallest: text-3 4.96 on `surface-3`) and amber on the band 6.58. Light: text roles clear 4.5 (text-3 4.93) but amber text on the band measures 3.95 to 4.79, under 4.5 on `bg` and `surface-2`. **Rule: on the band the word is ink (`text`), and the amber figure ◆ carries the colour (non-text, 3:1 holds).** In high contrast and forced colors the tint is off and a hairline replaces it (§5).
- **Line-style vocabulary** (extends the graph's edge tiers, ADR-0025, to everything with a "final or not" distinction), with the colours of §3:

  | Style | Meaning | Where |
  |---|---|---|
  | solid | recorded, passed, done | spine segments and passed marks up to the current station; graph recorded edges |
  | filled in a state colour | current, running | spine current mark |
  | dashed | not reached, suggested, proposed | spine segments after the current station; graph suggested edges |
  | hollow | not started, not reached | spine marks ahead |
  | dotted | unknown or unclear | spine with an unknown position (ADR-0054 §3) |

  Every style also has a word. Spine strokes use `text-2` and `text-3`, never `line`, so they clear 3:1 as graphics (text-3 worst case 6.32 Dark, 5.76 Light).

## 9. Figures and the signature table

**Figures.** State figures are the V1 presentation-class glyphs (◌ ○ ◆ ◇ ● ■ ‖ ✕ ✓ · –) and their ASCII twins, unchanged; sizes 12, 16 and 20 px drawn separately, not scaled, as research §7.5 proposes. The spine marks are these figures at 8, 10 and 16 px (ADR-0054 §5). Node figures: V1's `ENCODING` shapes stay (mission circle, project cluster, execution triangle, diamond reserved for decisions and approvals), because one shape means one fact. The prototype draws a mission as a diamond and a project as a faceted hull; the hull look may restyle the `cluster` shape (U1-h), the diamond is not adopted. The prototype's idea sparkle has no graph kind to attach to (ideas are not nodes in V1) and is deferred.

**Signatures.** What marks each kind of moment, and which doc owns it:

| Moment | Signature | Motion | Owner of the rule |
|---|---|---|---|
| Where a mission is | the spine, three sizes | none | ADR-0054 |
| A mission needs you | ◆ and its word, the static attention band | the existing badge arrival once | §8, ADR-0055 |
| Work is live | the static halo, the core mark with its breath, the sentence | breath only (ADR-0055 §3) | ADR-0055, ADR-0024 |
| Output happened | one opacity pulse per batch, the travelling marker | 240 ms and 600 ms | ADR-0024 §6 |
| Archeus acted | the thread line, drawn once, and the thread rule | 600 ms | ADR-0026 |
| State changed | the badge cross-fade | 160 ms | ADR-0024 |
| Work failed | ✕, the reason inline | the 160 ms cross-fade only | ADR-0055 §2 |
| Offline | banner text, hollow presence node, "as of" time | none | V1 |

## 10. What U1-a encodes and which gates it touches

Tokens file (`clients/app/tokens/tokens.json`): the `dark` and `light` value sets of §3.1 and §3.2; a `high_contrast` section that keeps the aliases and adds per-theme overrides (§4); `targets.desktop-primary: 44`; `motion.breath: 6000` (ADR-0055); `alpha.band: 0.12`. No third theme key.

Files that carry the same colours outside the generated CSS and must move with the tokens: `clients/app/public/manifest.webmanifest` (`background_color` and `theme_color`, currently `#0E1116`; `test_the_manifest_names_what_the_pwa_needs` pins `background_color` to `themes.dark.bg`), `src/state/appearance.js` (`BG`, generated), `archeus/cli/tui/tokens.py` (`SHELL`, `COLOURS`, generated). The TUI's ANSI-256 quantisation was checked here with `claude_sessions.themes.hex_to_x256` (the function the generator uses): in Dark the focus `#FFF3CF` lands on 230 and the six states on 75, 215, 204, 248, 183 and 78; in Light the focus is 233 and the states 26, 94, 160, 60, 98 and 29. All distinct, so `test_the_terminal_focus_is_never_a_state_colour` should pass; U1-a runs it, this document does not claim it did.

V1 design gates and what each needs for the palette work:

| Gate | Status for U1-a |
|---|---|
| `test_every_role_clears_its_contrast_floor_on_every_surface` | unchanged; V2 passes it. V2 holds `text-3` to 4.5 where V1's floor is 3.0: raise the floor in the gate so the V2 value is protected (a strengthening, not a loosening). |
| `test_state_colours_are_told_apart`, `test_focus_is_never_read_as_a_state` | unchanged; V2 passes (§3). |
| `test_t6_only_the_token_sets_are_themes_and_each_has_its_attribute` | unchanged (`['dark','light']`); the generator keeps its emitted patterns. |
| high contrast | no gate exists today. Add one: floors of §4 over the per-theme overrides. New, not an amendment. |
| `test_the_manifest_names_what_the_pwa_needs` | unchanged, but the manifest file must change with `themes.dark.bg`. |
| `test_no_readback_effects` | unchanged (Q10). |

## 11. Bundle baseline and ceiling (G0-6)

Measured 2026-10-25 in `D:\archeus-v2real` at 539b29a: `npm run build` (`tsc --noEmit -p . && vite build`) through the shared test lock, Node v24.15.0, vite 8.3.1, react 19.3.0, typescript 5.9.3. There is no `node_modules` in this worktree; one was junctioned from `D:\archeus-p21-e\clients\app` (same `package-lock.json`, same versions of the five packages checked), no network install, the junction and the build output removed afterwards.

| File (output name hashes change) | Raw bytes | gzip -9 bytes |
|---|---|---|
| `assets/index-*.js` | 498,837 | 151,890 |
| `assets/index-*.css` | 26,031 | 6,055 |
| `assets/appearance-*.js` (the unbundled boot script) | 1,655 | 863 |
| **JS plus CSS** | **526,523** | **158,808** |

gzip -9 is Python `gzip.compress(data, 9, mtime=0)`, which is deterministic; vite's own summary, at its default level, printed 153.92 kB for the JS and 6.08 kB for the CSS. Other shipped bytes, not counted: `index.html` 789, `sw.js` 1,904, `manifest.webmanifest` 492, icons 31,862.

**Proposed ceiling:** JS plus CSS at most **180,000 bytes gzip -9** (the baseline plus 21,192, +13.3 %), and the display font at most **40,000 bytes** woff2 (measured 35,432 subset), counted separately. The spine, tables and tokens are expected to cost a few kilobytes; the ceiling leaves room for U2 and is not a target. **Enforcement:** a Node test `clients/app/test/budget.test.ts`, which reads `archeus/api/static/assets` after the build and fails with "build first" if it is absent. The CI client job runs `npm run build` before `npm test` (`.github/workflows/ci.yml`, the job that also runs `npm audit`), so the test has its input there. Locally it needs a build. I did not write the test: the brief asks for docs only.

## 12. Not decided here

Compact density and the meta column (§7); the exact element and place of the core mark on Now (wireframes, G0-5, Codex); headings and wordmark in the display font; node figure restyle beyond the cluster hull; text size of the display line beyond V1's 28/34. Open owner questions are in the Gate 0 report.

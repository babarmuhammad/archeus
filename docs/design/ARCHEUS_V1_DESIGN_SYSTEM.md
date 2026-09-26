# Archeus V1 — Design System ("Quiet instrument, living thread")

Status: **DECIDED** for principles, semantic roles, state model and accessibility floors;
**PROPOSED** for exact hex values (validated by the contrast gate in P16 before they freeze).
Research and rationale: [ARCHEUS_V1_DESIGN_RESEARCH.md](ARCHEUS_V1_DESIGN_RESEARCH.md).
UI structure: [../architecture/ui-architecture.md](../architecture/ui-architecture.md).

This is a product language, not a component library. It says what Archeus looks like *because of
what Archeus is*: a persistent colleague whose work you glance at, verify and direct.

---

## 1. Design philosophy

1. **Quiet by default, loud only when it means something.** Surfaces, type and spacing carry
   hierarchy. Colour is reserved for *state* and for the *thread*. If everything is quiet, a
   single amber diamond on a phone is enough to say "you are needed".
2. **State is the content.** The most important pixels on any screen say what is true, who owns
   the next step and what happens next. Decoration never competes with them.
3. **The system is alive because things change, not because things move.** Motion only reports
   change (a task finished, Archeus touched an object, a stream is producing output).
4. **Proof on demand.** Every consequential element has a *Why* affordance. Evidence is one step
   away, never zero (clutter) and never three (distrust).
5. **Point of view with restraint.** One signature element (the thread). Everything else is
   craft: alignment, rhythm, consistent iconography, honest typography.
6. **Same language on every surface.** Desktop, web, mobile and TUI share roles, glyphs, state
   names and copy. Density and interaction adapt; meaning does not.

Checked against the Apple Design Skill's template test: the plan is specific to Archeus (state
colours + thread + inspector *Why* only make sense for an agentic system you must trust), so it is
not a default. Its dark appearance is *not* "near-black + acid accent": after design review B.1 there is no hue
accent at all — primary actions are neutral fills, the thread is near-white ink, and the only hues
on screen are state glyphs and labels.

## 2. Signature element — the thread

A fine luminous line (1 px at 1×, 1.5 px at ≥ 2×; colour `thread`) that links **an Archeus
action to the world object it touched**:

- In the conversation: from a message to the card or object it acted on (e.g. "Pinned *Standup 21
  Sep* into *Dashboard*" draws a line to the Dashboard row in *Happening now*).
- In lists: a 2 px left rule on rows Archeus changed since the user last looked (fades out on
  acknowledgement).
- In the spatial view: the edge Archeus is currently traversing (live execution energy).

Rules: appears only when Archeus acts; never decorative; max one travelling animation at a time
(transform/opacity only, ≤ 600 ms); under reduced motion it appears without travel; under High
Contrast it becomes a solid 2 px line in `focus` colour. **Removal test:** without the thread,
the user loses the visible connection between what Archeus *said* and what it *did* — so it
stays; nothing else gets a signature.

## 3. Colour system

### 3.1 Roles

| Role | Use | Never |
|---|---|---|
| `bg` | app background | text |
| `surface-1/2/3` | base panel, raised panel (inspector), overlay (sheet, popover) | state |
| `line` / `line-strong` | hairline separators, input borders | emphasis |
| `text` / `text-2` / `text-3` | primary, secondary, tertiary text | on coloured fills below contrast floor |
| `primary` | fill of the one primary action on a view — a **neutral** inverted fill (`text` on `bg`), never a hue | state |
| `thread` | the signature line only (§2) — near-white on dark, near-black ink on light | anything else |
| `link` | inline links: `text` colour + underline | colour-only links |
| `focus` | focus ring (2 px, offset 2 px) | anything else |
| `state.*` | state glyphs, status labels, subtle row tints (≤ 12% alpha) | buttons, links, the thread |

### 3.2 Semantic state colours (fixed across all themes)

| Token | Meaning | Dark (proposed) | Light (proposed) | Glyph |
|---|---|---|---|---|
| `state.active` | working now | `#5AA9FF` | `#0B63CE` | ● |
| `state.attention` | needs the user | `#F2B544` | `#9A6100` | ◆ |
| `state.blocked` | cannot proceed, not waiting on user | `#F07178` | `#B3261E` | ■ |
| `state.paused` | paused by someone | `#A7B0BD` | `#5B6472` | ‖ |
| `state.thinking` | understanding/planning | `#B79CFF` | `#6A45C9` | ◌ |
| `state.done` | verified and accepted | `#5FD08B` | `#1E7F45` | ✓ |

- **Never colour alone:** every state is glyph + label (+ colour). The glyph set above is also the
  TUI's.
- **Red means "a problem needs resolving"** and is shared by Blocked (■) and Failed (✕); glyph and
  label distinguish them. (The first draft gave Failed its own orange; measured ΔE was 22 on dark
  and 11 on light — two colours nobody could tell apart claiming two meanings. Design review B.1.)
- **No state colour is also an interface colour.** Primary actions are neutral fills and links are
  underlined text, so the only hues on a screen are states. (The first draft's blue accent sat
  ΔE 18 from `state.active` on dark and was identical to it on light. Design review B.1.)
- `attention` is the only colour allowed to appear in the tab bar badge and the tray icon.

### 3.3 Themes

| Theme | Status | Notes |
|---|---|---|
| Archeus Dark | follows the OS | `bg #0E1116`, `surface-1 #141922`, `surface-2 #1A2130`, `text #E6EAF0` (14.6:1 on surface-1), `text-2 #AAB3C0` (8.3:1), `primary` fill `#E6EAF0` with `#0E1116` label, `thread #F4F1EA`, `focus #FFD166` (12.2:1) |
| Archeus Light | follows the OS | `bg #F7F8FA`, `surface-1 #FFFFFF`, `text #11151C` (18.3:1), `text-2 #4A5463` (7.7:1), `primary` fill `#11151C`, `thread #11151C` |
| High Contrast (dark + light) | follows `prefers-contrast: more` / Windows contrast themes (`forced-colors`) | solid surfaces, 7:1 body text, 2 px lines, no tints |

Appearance **follows the operating system** (`prefers-color-scheme`, `prefers-contrast`,
`forced-colors`, `prefers-reduced-transparency`) — there is no app-level light/dark switch
(`dark-mode.md` › "Avoid offering an app-specific appearance setting"). The user's only appearance
choices are thread tint, density and motion. Measured contrast of every state glyph colour on
`surface-1`: dark 6.2–9.6:1, light 5.0–6.5:1 (all ≥ 4.5:1, so state *labels* may use them too).

Legacy `themes.PALETTES` (39 authored palettes) survive **only as thread tints**; surfaces and state colours do not change. Skins and worlds are not
carried into the V1 client (ADR-0017): they redefine chrome per look, which conflicts with fixed
state semantics. The legacy GUI keeps them until it retires. The build rejects a thread tint
that fails 3:1 against `surface-1` or collides (CIE76 ΔE < 30) with any state colour.

Contrast floors, enforced by `tests/v1/design/test_contrast.py` over every theme × role pair:
text ≥ 4.5:1 on its surface; `text-2` ≥ 4.5:1; `text-3` ≥ 3:1 and never for essential content;
state glyphs ≥ 3:1 on `surface-1`; focus ring ≥ 3:1 against both the control and the surface.

## 4. Typography

| Role | Desktop | Mobile | Weight | Use |
|---|---|---|---|---|
| `display` | 28/34 | 28/34 | 600 | Now greeting line only |
| `title-1` | 20/26 | 22/28 | 600 | view titles |
| `title-2` | 16/22 | 18/24 | 600 | section and inspector titles |
| `body` | 13/20 | 17/24 | 400 | default text (HIG floors: 13 desktop, 17 mobile) |
| `body-strong` | 13/20 | 17/24 | 600 | emphasis in rows |
| `caption` | 12/16 | 13/18 | 400 | metadata (never below 10 desktop / 11 mobile) |
| `mono` | 12/18 | 14/20 | 400 | ids, commands, diffs, numbers in tables |

- Families: `"Segoe UI Variable Text", "Segoe UI", system-ui, -apple-system, Roboto, sans-serif`
  for text; `"Cascadia Mono", Consolas, ui-monospace, "SF Mono", monospace` for mono. No web
  fonts, no CDN (offline, and the repo's rule).
- Sizes are rem-based; the app root follows the OS/browser text size; layouts survive 200%.
- Numbers use tabular figures (`font-variant-numeric: tabular-nums`).
- Copy style: sentence case for everything except proper nouns; labels say what happens ("Approve
  push", not "Submit"); progress text is specific ("Running 214 tests in Payments").

## 5. Spacing, layout and grid

- 4 px base unit; scale `0 2 4 8 12 16 24 32 48 64`.
- Density modes: *comfortable* (default) and *compact* (desktop only; row height 28 → 24).
- Desktop layout: sidebar 232 px (collapses to a 56 px icon rail below 1000 px of window), main
  flexible, inspector 360–560 px resizable; content max line length 72ch for prose.
- **Component layout reads its container, not the window** (container queries; carried from the
  current repo's hard-won rule). Only chrome (sidebar rail, tab bar vs sidebar) uses media queries.
- Lists over cards: a mission is a row, not a card, except inside the conversation where cards
  are the unit.

## 6. Surfaces, borders, radius, elevation, materials

| Layer | Surface | Border | Radius | Elevation |
|---|---|---|---|---|
| Base (lists, views) | `surface-1` | none; `line` separators | 0 | 0 |
| Raised (inspector, cards in conversation) | `surface-2` | 1 px `line` | 8 px | shadow `0 1px 2px rgba(0,0,0,.24)` |
| Overlay (sheets, popovers, command bar) | `surface-3` | 1 px `line-strong` | 12 px (sheets: 16 top) | shadow `0 8px 24px rgba(0,0,0,.32)` |
| Controls | inherit | 1 px `line` | 6 px | 0 |

- **Transparency:** overlays may use 92–96% opaque `surface-3`; no `backdrop-filter`, no blur,
  no blend modes (they tear the Qt WebEngine GPU surface — verified in the current repo — and
  cost readbacks everywhere). Reduced transparency → 100% opaque.
- No gradients on surfaces. The only gradient allowed is the thread's travelling highlight.

## 7. Iconography

- One outline icon set, 1.5 px stroke at 20 px, drawn on a 24 px grid; filled variants only for
  selected nav items. Proposed base: a permissively licensed set vendored into the build (no CDN).
- Every icon has a text label or an accessible name; icon-only buttons are allowed only in
  toolbars with tooltips and names.
- Object-kind icons (mission, project, repository, decision, person, meeting, knowledge, idea,
  automation, account) are consistent across list, inspector, graph and TUI (TUI uses letters:
  M P R D @ N K I A $).

## 8. Motion

| Motion | Duration | Easing | Trigger |
|---|---|---|---|
| State change (glyph cross-fade + 2 px lift) | 160 ms | ease-out | domain state changed |
| Row insert/remove | 200 ms | ease-out | list changed (keyed reconcile) |
| Inspector slide | 220 ms | ease-out | open/close |
| Sheet (mobile) | 280 ms | spring-like ease-out | open/close |
| Thread travel | ≤ 600 ms, once | ease-in-out | Archeus acted on an object |
| Active pulse | one 240 ms opacity pulse per batch of new output, at most every 2 s | ease-out | execution stream produced events |

Rules (carried from the repo and the HIG): animate only `transform` and `opacity`; no ambient
loops; nothing loops — the active pulse fires once per batch of real output (design review B.5 replaced
the first draft's breathing glyph, which was an ambient loop on the most-watched element);
one animation loop for the whole app that parks when the window is hidden or blurred; reduced
motion → cross-fades only, no travel, no breathing. A test parses every keyframe and rejects
other properties (as `tests/test_gui_flicker.py` does today).

## 9. Interaction states

| State | Treatment |
|---|---|
| Hover | row tint `text` at 4% alpha; pointer cursor on interactive elements |
| Pressed | tint 8%; scale 0.98 on buttons (transform) |
| Focus | 2 px `focus` ring, 2 px offset, always visible on keyboard focus (`:focus-visible`) |
| Selected | 2 px `text` left rule + `surface-2` background |
| Disabled | 40% opacity **plus** a reason in the tooltip/accessible description ("Needs the approve scope on this device") |
| Loading | skeleton rows for lists (static, no shimmer loop); inline spinner only inside a control; specific progress text |
| Empty | one sentence saying what will appear here and one action ("No missions yet. Tell Archeus what you want.") |
| Error | inline, next to the thing; says what happened and what to do; never a modal for a recoverable error |
| Success | the state change itself (✓) plus a transient toast only when the success happened off-screen |
| Warning | `attention` glyph + text; used for "this will need approval", "stale knowledge" |

## 10. Work-state vocabulary (the heart of the system)

Presentational states map domain states (see
[../architecture/state-machines.md](../architecture/state-machines.md)) to one glyph, one colour
role and one label pattern. The mapping is one table in `clients/app/src/state/presentation.ts`
generated from `archeus/core/domain/states.py` so UI and domain cannot drift.

| Presentation | Glyph | Label pattern | Domain states |
|---|---|---|---|
| Active | ● | "Implementing chart components" (current task title, present participle) | EXECUTING, RUNNING, VERIFYING, REVIEWING, STARTING |
| Needs you | ◆ | "Waiting: approve plan v2" / "Waiting: accept the video" | APPROVAL_REQUIRED, AWAITING_APPROVAL, AWAITING_HUMAN, acceptance-BLOCKED |
| Blocked | ■ | "Blocked: all eligible accounts at ceiling · resets 16:05" | BLOCKED (not on user), CONFLICT, LIMITED (accounts) |
| Paused | ‖ | "Paused by you 11:40" / "Pausing 2 executions…" | PAUSED, PAUSING |
| Planning | ◌ | "Planning: reading Monday's notes" | CREATED, UNDERSTANDING, CONTEXT_GATHERING, REASONING, PLANNING, REPLANNING |
| Verifying | ● + "Verifying" label | "Verifying: 214 tests" | VERIFYING (a sub-label of Active, same colour) |
| Done | ✓ | "Done 14:20 · verified · reviewed" | COMPLETED, SUCCEEDED, PASSED, MERGED |
| Failed | ✕ (red, shared with Blocked) | "Failed: tests still failing after 2 replans" | FAILED, ENDED_ERROR |
| Inactive | – | "Cancelled" / "Archived" | CANCELLED, ARCHIVED, SUPERSEDED |

**Approval required** always renders the canonical action (command/target/diff hash) in `mono`
with the policy reason underneath, and two buttons of equal size; destructive approvals put
Reject on the leading side and require step-up.

**Verification** results render as a checklist of named checks with pass/fail glyphs and a link
to the output artifact; `independent = false` reviews carry a caption "reviewed on the same
account — no other resource was free".

## 11. Components (product components, not a generic kit)

| Component | Purpose | Key rules |
|---|---|---|
| **Presence line** | top of Now: "Archeus · working on 2 missions · 1 needs you" | derived from counts, never personality text |
| **Digest** | since-you-left grouped list | every bullet links to its object; Dismiss advances the per-user cursor |
| **Mission row** | one mission in any list | glyph, title, project, status line, waiting-on, age; no tokens/sessions |
| **Card** (conversation) | live view of an object inside a message | types: mission proposal, plan, approval, route explanation, diff, verification, digest; updates live; shows "inferred" chips |
| **Challenge block** | Archeus disagrees or asks | two explicit choices as buttons; never a yes/no on prose |
| **Inspector** | canonical detail of any object | fixed tabs per kind; *Why* tab always last-but-one; Timeline last |
| **Why panel** | explainability | three sections: Context used (with reasons), Policy (matched rules), Route (candidates × reason); raw record toggle |
| **Attention item** | one thing needing the user | kind icon, one-line ask, primary + secondary action, due/expiry |
| **Plan list** | task DAG as indented list with lanes | current task highlighted; approval points marked ◆ |
| **Resource row** | account with priority handle, ceiling slider, utilisation bars, health | reserve shown as hatched band; health glyph |
| **Policy grid** | action classes × scope | locked cells show a lock; simulate box |
| **Composer** | intent input | supports control verbs, `@` object mentions, file drop (meeting notes); shows "Archeus will…" preview for control verbs |
| **Command bar** | ⌘/Ctrl+K anywhere | same parser as composer + jump-to-object |
| **Graph view** | spatial inspection | encoding in research §26; keyboard traversal; list fallback |
| **Toast** | off-screen success/failure | max one at a time, 4 s, never for errors needing action |

## 12. Accessibility rules (floors, gated)

- Contrast floors in §3; High Contrast themes.
- Keyboard: every action reachable; logical tab order; skip link to main; list navigation with
  arrow keys; `Esc` closes the topmost overlay; shortcuts discoverable in the command bar.
- Screen readers: landmarks (nav, main, complementary for inspector); cards are `article` with
  a label; streaming progress in a polite live region, rate-limited to one announcement per 5 s;
  new approvals announced assertively once; Archeus messages labelled as AI-generated; graph view
  exposes a list equivalent.
- Targets: 28×28 px desktop (20 minimum for dense toolbars), 44×44 pt mobile.
- Text scaling to 200% without clipping or horizontal scroll at 390 px wide.
- No information by colour alone; no information by motion alone.
- Reduced motion, reduced transparency and forced colours (Windows High Contrast) honoured.
- Time limits: approvals show their expiry and can be extended.

## 13. Desktop adaptation

Sidebar (one level, with sub-sections inside Control only — two levels max; nothing critical at
its bottom edge — *Pause all* lives in the Now header, the tray and the command bar), inspector column,
tray menu (Open, Pause all, Emergency stop, Quit), native notifications, standard shortcuts
(⌘/Ctrl+K, ⌘/Ctrl+1–4 destinations, ⌘/Ctrl+. pause focused mission, `?` shortcuts), right-click
menus on rows, drag to reprioritise, resizable columns, compact density.

## 14. Mobile adaptation

Bottom tab bar (Now, Work, World, Attention) with the attention badge; Control behind the avatar
menu; sheets for approvals and inspectors (grabber, swipe to dismiss, one at a time — swiping an
approval sheet away means **decide later**, never reject; the item stays in Attention); pull to
refresh (re-query); safe areas; one-handed reach — primary actions in the lower half; no hover
dependence; step-up PIN pad for destructive approvals; comfortable density only.

## 15. TUI equivalents

| GUI element | TUI |
|---|---|
| State glyph + colour | same glyph when the terminal font has it, else the ASCII set `* ! # = ~ + x` (active, needs you, blocked, paused, planning, done, failed) chosen by a startup probe; ANSI colour from the token table (nearest non-system 256-colour, never 0–15, as `themes.hex_to_x256` does today); monochrome safe |
| Sidebar destinations | top line `1 Now 2 Work 3 World 4 Control ◆2 attention` |
| Inspector | full-screen pager with tab keys `o p n e t w l` (outcome, plan, now, evidence, thread, why, timeline) |
| Cards | boxed blocks with the primary action key shown (`[a] approve  [r] reject`) |
| Composer / command bar | `:` command line with the same grammar |
| Thread | `›` marker on rows changed since last look |
| Toasts | status line message, 4 s |
| Motion | none |

## 16. Tokens (single source)

`clients/app/tokens/tokens.json` (hex-first, like `themes.py`) generates:
`clients/app/src/styles/tokens.css` (CSS custom properties), `clients/app/src/tokens.ts`,
`archeus/cli/tui/tokens.py` (ANSI). A test regenerates and compares, and the contrast test reads
the same file. Adding a component never edits tokens; adding a theme never edits components.

```json
{
  "space": [0, 2, 4, 8, 12, 16, 24, 32, 48, 64],
  "radius": {"control": 6, "raised": 8, "overlay": 12, "sheet": 16},
  "type": {"body": {"desktop": [13, 20], "mobile": [17, 24]}},
  "motion": {"state": 160, "row": 200, "inspector": 220, "sheet": 280, "thread": 600},
  "themes": {
    "dark": {"bg": "#0E1116", "surface-1": "#141922", "text": "#E6EAF0",
             "primary": "#E6EAF0", "thread": "#F4F1EA", "state.attention": "#F2B544"}
  }
}
```

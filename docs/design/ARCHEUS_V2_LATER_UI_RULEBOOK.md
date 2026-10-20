# Archeus later-V2 UI — Do / Don't rulebook

**Status: PROPOSED — NOT IN FORCE.** These rules summarise
[ARCHEUS_V2_LATER_UI_RESEARCH.md](ARCHEUS_V2_LATER_UI_RESEARCH.md) (*LR*) for implementation
sessions. They apply only to a later-V2 phase the user has approved (LR §22). Until then the V1
rulebook governs V1 and [ARCHEUS_V2_UI_ARCHITECTURE.md](ARCHEUS_V2_UI_ARCHITECTURE.md) (*A*)
governs V2-U1…U6. Where a rule here conflicts with an accepted A decision, **A wins** until the
user says otherwise.

Each rule names its evidence. A rule without a test is a wish: every rule marked **[gate]** must
leave a mutation-verified check behind when it is implemented.

## 1. Principles that do not move

1. **Do** keep A's five principles: light is evidence, stillness is the canvas, depth means
   focus, objects persist, intensity is earned. (A §A)
2. **Do** keep the idle invariant: zero rAF callbacks and zero running animations when no
   recorded work is happening. **[gate]** (A §C.1)
3. **Don't** animate anything but `transform` and `opacity`. No `filter`, `backdrop-filter`,
   `mix-blend-mode`, `box-shadow`, `stroke-dashoffset`, colour over large areas, or animated
   height. **[gate]** (A §C.1, LJ-5, LMo-32, LMo-34)
4. **Don't** add an orb, hub, mascot, character, HUD bracket, holographic grid, particle field,
   bloom, glass, multi-hue glow, scanline or fabricated number. (A §U, LR §5)

## 2. Information and language

5. **Do** lead every surface with one sentence that is a verdict ("2 need you · 3 running ·
   nothing failing"), not a greeting and not a dashboard. (LM-14, LV-17, D-7)
6. **Do** show a needs-you item as **one line**: the verb, the object, the consequence, the
   expiry in words. Details live one depth down. (LA-1, LM-1, D-1)
7. **Do** give every object three depths — row, peek, page — and add one kind of information per
   depth. (LP-5, LP-25)
8. **Don't** show the same decision twice on one screen. **[gate]** (D-3)
9. **Do** put the resolving control on the same screen as every needs-you indicator, on every
   surface and device. A badge without its control is a defect. **[gate]** (LA-5)
10. **Don't** show machine language at the first two depths: no raw policy grammar, ISO
    timestamps, enum names or internal ids. Say it in words; put the raw value one level down in
    mono with a copy control. **[gate]** (D-2, LM-5)
11. **Do** write in one voice — plain, precise, impersonal, slightly dry — and shift tone by
    state: *done* brief, *needs you* decision + consequence, *failed* what broke / what was kept /
    what next, *offline* what is known and as of when. No exclamation marks, no apology
    theatre. (LV-23)
12. **Do** say what is an estimate, what is stale ("as of 14:02") and what is not verified.
    (LJ-19, LM-2)
13. **Do** separate "executed" from "verified" everywhere, and show what verification checked.
    (LM-5, LA-9, LA §4)
14. **Do** show what policy decided on the user's behalf, with its reason, as a collapsed log.
    Silence is not a record. (LA-4, LA-12)

## 3. Decisions (approvals)

15. **Do** design the decision as one surface: what will happen (one sentence) · why it asks (in
    words) · decision context (you asked / it said / last tools / waiting since) · what changed
    since the last plan version · named verbs. (LJ-14, LM-20, LM-21)
16. **Do** bind a decision to the plan version that was shown; a changed plan needs a new
    decision. (LM-10; Core's `decided_plan_version`)
17. **Do** move focus to the next decision after one is made. **Don't** drop keystrokes during
    the transition. **[gate]** (LP-22)
18. **Don't** approve from a notification or by swipe. The notification opens the decision.
    (LM-6, LM-9, LM-27, A §P)
19. **Do** treat a burst of approval requests as an alarm, not a longer list. (LM-9)
20. **Do** escalate an unanswered decision by *recorded* wait time as a change of form (wording,
    position, then the phone) — never by strobe, colour flashing or sound loops. (LJ-15, A F-4)

## 4. Mobile

21. **Do** design the phone as a different composition with the same language: three
    destinations, a persistent mission strip, pages for decisions, a vertical because-chain
    instead of a graph in portrait. (LR §8, LM-16, LM-18)
22. **Don't** put a careful decision in a bottom sheet; sheets are for quick reference, have a
    visible close, and never stack. (LM-24)
23. **Do** keep the e-stop visible in the header of every phone screen; it never collapses,
    minimises on scroll or sits behind a material. **[gate]** (LM-25, D-4)
24. **Do** size decision buttons ≥ 12 mm at the bottom edge, separated, with destructive and
    frequent actions never adjacent in a corner; leave room to scroll the decision to mid-screen.
    (LM-26)
25. **Do** push a history entry for every sheet and page so Back closes it and never exits the
    app. **[gate]** (LM-27)
26. **Don't** queue consequential actions while offline; drafts may wait and are re-shown against
    fresh state. **[gate]** (LM-10, A §O)
27. **Do** blur decision contents when the PWA is backgrounded. (LMo-13)
28. **Don't** make any gesture the only way to do something; every gesture accelerates a visible
    control. (LM-24, LM-13)
29. **Don't** promise an ETA; show the phase, the step and the elapsed time. (LM-4)

## 5. Desktop

30. **Do** spend extra width on more columns, never on longer lines: list + inspector from
    1,100; evidence inspector from 1,700; compare from 2,400. Prose ≤ ≈ 80 characters. (LP §3)
31. **Do** treat pane sizes and layout as user state that survives updates. **[gate]** (LP-24)
32. **Don't** float panels over work or scale the application. (LP-8, PR-3)
33. **Do** recede the chrome one step below the content; keep a boundary floor between sections.
    (LP-2, LP-3)
34. **Do** remove web tells in the Qt shell: no pointer cursor on every control, no hover wash on
    every row, no unpainted or stale frame on show or route change. (LP-14, LP-30)
35. **Do** keep a keyboard decision loop: j/k, Space to peek, Enter first action, Ctrl+Enter
    second, palette for everything. (LP-22, LA-1)

## 6. Motion

36. **Do** make motion inversely proportional to frequency: 100+/day or keyboard-initiated →
    none; tens/day → ≤ 160 ms opacity/colour; several/day → 200–320 ms spatial from the source;
    rare → gated hero. (LMo-3, LMo-10, LP-21)
37. **Do** start motion at its cause and keep paths symmetric; one spatial primitive at a time
    per region. (LMo-1, LMo-20)
38. **Do** make every motion interruptible to its end state; input is never blocked. **[gate]**
    (A F-5, LMo-1)
39. **Don't** exceed 4 % overshoot (spring damping ζ ≥ 0.72); effects (colour, opacity) never
    overshoot. (A §C.3, LMo-2, LMo-4)
40. **Don't** stagger list entrances, slide peer navigation, bounce state chips, or loop any
    indicator beside content. **Never** a sustained oscillation near 0.2 Hz. (LMo-21, LMo-24,
    LMo-3)
41. **Do** register every primitive in `tokens/motion.json` with its meaning, trigger, duration,
    curve, distance, max frequency, ladder level and reduced/quiet forms (LR Appendix 2).
    **[gate]**

## 7. Visual depth and identity

42. **Do** create richness by ranking, scale and truth: one dramatic typographic jump per
    surface, four opaque planes, one light direction, tabular figures. (LV-1…LV-5)
43. **Do** treat the thread as the verb and the day's light as the noun; both are drawn only from
    the record, and every mark opens what it represents (proof of life). (LV-11, LV-13, A §J)
44. **Do** use one scale across days and encode outcome by shape as well as colour in any
    identity visual. (LV-12, LV-14, PR-5)
45. **Don't** use structure as decoration: a time ruler under a timeline is allowed; a grid
    behind content is not. (LV-5)
46. **Don't** add weights other than 400 and 600 or try to drive the optical-size axis; Qt reaches
    only named instances. (PR-4)

## 8. Accessibility

47. **Do** give every primitive a reduced form (crossfade ≤ 160 ms or instant with focus kept)
    and a quiet form; motion never carries meaning alone. **[gate]** (A §C.7, LMo-23, LMo-30)
48. **Do** draw focus and selection with `outline`, so they survive forced colours; every state
    stays distinct by shape alone. **[gate]** (LMo-48, PR-5)
49. **Do** keep every layout working at 200 % text: rows wrap, buttons stack, verbs and
    consequences never truncate; re-measure expanded content on resize and font load. **[gate]**
    (A §F)
50. **Do** announce every async state change once, politely (arrival assertive once). (A §P,
    LMo-14)

## 9. Performance and dependencies

51. **Do** price every addition before it lands: gzip size, CPU, Qt p95 frames on integrated
    graphics, and its reduced/high-contrast/forced-colours/phone forms. **[gate]** (A §Q)
52. **Don't** add an animation or UI library; the platform (WAAPI, `linear()`, `@starting-style`,
    Popover, anchor positioning once verified in Qt) covers it. (LMo-37, A §R)
53. **Don't** use `interpolate-size`/`calc-size()` for animation, leave `will-change` in a
    stylesheet, or reopen View Transitions in Qt 6.11. (LMo-32, LMo-36, PR-2)

## 10. Sound and haptics (only if LD-10 is approved)

54. **Do** keep sound off by default; at most two earcons (needs you; failed/stopped), played only
    when the window is unfocused, always paired with a visual and text cue. **Don't** sound
    routine success. (LV-32, LMo-40…44)
55. **Do** treat haptics as Android-only and never the only cue. (LMo-45, LMo-50)

# ARCHEUS V2 design layer

25 October 2026. Standalone, local design assets for `v2/live-design`. No application files changed. This is a review and adoption kit, not a replacement simulation or Core client.

## Open the atlas

From this directory, run `py -m http.server 8000`, then open `http://localhost:8000/gallery.html`. ES modules require HTTP. Everything is served locally; there are no external imports, fonts, dependencies, telemetry, or service workers.

The atlas contains three independently scrolling frames at actual CSS widths of 390, 768, and 1280 pixels. Horizontal scrolling preserves their real container sizes. The shared appearance selector applies Dark, Light, Dark HC, Light HC, System, or simulated Forced colors to all frames. Quiet suppresses optional motion and exposes the static running count. OS reduced motion and real forced colors take precedence. A single specimen can also be opened as `gallery.html?specimen=1&theme=light&motion=reduced` and resized freely.

## Principles

| Principle | Implementation | Source / reason |
|---|---|---|
| A space, not a dashboard | Sparse constellation, centered core, generous separation, warm ink; no KPI tile wall | All 15 concept PNGs, especially 02, 07, 09, 15 |
| Light reveals depth | Opaque surface steps, static radial light, hairlines; no filter, backdrop filter, blend mode, or shadow | Visual language §8; concepts 02–04 |
| Meaning survives monochrome | Every state has a shape and a written word; current / passed / ahead use fill and line styles | Visual language §5, §9 |
| Attention is specific | Decision cards show What, Why, and action. Their state accents are horizontal; the thread retains the left edge | Visual language §8 |
| Calm remains calm | No automatic gallery animation. Only eligible app core may loop | ADR-0055 |
| Existing decisions stay authoritative | Approved Light palette unchanged, sans headings and wordmark, serif sentence only | Owner decisions and visual language §6 |
| Integration remains small | Namespaced component classes; existing token names; icon signature unchanged | Builders can adopt one screen at a time |

## Files and contracts

| File | Contract |
|---|---|
| `tokens.css` | Local snapshot of existing `clients/v2-live/css/tokens.css`, comments removed. Palette values and theme rules preserved. For adoption use the app's existing tokens rather than load both copies. |
| `components.css` | Load after tokens. Put `class="ds"` on the containing surface and `class="ds-container"` on a width-owning ancestor. Uses named `ds` container queries at 600 / 1024 / 1920 px. No global body reset. |
| `icons.js` | `icon(name, size = 22)` returns decorative SVG DOM, matching existing API and default size. Named `P` export is additive. Every existing key retained; over 60 total. 24 px grid, 1.5 stroke, round caps. Relative `./dom.js` matches both this kit and the app's `js/` folder. |
| `dom.js` | Local copy of app element builders; text stays text, never HTML. No runtime import outside this directory. |
| `brand.js` | `wordmark()`, `lockup()`, `coreMark(running = false, count = 1)` return DOM. `faviconSVG` / `pwaIconSVG` export standalone SVG strings. No animation or read subscription in JS. |
| `favicon.svg`, `pwa-icon.svg` | Ready-to-copy SVG assets; PWA artwork stays within maskable safe area. Export PNG variants when a target platform requires them; no manifest / installation claim. |
| `illustrations.js` | `illustration(name, label?)`: `missions`, `clear`, `offline`, `error`, `first`. Decorative by default; optional label creates a named image. |
| `fonts/` | Existing local Libre Caslon Text font and OFL copied together. Only state sentence uses it. No new font dependency. |
| `gallery.html`, `gallery.js`, `gallery.css` | Review harness only. Native interactions and fixture feedback; no persistence, Core, authentication, or application state machine. |

## Token usage and materials

| Role | Tokens | Use |
|---|---|---|
| Ground | `--bg` | App frame and surrounding space |
| Resting material | `--s1` | Cards, rail, saved records |
| Group / selected material | `--s2` | Controls, table headers, bands |
| Raised material | `--s3` | Solid sheet, chat bar, slash menu, tooltip, toast |
| Ink | `--text`, `--text-2`, `--text-3` | Primary fact, explanation, metadata; never opacity-dim body text |
| Rules | `--line`, `--line-strong`, `--hair` | Decorative boundaries, control boundaries, HC thickness |
| Primary action | `--primary`, `--on-primary` | Ivory on dark, dark ink on Light |
| Focus | `--focus` | 3 px outline + 3 px offset; Dark resolves to approved #FFF3CF; real forced colors uses Highlight |
| Semantic confirmation | `--done`, `--active`, `--attention`, `--blocked`, `--paused`, `--thinking` | Glyph and state edge, with word alongside |
| Decision band | `--band` | Existing opaque approved material. State word remains `--text`; attention glyph carries color |
| Overlay veil | `--scrim` | Scrim only. Content surface remains opaque |
| Signature light | `--thread` or state token | Radial gradient at 4–9% ink, fading to transparent; never behind low-contrast semantic text as a tint |

All new defaults are declared together in the opening `:root` block of `components.css`. `--ds-edge` and `--ds-glow` are local semantic aliases, reassigned by `data-state`. Geometry / type additions do not create a second palette. `color-mix()` is decorative enhancement: if unsupported, solid background and hairline remain sufficient.

| Elevation | Material | Edge / light |
|---|---|---|
| Ground | `bg` | No frame around empty space |
| Card | `s1` | Hairline; state-colored top edge; static inner light on hover / focus |
| Selected | `s2` | Stronger rule, explicit selected state |
| Raised | `s3` | Strong rule; no translucent content or drop shadow |
| Attention | `band` | Horizontal attention rules; state word in primary ink |

## Component anatomy

| Component | Structure / class | Meaning / interaction |
|---|---|---|
| App frame | `.ds-container > .ds-frame`; `.ds-rail`, `.ds-main`, `.ds-inspector`, `.ds-bottom` | Phone main + bottom navigation; tablet 68 px rail; desktop 192 px rail and 300 px inspector. No phone Map item. |
| Mission card | `.ds-card[data-kind="mission"][data-state]` | Object icon + kind + badge; title; explanation; compact spine |
| Decision / approval | `data-kind="decision"` / `approval` | Band, reason, consequence where relevant, explicit approve / reject |
| Status card | `data-kind="status"` | State, reason inline, recovery action |
| Plan | `data-kind="plan"` | Proposed numbered steps; never imply execution |
| Idea | `data-kind="idea"` | Dashed proposed edge; text says unscheduled |
| Knowledge | `data-kind="knowledge"` | More squared record material; provenance / confirmed text |
| Badge / chip | `.ds-badge[data-state]`, `.ds-chip` | Passive badge has glyph + word; interactive chip uses button and `aria-pressed` |
| Button | `.ds-btn`, `.primary`, `.quiet`, `.danger` | 48 px minimum in both axes; text labels or accessible names on icon-only controls |
| Segmented | `.ds-segmented` | Button group, one `aria-pressed=true`; visible selected edge |
| Tabs | `.ds-tabs`, `.ds-tab` | Why / Relations / Evidence; ARIA panel associations and roving keyboard focus in gallery |
| Toggle | `.ds-toggle > input[type=checkbox][role=switch]` | Native keyboard activation; thumb position and checked state |
| Input | `.ds-field`, `.ds-input`, `.ds-select`, `.ds-textarea` | Persistent label, native controls, inline error and `aria-describedby` |
| Chat bar | `.ds-chat` | Textarea + submit, label and shared focus ring; gallery captures text locally only |
| Slash menu | `.ds-slash` containing list-item buttons | All items Tab-reachable; native list, not an ARIA menu requiring custom arrow behavior |
| Sheet | `.ds-sheet-stage`, scrim, `.ds-sheet`, head / body / foot / grab | Bottom on phone; right side on tablet; squared inspector at desktop. Scroll body, persistent actions. |
| Usage meter | `.ds-meter`, track, fill | Numeric value and accessible meter. Marks every 20%. Review threshold explicitly worded at 20%. Unknown is hatched and labeled Unknown, never zero. |
| Spine | `.ds-spine` with `.ds-station` | Six Core station words; accessible sentence; passed check disc / current ring with dot / hollow ahead; dotted unknown |
| Table / list | `.ds-table-wrap`, `.ds-table`, `.ds-list` | Native headers; 44 px minimum rows. Tables scroll without shrinking text. |
| Toast | `.ds-toast` | Explicit dismiss, no timeout. Dynamic gallery notice has polite live region. Errors remain inline. |
| Tooltip | `.ds-tip-wrap`, `.ds-tooltip` | Hover / keyboard focus; Escape dismisses; real accessible name on trigger |
| Empty / offline / error | `.ds-empty`, `.ds-banner`, illustration | Specific fact, saved timestamp for offline, recovery action for errors |
| Skeleton | `.ds-skeleton` | Static and `aria-hidden`; container names loading state. Optional explicit `data-shimmer="once"` preview only. |
| Divider | `.ds-divider` | Native `hr`, decorative hairline |
| Scroll area | `.ds-scroll` | Keyboard focusable region, stable content, local/scroll background fade edges; no mask hiding text |

## State glyphs

These are presentation examples requested for this layer. Existing Core state-to-presentation mapping remains authoritative during adoption; do not replace `present()` with a color lookup or infer domain state from these samples.

| State word | Shape | Token | ASCII equivalent |
|---|---|---|---|
| Done | Solid disc | `done` | `+ Done` |
| Running | Hollow ring | `active` | `o Running` |
| Needs you | Highlighted ring with solid center | `attention` | `! Needs you` |
| Blocked | Hollow octagonal boundary with cross | `blocked` | `x Blocked` |
| Paused | Two vertical bars | `paused` | `|| Paused` |
| Thinking | Three static dots | `thinking` | `... Thinking` |

| Spine fact | Shape / segment | Text equivalent |
|---|---|---|
| Passed station | Solid disc with contrasting check; solid incoming segment | Station name + accessible progress sentence |
| Current station | State glyph; Running gets ring + filled center; solid incoming segment | `aria-current="step"`, sentence names current station |
| Ahead | Hollow ring; dashed incoming segment | Unreached stations remain named |
| Unknown hold | Dotted ring and segments | “Blocked, position unknown.” No guessed position |
| Completed mission | Six checked discs | “Done, all 6 steps passed.” |

Station words are **Understanding / Planning / Approval / Executing / Verifying / Reviewing**, read from current `spine-model.js`, rather than the shorter imperative labels in early concepts. Row, card, inspector mark sizes are 8 / 10 / 16 px. Phone inspector wraps into two rows of three. Gallery's renderer demonstrates known fixtures only: keep existing `spineOf(state, held_from)` for real mapping, including Created, Cancelled, Approved, Failed, and Resumed cases.

## Spacing, type and shape

| Scale | Values | Use |
|---|---|---|
| Space | 4 / 8 / 12 / 16 / 24 / 32 / 48 px at default root size | Glyph gap; controls; rows; card padding; section separation |
| Body | Phone 17 px / 1.5; frame tablet / desktop 13 px / 1.5 | Existing device density retained; component catalog outside app frame stays 17 px for review |
| Caption | 13 px / 1.4–1.5 | Timestamp, source, explanation |
| Title | 22 px / 1.25; section 18 px | Sans headings; weight 600 |
| State sentence | 28 px / 1.2; gallery display up to 40 px | Libre Caslon Text, weight 500; only serif use |
| Mono | Existing `--mono`, tabular numerals | Usage, branch, terminal, timestamps |
| Eyebrow | 12 px, tracking .14em | Short object-kind labels, not paragraphs |
| Wordmark | 14 px sans, tracking .23em; V2 10 px | Quiet compact lockup; no new serif-heading decision |
| Radius | 6 / 12 / 20 px; badge pill | Controls / cards / phone sheet |
| Touch | Controls >=44 px, buttons 48 px, rows >=44 px | No invisible overlap to fake a target |

Gallery's atlas heading and specimen display are review typography; the component app frame retains the supplied application density. At 1920 px container size the frame body rises to 15 px and display to 32 px. Root font scaling remains supported; no transform-based device shrink.

## Motion beats

| Beat | Implementation | Eligibility / equivalent |
|---|---|---|
| Hover, focus, tabs, selection, spine redraw | Instant | No transition; no decorative feedback loop |
| Core breath | `.core-breath` child of `[data-core="breath"][data-live="true"]` under `[data-motion="full"]` | Scale 1 → 1.018 → 1; 6000 ms; ease-in-out; OS no-preference only |
| Quiet / OS reduced motion | No animation, scale 1 | Static core plus `N running` text when running fact holds |
| Loading | Static by default | ADR-0055 explicitly says skeletons do not move |
| Requested shimmer preview | Explicit `data-shimmer="once"`; 600 ms transform, one iteration; full mode + OS no-preference only | User-invoked gallery preview; do not adopt into app without resolving ADR conflict |
| Badge change | No automatic fixture beat | App may retain registered 160 ms cross-fade; CSS layer does not invent event timing |
| Sheet / toast | Instant in this kit | App can retain registered 280 / 160 ms entries once bound to real presentation events |

The app owns breath eligibility. Start only for a **fresh current read with active executions, visible document, and Full motion**. Stop on hidden document, stale/failed read, loss of live connection, no active execution, Quiet, or OS reduced motion. Set `data-core="idle"` when ineligible. Do not use gallery fixtures as liveness evidence. The gallery deliberately never sets `data-core="breath"`. Use only one eligible core per Now surface. `brand.js` does not subscribe, schedule, or animate.

## Accessibility and adoption limits

| Rule | Implementation / builder responsibility |
|---|---|
| Color is supplementary | Word + glyph in every badge; spine fill, line style, word and sentence |
| Existing palette contrast | Exact approved tokens reused; no fresh contrast measurement claimed. Decorative low-contrast hairlines are not state evidence. |
| Focus | Dark focus token retained; outlines are never removed except textarea inside focused chat group |
| Native first | Buttons, textarea, select, checkbox, table, list; tabs implement Left / Right / Home / End |
| Tooltip | Hover / focus, accessible description, Escape dismissal. Never put essential information only in tooltip. |
| Error | Persistent inline reason, no shake, no failure toast or automatic retries |
| Offline | Last-saved timestamp, hollow presence / offline icon, explicit offline word |
| Motion | System reduced motion wins even when Full is selected; no fixture breath |
| High contrast | Existing HC tokens and 2 px hairlines; decorative card light removed |
| Real forced colors | System tokens, native switch fallback, filled passed checks retain Canvas contrast; focus uses Highlight |
| Modal integration | Gallery sheet is an inline section, not falsely labeled modal. App must supply dialog focus entry / trap / restore, inert background, Escape, and actual dismissal policy. Use native dialog where possible. |
| State safety | Keep `core-words.js`, `spine-model.js`, action gating and confirmation policy. This layer does not authorize any action. |
| SVG semantics | Icons decorative; visible control labels or `aria-label` required. Illustrations decorative unless explicit label supplied. |
| Zoom / text | Rem spacing and type, flexible wrap, 44–48 px minima; browser probe still required at 200% and 400%. |

## Adoption map

Load `components.css` after the existing token sheet. Add `ds` and `ds-container` to an appropriate ancestor; then adopt markup one component at a time. The stylesheet intentionally does not alias every old class and is not a global replacement for `app.css`. Preserve existing event handlers, text sources, IDs, and focus / action semantics.

| Existing file / region | Existing classes / function | Adopt / restyle | Preserve |
|---|---|---|---|
| `css/tokens.css` | Root theme sets | Keep existing file; do not copy palette twice | Six theme modes and approved Light values |
| `css/app.css`, shell | `.app`, `.rail`, `.main-col`, `.inspector`, `.bottombar` | `.ds-frame`, rail / main / inspector / bottom within width container | Existing app shell positioning, router, selected navigation and Chat below 600 px |
| Shell navigation | `.nav-item`, `.bb-item` | `.ds-nav` | `aria-current`, counts, route destination |
| `js/views.js` Now | `.now-hero`, `.state-sentence`, `viewNow()` | `.ds-state-sentence`, spaced hero | `sim.sentence()` and truthful counts |
| `js/views.js` panels | `panel()`, `.panel`, `.body`, `.cols` | `.ds-card`, `.ds-stack`, `.ds-grid` selectively | Group headings, DOM reading order |
| Work / Now | `missionRow()`, `.mrow`, `.t`, `.m`, `.sp` | 44+ px list row or mission card | Existing route and compact spine |
| Attention | `attentionItem()`, `.card`, `.band`, `.top`, `.ttl` | Decision / approval / status card recipes | What / Why / consequence, `present()` words, no left attention band |
| Badge helper | `badge()`, `.badge[data-role]`, `.g`, `.w` | `.ds-badge[data-state]` plus requested vector presentation where approved | Machine state label from `present()`; do not silently replace domain glyph mapping |
| Shared actions | `.btn`, `.primary`, `.quiet`, `.danger`, `.actions` | `.ds-btn` variants, `.ds-row` | Action handlers and disabled conditions |
| `js/icons.js` | `icon(name,size)` | Replace file with this `icons.js`; existing `dom.js` import works | Every old icon name and 22 px default |
| `js/views.js`, map | `coreMark(live,n)`, `.core`, `.core-mark`, `.core-txt` | `brand.js` core and `.core-breath` | Adapter needed: app function's `live` argument means factual live work, not animation permission |
| `js/map.js` | Center overlay / graph | Optional static constellation geometry and core recipe | Existing graph layout, object encodings, accessible text mirror; mission circle, execution triangle, decision diamond |
| `js/spine.js` | `spineRow/Card/Inspector()`, `.spine`, `.spine-card`, `.spine-insp` | Adopt ds station markup or port appearance to original SVG renderer | `spineOf()` and every special-state case; gallery renderer is fixture-only |
| Inspectors | `inspectorMission/Approval()`, `.grab`, `.insp-head/body/foot`, `.tabs`, `.tab` | Sheet anatomy and tabs | Existing content tabs / state; Why / Relations / Evidence specimen is not instruction to delete Outcome / Plan / Now / Timeline |
| `js/views.js`, accounts | `meter()`, `.meter`, `.bar`, `.warn`, `.unk` | Meter track, 20% divisions, accessible value and Unknown form | Actual usage reader; 20% weekly review threshold is not a new provider quota |
| Chat code / `css/app.css` | `.composer`, `.slash`, `.slash-row`, `.cardbox`, `.msgs` | Chat bar, slash list, decision card | Existing command parser, fixture actions and message labels |
| Settings / appearance | `.chips`, `.chip`, `.sel-wrap` | Chips, segmented control, native field / toggle | Store choices, System behavior, language switch and notes setting |
| Replay | `.tl`, `.tl-row`, `.cat` | List / table material and spacing | Replay categories, UNKNOWN / pruned records, no re-run action |
| Toast helper | `.toast` | `.ds-toast`, polite live region for neutral success | No failure toast; explicit dismiss; focus stays on initiating control |
| Empty helper | `empty()`, `.empty` | `.ds-empty` with illustration | Specific reason and truthful unknown / offline wording |
| `css/app.css` | `.sep`, `.stack`, scrolling regions | Divider / list / scroll recipe | Native scrolling and screen-specific sticky regions |
| Terminal | `.term-screen`, `.term-keys` | Token and mono alignment only; gallery includes text equivalent | `term.js` semantics, ASCII fallback and keyboard commands |

Suggested sequence: icons and buttons → badges and cards on Attention → Now sentence and core → Work rows and spine appearance → inspectors → Chat → Accounts and Settings. Review each screen in all six looks at phone, tablet, and desktop widths before broadening.

## Do / don't

| Do | Don't |
|---|---|
| Leave breathing room around a specific fact | Fill every gap with a border or metric |
| Use ink text on attention material | Put amber body text on the Light band |
| Use static, localized radial light | Blur a full-screen backdrop or animate glow |
| Keep one strong primary action per decision | Make approve, reject and secondary actions equally loud |
| Name time and freshness | Animate to imply output that did not happen |
| Keep source state words | Rename Core states to suit a prettier diagram |
| Let unknown remain unknown | Guess a hold position or turn unknown usage into zero |
| Keep headings and wordmark sans | Spread display serif through navigation and tables |
| Use self-contained local assets | Reach outside this directory at runtime |

## Verification and open decisions

No browser, server, test, syntax runner, rendering probe, contrast measurement, screen-reader session, or network used for validation. Source and asset references were read manually. All 15 concept images were visually inspected through the available local image reader. Claude must run rendering and interaction probes before adoption; this document makes no visual-pass claim.

| Review item | Recommendation |
|---|---|
| Skeleton shimmer conflicts with ADR-0055 static skeleton rule | Keep static default. Leave explicit gallery preview out of app unless owner amends motion rule. |
| Requested state glyphs differ from existing presentation-class figures | Review vector glyph adoption with owner / presentation owner. Preserve existing domain mapping meanwhile. |
| Core geometry and sans wordmark are proposed assets | Review against concept mood before replacing application identity assets; no new serif-wordmark decision assumed. |
| Font asset budget | Kit copies existing 126,876-byte TTF and OFL for offline independence. Production builder should use approved content-hashed subset pipeline; this kit does not claim the <=40 KB production font budget. |
| Real forced-colors, zoom, font swap and hit targets | Claude probes required; palette inheritance does not prove rendered contrast or effective hit area. |
| Full app integration | No app changes made. Focus traps, fresh-read gating, router handlers and Core semantics remain builder responsibilities. |

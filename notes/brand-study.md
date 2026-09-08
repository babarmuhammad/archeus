# Brand study: archeus

Internal. Not published; `docs/` is the manual and this is the reasoning behind the
words in it. Written alongside the repositioning that replaced *"The workspace layer for
Claude Code"* with the sentence in §3.

**Scope, and the sibling document.** This study owns the *meaning, the copy and the
colour*. `notes/constellation-study.md` owns the *geometry* — the figure the mark, the
backdrop and the architecture graph all draw — and is being implemented in parallel. Where
the two touch (§5.3, §6) that document wins on shape and this one on why the shape is
right.

---

## 1. What the name means

**Archeus** is Paracelsus's term (De Natura Rerum, ~1537) for the *vital principle*: the
organising force he held responsible for keeping a living body coherent — sorting what
belongs from what does not, directing growth, and repairing what decays — while the body
grows and its parts change. It is not the body and not the soul. It is the thing that
keeps a body *one thing* over time.

That is a literal, not a poetic, description of what this product does.

| The old idea | The software |
|---|---|
| Keeps a body coherent *while it grows* | Keeps a project's context coherent while the codebase grows |
| Sorts what belongs from what does not | `memory.py` consolidation: duplicate entities merge, the least-connected are evicted under a global importance cap |
| Directs growth rather than adding mass | The always-on CLAUDE.md block is a ≤250-token index that does **not** grow with the repo; detail is pushed into path-scoped `.claude/rules/` |
| Repairs what decays | Temporal facts — a superseded fact is invalidated with a timestamp, kept as history, never injected. Lessons decay when unused |
| Is not the body | archeus is not the agent. It configures and launches Claude Code; every coding turn is the agent's |

The last row is the one that matters most for positioning, and it is why the name was
worth the rename. A "workspace manager" is furniture. An *archeus* is the thing that
keeps something else alive and whole — which is exactly the relationship this software
has to a coding agent, and exactly the relationship the old name (`claudectl`, a control
utility for one vendor's CLI) could not express.

Two consequences follow from the meaning, and everything in §3–§6 is downstream of them:

1. **Memory leads, workspace follows.** Coherence-over-time is the memory graph. The
   session archive and launch control are how you reach it. The old sentence put the
   furniture first and never said the word *memory* at all.
2. **The agent is a parameter, not the subject.** An archeus is defined by the body it
   sustains, not by which body. This is what makes "for AI coding agents" a statement
   about the *kind* of thing archeus is, rather than a claim about integrations that do
   not exist. See the tone rule in §4.4 — it is only honest if the roadmap stays roadmap.

---

## 2. Where the meaning is allowed to show

The name is obscure. That is a cost, and the answer to it is **never to explain it in
product copy**. A tagline that has to teach you a 16th-century alchemical term has failed
before it starts, and `docs/index.md`'s Rust-disambiguation admonition already proves how
much space a name can eat.

So the meaning is carried structurally, not verbally:

- the **sentence** says what an archeus does, in the reader's words (§3)
- the **voice** behaves like an archeus — it prunes, it names decay, it does not accrete
  (§4)
- the **mark** is a bounded solid that holds its shape (§5)
- the **backdrop** is one calm field that responds to real state and stops when nothing
  is happening (§6)

The word "archeus" is explained in exactly one place in the shipped text: the 2.0.0 entry
in `CHANGELOG.md`, where the rename has to be justified anyway.

> "In Paracelsian alchemy the *archeus* is the organising principle that keeps a body
> coherent as it grows, which is the job here." — `CHANGELOG.md`, 2.0.0

That is the whole of it, and it should stay the whole of it. The same entry records the
*other* reason the name changed, which is the one this study builds the positioning on:
"the tool is outgrowing what the name says: reading and managing *other* agent harnesses'
state is the next piece of work, and a tool named after one vendor's product cannot carry
it." The rename and §3's sentence are the same decision, ten months apart.

---

## 3. The sentence

Canonical, verbatim. This is the string `tests/test_brand_copy.py` asserts:

> **The memory and workspace layer for AI coding agents.**
> Persistent per-project memory, every session you have ever had, and control over what
> the next one costs. Works with Claude Code today.

Short slots (description fields, taglines) take the first sentence alone:

```
The memory and workspace layer for AI coding agents.
```

Held **separate**, and stated as a long-term goal, never as a feature:

> *Where this is going:* provider-neutral memory, then an open harness of its own. Claude
> Code is the first surface, not the boundary.

### Why the old sentence was replaced

*"The workspace layer for Claude Code"* had three faults, in increasing order of cost:

1. **It never said "memory".** The memory graph is the hardest thing in the codebase
   (`memory.py`, `context_inject.py`, `.claude/rules/` generation, recall ranking by
   Reciprocal Rank Fusion) and the only part with no equivalent anywhere else. It was
   invisible in the pitch and appeared first at bullet three.
2. **It named one vendor's CLI as the category.** Both of the problems the README
   describes — forgetfulness between sessions, and a context file whose cost grows
   monotonically — are properties of terminal coding agents in general. Scoping the
   sentence to Claude Code scoped the *problem* to Claude Code, which is smaller and less
   true than the thing being sold.
3. **It had already drifted.** `plugin/.claude-plugin/plugin.json` and
   `.claude-plugin/marketplace.json` said *manager*, not *layer*; `CLAUDE.md` still said
   *Windows workspace manager* long after CI started testing macOS and Linux. Three
   phrasings of one positioning, in a repo with no gate on any of them.

Fault 3 is the reason this study ends in a table and a test rather than a slogan. A
sentence with no gate is a sentence that becomes three sentences.

### The clause that does the work

`Works with Claude Code today` is load-bearing in both directions. It is the honest
statement of the only supported surface, *and* it is what earns the right to say "AI
coding agents" in the first clause without the sentence becoming a promise. Remove it and
the pitch is a lie; remove "for AI coding agents" and the product is furniture again.

---

## 4. Tone of voice

Derived from the voice the docs already have — these are descriptions of existing
practice, not new rules. Each has a citation and, where it exists, the counter-example
that motivated it.

### 4.1 Plain declarative sentences

Subject, verb, object. No inversion for drama, no rhetorical questions outside a heading.

> "`/resume` is the closest built-in. It reattaches you to a recent session in the current
> directory, and for 'put me back where I was five minutes ago' it is faster than anything
> else — including archeus." — `docs/compare.md`

### 4.2 No marketing verbs

Banned: *empower, unlock, supercharge, seamlessly, revolutionise, leverage, effortlessly,
game-changing, blazing-fast*. Also banned: superlatives the repo cannot measure. The
docs' strongest available claim is an arithmetic one, and it is stated as arithmetic:

> "Fixing it took this repository from 22,238 always-on tokens to 18,363 — 3,875 off every
> single turn." — `www/lib/content.ts`, station 04

A number with a method beats an adjective. If there is no number, there is no claim.

### 4.3 Name the cost

Every capability paragraph states its price in the same breath. This is the rule the
product's whole token-economy argument depends on, and it is already the docs' habit:

> "**The memory features cost tokens to build.** Extraction and lesson distillation are
> Claude calls. They are routed to a cheap model and run rarely, but they are not free —
> the saving is on the per-message context you stop paying for." — `docs/compare.md`

> "**The honest limit:** this is lexical retrieval. A query that shares no vocabulary with
> the stored summary will miss, and no weight tuning changes that." — `docs/memory.md:40`

`docs/compare.md` §"What archeus does not do" exists for this reason and must not shrink.
A comparison page that only lists strengths is not useful — and a limits section that is
edited only when someone complains stops being a limits section.

### 4.4 Say what it does today; say separately where it is going

Two paragraphs, never one sentence. A roadmap item folded into a feature list is a claim,
regardless of tense. The pattern in use:

> "A long-term goal, not a feature, and none of it ships today: provider-neutral memory,
> then an open harness of its own. Claude Code is the first surface, not the boundary."
> — `docs/getting-started.md:30`

`tests/test_brand_copy.py::test_the_direction_is_stated_as_a_goal_and_not_as_a_feature`
enforces both halves: the direction has to be present *and* it has to be labelled a goal.
Stating one without the other is how "provider-neutral" becomes a support request.

### 4.5 Lower case for the product, always

`archeus`, never `Archeus`, never `ARCHEUS` in prose — including at the start of a
sentence, where the fix is to reorder the sentence rather than to capitalise the name.
`ARCHEUS` is the wordmark (§5.2) and appears only as an image or a lockup. `tools/_rename_brand.py`
carries the `Claudectl`/`CLAUDECTL` substitutions for historical text; nothing new should
need them.

### 4.6 Second person for the reader, third for the software

"You pick a project"; "archeus maintains the graph". Never "we". There is one author and
a "we" in a solo project reads as a marketing department that does not exist.

### 4.7 Em dashes are for the aside that carries the cost

The house punctuation, used heavily and deliberately — it is how a claim and its price fit
in one sentence. Two per sentence is the ceiling; three means the sentence wanted to be
two.

---

## 5. The mark, in three tiers

One artwork, three renderings, each with a job no other tier can do. All three derive from
a single hand-drawn source; nothing is generated from a hue ladder. (That mistake was made
once already, on the *palette* side — `gui.py` used to rebuild every GUI surface from the
accent's hue, which made every dark theme the same theme rotated on a colour wheel. See
the themes note in `CLAUDE.md`.)

### 5.1 Dark tile — the app and OS icon

**Source of truth: `docs/assets/logo.png`** (1254px, artwork off-centre, soft drop shadow
running to the canvas edge). A cream/gold letterform inside a near-black rounded tile,
with an orbital ellipse crossing it and one bright node on the orbit. The orbit *is* the
archeus reading: a bounded form with something in motion around it that never leaves.

`tools/make_icon.py` is the only consumer and does exactly two things to the source, both
of which matter:

- **Crops to the tile**, taken from the alpha channel at `_TILE_ALPHA = 128` with
  `_FEATHER = 4`. An icon must not carry a baked drop shadow — every OS draws its own —
  and an off-centre one looks wrong the moment it sits beside another icon in a taskbar.
- **Saves from the largest frame.** Passing `sizes` alongside a small base silently keeps
  only 16×16.

Targets: `claude_sessions/archeus.ico` (Qt window, shortcuts, taskbar pin — inside the
package, because `package-data` ships it from there and a repo-root copy meant every pip
and pipx install ran with no icon at all), `docs/assets/favicon.ico`,
`www/public/favicon.ico`. Sizes 16/32/48/64/128/256.

This tier assumes a dark ground and is the only tier allowed to carry its own background.

### 5.2 Light lockup — README, OG card, social

The word **ARCHEUS** set large, with the tile to its side. Rendered by
`tools/make_og_card.py` to `docs/assets/og-card.png` *and* `www/public/og-card.png` —
both, from one run, because this used to write the docs copy and leave `www/public/` to be
updated by hand, and the two had drifted apart by a kilobyte.

Card palette, which is the app's `--grad` and not a separate brand palette:

| Role | Value | Also used as |
|---|---|---|
| `NAVY_TOP` / `NAVY_BOT` | `#10203C` → `#050810` | card ground, vertical gradient |
| `CYAN` | `#7DCFFF` | wordmark, left accent rule top, footer URL |
| `VIOLET` | `#8A5CF6` | left accent rule bottom, bullet dots |
| `TXT` / `DIM` | `#DBE4F3` / `#7D8AA5` | tagline / bullets |

The layout constraint is worth recording because the new sentence broke it: at 44px the
canonical sentence measures 1155px of a 1200px card, which both crowds the right edge and
— since the mark is sized from the *measured* text width, not a fixed number — dropped
the mark below the 160px floor and skipped it entirely. `TAG` is therefore wrapped
(`TAG_W = 600`, breaking after "layer", the only break in the sentence that does not split
a phrase) at one font size down. `TAG` stays a single string: the gate greps this file for
the sentence, and a hand-split literal would hide it.

Fonts: Windows-shipped (Bahnschrift → Segoe UI → Consolas) with a DejaVu fallback so a
Linux CI run produces something rather than dying. No `@font-face` anywhere in the product
— the GUI is self-contained and works offline.

### 5.3 Monochrome glyph — inline, `currentColor`

`www/components/site/Mark.tsx` — inline SVG rather than a file, one request fewer,
`viewBox="0 0 32 32"`, and it is deliberately the same figure the journey scene draws
(`www/components/journey/scene.ts`), so the mark and the backdrop are one object at two
scales.

**Which figure that is, is changing under this study.** Today it is a dodecahedron
silhouette: outer hexagonal contour, internal edges from the top vertex, one filled node.
`notes/constellation-study.md` is replacing it with a *cluster* — a wireframe hull holding
a population of smaller points, tied to neighbouring hulls by filaments — and that
document, not this one, is the authority on the geometry. Its argument is the correct one
and it is the same argument as §1: "The dodecahedron was a *solid* … It says 'here is a
thing'; the project's subject is 'here is a thing made of things, and it is connected to
other things'." A closed platonic solid says *finished*. An archeus is what holds
something coherent *while it grows*, which is a statement about a population, not about an
object.

Everything below in this section is about colour and reach and holds for either figure.

**The requirement this tier exists to satisfy:** it has to survive 39 palettes (32 offered
in the picker, 7 owned by a world), of which 4 are light (`catppuccin-latte`, `dawn`,
`paper`, `mono-light`) and 6 are near-black OLED (`oled-amber|blue|cyan|green|red|violet`,
background luminance ~5/255) — plus 8 skins, 4 of which are a world that replaces the icon
set. A glyph with baked colours is wrong in at least ten of those and unreadable in
several.

`currentColor` is not a style preference here, it is the cheapest correct answer:
`tests/test_themes.py` already enforces 4.5:1 body and 3:1 secondary contrast per palette,
so a glyph that inherits the text colour inherits a proven contrast ratio and needs no
per-palette work, no `@media (prefers-color-scheme)` branch, and no third asset.

**Honest state of this tier, today:** `Mark.tsx` hardcodes `stroke="var(--color-cyan)"`
and `stroke="var(--color-violet)"`. Those vars exist on the marketing site and do not
exist in the app, whose accents are `--accent`/`--accent2`. So the app has no mark at all
— `claude_sessions/web/index.html` renders a letter in a gradient tile where the glyph
should be. (That letter was `C`, a leftover from the old name that survived the rename
because nothing greps a single character; it is `A` now, which is a patch, not the fix.)
The single-path `currentColor` variant is the outstanding piece of work and is deliberately
out of scope for this pass, which owns copy.

---

## 6. The backdrop

The backdrop is where the meaning is stated without words, and the design rule it follows
is the same one the memory graph follows: **bounded, driven by real state, and it stops.**

**In the app — `claude_sessions/web/stage.js`.** One full-viewport `<canvas id="stage">` at
`z-index:-2`, one three.js scene per skin (7 of them: `hud`, `crt`, `brutal`, plus the four
worlds `anime`/`cyber`/`deck`/`graph`), each one or two draw calls over a merged buffer
animated entirely in the shader.

Two facts about it are brand statements, not performance notes:

- **It is driven by real state.** `STAGE.energy()` weights *running jobs*; today's token
  burn only sets a floor and is capped at 0.45. Feeding it off throughput alone made it
  run forever after a single token had been spent — the same bug the activity equalizer
  hit. A background that animates when nothing is happening is decoration; one that
  brightens because work is actually running is an instrument. An archeus responds to the
  body's state or it is not one.
- **It has a luminance ceiling.** `u_calm` (per skin, none above ~0.45) mixes every scene
  back toward `--bg`. The first cut shipped bloom on by default and was rejected as
  *"overstimulating, confonde"* — both users then switched to the one skin with no
  backdrop at all. `calm` (how bright) and `flow` (how much it moves) are separate knobs
  precisely because turning both down produced a background that had stopped being a
  background and become a gradient.

It stops five ways (`document.hidden`, `!MO.vis`, `motion:off`, `stage:off`,
`prefers-reduced-motion`) plus `webglcontextlost`, and fails open to a static CSS wash.

**On the site — `www/components/journey/scene.ts`.** Six wireframe stations on a
`CatmullRomCurve3`, radii descending `2.35 → 1.30`, the camera travelling the curve on
scroll and parking at each station; the sixth is a pull-back that looks at the middle of
the constellation. Every word of copy is server-rendered DOM positioned over it, so the
page reads identically with WebGL disabled, in a crawler, and in `curl`.

**The shared figure, and where it is going.** One figure runs through the tile's orbital
ellipse (§5.1), the glyph (§5.3), the stage's scenes and the journey's stations, and it is
mid-revision. It was *a bounded solid with something orbiting it*. `notes/constellation-study.md`
is making it *a hull holding a population, tied to other hulls* — "nodes made of nodes",
which is literally the shape of the memory graph: entities inside modules inside
repositories.

That revision is the right one for the brand and not only for the render, because it
closes the gap this study opened in §1. A solid says *coherent*; it does not say *while it
grows*. A hull with a population inside it and filaments out of it says both, and it is
the same sentence as §3 — memory first, and the thing it holds together is a project, not
a file. What it still must not become: a network diagram, a cloud, or a brain. Those say
*connected*, *elsewhere* and *thinking*, and archeus is none of the three.

---

## 7. One sentence → 16 files

The dead literal `workspace layer for Claude Code` was in 15 tracked files plus the
gitignored `CLAUDE.md`. Those 16 are the surface table; the four below the rule are files
the change forced but that did not carry the literal themselves.

| # | Surface | File | Carries |
|---|---|---|---|
| 1 | PyPI | `pyproject.toml` | `description`, full pitch; keywords lead with `ai-agents`, `agent-memory`, `coding-agent` |
| 2 | Docs site | `mkdocs.yml` | `site_description`, full pitch |
| 3 | Docs home | `docs/index.md` | h1 lead + TechArticle JSON-LD `description` + Rust disambiguation |
| 4 | Docs entry | `docs/getting-started.md` | opening sentence, front-matter `description`, and the "Where this is going" admonition |
| 5 | LLM-facing | `docs/llms.txt` | summary blockquote + disambiguation + the goal paragraph |
| 6 | Comparison | `docs/compare.md` | h1 lead, front matter, and a new "drives Claude Code only, today" limit |
| 7 | Repo front page | `README.md` | pitch block, Rust line, "What problem does this solve", 3 (was 7) bullets, new "Where this is going" |
| 8 | Site identity | `www/lib/site.ts` | `tagline` — the single source for the manifest, both `llms*.txt` routes and the OG `alt` |
| 9 | Site copy | `www/lib/content.ts` | `HOME.title` / `h1` / `description` / `intro`, station 02, station 06 |
| 10 | Site FAQ | `www/lib/faq.ts` | "What is archeus?", the Rust answer, and a new "other agents?" answer |
| 11 | Site head | `www/app/layout.tsx` | `keywords` (agent terms first), `alternateName` on both JSON-LD nodes |
| 12 | CLI | `claude_sessions/cli.py` | `--help` first line |
| 13 | GUI | `claude_sessions/web/index.html` | sidebar `<small>` — short form, `memory & workspace for AI agents` (§8) |
| 14 | Plugin | `plugin/.claude-plugin/plugin.json` | `description` — was *manager*; `keywords` |
| 15 | Marketplace | `.claude-plugin/marketplace.json` | `description` — was *layer*, mismatched #14; `tags` |
| 16 | Citation | `CITATION.cff` | `message`, `abstract`, `keywords` |
| — | Contributor entry | `CONTRIBUTING.md` | opening paragraph |
| — | Site README | `www/README.md` | opening paragraph |
| — | OG image | `tools/make_og_card.py` | `TAG`, `BULLETS`, wrap; regenerates both cards |
| — | Agent context | `CLAUDE.md` | "What it is" + the stale `claudectl.git` URL (gitignored, so no gate saw either) |
| — | Downstream | `www/app/llms.txt/route.ts`, `www/app/llms-full.txt/route.ts` | the tagline is now a full sentence and `HOME.description` opens with it — the `${tagline}.` interpolations printed `agents..` and then the sentence twice |

**Why a gate and not a generator.** Rows 1, 2, 14, 15 and 16 are static formats that
cannot import Python; rows 8–11 are TypeScript the Python build never runs; row 13 is
HTML. A generator would need a build step and a committed artefact per format, and the
artefacts are what fall behind — the exact failure `docs/gui-audit.md` demonstrated by
hand-maintaining a copy of something the code already stated. So the sentence is defined
once in `tests/test_brand_copy.py` and every surface is asserted against it, with the dead
phrasings asserted absent from every tracked file. The absence check is the half that
catches a surface nobody remembered to list.

---

## 8. What is deliberately not settled

- **The monochrome glyph does not exist yet** (§5.3). The app shows a letter, not the
  mark. This is the largest open brand gap — and it should be cut *after*
  `notes/constellation-study.md` lands, from the cluster, not from the dodecahedron it is
  replacing. Cutting it now would produce a glyph that disagrees with the backdrop within
  the week.
- **The GUI sidebar carries no descriptor at all — settled, against §7's row 13.** It
  briefly carried a short form (`memory & workspace for AI agents`) on the reasoning that
  `.brand small` is 11px inside a 280px sidebar and the full sentence would wrap. That was
  the wrong question. A tagline is a *website* device: Krug's definition puts it under the
  Site ID because its reader has not yet decided what the site is for, and nobody looking
  at this sidebar is that reader — they installed it, launched it, and are looking at
  their own projects. It also fails NN/g's differentiation test in both directions (every
  coding-agent tool could print it verbatim; no product claims the opposite), and Apple's
  HIG states the general rule twice: "ensure branding always defers to content", and
  "people seldom need to be reminded which app they're using".

  What the slot carries instead is the convention every current app follows — the
  switchable **context**, with a line of **state** under it. shadcn's sidebar header ships
  as a team switcher with the plan underneath; Notion, Linear, GitLab and Figma all put
  workspace/account/context there. Ours is the Claude Code account, which previously had
  no home outside the launch modal, over a measurement (`N projects · M active`).
  `SHORT_SLOTS` is kept but empty, and
  `test_brand_copy.py::test_the_app_chrome_carries_no_tagline` asserts the ABSENCE —
  because the pressure to put something explanatory back at the top of a sidebar does not
  go away.
- **The documentation domain is frozen.** It is still on the old name, which is not
  registered under the new one; the literal string lives in `HOLD` in
  `tools/_rename_brand.py` — and only there, so this file can be exempted from the
  old-name gate without hiding it —
  `test_the_domain_is_the_only_thing_still_waiting_on_a_move` fails if anything else joins
  it. Every link in every file above still resolves there on purpose.
- **The h1 keeps its full stop.** The pitch is a sentence and is asserted verbatim, so
  `www/lib/content.ts`'s `h1` ends in a period. Unusual typographically; consistent with
  every other slot, which is the tie-breaker.
- **`www/content/blog/*.md` was not rewritten.** Blog posts are dated artefacts and one of
  them argues for "putting a workspace layer in front" as a general technique, which is
  still true and is not the product's pitch.

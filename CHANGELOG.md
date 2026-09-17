# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.6.0] - 2026-09-17

### Changed

- **A project opens on four tab groups instead of nine tabs, and each group leads with
  the tab it is opened for.** Session, then Context (Memory, CLAUDE.md, Audit), Project
  (Tools, Usage, Repos) and Actions (Plan → Execute, Code Review). `Review` is called
  `Code Review`, which is what it does. Coming back to a group keeps the sub-tab you were
  last on, so the order decides the first visit only — which is the visit where guessing
  wrong costs a click.

- **The pages lead with what people came for.** Tools is two columns the page decides:
  on the left what the project *launches* with (its agents, its extra directories, its
  extra PATH), on the right what it has *been doing* (most-run commands, what to work
  on). Memory opens on what archeus knows, then on what it learned. The read-only
  diagnostics — project health and Claude Code's own record of the project — moved to
  Audit, where the rest of them already were, and the Architecture card went with the
  **Graph** button in the tab strip, which was already the door people used.

- **The apex site's header carries the donation link.** A warm caramel *Buy me a Coffee*
  button — a plain link, never a Ko-fi widget, whose embed would drag cookie consent back
  onto a site that has none — and the only control on the site that is not blue. `/support`
  keeps the explanation and has dropped its own duplicate call to action.

### Added

- **CLAUDE.md is editable from the GUI, and only the half you wrote.** The project's
  CLAUDE.md tab opens on a *Your prose* box holding the manual block and nothing else:
  everything archeus generates is left out of it and put back untouched on save, so the
  editor cannot overwrite a generated block even by accident.

### Fixed

- **The Memory tab left a whole column empty beside its first card.** A pile balances
  its cards across columns, but a card that takes the full width ends the balanced run
  above it — and the lessons card took the full width because its table has five
  columns. With it second on the page, the run above held one card and filled one column
  of two, leaving 828x770px of background beside it. A pile no longer gives a wide table
  the full width: the same table reads fine in an 828px column, and the page is 1489px
  tall instead of 2187. `tools/shot_gui.py` now fails a pile run that cannot fill its
  columns, and measures horizontal emptiness as well as vertical — every check it had
  measured height, so a card twice as wide as its contents was reported as clean.

- **The settings pages were mostly background on a wide window.** The annotated form
  puts an explanation on the left and the controls on the right, but the explanation was
  capped at 300px however wide the window got — so a ten-line description ran down a
  ribbon with 1225px empty beside it, and 1889px at 2560. The form is capped at a width
  it can use and the explanation gets a reading measure. The five version cards on
  Updates were full-width blocks holding about 500px of content each and are now a grid
  like every other set of independent cards, and the sentence explaining `install mode`
  is beside the value instead of 165px wide under it.

- **The home page said the same thing twice.** The hero printed the site's one-line
  intro and the first station's lead one under the other, in two sizes; they are the
  same sentence with twenty more words on the end. It prints the longer one.

- **The longest prose on the site was 102 characters a line.** The `zigzag` layout —
  /support, /changelog, /contributing, /code of conduct and every blog post — set its
  copy column to 54rem while the four other layouts held theirs between 44 and 52, and
  body paragraphs on the legal pages had no cap at all: they ran the full column width
  under a lead that stopped 114px short of them, so the two ended on different right
  edges. One measure now, about 88 characters, and `tools/audit_site.py` measures every
  paragraph on both sites at desktop width and fails past 96.

- **A numeric column's header did not stand over its own numbers.** `text-align:right`
  had only ever been written on the cells, so `tokens` sat at the left of a column whose
  figures ended 250px to its right — on the context audit, both usage tables, the lessons
  table, disk and rotation. The header takes its alignment from its cells now rather than
  from whatever the renderer remembered to type. The same pass gives the narrow-window
  stacked layout its labels, and it had never run on a table filled by a fetch after the
  page was painted, which was most of them.

- **The site header scrolled sideways between 768 and 895px.** Six nav links are 627px
  wide, which is more header than a tablet has once the wordmark, Docs and GitHub are
  beside them; the links now appear at `lg` rather than `md`, and below that they are in
  the disclosure menu they were always in on a phone. `tools/audit_site.py` checks
  768x1024 as well as 390x844 now — a phone gets the menu and a desktop has the room, so
  the tablet band is the one width a phone-only probe could never see.

## [2.5.0] - 2026-09-16

### Added

- **Automatic account rotation.** When the account in use fills its 5-hour or weekly
  window, the next one with headroom takes over — archeus's own Claude calls, scheduled
  loops and new sessions all start on it. Three modes (Accounts → Account rotation): off,
  semi-automatic (the default — new work moves by itself, and a session you are in is
  offered the move) and fully automatic (the successor session opens on its own), plus a
  switch-away threshold and a per-login opt-out. Every switch is recorded in the Logs.
  It rotates by launching the unmodified `claude` binary under each account's own
  `CLAUDE_CONFIG_DIR` and never reads, stores or refreshes a credential, so it cannot log
  an account out of Claude Code. The successor resumes the conversation itself
  (`--resume` on the transcript's absolute path, forked), rather than re-typing a summary
  of it. Codex and pi are deliberately not rotated: their windows are not Anthropic's and
  there is no headroom figure to compare.

  Two things watch a session you are **sitting in**, which is the one case archeus is not
  itself present for. The **status line** reads this account's own 5-hour and weekly
  percentages off Claude Code on every turn, so the row says `96% — continue on work2` as
  soon as one crosses the switch threshold — before the window is spent, rather than after
  a turn has already been refused — and in fully automatic it opens the successor itself.
  A **`StopFailure` hook** catches the turn that does die on a limit: it records the
  refusal where every archeus process can read it, so a running GUI and archeus's own
  Claude calls stop choosing that account too, and then applies your mode. The hook is
  installed and removed by the mode setting, and the rotation card says which logins carry
  it. An offer is not repeated for ten minutes per session, because both triggers fire
  repeatedly by nature.

  One subtlety worth naming, because it made the pre-emptive half inert on a real
  machine: `elect()` is deliberately STICKY — it keeps the account in hand until that
  account is spent — and it decides that from the usage poller's cache, which a status
  line process has never filled. So it answered with the very account it was being asked
  to leave, and the row read "no account with headroom" beside five idle logins. Leaving
  is now a separate question (`rotate.next_account`) from starting, which is what the two
  callers that have already decided to leave actually mean.

- **A guided tour, in the app and on the web.** Two tours of the same product:
  the first five minutes, ending with a session launched, and every function
  archeus has with what each one is for. In the desktop app it is a coach-mark
  that opens the screen it is describing and rings it — never a dialog over the
  thing it explains — reached from **?** → *Guided tour*. In the terminal UI it
  is a screen of its own, **Getting started** on the main menu, which prints the
  key that reaches each thing from there. And on the apex, at `/getting-started`,
  it is walkable with the screenshots for anyone who has not installed anything
  yet.

  The steps are written once, in `claude_sessions/tour.py`, and
  `tools/gen_tour.py` carries them to the website — a product with three
  interfaces and three explanations of itself has three products. What the
  narrative is NOT is a copy of the tables that already declare every screen: a
  blurb says what a screen shows, a step has to say when you would reach for it.
  `tests/test_tour.py` fails when a step names a page, tab or manual page that
  does not exist, and when a screen the app has appears in no step at all —
  which is how a feature ends up being discovered two years after it shipped.

- **The tour records itself.** `py tools/capture_tour.py` drives the real app
  through the real steps in a real browser and writes an animated WebP;
  `py tools/shot_tui.py --tour` does the same for the terminal. Both publish to
  the manual and the apex. It is a generated artefact like every screenshot,
  so it is re-recordable with one command when a screen moves, rather than a
  video that quietly stops matching the product.

- **Live sessions on the dashboard.** One row per session being worked in right now — the
  project, who is on it, what it is blocked on this second, and the shape of its recent
  activity as a strip of coloured ticks, with a click through to the full flow graph. It
  rides the dashboard's existing poll rather than opening a second one, and "live" is
  decided in one place, so the count and the list cannot disagree. Deliberately a list and
  not several graphs on one canvas: zoetrope was sent exactly that and declined it, because
  several trees do not fit at a readable size and a fleet of tailers pays for the parse
  continuously.

- **Session flow graph** — open any session as a live flow graph (**Flow**, beside
  *Transcript* in the session detail pane): prompts, model turns, tool calls, results,
  errors and subagent lanes on the session's own clock, with play/pause, speed, scrub,
  wheel-zoom and a click-to-inspect panel. Idle gaps are clamped, so a twelve-hour session
  replays in seconds, and **Follow** appends a session that is still running. Claude Code,
  Codex and pi. Behaviour adopted from
  [zoetrope](https://github.com/furkankly/zoetrope) (MIT).

- **Four policy pages on the apex, and an operator who is named.** `/legal/privacy`,
  `/legal/terms`, `/legal/cookies` and `/legal/refunds`, prerendered from one data table
  and wired from it into the footer, the sitemap, `/llms.txt` and `/llms-full.txt` — the
  manual links to those copies rather than carrying a second set, because two copies of a
  policy is two policies and the second one is wrong.

- **A support page on the apex, at `/support`.** "Why is there a donate button on a free
  MIT project" is a fair question and a footer link cannot answer it, so the footer now
  points at a page that does: what a donation buys (nothing — no tier, no perk, no
  sponsor-only build), what it does not change, and the ways of helping that cost nothing.
  It does not restate the refund policy; it links to it. Still an ordinary hyperlink out
  to Ko-fi — no widget, no iframe, no script — so nothing of theirs loads until you follow
  it, which is what keeps the cookie policy able to say there is nothing to consent to.

- **Ko-fi, on six surfaces, from one handle.** A badge and a License line in the README,
  `.github/FUNDING.yml` (which is what turns on GitHub's Sponsor button), a footer link,
  and funding metadata in `pyproject.toml`, the npm package and the gemspec. No widget and
  no Ko-fi JavaScript — an embed would have dragged cookie consent back in, which is
  exactly the surface those policy pages keep closed.

- **Memory has an episodic layer, and a quiet project now forgets.** Alongside the facts
  it already kept, memory records what each session was *like* — its tool errors, the last
  error text, an outcome, the duration, the branch and the tokens — all read in the pass
  that was already running, so nothing here spends a token. Retrieval is what makes it
  worth having: `score_episodes` reuses the existing BM25 and IDF to answer "have I done
  this before", ranks a session that ended badly slightly higher because the dead end is
  the useful one, and renders LAST inside the same 600-token budget, so it is the first
  thing dropped when the prompt is already rich in facts. The ring holds 50 with a 60-day
  TTL.

  Forgetting used to hang off a refresh — consolidation, lesson decay and invalidation
  all ran only when something had changed, which is backwards, because facts go stale
  precisely when nothing is happening. `forget_pass` runs on the scheduler's quiet branch
  instead: episodes and lessons past their TTL, invalidations older than 30 days, and a
  staleness flag on anything not re-confirmed in 90 days. Staleness is flagged and
  counted, never evicted — a heuristic that quietly reshapes what recall returns is how a
  memory system starts lying confidently.

  Two retrieval defects went with it. Entities merged on **name alone**, so a workspace
  holding several repos that each legitimately contain a `Claude Code` or a `memory
  system` merged them across repositories — and the merge SUMS rank, so each fused entity
  outranked every true fact. Merging is scoped by repo now. And where two descriptions
  disagreed, the loser was silently overwritten by string length; a contradiction
  auto-supersedes where the evidence is temporal and is **recorded** where it is not.

- **Write a hook by hand, name it, and file it.** Installing a ready-made template, asking
  Claude to generate one, or hand-editing Claude Code's `settings.json` were the three
  ways in; writing one yourself is the fourth. A hook can also carry a name and a
  category, which live in archeus's own settings and never in Claude Code's — that file
  belongs to another program, and an unrecognised key in a hook entry risks its schema
  refusing the lot. The identity is `(event, commands)`, the same one the account
  provisioner already uses to decide whether two accounts hold the same hook.

### Changed

- Removed duplicated definitions across the TUI, the scanners and the tooling: one
  display-width rule, one hidden-character class, one convention-overlap threshold, one
  snapshot reader, one render gate. No behaviour change.

- **The event log no longer lets one repeated warning evict every real error.** Measured on
  a real log: 1,589 events, of which 1,270 were a single slow-endpoint warning and 79 were
  `claude exited 1` failures the ring had already pushed out. The dedupe window stops a
  burst; nothing stopped a steady drip over two weeks. Rotation now thins what it keeps —
  at most 40 lines of any one `(source, shape)`, newest first — which on that log keeps
  every quota warning and every subprocess error at half the bytes. Applied only when the
  log rotates, so the common append is still one `getsize` and no rewrite.

- **Three controls are identifiable as controls.** The apex's secondary CTA, the copy
  button and the mobile menu summary were outlined in `--color-line` at 1.36:1 — under the
  3:1 that SC 1.4.11 asks of a control boundary, and on the secondary CTA the only thing
  separating it from body text. They now use a 3.28:1 border; decorative hairlines are
  unchanged, the distinction being whether the boundary does identifying work.

- **`/about` no longer publishes figures nobody measured.** A stat tile that had no number
  rendered as `GitHub stars —`, which reads as a claim of none rather than as "not
  counted"; a tile now survives only if its value carries a digit, and the disclosure line
  says when the figures were taken.

### Fixed

- **Half of the rate-limit guard had never worked.** `quota`'s 429 pattern contained two
  literal backspace bytes where `\b` had been meant, so it could never match; a 429 was
  only ever caught when the text happened to carry another marker as well. It now matches a
  status code (`"apiErrorStatus":429`, `status: 429`) without matching a number in prose.

- **`tools/inspect_cluster.py` inspected a hardcoded checkout path** rather than the tree it
  runs in, so in any other worktree it graded a copy — which is what its own docstring says
  it exists to avoid.

- **A link gate could not tell a trailing slash from a path separator.**
  `test_an_apex_link_has_no_trailing_slash` backtracked to the first slash it could end on,
  so a correct two-level apex URL was reported as a defect. Until the policy pages landed no
  tracked file named one, so that half of the pattern had never been exercised.

- **`npx archeus` did nothing at all** (npm package 2.4.1; the Python package is
  unchanged). Under `npx`, npm puts its own generated shim on PATH under the name
  the launcher then looks up, so it found itself: on Windows that shim is a `.cmd`,
  which Node will not execute without a shell, and the failure surfaced as exit 1
  with nothing printed; on macOS and Linux it is a symlink back to the same file,
  which would have re-entered it forever. The launcher now keeps a real console
  script — an `.exe` on Windows, anything not resolving inside `node_modules`
  elsewhere — and falls through to running archeus as a module when the only
  match is npm's.

## [2.4.0] - 2026-09-15

### Added

- **A Harnesses page, and a sidebar about the workspace rather than about one CLI.**
  Five screens only Claude Code has — Accounts, its own client state, output styles,
  subagents and hooks — moved out of the sidebar and behind a tab for that CLI, beside a
  new Setup screen per harness: whether it is installed, where, which version, whether an
  update is waiting, and its full capability table with the reason beside every gap. The
  pages themselves are unchanged; only which door they sit behind moved. Five greyed rows
  teach you the app is about one tool.

- **Usage & cost reads every CLI.** A harness strip over the page, and the split is real:
  daily tokens and per-project spend are counted out of each CLI's own transcripts, which
  archeus already parses. Only the plan-window rail is Anthropic's, and it greys with its
  reason instead of switching the whole page off — which is what the old `usage`
  capability did for Codex and pi, wrongly. The dashboard's `spend today` names which CLI
  spent it when more than one did.

- **Models and quick-start presets for Codex and pi.** Both were an empty box on a fresh
  install, because the model list was read only from what the CLI had already run. It now
  also reads the catalogue each CLI **ships** — pi installs a 1,354-model provider list
  covering its own models and Codex's — so the picker has suggestions before the first
  session, labelled *run here* versus *ships with this CLI*. Three presets per CLI over
  its own two scales, and a preset naming a model the catalogue does not publish is
  dropped rather than offered.

- **Non-Anthropic sessions are priced.** That same catalogue carries per-model prices, so
  a `gpt-5.5` or Gemini session shows a cost instead of `n/a`. A model nothing publishes a
  price for stays unpriced — no guess, because an Opus-tier fallback on a `gpt-5.6-luna`
  session would be wrong by a factor of fifty.

- **`codex.exe` and `pi` paths in ⚙ Settings → Paths & limits**, beside `claude.exe`, for
  an install the automatic search cannot reach.

### Changed

- **Three capabilities Codex was declared not to have, it has.** Checked against the
  installed binary rather than assumed: `codex mcp list/get/add/remove` is a full MCP
  surface, `codex plugin list` reads every marketplace, and `codex doctor` reports the
  installed version and whether a newer one exists — all three offline and without a
  login. The MCP page, the Plugins page and the Updates page answer for Codex now;
  plugins are read-only there, because installing goes through a marketplace resolver
  archeus does not own. `codex update` and `pi update` are buttons.

- **Hooks stay unavailable for Codex, with the real reason.** Its hook contract is
  byte-identical to Claude Code's — the binary carries the same `session_id`,
  `transcript_path`, `hook_event_name` and `stop_hook_active` payload fields — but every
  handler in `hooks.json` is gated on an undocumented `trusted_hash` whose mismatch is
  refused **silently**. A hook archeus installs that never fires and never says so is
  worse than no hook.

- **Auto-memory says where its two deliveries land.** The digest already reached every
  installed CLI's instructions file; the path-scoped `.claude/rules/*.md` half only ever
  reached Claude Code, and nothing said so. That is a declared capability now, the Memory
  tab names which CLIs read those files, and the CLAUDE.md map lists every instructions
  file a project loads rather than only Claude Code's.

### Fixed

- **Installing a second CLI no longer reports the workspace as broken.** The dashboard's
  wiring ring counted hooks and a statusline over *every* CLI home, and neither is
  something Codex or pi has — so a fully-wired machine dropped from 1/1 to 1/3 the moment
  a second CLI appeared.

- **A Codex or pi project is no longer attributed to an account called `.codex`.** The
  spend breakdown resolved account names from Claude Code's account list alone.

- **Structured data on every page of the manual, derived from the page.** All twenty-nine
  pages now carry a `TechArticle` and a `BreadcrumbList`, under the same author, website
  and application `@id`s the marketing site uses — so the two hosts describe one project
  rather than two that share a name. Troubleshooting additionally emits a `FAQPage` and
  Quickstart a `HowTo`, both **built from the page's own headings** at build time rather
  than written beside it: the questions an answer engine quotes are the exact symptom
  strings and error messages the page already displays. Previously one page in
  twenty-nine opted into any structured data at all.

- **`tools/optimize_images.py`, `tools/check_site_seo.py` and `tools/audit_site.py`.**
  Respectively: every published image at the size it should be; the built HTML checked
  for titles, canonicals, descriptions, social cards, JSON-LD and image dimensions; and
  every page loaded at 390x844 with a failure on anything past the right edge. The first
  two run in CI on every push, the third on the weekly schedule.

- **`tools/set_domain.py`** — moves both published sites to a new domain in one command,
  with `notes/domain-change.md` for the parts no script can do (DNS, the Vercel projects,
  GitHub Pages, the Search Console change of address, and the 301s that have to stay up
  for a year). `notes/search-console.md` covers verification.

### Changed

- **Both sites are about 10 MB lighter.** The architecture-graph animation is written as
  animated WebP instead of GIF — the same 30 frames at 538 KB instead of 5770 KB — and it
  is the largest paint on two pages. The manual's screenshots get a WebP derivative where
  it beats the PNG (Desktop app went from 1470 KB of images to 227 KB); the PNG stays as
  the master, because that is what the README embeds and what PyPI renders. The docs
  header logo was the 1254px master at 998 KB on every page and is now a 256px
  derivative; the favicon carried a 256px frame and now stops at 48.

- **Images in the manual declare their intrinsic size and load lazily**, so the text under
  them no longer moves when they arrive.

- **Explicit crawler rules on both hosts**, including `Google-Extended` and
  `Applebot-Extended` — the two agents for which "no rule" reads as a refusal rather than
  as the default. Preview deployments are excluded from indexing.

- **HSTS, `X-Content-Type-Options` and `Referrer-Policy` on both sites.** Not `preload`,
  deliberately: that list is effectively permanent and a domain move is pending.

- Nineteen pages had a meta description longer than a search result renders; all are
  rewritten to fit. `docs/api.md` had none at all and fell back to the site-wide one.

- The FAQ page's twenty-three questions are headings now. The page emitted a twenty-three
  entry `FAQPage` while the only headings in its markup were the four in the footer.

- PyPI can filter this package by Python version: the classifiers named `3` and no minor.

### Fixed

- **Seventeen internal links redirected before they arrived.** The apex serves `/features`
  and the manual serves `/installation/`; links written with the other site's convention
  cost a 308 each. Two links pointed at the pre-domain GitHub Pages host.

- **A `.grid` override made three pages of the manual scroll sideways on a phone.** A bare
  `minmax(20rem, 1fr)` is a floor the track cannot go under; Material's own rule clamps it
  with `min(100%, …)` and this one did not carry that across. Found by measuring, not by
  looking.

- `app/apple-icon.png` was built and routed but never linked: naming `icons` in the root
  metadata replaces Next's file-convention detection rather than adding to it. The web
  manifest pointed at an ICO for a size the file no longer contains.

- **archeus reads three coding CLIs, not one.** OpenAI Codex and pi join Claude Code as
  first-class harnesses: their projects, sessions, previews, turn counts, models, token
  spend, search and usage all merge into the same lists, with no configuration — archeus
  looks for each binary and its home, and a CLI it cannot find is simply not offered. A
  *provider* is an endpoint and a *harness* is the binary itself; the two axes are
  orthogonal, and the launch picker shows both because they are both answers to "what runs
  this session". See
  [More than one CLI](https://github.com/babarmuhammad/archeus/blob/main/docs/harnesses.md).

- **One memory graph behind all three.** A project's memory is the project's, not Claude
  Code's memory of the project, so the same digest is delivered into every instructions
  file an installed CLI reads — `CLAUDE.md` for Claude Code, `AGENTS.md` for Codex, and
  both for pi, which reads either. A machine with no Codex never grows an `AGENTS.md`. The
  agent routing table deliberately does not follow: delegation is a Claude Code capability,
  and writing "delegate with the Agent tool" into `AGENTS.md` would instruct Codex to use a
  tool it does not have.

- **Skills install into every CLI.** `SKILL.md` is the Agent Skills standard and all three
  read the same file, so a personal skill lands in every account *and* every CLI, and a
  project skill writes `.claude/skills` and `.agents/skills` — two directories, not three,
  because `.agents/skills` is the cross-harness convention Codex and pi share.

- **New session opens on a tab strip.** Which CLI or backend a session runs on used to be a
  chip row six fields down inside a collapsed "Advanced" panel, beside the thinking cap —
  the only control in that form that changed which *tool* ran. It is now the first question,
  because it decides what the rest of the form means: a Codex session has no worktree and no
  name-at-launch, a pi session has no permission mode, and those fields are removed with the
  reason stated rather than left as dead inputs. The default is Claude Code and is
  configurable in Settings → Defaults → **Starts on**.

- **A CLI can be switched off, and off means everywhere** — the launch tabs, the project
  list, the sessions list, the usage table, and the instructions files that get a memory
  block. Nothing is uninstalled and nothing on disk is touched. Claude Code is listed and
  locked: it is the binary archeus itself runs for memory extraction, lessons and every
  other AI feature.

### Fixed

- **A one-shot run in the OS scratch directory is no longer a project.** A `codex exec` or
  `claude -p` in `%TEMP%` writes the same session state a real project does, and the sidebar
  grew a tab for a directory that is gone by the next boot.

- **Codex sessions reported zero tokens, and search, usage and the dashboard reported no
  sessions at all.** The corpus walk listed `*.jsonl` in the project folder, which is where
  Codex keeps an index rather than a transcript; it goes through the same two seams the
  sessions list already used. Token spend is read from the rollout's `token_count` events,
  whose cumulative totals are banked as deltas — summing one per turn multiplies a session's
  spend by its turn count.

- **Run a session against a local model, OpenRouter or a self-hosted server**, not only
  OmniRoute. archeus could already point a real `claude` session at another backend —
  that is what the OmniRoute support has always been — but the capability was wired to one
  product name, so an Ollama, vLLM or llama.cpp server speaking the same protocol was
  unreachable. Settings → **Model provider** now takes any endpoint that serves
  `POST /v1/messages`. Sessions keep their agents, skills, hooks, MCP servers, slash
  commands and checkpoints, because none of those ever talk to the model API. See
  [Model providers](https://github.com/babarmuhammad/archeus/blob/main/docs/providers.md) for the list of
  what a backend swap genuinely costs — subagents, prompt caching, extended thinking and
  `web_search` are affected, and three of the four cannot be fixed from outside Claude Code.

- **Every session picks its own backend.** One backend at a time was a real constraint, not a
  screen limitation: the failover and gateway proxies re-read the settings on every request, so
  two live backends would have handed one session's credential to the other's upstream. Backends
  are now **named profiles** — Settings → **Models** lists them, each with its own URL, key,
  model, context window, translating gateway and failover list — and each one owns its own pair
  of ports, so its proxies are pinned to it at spawn and can no longer resolve to a neighbour.
  The launch modal and the terminal picker both offer the list, so one project can run on a local
  vLLM while the next runs on OmniRoute and a third on your Anthropic account. Your existing
  backend is carried across into a profile on first start, keeping its key, URL, model and
  failover list; nothing is lost and nothing needs re-entering.

- **Run archeus's own Claude calls on the configured provider too.** Memory extraction,
  lesson distillation, code review and the CLAUDE.md / agent / skill / hook / system-prompt
  generators always went to Anthropic, whatever the provider card said — they are the
  cheapest, highest-volume calls archeus makes and the best fit for a local model. Opt in
  with **Run archeus's own calls here too**; off by default, because these run unattended
  and moving them changes which account is billed. An unreachable backend fails the call
  rather than quietly falling back to the account you routed away from.

### Fixed

- **The upgrade from the previous name is finished.** The rename moved everything that was a
  path and nothing that was not, and the one repair it did ship ran exactly once — at the one
  moment when nothing was broken yet. Four things came out of that, and every one of them was
  measured on a real machine rather than reasoned about:
    - **Hooks and the statusline are repaired on every start**, not once during the migration.
      They record an absolute path into the environment that installed them, and everything
      that kills such a path — uninstalling the old package from its own pipx venv, moving or
      re-cloning a checkout, rebuilding a virtualenv — happens *after* the migration has run
      and closed its flag. Only a path that no longer exists and names one of archeus's own
      scripts is rewritten; a hook you wrote by hand, or a fork running from a checkout, is
      left alone. The statusline is rebuilt with the windowless interpreter it was installed
      with, so the repair does not start flashing a console window once per conversation turn.
    - **A duplicated memory block in `CLAUDE.md` is removed.** The sentinel comments around the
      generated memory, agent-routing and loop blocks carry the tool's name, so after the
      rename nothing could find the old ones and every build appended a second block beside
      the first — which then went into every session, for ever, saying whatever it said the
      day the rename landed. A block the new name has since rewritten is dropped; a block with
      no successor is renamed in place, so the next build updates it instead of duplicating it
      too. A half-written pair is left alone, and the `KEEP` fence around your own prose is
      always renamed and never removed — until it was, the compression pass could not see it.
    - **Scheduled loops are re-registered.** A scheduler entry is a name, not a path, so the
      registry moved and the Task Scheduler / cron entry did not: the loop read as unscheduled
      in the UI while the old entry went on firing, into an interpreter that may since have
      been deleted. The old entry is removed and the loop re-registered, which rebuilds its
      command line at the same time.
    - **`CLAUDECTL_*` environment variables and a plugin still installed under the old id are
      reported on startup.** Both have been silently doing nothing since the rename, and
      neither is archeus's to edit: one lives in your shell profile, the other in caches that
      only the `claude` CLI may write.
- **`CLAUDE.md` is written atomically.** The writer for all three machine-maintained blocks was
  the last one still using a plain truncating write, and Claude Code parses that file on every
  turn — a write that died partway left it half a file.
- **Adding a backend threw away the form it had just opened.** A new profile has no id until it
  is saved — that is what keeps an abandoned Add from leaving anything behind — but the list
  redraw dropped any selection whose id was not in the list, which is every draft. The pane blanked
  the moment it appeared.
- **The model catalogue never loaded.** Backends are per-profile now and the catalogue endpoint
  takes the profile id; the page was still asking for it without one, so the request was refused
  and the model picker was simply never built. The card offered a free-text box where it should
  have offered the live list.
- **Stopping the failover proxy did nothing at all.** The button raised a `TypeError` on the
  background thread — it asked to stop "the" proxy, from before there was one per backend — where
  nothing logs it, so the job neither finished nor reported. The last call site missed in that
  conversion.
- **An image sent through the translating gateway is now reported.** Anything that is not text, a
  tool call or a tool result had no branch in the translation and left the request in silence, so
  a vision model behind the gateway stopped seeing the picture with nothing said anywhere. It is
  still dropped — translating it is a larger change — but the proxy console now says so, once per
  kind of block, exactly as it already did for prompt caching.
- **Which backend a session ran on is written down at launch** instead of guessed afterwards from
  the model ids in its transcript. That guess cannot tell an Anthropic model served *through* a
  provider from a direct run, and said so in its own source. A new session's id is archeus's to
  choose, so the answer is recorded before the first line is written; sessions started elsewhere
  still fall back to the guess.
- **Four generators bypassed the one headless-call helper.** Authoring an agent, a skill or a
  system prompt, and analysing an MCP server, each rebuilt the same `claude --print` command
  by hand — so none of them honoured the `--max-budget-usd` cap, and all four passed the whole
  prompt as a command-line argument, which is the Windows length limit the shared helper exists
  to avoid. They call it now, and a test fails a fifth copy.
- **Subagents kept a model id a routed backend cannot resolve.** The frontmatter-stripping
  that makes agents work on a non-Anthropic model was a parameter three of its four callers
  never passed, so agents synced from the GUI or accepted from a suggestion still carried
  `model: claude-…` and 401'd. It is derived from the active provider now instead of being
  asked of each caller.
- **A routed model's cost read as `~$0.00`.** There are no published rates for one, which
  is not the same as it being free — a paid OpenRouter or self-hosted model was reported as
  approximately nothing. It shows `n/a`; a session mixing Anthropic and routed models still
  quotes the part that is known.
- **Extended thinking no longer fails the whole turn on a non-Anthropic backend.** Claude
  Code sends the adaptive-thinking field unconditionally and an upstream that does not know
  it answers 400, so it is disabled automatically whenever a provider is configured.

### Changed

- The `omniroute_base_url` / `omniroute_api_key` / `omniroute_exec_model` settings are now
  `provider_*`, with `provider_kind` choosing between OmniRoute's managed daemon and a
  server you already run. Existing settings are migrated on first start.

## [2.3.0] - 2026-09-11

### Changed

- **The banner is the gold ARCHEUS lockup, and so is the social card.** It
  replaces the generated cyan wordmark everywhere it was used, and it is artwork
  now rather than output — `tools/make_og_card.py` no longer writes
  `docs/assets/wordmark.png`, it READS it, so the card and the README show the
  same file and neither can drift. Transparent, so it works on a light GitHub
  page, a dark one, and straight on the card's navy. The card loses its cyan
  `archeus` title with it: the mark carries the name, in the brand's own
  letterforms and twice the size, so the word was on the card twice.

### Fixed

- **"Update now" installs, with archeus still open.** It had never worked on
  any path, for four separate reasons, and each one hid the next.

  - **pip was run with no stdout.** The worker is detached, so its output goes
    to a file handle — and a child that redirects nothing does not inherit one.
    pip came up with `sys.stdout` None and, under `pythonw` (which is what the
    desktop shell runs on), exited 1 having printed nothing at all, not even a
    traceback. The update log held the worker's own two lines and no pip output,
    which reads exactly like an install that never ran. The install is captured
    now, and the whole of pip's output goes to the log.
  - **It waited five minutes and then installed anyway.** The strip says "it
    installs when you close archeus" and a session lasts hours, so the cap fired
    first every time and pip met the locked console script it had been deferred
    to avoid. Measured: that install fails *after* uninstalling the old package,
    leaving nothing installed at all. The wait is unbounded, and a caller that
    passes a deadline gets "could not" rather than the unsafe install.
  - **It never had to wait in the first place.** A running `.exe` can be
    renamed, only not overwritten, so the worker moves the console script aside
    and pip writes a fresh one beside it — and puts the old one back if the
    install fails. *Update now* installs immediately; *install on quit* is the
    same worker told to wait for this process first.
  - **A checkout called itself a stale pip install.** One `pip install -e .`
    leaves `archeus.egg-info` in the repository for ever, and the checkout is
    first on `sys.path`, so `importlib.metadata` reported the working tree as an
    installed distribution at whatever version that file was built at — 2.1.0
    for a 2.2.0 tree. The banner offered an upgrade, pip answered "Requirement
    already satisfied" about a copy the process was not running, and the restart
    showed the old version and offered it again. What archeus is running is
    decided by the layout on disk now, not by the record sitting next to it.

  The strip itself was the fourth fault: the click starts a job whose banner IS
  the update strip, and the finish path hides the strip it borrowed, so the
  message that followed — with its **Restart now** button — was painted into a
  hidden element. And the job used to report "done" the moment a background
  worker had been *started*, which is a different fact from an install that
  worked; it now holds until pip is finished and reports what pip said.

- **The app icon reaches installs without PyQt6 — which is most of them.** The
  mark shipped inside the package and only the Qt window ever read it. PyQt6 is
  optional, so a plain `pip install archeus` opens the GUI as an Edge `--app`
  window, whose taskbar icon is the page's favicon, and the page served none.
  The server now serves `/favicon.ico` from the same file the Qt window uses.

- **A browser tab that abandons a request no longer prints a traceback.**
  Closing the window, or navigating away while the page's fetches were still in
  flight, dumped fifteen lines of `ConnectionAbortedError: [WinError 10053]`
  into the console with nothing wrong — `socketserver` prints a full traceback
  for any exception escaping a handler, and the per-request log silencer does
  not cover it. Both local servers now share one rule for which exceptions are
  the user's problem: a peer that went away is dropped, anything else goes to
  the log and the Events screen. The failover proxy had the same hole, and its
  console window is the one users are told to read.

- **Auto-memory's interval is counted from the last pass, and the clock now
  survives the process.** A pass ran a couple of seconds after every launch, so
  closing and reopening archeus five times in an hour bought five passes and
  spent five times the quota the schedule was supposed to cap. The last pass is
  recorded (a file mtime, so there is no state to corrupt), the first pass of a
  run waits out whatever is left of the interval, and the Auto-memory card
  shows when the next one is due.

- **Two paragraphs printed on top of each other on the Updates page.** The
  annotation column of a settings card gave `grid-row: 2 / span 20` to both the
  section's first paragraph and every `.secthint` below it — which is one grid
  cell, not a stack. The layout audit gained the check that sees it: two
  normal-flow children of a card whose boxes overlap, the opposite failure to
  the empty-floor measurement it already had.

## [2.2.0] - 2026-09-10

### Changed

- **Every page now has a declared shape, and five shapes is all there are.** A
  page's composition used to be whatever its renderer happened to emit, so the
  choice between a plain grid of cards and a balanced pile was made by hand,
  once per page, twenty-eight times — and nothing could tell a considered
  layout from an accident. The shape is now the sixth field of the table the
  page itself is declared in, and one function reads it, so a renderer emits
  its sections and never states, or gets to forget, what kind of page it is on.

  There were six shapes; the sixth was `grid`, the un-designed default. Every
  page has a real one now, so it is deleted rather than left as the place the
  next page lands by accident.

  - **A list of one kind of thing is a list, with what you picked beside it.**
    MCP servers, hooks, output styles, accounts, repos and sessions were pages
    of rows whose name sat at the left of the window and whose buttons sat at
    the right of it — on a wide display, a name, two thousand pixels of
    nothing, and then the controls. Each is now a list in its own scroller with
    a detail pane next to it. Three of them stop opening a drawer over the page
    you were reading to show you a detail: the MCP server's configuration, an
    output style's text, and a repo's worktrees are in the pane.
  - **The two halves of a split are level.** A detail pane sized to its own
    content sat as a 200px box beside a 900px list with the column under it
    simply dark — 616px of it on the MCP page, at every window width. Both
    halves are panes the height of the row now, the detail scrolls inside its
    own instead of growing the row past the window, and every split opens with
    a row already picked, so the pane is never an invitation next to a full
    list.
  - **Output styles is one list, not five grids of the same object.** Clicking
    a card used to write a settings.json — selecting a style and inspecting one
    were the same gesture. Picking a row now only picks it; putting a style in
    force, copying a starter and deleting are buttons in the pane.
  - **The session list gives up its hover-only action strip.** Ten actions
    appeared at the right edge of a row when the pointer crossed it. Resume
    stays on the row — resuming is one click, from the list, as it was — and
    the other ten are in the pane, on the session you picked, visible.
  - **A page that is one homogeneous list gets the whole width.** Logs, search,
    the code review, per-session usage and the context audit were single cards
    in a three-track grid, so the list you opened the page for got one column
    of three.
  - **The settings pages stop flowing their controls into columns.** Every
    design system says the same thing about a form and multicol was exactly the
    wrong shape for the five pages that are nothing but controls. Each section
    is now a single column of controls with its title and the sentence
    explaining it in a narrow column beside them, which is what the width on a
    wide display is for. A section's Save sits under the controls it saves
    rather than pinned to the far edge of a half-empty card, and it is
    secondary: six primary buttons down one page is six things all claiming to
    be the thing to press.
  - **A number input is as wide as its value.** A four-digit port had a 900px
    box, because the rule that gives every control the full width of its field
    is right for a path and wrong for a number.
  - **A form section does not mix its save patterns.** Nothing did, and the one
    place that nearly did is commented in the wiring — update checks and
    notifications write the moment you pick one, so they sit in a card with no
    Save at all. That is a gate now, read out of the wiring rather than from a
    list: a chip row that posts on pick, inside a card that also has a Save,
    fails the build.
  - **Two fields share a row only when they are one value.** Five pairs on the
    settings pages were two unrelated settings side by side to save vertical
    space — an editor path beside the Claude binary, the config dir beside a
    spend cap, two independent memory caps, two unrelated switches, a proxy
    port beside a window preference. Each is a control on its own row. The
    three that remain are one value each: an exporter's endpoint and protocol,
    a proxy's URL and key, a model and the effort it runs at.
  - **An empty state is left-aligned where the content it replaces would have
    started.** Centred with 7vh above it, it read as a page-level apology
    wherever it was really an in-card note — floating in the middle of a detail
    pane, or a third of the way down a card whose heading is at the top. It
    keeps the old treatment in the one place it earns it: written straight into
    the page with no card around it.
  - **The app chrome stops claiming to be sticky.** The header and the tab strip
    carried `position:sticky` and had nothing to stick to — they are siblings
    above the only thing that scrolls, so it did nothing. They stay positioned,
    because that is what makes their `z-index` mean anything.

  - **A section whose body resolves to nothing is not painted**, and neither is
    a table whose header stands over no rows. Reading the pages found eight of
    them. Emptiness that is itself the information keeps its card — "no MCP
    servers configured" is that page's whole subject — because an empty state
    is text, and the rule only removes what has nothing at all.


## [2.1.0] - 2026-09-09

### Added

- **Every page now fits the space it has, at any window size.** Every internal
  layout rule in the GUI decided its shape from the WINDOW, and no card is ever
  the width of the window: a card sits in a 560-760px column of the content
  grid at any window above 1280px. So the rules written to rescue narrow
  content — a table's row-stacking, the settings matrix, a page header's gauge,
  the three-across lists, the list+detail split, the dashboard's own layout —
  described a state nobody is ever in. On a 2048px window the Memory tab's
  lessons table was handed one 740px column, squeezed its status column to
  23px, stacked `approved` onto its own tag, and left the other half of the row
  dark. Those rules now measure the box they are in rather than the screen,
  which also means dragging the sidebar re-lays the page out instead of moving
  the content edge by 240px with nothing noticing.

  A row of cards is also what leaves a hole in a page — a row is as tall as its
  tallest card, and the rest of it is empty. Pages that are a stack of
  independent sections (Help, Tools, CLAUDE.md, Plan → Execute, Memory, Output
  styles, Loops, Audit, the settings pages, the global CLAUDE.md) now balance
  their sections into columns instead, so a 147px section beside a 794px one
  costs nothing. A card holding something genuinely wide — a five-column table,
  the per-account settings matrix — takes the full width by itself, decided by
  what is in it rather than by a list somebody has to maintain. Sparse pages
  stretch to fill instead of leaving an empty column, and explanatory prose
  inside a card stops at a readable line length rather than running the width
  of a 2560px display.

  Measured with a new probe in `tools/shot_gui.py` that reports dead space
  rather than overflow — ragged rows, wasted grid cells, empty card floors,
  squeezed table columns, over-long lines — across 19 pages, 9 project tabs and
  8 looks at three widths: 78 findings, down to none. It fails the run rather
  than printing, and counts what it measured, because a probe that stops
  finding anything reports success. Verified in the desktop shell as well as
  the test browser (`tools/probe_layout_qt.py`).

- **A build queue for project memory.** Turn it on and archeus works through
  the modules that still owe an extraction while you are not using it, across
  every account rather than whichever one the process happened to start under,
  and stops when you tell it to.

- **Workspace status now checks whether your CLAUDE.md prose still agrees with
  the memory graph.** `CLAUDE.md` has two halves and archeus owns exactly one:
  it rewrites the AUTOGEN, SESSIONS and memory blocks from live inputs, and it
  never touches the prose above them, because a tool that silently rewords what
  you wrote is worse than one that lets it age. The cost of that guarantee is
  that the hand-written half had no freshness signal of its own, and it is
  append-only by habit — a fact written near the top is rarely read again.

  The new `claude_md_claims` check reads the countable claims in your prose
  ("32 palettes", "4 worlds") and compares them against the same claims in the
  memory graph, which *is* re-extracted from the code:

  ```
  🟡 CLAUDE.md says 29 palettes, memory says 32
  ```

  It reports a disagreement, not a verdict. The graph is usually the fresher
  side, but it holds entities extracted in different cycles and can lag too, so
  the remedy names rebuilding memory first and the GUI button opens the file
  rather than pretending to repair it. There is deliberately no automatic fix.

  Conservative on purpose, because a noisy check gets switched off: a noun
  stated with two different numbers is ignored rather than guessed at, units
  (`tokens`, `days`, `lines`) never count, only plural nouns count, and a
  sentence in the past tense is skipped — *"an earlier design was 26
  renderers"* is history, not a stale claim. A project with no memory graph is
  marked `n/a` and scores nothing either way. One JSON read, no model call and
  no subprocess.

### Changed

- **The graph world's cluster is drawn without a lighting model, and so are the
  architecture graph and the website.** It keeps every part it had — the rod
  shell, the inner web on its own reversed clock, the hull faces, the coarse
  frame, the spokes, the beads, the junctions, the centre, the orbiters, the
  conduits — as fine additive lines and rings rather than lit, glassy solids,
  so all three surfaces represent one object instead of three approximations of
  it. It is also 24,494 triangles in 19 draw calls where it was 353,566 in 33,
  which is what fixed the stutter below.

- **Updating no longer opens a terminal.** The installer has to wait for
  archeus to exit before it can replace the running files, and it used to do
  that in a console window that took the foreground and sat on "Waiting for
  archeus to exit…" — which reads as the update having hung. It runs detached
  and windowless now, writes to a log, and can bring archeus back up when it
  finishes.

- **"Open project by path" opens the project.** It launched a session in that
  directory instead, which is a different and much larger action than the one
  the button names.

### Fixed

- **The graph world stuttered in the desktop shell, worst in full screen.**
  Measured inside the real Qt window, the lit cluster pushed frame delivery to
  a 249.9ms 95th percentile with no long tasks at all, so Chromium halved the
  page's frame rate and the whole app lurched between 60 and ~17Hz. The flat
  cluster holds 16.8ms. Two sessions of measurements before it had been reading
  a PARKED page — the probe never took focus, and the app pauses everything
  when it loses focus by design — so the tool now takes the foreground
  properly and prints whether it had focus, rather than reporting zero frames
  beside a clean frame rate.

- **Eight places the app spoke to itself instead of to you.** Found by reading
  every page's text rather than looking at it: the freshness rows on the Memory
  tab were the checks' own identifiers with their underscores swapped for spaces
  (`claude md`, `claude md fresh` — two rows whose names do not say how they
  differ), so each check has a written label now; the remedies beside them said
  "press m → b", which is the terminal's key path printed next to the GUI button
  that does the same thing; the account sync card printed a seven-column table
  header over the words "No accounts to compare"; the Audit tab's token column
  read `~?`; the Loops command preview read `every ?` until you typed an
  interval; the Memory tab answered "when" as `2026-08-12T09:15:00Z` in three
  places and as "10m ago" in four others; and the project's Usage tab printed
  raw token counts where the rest of the app writes `412.0k`.

- **The dashboard was hiding accounts.** The plan-usage rail was a horizontal
  scroller sized for three cards, so with five accounts configured two of them
  were simply not on the dashboard. It wraps now.

- **Four responsive rules that had never once applied.** The narrow-window
  chrome and the icon rail's content gutters were declared before the rules
  they countermand, and a `@media` block adds no specificity — so at narrow
  widths the tab row never tightened, the metric strip never closed up and the
  big readouts never shrank. Ten declarations that restated their base rules
  character for character are gone with them.

- **Published numbers that had drifted since 1.8.2.** The project dashboard
  still reported version 1.8.2, 1,367 tests, 183 Python files and 129 commits;
  the marketing site parses that page, so every number on it was stale too. The
  README's test badge said 1,706 — a third number, matching neither. The
  documentation and the site also advertised 29 palettes, 7 skins and 19 hook
  templates against a codebase holding 32, 8 and 31, and `docs/hooks.md`
  described only 17 of the 31 templates, missing the memory-freshness,
  failure-logging, notification and test-running families entirely.

- **The README test badge is generated now, not hand-typed.**
  `tools/gen_metrics.py` already counted the tests for the dashboard; it writes
  the badge from that same number, so the two surfaces cannot disagree again.
  Refreshed by the existing weekly metrics workflow. `tests/test_docs_numbers.py`
  gates the counts that *are* derivable from this repository — palettes, skins,
  worlds, hook templates, plugin commands and bundled skills — across the
  README, every documentation page and the marketing site's copy.

- **`gen_metrics.py` emitted two dead links** on every run: `[Download](download.md)`
  and `[Changelog](changelog.md)` name documentation pages that moved to the apex
  site. Someone had been hand-correcting the generated file; the generator
  overwrote it each time.

## [2.0.1] - 2026-09-08

### Fixed

- **The desktop window had no icon for anyone who installed from PyPI.** The
  `.ico` lived at the repository root, which `package-data` cannot reach, so it
  never entered the wheel — `gui_qt._icon_path()` returned `''` and Qt drew its
  default. A dev checkout had an icon and nothing else did, which is why this
  survived so long: the machine it was written on always had one.

  The icon now lives inside the package, where `_icon_path` was already looking
  as its second candidate, and ships with it.

### Changed

- **One logo, everywhere.** archeus had two marks — a navy-tile one for the
  terminal and an inverted bright-tile one for the desktop GUI — each drawn by
  its own script. Two marks for one product is two things to keep in step, and
  the answer to "which one is the logo" was "it depends where you are looking".

  There is now a single hand-drawn mark, kept as `docs/assets/logo.png`, and one
  generator that writes every icon from it: the app icon, the documentation
  favicon and the marketing-site favicon. `tools/make_gui_icon.py` is deleted.

  Two things `tools/make_icon.py` does to the source, both deliberate: it crops
  to the tile using the alpha channel, because the export carries a soft drop
  shadow that an icon must not bake in (every OS draws its own) and the artwork
  sits off-centre in its canvas; and it saves from the largest frame, because
  passing `sizes` alongside a small base silently keeps only 16×16.

- **The social card carries the mark**, sized from the measured width of the
  text rather than a chosen number — the first attempt used a fixed 360px and
  landed on top of the tagline. It is written to both sites now. It used to be
  generated into the documentation site and copied into the marketing one by
  hand, and the two had already drifted apart by a kilobyte.

## [2.0.0]

### Changed

- **claudectl is now archeus.** The name changes; nothing else in this release
  does. Two reasons, and the second is the one that mattered:

  An unrelated Rust project publishes a `claudectl` too, and it holds six of the
  eight organic search results for the name — partly because a Rust crate is
  granted three high-authority domains (crates.io, docs.rs, lib.rs) where a
  Python package is granted one. That is not a gap any amount of content
  closes. And the tool is outgrowing what the name says: reading and managing
  *other* agent harnesses' state is the next piece of work, and a tool named
  after one vendor's product cannot carry it.

  In Paracelsian alchemy the *archeus* is the organising principle that keeps a
  body coherent as it grows, which is the job here.

  **Everything migrates on first run, and nothing is deleted.** Settings,
  accounts, per-project launch defaults, the stats and model caches, the agent
  and skill libraries, and every project's `.claudectl/` — its memory graph,
  snapshots, plans and logs — move to the new names in one pass. A destination
  that already exists is merged into rather than clobbered, and a step that
  fails leaves both copies in place and is retried on the next start rather
  than being written off.

  What this means for you:

  ```
  pip install archeus          # the command is `archeus` now
  ```

  Installed hooks and the statusline need no attention: they were always
  recorded as a path to a script, never as the command name.

  Renamed alongside: the `X-Claudectl` GUI request header, the `CLAUDECTL_*`
  environment variables, `~/.claude/claudectl.json` and its sibling caches,
  and `<project>/.claudectl/`.

  Not yet renamed, on purpose: the documentation domain and the GitHub
  repository path, which still resolve under the old name until both moves
  happen. They are one substitution away.

## [1.9.1] - 2026-09-08

The last release published as `claudectl`. Its only change is a notice saying
so — in the terminal UI's banner, in `claudectl --help` and on the PyPI page.
Without it `pip install -U claudectl` would report "already up to date"
forever, because from PyPI's side nothing had changed.

## [1.9.0] - 2026-09-04

Two things claudectl says about itself turned out not to be true, and both are
now. It said a GUI job would never hang on a keyboard, and three of them did.
It said the local API was guarded by three layers, and it had two — while the
page carrying the key was handed to anyone who asked for it. This release is
mostly that: the security sweep, the hangs, and a session list you can read.

### Security

- **Cross-site scripting in the desktop GUI, and it reached a shell.** Every
  value that reached an inline event handler in `web/app.js` — seventy-nine
  interpolations — was escaped at the wrong layer. `${JSON.stringify(v)}` inside
  `onclick='…'` escapes for JavaScript and *nothing* for HTML; `'${jsq(v)}'`
  inside `on…="…"` did the mirror image. One apostrophe closed the attribute and everything after it was
  parsed as new attributes.

  The values are not yours: a filename from a repository you cloned, an MCP
  server name out of a project's `.mcp.json`, a git branch, a skill directory,
  a plugin name. Injected script ran same-origin with the API token in scope,
  and `/api/settings` plus `/api/open-editor` turn that into an arbitrary
  command. One helper, `hesc()`, applies both layers in the right order and is
  now the only way a value reaches a handler; `tests/test_inline_handlers.py`
  fails the build if a bare `JSON.stringify` ever appears in markup again.

  It was also a plain bug: a suggestion containing "don't" broke the page.
- **The page that carries the API token gave it away.** `GET /` was served on the
  `Host` check alone, and `/` is the response the per-run token is substituted
  into — so any process that could open a socket to the port could simply ask
  for it, which on Windows includes a process running as a *different user*,
  because loopback is not a user-identity boundary. `/` now takes the token in
  its query string exactly as `/graph` always has, the launcher puts it there,
  and the SPA drops it from the address bar on boot.
- **The guard now has the three layers it always claimed.** `gui._guard()`
  implemented `Host` and the token; the documented middle layer — rejecting a
  cross-site fetch — existed only in the failover proxy. It is the layer that
  still holds if the token leaks, so it is the one that mattered here. It had to
  be written as an allowlist rather than the proxy's outright rejection, because
  the SPA's own `fetch()` sends those headers.
- **`git clone` ran an attacker's URL before anything reviewed it.**
  Installing a skill from git passed the URL straight to `git clone` with no
  scheme check and no `--`, and `ext::sh -c …` is a real git transport that
  executes on clone. The review gate that shows you what will be installed runs
  *after* the checkout, so it never protected the fetch. Remote URLs are now
  validated in one place (`proc.remote_url_ok`) and the option list is
  terminated; the same applies to adding a plugin marketplace and merging a
  worktree branch.
- **Two endpoints deleted whatever they were told to.** `/api/agents/delete`
  reached `os.remove(body['file'])` and `/api/skills/remove` reached
  `shutil.rmtree(body['dir'])` with no validation at all, so
  `{"dir": "C:\\Users\\you"}` was a recursive delete of your home directory.
  Both now require a path claudectl actually manages. `target_cfgdir`, which
  becomes `CLAUDE_CONFIG_DIR` for a spawned `claude`, is validated by the same
  account allowlist as `cfgdir` — it was skipped only because it is spelled
  differently.
- **Path traversal in output styles.** `read` and `delete` joined the style name
  into a path raw, three functions away from a `save` that had always sanitised
  it: `?name=../../../../Users/you/Documents/notes` read that file, and delete
  removed any `.md` on the volume.
- **A repository name could inject script into the architecture graph**, which is
  served same-origin with the GUI and under the same policy. The graph's JSON
  payload is also now safe against U+2028/U+2029, which are JavaScript line
  terminators that `ensure_ascii=False` emitted raw.
- **`.claudectl/` marks itself never-commit.** claudectl writes it into *your*
  repositories, and it holds `bash-log.txt` — every Bash command Claude Code ran,
  which routinely includes `export TOKEN=…` and `curl -H "Authorization: …"` —
  plus `injected-context.md`, an entire transcript. It now seeds a `.gitignore`
  the first time it is created. `claudectl.json`, which holds your OmniRoute key,
  is written `0600`.
- **`/api/state` echoed the OTEL headers value back to the page**, and that
  setting is documented as carrying `Authorization=Bearer <token>`. It is the one
  secret in the settings payload that never got `omniroute_api_key`'s write-only
  treatment. It is reported as a boolean now, and the field in the settings page
  is write-only: blank means keep what is stored.
- A non-ASCII byte in the `X-Claudectl` header raised inside `hmac.compare_digest`
  and printed a traceback instead of answering 403.

### Added

- **Logs, in both interfaces.** A new **⚙ Logs** screen in the TUI and **Logs**
  page in the GUI, over one append-only file at
  `~/.claude/claudectl-events.jsonl`: claudectl's own headless Claude calls and
  why they failed, background job crashes, auto-memory scheduler passes, the
  failover proxy, and any state file it had to quarantine. Newest first,
  filterable by level and by text, capped at 256 KB.

  Until now those failures went nowhere at all. The `claudectl` logger carried a
  `NullHandler` unless `CLAUDECTL_DEBUG` was set — which is off for everyone —
  so around forty `log.exception` sites, including *every* background job crash
  and *every* faulted API handler, wrote to nothing. One logging handler now
  fans them all in; no per-turn path writes to the log, and no hook touches it.
- **Hand off** — on every session row in the GUI, and `⇧K` in the terminal UI.
  Start a new session seeded with a previous one's transcript, under any account
  you like. It replaces the Tools-tab "new chat with injected context" flow,
  where you had to pick the source session from a list; the row *is* the source
  now.
- **A `standard` skin** — no chassis, system font, hairline borders. The plain
  one, for when the point is the content. 32 palettes, 8 skins.
- **`headless_quota` setting** — `prompt` (default), `auto` or `off`. Decides
  what happens when claudectl wants to make one of its own Claude calls and the
  account's limit is already full.

### Fixed

- **A session row shows what the session is about again.** The action strip was
  invisible until you hovered a row, but it still occupied its full width at all
  times — so adding **Hand off** as a tenth action took roughly a quarter of the
  title away from every row, whether you were reading or acting. The strip is out
  of the layout entirely now: the title gets the whole row at rest, the actions
  fade in over its right end on hover, and nothing moves. They are reachable by
  keyboard for the first time. The row also carries the full title as a tooltip,
  the preview text kept behind it is no longer clipped to 65 characters, and an
  archived row shows its AI title instead of falling back to the preview.

  In the terminal UI the name column scales with the window instead of a fixed 30
  columns, and the hint bar drops whole hints rather than cutting the last one
  mid-word — which is what `⇧K hand off` had been doing at 80 columns.
- **Three GUI jobs hung until a six-hour reaper.** AI-generate agent, AI-generate
  hook and AI CLAUDE.md all reached an interactive terminal primitive on a
  background thread, where no keypress is ever coming: nothing logged, nothing
  timed out, and the interface said "running" the whole time. Each is now split
  into a non-interactive function the job calls and a thin terminal wrapper.

  The underlying cause is more general and is now closed generally: a module that
  did `from .ui import text_input` held its own reference, which patching `ui`
  never moved. The bridge sweeps for the original function instead of naming
  modules — naming them is what had already failed twice.
- **claudectl spent accounts that had nothing left.** Every internal
  `claude -p` call — AI agents, AI skills, MCP analysis, system prompts, AI
  CLAUDE.md, memory and lessons extraction, Plan → Execute and its council,
  scheduled loops — launched without checking the account's rate-limit window.
  On a full window the call failed and you were told "No output from Claude",
  while a second configured account sat there with headroom.

  claudectl now stops and offers the accounts that still have headroom: a picker
  in the TUI, the existing approval modal in the GUI. Unattended work (the
  scheduler, the detached scan worker, a scheduled loop) never prompts — it
  records the reason and skips, rather than quietly spending an account you did
  not offer. The check reads the usage data the plan-usage poller already
  fetched, so it costs no network call; an unknown limit is never treated as a
  full one. `claude mcp`, `claude plugin` and `claude --version` are untouched —
  they cost no quota.
- **The two foreground runners destroyed the reason a call failed.**
  `run_with_progress` and `run_with_progress_stdin` sent the child's stderr to
  `DEVNULL` and returned nothing on a nonzero exit, so a rate limit, an expired
  login and a genuine crash were all reported identically as "No output from
  Claude". They now capture stderr and latch it in the same place
  `_run_cancellable` already did, and the callers report what `claude` actually
  said.
- **Rate-limit detection no longer fires on the model's own output.** Reading the
  whole of stdout to find the real refusal meant a bare `429` matched a token
  count and a bare `quota` matched any answer that discussed rate limiting —
  locking an account out of headless work for fifteen minutes after a run that
  had nothing wrong with it.
- **Archived sessions from other accounts were invisible**, and the ones you
  could see could not be restored to the right place.
- **`/api/sessions` was re-parsing every transcript on every GUI restart** — an
  8-second median on a large project. The disk cache existed but nothing on the
  cold path could reach it. It also now carries a schema number, so a change to
  what claudectl stores about a session is visible on old sessions instead of
  only on new ones.
- **The window kept painting while it was not on screen.** CSS animations, a
  world's overlay and the CRT caret all kept running behind a hidden canvas, and
  a light or OLED palette flashed the wrong colour during the swap. Blur is
  debounced, focus is not, and the dashboard's teardown-and-refetch is debounced
  with it — Qt fires spurious blur/focus pairs on things that are not a focus
  change. A tab becoming visible inside the debounce window could also leave the
  page stuck in its blurred state.
- **Unresolvable projects cost 98% of the project listing.** A path that no
  longer exists on disk was re-walked on every call, forever, because only
  successful lookups were cached. `claude mcp list` is cached for 30 seconds now
  including its failures — which is the case that costs the most, because a
  slow-failing MCP server is exactly when it is slowest.
- **The whole OTEL section of the settings page was inert.** It read
  `ST.otel_enabled` and friends while `/api/state` nested them under `ST.otel`,
  so every field rendered its default no matter what was saved — and pressing
  Save then wrote those defaults back over the real configuration, including
  blanking the headers. The payload is flat now, named exactly as
  `/api/settings` takes the values back.
- **Two "Open in editor" buttons had never worked**, sending a parameter the
  endpoint does not read. `/api/job/<id>/decide` — the route every approval gate
  resolves through — wrote two HTTP responses for one request.
- **One noisy warning was crowding the event log out.** The dedupe key contained
  the measurement it was deduplicating, so 609 of 674 events were the same
  warning differing by one decimal. Only decimals collapse now: an HTTP status or
  a project path with a digit in it is part of the event's identity, and folding
  those was dropping real failures.

### Changed

- `.claudectl/` is created through one helper, and `config.write_atomic` takes an
  optional file mode.
- The plugin manifest, the marketplace entry, the docs page and `CITATION.cff`
  are all checked against `pyproject.toml` by one test.

## [1.8.2] - 2026-09-01

Memory was twelve things and the interface could name three of them. This
release makes the whole layer legible — what exists, what writes it, when it
reaches a session and what it costs — and fixes the four ways it was quietly
spending more of your limit than you asked it to.

### Fixed

- **Path-scoped rule files were loaded on every turn, not lazily.** They were
  written with `globs:` frontmatter — Cursor's key. Claude Code reads `paths:`,
  and a rule file without it is loaded unconditionally, so the entire point of
  splitting memory into one file per module was lost while the UI reported each
  one as free until Claude opened a matching path. Measured on this repo:
  **22 238 → 18 363 always-on tokens, 3 875 off every single turn.** Existing
  rule files are rewritten with the correct key on the next sync — free, no
  Claude call.
- **A failed memory cycle was reported as progress.** Failed and skipped units
  were summed into one `pending_units`, and every surface worded it "the next
  cycle takes them" — so on a rate-limited account six *failed* extractions an
  hour read as work safely queued. Failures are now counted as failures and
  shown with the error that caused them. A nonzero exit also discarded the real
  error text whenever no job was attached, which is exactly the scheduler and
  the detached background worker.
- **Auto-memory no longer speeds up when it has a backlog.** A capped cycle used
  to schedule the next pass 45 seconds later, again and again until the project
  caught up. Across several opted-in projects that is most of a daily limit
  inside an hour, and on a failing account it was the same dead calls in a loop.
  One pass runs when claudectl starts and one every interval you configured: the
  per-cycle cap decides how much a pass may spend, the interval decides how
  often that happens, and nothing else schedules work.
- **Opening a project no longer adds an unscheduled memory cycle.** Opting a
  project into background auto-memory also implied "refresh whenever you open
  it", so the configured interval bounded nothing — and the GUI never consulted
  the per-project flag at all, deciding from the global setting alone. Background
  auto-memory now owns the spend; **Build with Claude** still refreshes on demand.
- **Disabling or deleting a hook applies to every account.** Installing one
  already did. Turning one off wrote only the account you happened to be looking
  at, so a hook installed once and disabled once kept firing from the others —
  with the UI showing it as off. Selecting an account still acts on that one alone.
- **Session topics no longer list claudectl talking to itself.** `claude -p`
  leaves a transcript like any other session, so the CLAUDE.md SESSIONS block was
  spending always-on tokens describing claudectl extracting a module or
  distilling lessons.
- **Opening the recall preview no longer counts as reinforcement.** It appended
  to the hits log, so inspecting memory reshaped which facts survived eviction.
- **The reinforcement log says how many hits are waiting to be folded in**,
  instead of a fixed phrase derived from an unrelated number.
- **Lifetime memory spend includes lesson scans**, which are Claude calls like
  any other.
- **A broken `@import` in a CLAUDE.md is flagged.** Claude loads nothing for it
  and says nothing about it.

### Added

- **The Memory tab inventories every memory artifact** — the graph, the CLAUDE.md
  digest, the AUTOGEN and SESSIONS blocks, the path-scoped rule files, the
  worklog, both sidecars, the cross-project conventions block, the workspace
  manifest, lessons, version snapshots and the per-prompt injection — grouped by
  **when each one reaches a session**: always on, every prompt, when relevant, or
  stored and never loaded. Each row says what it does for you, what it costs and
  what to press. The always-on total is given as a share of the context window,
  which is the only denominator that makes a token count mean anything.
- **What a cycle spent and what it dropped.** Cost per cycle, cumulative spend
  for the project, the names eviction removed, the facts recall reinforces most
  (clickable, showing what each one actually is), and how many sessions each
  lesson is from being dropped.
- **The CLAUDE.md tab shows the file block by block** — your prose, KEEP-fenced
  regions, AUTOGEN, SESSIONS and the memory digest — each with its token cost and
  the one button that regenerates that block alone.
- **Workspace health is per-check rows**, each carrying the points it is worth
  and the button that clears it, instead of terminal output.
- **Version history sits beside the artifact it belongs to** — graph history on
  the Memory tab, CLAUDE.md history on the CLAUDE.md tab — with recent versions
  shown and the rest collapsed.
- **The recall preview says why each entity was picked.**
- **The next pass is stated wherever a cycle left work queued**, so "still
  queued" has an answer to "until when".

### Changed

- **The CLAUDE.md memory digest carries facts, not a table of contents.** It was
  spending its budget listing module names — which tells a session nothing `ls`
  would not — and now spends it on the highest-signal lessons and the module
  dependency edges.
- **The Audit tab is now only what a turn costs across every surface at once**,
  project-scoped and account-scoped together, with the version history it used to
  host moved beside the files it belongs to.
- Generated files (`.claude/rules/claudectl-mem-*.md`, `docs/api.md`,
  `plugin/skills/`) are marked `linguist-generated`, so their diffs collapse in
  review.

## [1.8.1] - 2026-08-31

### Fixed

- **Auto-memory crashed in the GUI**, with
  `Memory update failed: 'NoneType' object has no attribute 'reconfigure'`. The
  stale-on-edit work added in 1.8.0 imported a *hook script* for one path
  helper, and a hook reconfigures stdout when it is imported — correctly, since
  Claude Code hands it a pipe. The GUI runs as a windowed process with no
  console, where `sys.stdout` is `None`, so that line took down the whole
  refresh cycle. In the GUI auto-memory therefore never ran at all: the hourly
  pass failed silently on every project, and opening a project only made the
  same failure visible. The dependency now points hook → library, never the
  other way, and a gate walks the package for any module importing an entry
  point — it found two more instances immediately (see below).
- **The context-weight audit under-reported two always-on hooks.** It imported
  `minimalcode_hook` and `concise_hook` for their rule text inside a bare
  `except Exception: pass`, so in the GUI the import failed and both hooks'
  per-session cost silently vanished from the total. The text now lives in
  `hookrules.py`, which the audit and the hooks share.
- **A hook no longer dies when there is no stdout.** Setting UTF-8 on a pipe is
  right; being the reason the hook exits when stdout is absent is not.
- **Auto-memory runs on launch and on the interval, from either interface.**
  The periodic pass had one caller, in the GUI's server startup — so on the
  terminal side "keep this project's memory updated automatically" only ever
  happened when you opened the project. The scheduler loop itself had no test
  beyond "the stop flag can be set"; the launch pass, the repeat and the stop
  are now covered.

## [1.8.0] - 2026-08-31

### Added

- **`claudectl --help`** (and `-h`, `help`, `--version`, `-V`). A pip install used to
  answer the most obvious command by opening a full-screen terminal UI. The help text
  covers every subcommand, what the tool does and where its state lives; it is answered
  from `cli.py`, which imports the standard library and nothing else, so it costs nothing
  and cannot be broken by anything in the TUI stack. A test enumerates the dispatch table
  from the source, so the text cannot fall behind it.
- **Hide projects you never want to see.** Every folder Claude Code has ever run in shows
  up in the project list, including one-off experiments and folders that no longer exist
  as work. A project can now be hidden from the TUI project menu and the GUI sidebar —
  from `Hide / restore projects` in the main menu, or the `Hide` button on a project page.
  It is a view flag (`project_defaults[<enc>].hidden`), so nothing on disk moves: the
  sessions stay resumable and restoring costs one click. The TUI says how many rows are
  filtered; the GUI grows a `Show N hidden projects` button while any are.
- **The Skills section shows what Claude Code actually loads.** It listed claudectl's own
  private library (`~/.claude/claudectl-skills`) — a directory nothing reads — beside a
  "Project skills" card that could never fill, because opening a global page ends project
  context. Now it is the four scopes Claude Code really resolves (personal, project,
  plugin, bundled), each row carrying the command you type and its real usage count from
  Claude Code's own `skillUsage` counters, plus the starters to install from. What was in
  the private library is migrated into `<account>/skills` once, and `sync-accounts` levels
  skills across accounts like everything else.
- **Desktop notifications** when a background job that ran longer than 20s finishes, and
  when the detached memory worker is done — which had no interface of any kind before.
  One hook in the job runner, one in the worker; `Settings → Notifications` turns them off.
- **Loops, including ones that run with nothing open.** A `/loop` is session-scoped — it
  fires only while its session is open and idle — so claudectl offers both: start one *in a
  session* (and watch it through that session's transcript), or *in the background*, where
  claudectl registers an entry in Task Scheduler (cron elsewhere) that runs headless
  `claude -p` on the interval, under the account you pick, with claudectl closed. A
  background loop carries its guardrails in the runner rather than the UI: a permission mode
  you choose (`claude -p` starts in Manual and would otherwise do nothing), a 7-day expiry
  that the scheduled run enforces on itself, your per-call budget cap on every run, a
  notification when one fails, and a log of the last twenty runs with their cost. Each run
  is a fresh session that reads a rolling `CLAUDECTL:LOOP` record in the project's
  CLAUDE.md — rewritten every time, capped at five entries, so it cannot grow. `loop.md` is
  edited on the same page for either scope, with an AI draft behind the usual approval gate.
- **Agents that actually get delegated to.** Copying agent files into a project makes them
  available; Claude Code still picks a subagent by matching the task against its
  `description`, and nothing reads the body — measured here, `agentLastUsed` held one entry
  against ten installed agents. Four levers now: a `CLAUDECTL:AGENTS` delegation table in
  the project's CLAUDE.md (the one file read on every turn), **Sharpen descriptions** (one
  Claude call rewrites each installed agent's description into *Use PROACTIVELY when …*
  form, diff-approved, bodies untouched), an optional `suggest-subagent` prompt hook that
  names a keyword match with no model call and stays silent otherwise, and a last-used
  marker in the picker so the dead weight is visible.
- **Output styles explain themselves**, in scope order with the active one and the file
  that pins it named, and four claudectl starters (Terse, Reviewer, Pair, Ship) to copy.
- **Global CLAUDE.md has its own page.** It was the third card at the bottom of the MCP
  servers page.
- **Search boxes** on the agent library, the project agent picker and the skills inventory.
- **Skills usage that means something.** `skillUsage` counts one thing — the times you
  *typed* `/name` — so a plugin that works through a `SessionStart` hook reads as unused
  forever (caveman: "used twice, 56 days ago", while shaping every session). The page now
  shows that counter merged across **every** account beside a second, measured signal from
  your transcripts: *in 27 of your last 30 sessions*. Two flags cover the rest — **manual
  only** (`disable-model-invocation`) and **thin description**, the two reasons a skill
  silently never fires. Personal skills install into, and delete from, every account.

- **Auto-memory that actually runs, and converges.** Turned on per project (memory hub
  `o`, or the checkbox on the GUI memory tab — one flag now honoured by both interfaces
  *and* the detached worker), a project's memory no longer goes stale while it is on. Each
  cycle extracts what its budget allows and leaves the rest queued; the scheduler returns
  in seconds rather than after the full interval until the project has caught up. It
  bootstraps a project with no graph at all, so the first build no longer has to be
  manual, and it runs from the TUI as well as the GUI.
- **A stale-on-edit hook.** `memory-stale-on-change` records the files Claude edits, so
  auto-memory re-extracts exactly those instead of walking the project. The periodic scan
  remains the reconciler for edits made outside Claude Code.
- **Nothing shrinks without a way back.** Pin any entity or lesson and the importance cap
  can never evict it. Fence a section of CLAUDE.md between `CLAUDECTL:KEEP` markers and AI
  compression never even *sends* it to the model. Prune names the exact session entries it
  will drop and asks first — the GUI destroyed silently while the TUI confirmed. Twelve
  versions of CLAUDE.md and of the memory graph are kept, browsable with a diff and
  restorable from the context-audit page; restoring is itself snapshotted.
- **"What to work on" is worth reading.** Four new free signals (stale context with the
  key that clears it, `TODO`/`FIXME` markers, deferred `ponytail:` shortcuts, untested
  modules) plus an optional one-call *Find work* scan that adds bugs, vulnerabilities,
  slow paths and functions worth building. Findings persist, so the card stays instant.
- **Sharpen descriptions is machine-wide.** It lived on one project's tab and rewrote that
  project's agents only. It now covers every account's agents, every project's, and the
  library — grouped so the same agent in twelve projects is one question and twelve
  writes, behind one approval gate.
- **Controls for the memory settings that had none.** Seven of fourteen lived only in
  `claudectl.json`, including `memory_max_calls`, which the memory hub and the health
  check both told you to raise.
- **Per-cycle cost, and what a cycle actually did**, in the memory hub and the GUI. The
  real figure was captured from every headless call and read by nothing.

### Fixed

- **Auto-memory did nothing at all once more than six modules had changed** — the harder
  you worked, the less it updated — and it could never build a project that had no graph
  yet, so "keep this updated automatically" required a manual build first. The GUI
  checkbox wrote a flag only the GUI scheduler read, while the TUI and the worker gated on
  a setting with no control on either surface, so ticking the box did nothing outside a
  running GUI window.
- **A failed extraction wiped a module's memory and never retried it.** A Claude call that
  timed out returned an empty result indistinguishable from "this module has nothing", so
  every fact already known about it was marked superseded — and its file hashes were
  recorded as current, making the loss invisible to every later check. A capped run did
  the same to every module it skipped. Provenance now advances only for modules actually
  extracted, and `save_memory` failing is no longer ignored at five call sites.
- **The staleness check read every source file in the project**, in full, to hash it — on
  every scheduler tick and every project open. Files are compared by `(mtime, size)` first
  and re-hashed only when that moves; content stays the source of truth, so touching a
  file still costs no Claude call.
- **A memory refresh reported success after crashing.** The GUI badge read the scan lock
  disappearing as completion, which a failed cycle does exactly like a successful one; the
  detached worker announced "Memory updated" when nothing had run, and told nobody at all
  when it failed.
- **The query `the` returned 33 entities.** The recall IDF could never reach zero and a
  positive score was the only gate, so with the prompt hook on, memory was injected into
  prompts that asked for none. Ranking now fuses four signals by position (BM25, path,
  dependency rank, and a confidence-weighted lesson signal) instead of adding four
  quantities on four different scales, and a contentless prompt retrieves nothing.
- **Recall reinforcement had never worked.** The counter that decides what eviction keeps
  was folded in only by a refresh that had work to do — so on this repo 807 recorded hits
  had produced a maximum counter value of 1 — and it credited every entity that ranked
  rather than the ones that fit the budget and were actually injected.
- **One generated rule file was always loaded and another could never load.** The
  path-scoped glob was built with a *character* prefix, so `{tests/, tools/}` became
  `t/**` (matching nothing, ~375 tokens that never loaded) while a unit whose files
  diverged at the first segment became `**` — permanently in context, in the one feature
  whose whole purpose is laziness.
- **The `memory-stale-on-change` preset had never marked anything stale.** It was bound to
  an event whose matcher is a list of literal filenames, and it invoked a script that does
  not touch memory.
- **A workspace could not stop reporting itself stale.** Only two operations recorded a
  freshness baseline, so rebuilding memory — the very thing the screen tells you to do —
  could never clear it. Checks that contribute nothing to the score no longer show a
  warning dot, and every missing point now prints what recovers it.
- **claudectl could rename Claude Code's live `.claude.json` out from under it.** Reading
  a file another program is writing occasionally catches a half-written one, and the
  corrupt-file quarantine treated that as damage worth preserving.
- **Cross-project conventions was permanently empty** and described inputs it does not
  read: it scanned one account, one directory deep. It now reads every account, accepts
  `decision` lessons, and lists near-misses with a Pin button instead of a dead end.
- **A finished job no longer repaints the page you moved to.** `onDone` handlers called
  `drawMemory()` / `drawPage(…)` unconditionally, so building memory and walking away put
  you back on the memory tab minutes later, over whatever you had opened. The refresh is
  now a guarded `redraw` in the job runner, gated on the view the job started from.
- **The `view` button on a built-in output style showed "(empty)"** — those ship inside
  Claude Code and have no file, which read as a broken button.
- **Selecting an output style with no project open threw**, because every write assumed
  `CUR.path`. The same bug made the Skills and Output styles pages' project sections
  structurally unreachable: navigating to a global page clears the current project, so the
  "this project" card could never have shown anything. They use the last opened project and
  say which one it is.
- **A folded YAML description (`description: >-`) parsed as the literal `>-`**, so every
  plugin skill looked as if it had no description at all.
- `load_settings()` copied the defaults shallowly, so every load of a settings file that
  named no `project_defaults` handed back the same dict — and each writer of one mutates
  it in place. In a long-lived process (the GUI, a long TUI run) one project's pins leaked
  into the next load.

## [1.7.0] - 2026-08-28

### Added

- **What you provision now reaches every account, not just the default one.** Hooks,
  plugins, marketplaces, user agents and the global `CLAUDE.md` were all written into
  whichever config directory happened to be active when the module was imported — in
  practice the default account. Measured across five configured logins, the default had
  18 hooks, 3 marketplaces, 3 plugins and a global `CLAUDE.md`; the other four had none of
  it. The status line was the only feature that ever reached all of them, because it was
  the only one with a real fan-out; that fan-out is now the rule rather than the exception.
- `claudectl sync-accounts` levels every account up to the union of them all, on the
  command line, on the GUI's Accounts page and in the TUI accounts menu. It shows the
  per-account diff **before** writing anything, only ever adds (an account keeps whatever
  the others lack, because nothing can tell a deliberate choice from a gap), routes every
  plugin install through the same review gate a single-account install uses, and reports
  nothing to do when re-run.
- The Plugins page says which accounts have each plugin and marketplace, and offers to
  install one into the accounts that do not. Adding a marketplace registers it everywhere;
  removing acts only on the account on screen.
- **Nineteen functions that existed only in the terminal UI now have a surface in the
  GUI**: the editor / `claude.exe` / config-dir paths and the headless budget cap; disabled
  hooks, an enable/disable control and an *Edit settings.json* button; the per-prompt
  recall hook, path-scoped rules and the recall budget, which the GUI had been printing
  read-only; the global `CLAUDE.md` viewer and editor; `claude mcp get` detail and MCP tool
  docs, which the analyze job used to write into a file the GUI could not open; env vars
  and headers when adding an MCP server; the one-key project setup the terminal offers as
  `!`; the architecture stats card, which revives an endpoint that had no consumer at all;
  tools and model when creating an agent; copying a skill into your library; and a Help
  page generated from the navigation and the terminal's own key table instead of retyped.
- Cross-project conventions, `loop.md` at both project and account scope, Claude Code's own
  per-project record and output-style previews — four endpoints that had no control in
  either surface — are reachable.

### Fixed

- `claude plugin …` and `claude mcp …` ran with no environment, so they acted on whatever
  account the process inherited while every reader resolved the configured one: with
  claudectl switched to another account, the Plugins page listed that account's plugins and
  *Install* wrote into the default. Both now name an account explicitly.
- `mcp.update_global_claude_md_mcp` and the conventions sync wrote a file Claude Code reads
  every session with a plain `open(..., 'w')`. A write that dies partway broke the whole
  session, not just claudectl. Both are atomic now.
- A hook disabled in the terminal vanished from the GUI, which then offered its template as
  uninstalled and created an enabled duplicate beside the disabled one.
- The job list on the dashboard raised as soon as any job had said anything: every producer
  appends a `{ok, text}` record and the reader indexed it as a string.
- The per-project recall toggle promised a hook that only one account had installed.

### Changed

- The GUI's accepted-settings list is derived from the settings registry minus an explicit
  internal set, rather than being a sixth hand-maintained copy that had already fallen
  behind it; the terminal's settings rows are named after the settings they write, so the
  two screens can be compared by a test instead of by hand.
- New parity gates, each watched failing under mutation: every route the SPA never calls
  must carry a written reason, a POST route must be reached with `post(`, a value rendered
  as on/off must be one the page can send back, the main menu's rows must name a GUI
  counterpart, and the account fan-out helper must have callers. The browser smoke tool
  walks the page and tab lists derived from the app instead of a hardcoded subset, and its
  floor rose from 40 checks to 85.

### Fixed

- The launch picker's effort slider pointed at the wrong label. `EFFORTS` had grown a
  seventh entry (`ultracode`) but the tick row was six labels typed into the markup, so
  the thumb at *xhigh* — 4/6 of the track — sat under HIGH, and `ultracode` was a stop
  with no label at all. The row is generated from the same list that sizes the slider,
  and each label is placed on its own stop rather than spread with `space-between`, which
  aligns label boxes and drifts every centre off its tick. `tools/shot_gui.py` now
  measures thumb-against-label for every stop.

### Added

- The sessions screen's 29 keys are described in one place instead of three. The action
  table, the `/` palette and the help screen had drifted apart — the palette was missing
  code review (`R`) and the help screen was missing `R`, plan→execute (`X`) and context
  injection (`K`), so code review had no discoverable entry point anywhere in the product.
  Both discovery surfaces are now generated from the table, and a test walks the key
  handlers in the source and fails when one of them has no row.
- The launch picker reads the model list from Anthropic instead of a hand-edited table, so
  a model released this week is selectable without a claudectl release. It uses the login
  Claude Code already holds — no API key — and refreshes once a day on a background thread.
  Facts (context window, supported efforts, release date) come from the API; cost rank,
  capability rank and the "best for" prose stay curated and are inherited by family, so a
  new generation appears with sensible columns rather than blanks. Every failure — no
  network, logged out, `auto_update: off` — falls back to the list shipped with this
  version, never to an empty picker, and a model you have pinned that Anthropic has retired
  keeps its place in the picker with a warning instead of being silently reset to *default*.
- claudectl reports its own version against PyPI and can update itself. A banner says when a
  newer release exists, the Updates screen and the Plugins page offer the upgrade, and
  `Settings → Updates` chooses between being told, installing on quit, and never checking.
  The upgrade runs in its own window after claudectl exits, because pip cannot rewrite the
  console script of the process running from it — and a git checkout is told to `git pull`
  rather than having a release installed over the top of it.
- Claude Code plugin distribution — `claudectl` installs as a plugin, with its bundled
  skills generated from the packaged templates and validated in CI.
- Multi-repo worktrees board and repo discovery, including submodule and linked-worktree
  classification read from the `gitdir:` pointer rather than a subprocess.
- Model failover proxy with TUI and GUI settings, so a dead model is retried instead of
  hanging the session.
- Desktop GUI overhaul: dashboard home, always-on account usage, a single 3D background
  stage, chassis skins and worlds, and an instrument dashboard.
- OmniRoute-aware dashboard and usage views, including free-tier session tagging.
- Resumable saved plans in Plan → Execute.
- Status line, installable per account.
- macOS and Linux support alongside Windows.

### Changed

- TUI/GUI parity is enforced as a CI gate rather than reviewed by hand; the API reference
  in `docs/api.md` is generated from the live route tables and checked for staleness.
- Per-turn work moved off the hot path — the status line dispatches before the TUI is
  imported, and hooks no longer re-stream whole transcripts on every turn.
- Duplicated primitives consolidated into single implementations for transcript reading,
  process control, JSON storage and session paths.
- Default models updated to Opus 5.
- README rewritten around real screenshots.

### Fixed

- Status line resolves the active account and project rather than the checkout it was
  installed from, and reports why an installed status line is not showing.
- Account-scoped settings writes no longer bind the config directory at import time, so
  every account is written correctly.
- Both local HTTP servers authenticate requests, with a host allowlist, browser
  fetch-metadata rejection and a per-run secret.
- State writes are atomic, and a file that exists but will not parse is quarantined
  instead of silently erased.
- Malformed requests return 400 instead of 500, and `cfgdir` is validated against known
  accounts.
- Session paths are resolved from the transcript's recorded `cwd` rather than decoded from
  the encoded folder name, which had dropped UNC-path projects entirely.
- Packaging: the skills templates glob now matches, so the wheel ships them; a CI job
  installs the built wheel and reads the data files back out of site-packages.

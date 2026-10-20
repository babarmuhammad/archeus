# Archeus later-V2 UI — reference study (2026-10-05)

**Status: RESEARCH EVIDENCE.** This is the evidence base for
[ARCHEUS_V2_LATER_UI_RESEARCH.md](ARCHEUS_V2_LATER_UI_RESEARCH.md) (cited there as *LR*). It
extends, and does not repeat, the V2-U0 evidence in
[../research/2026-10-v2-ui-reference-study.md](../research/2026-10-v2-ui-reference-study.md)
(`E-1`…`E-77`). Nothing here is a decision.

## How this was gathered, and how far to trust it

- **Method.** Six read-only research passes ran in parallel on 2026-10-05, one per topic: the
  JARVIS / AI-assistant landscape (`LJ`), agent-orchestration products (`LA`), premium desktop
  products (`LP`), mobile interaction (`LM`), motion, micro-interactions, accessibility and
  platform capability (`LMo`), and visual depth, data visualization and product personality
  (`LV`). A seventh source is the current V1 SPA itself, screenshotted against a seeded
  temporary Core (`D`).
- **Tools.** WebSearch, WebFetch, Jina Reader, the Hacker News Algolia API, the unauthenticated
  GitHub search API, and raw GitHub. OpenCLI search adapters failed with `BROWSER_CONNECT`, and
  every OpenCLI Reddit adapter needs a cookie, so **Reddit was not searched** except where press
  quotes it. Dribbble, Behance and Awwwards were searched; the results for "AI assistant" were
  generic dark dashboards and AI-generated HUD art, and were dropped as low signal. Two passes
  exhausted the session's web-search budget near the end, so **Bear, Craft, Lovable, v0, Bolt,
  Genspark, Raycast AI, Superhuman AI and Restate are not covered** — not looked at, rather than
  looked at and found wanting. No video was watched; motion claims about products come from
  their own documentation or from screenshots and GIF frames.
- **Evidence labels.**
  - **[O]** read in a primary source this session: the vendor's own docs, blog, changelog or
    issue tracker, the designer's own essay, the original paper, a repository's source or
    README, or a screenshot looked at directly.
  - **[S]** secondary: press, reviews, third-party breakdowns, forum threads.
  - **[U]** background knowledge, not re-fetched. Verify before quoting.
- **Dates.** Several products are reported at 2026 versions (iOS 27, macOS 27, Raycast 2.0,
  Linear's March 2026 refresh, Cursor 3, Codex mobile). Where only secondary sources describe a
  2026 release, the entry says so.
- **Fetched content was treated as data.** No fetched page carried instructions aimed at an
  agent.
- **The current-UI evidence is synthetic.** `D` was captured on a temporary Core running the
  fake harness with four plan approvals pending and nothing running. It shows layout and
  language, not a real day's corpus. The script and images are in
  `prototypes/v2-later/v1-diagnosis/`.

Each entry gives the lesson that was extracted and how it transfers. A reference that is only
attractive is not listed.

---

## D. The current V1 SPA (seeded temporary Core, 2026-10-05) [O]

Captured with `prototypes/v2-later/v1-diagnosis/shoot_v1.py` at 1440 × 900 (dark) and
390 × 844 (dark, DPR 2, touch). State: four missions waiting for plan approval, nothing running.

| Id | Observation | Lesson |
|---|---|---|
| **D-1** | Phone Now is **5,590 CSS px tall** (≈ 6.6 screens) for four approvals; phone Attention is 5,099 px. Each approval card is shown fully expanded, every field visible | The phone renders the desktop information model at full depth. Length, not visual quality, is the first phone problem |
| **D-2** | The approval card prints machine strings verbatim: `ASK — ASK deploy: profile:standard@2:USER:deploy (ASK, USER); builtin:floor:deploy-prod (ASK, GLOBAL, locked)` appears **twice per card** (Policy, then Why it asks); Expires is `2026-10-06T09:54:11.148Z` | The user reads policy grammar and ISO time instead of a sentence. The language layer is missing, not the visual layer |
| **D-3** | On desktop Now, one approval card is ≈ 595 px tall: at 1440 × 900 about 1.2 approvals fit above the fold. The conversation column repeats each approval with its own Approve / Reject | Two places on one screen decide the same thing; hierarchy is flat because everything is a full card |
| **D-4** | Phone chrome: the strip, "Go to or tell…" and Control take two header rows (≈ 120 px) plus a 48 px tab bar — ≈ 20 % of an 844 px screen before content. The emergency stop is not on the phone's first screen | Chrome cost and the e-stop's reachability on the phone both need a deliberate answer |
| **D-5** | Desktop Work at 1440: one-line rows span ≈ 1,100 px, title at the left and age at the far right, ≈ 650 px of nothing between | The extra width is unspent. A wide screen gets longer rows rather than more information |
| **D-6** | Phone mission sheet: the Priority control is the second thing on the page, above the outcome; seven tabs wrap to two rows; the tab bar draws over the sheet | Detail order follows the data model, not the question a person on a phone is asking |
| **D-7** | The state sentence ("Archeus is idle. 4 need you.") is the strongest element on every capture | The typographic hierarchy V2 decided (Display, headline) is the right spine; it needs the rest of the page to defer to it |

<!-- RECOVERY: only the first 60 lines of this file (§ intro + §D "The current V1 SPA")
     were ever read in a captured transcript. The rest (likely §A/B/C: the JARVIS/agent-product/
     mobile/motion/visual-depth reference passes referenced by ARCHEUS_V2_LATER_UI_RESEARCH.md as
     LJ/LA/LP/LM/LMo/LV) could not be located and is NOT recovered. -->

# Track A — site legal, compliance, accessibility, and Ko-fi support

Paste this whole file as the first message of a fresh session.

---

You are working in the archeus repo (D:\Claude) on branch `legal/site-compliance`, in a
dedicated git worktree. Three other agents are working the same repo in parallel on
`feat/session-flowgraph`, `chore/code-simplifier` and `feat/account-rotation`. Your branch
merges FIRST of the four, so keep your diff clean and self-contained.

**A fifth agent — not one of the four — is already working directly on `main`,** in the primary
working tree (`D:\Claude`), with uncommitted changes and unpushed commits. Treat `main` as
moving, not as a fixed base:

- **Never touch the primary working tree.** No `git add`, commit, stash, checkout, reset, clean
  or branch switch in `D:\Claude`. Work only inside your own worktree.
- `git worktree add` branches from the last commit, so that agent's uncommitted edits are not in
  your tree. That is correct — do not try to pull them in.
- Its work is entirely in `claude_sessions/**` and `tests/`, which you do not own, so a content
  conflict is unlikely. Still: `git fetch && git rebase origin/main` before you open a PR, and
  re-run your full gate list afterwards, because main will have moved since you branched.

## Ownership fence

You may create or edit ONLY:

```
www/**
docs/*.md, docs/stylesheets/**
mkdocs.yml
README.md
.github/FUNDING.yml                    (new)
pyproject.toml                         ([project.urls] only)
packaging/npm/package.json             ("funding" field only)
packaging/crates/Cargo.toml            (metadata only)
tools/check_site_seo.py
tests/test_site_links.py
tests/test_site_legal.py               (new)
notes/site-legal-audit.md              (new)
notes/site-legal-risks.md              (new)
notes/handoff-legal.md                 (new)
```

You may NOT touch: `claude_sessions/**`, `tools/shot_gui.py`, `docs/img/**`,
`www/public/img/**`, `CHANGELOG.md`, or any file under `tests/` not named above.

Do NOT regenerate screenshots — an integrator runs `tools/shot_gui.py --docs` once after all
four branches merge. Do NOT bump any version and do NOT publish to any registry; the package
metadata change rides the next release.

## Scope

The two published surfaces are ONE entity: `www/` (Next.js App Router, the apex) and `docs/`
(MkDocs, the manual). Read `notes/seo.md` and the CLAUDE.md sections on the two sites before
writing anything — the two hosts have OPPOSITE URL shapes (the apex serves `/features`, the
manual serves `/installation/`) and a link written with the other one's convention costs a 308.

## Phase 1 — audit before you write

Produce `notes/site-legal-audit.md` answering each item WITH EVIDENCE (a `file:line` or a
quoted string). Do not assume. A "no" backed by a grep is the deliverable; a skipped item is not.

1. **Data collection.** Does any page collect personal data? Enumerate every `<form>`, input,
   mailto, newsletter, waitlist, contact form, or POST target.
2. **Analytics and tracking.** Any `gtag`, Vercel Analytics or Speed Insights, Plausible,
   PostHog, Sentry, or first-party logging that sets an identifier.
3. **Cookies, localStorage, sessionStorage.** Enumerate every writer and classify each as
   strictly-necessary or not. Cookie CONSENT is legally required only for non-essential
   storage — if every writer is strictly necessary, the correct answer is a cookie policy with
   NO consent banner, and you must say so and show why.
4. **Third-party embeds.** iframes, external script/img/font sources, CDN calls, shields.io
   badges, raw.githubusercontent images. Each is a data transfer to a third party and belongs
   in the privacy policy.
5. **Payments.** See the Ko-fi section below — money now moves, so this item is no longer
   "nothing is sold".
6. **Claims audit.** Every superlative, benchmark number, "zero dependencies", test count,
   performance figure, security claim, and comparison to another product (`docs/compare.md`
   especially). For each: is it TRUE today and verifiable from this repo? Flag every one that
   is stale, unverifiable, or absolute.
7. **Testimonials, reviews, logos.** Any quote, star rating, user count, "trusted by", or
   third-party logo. Anything that is not a real attributable quote with permission gets
   removed, not softened.
8. **Images and assets.** Licence for every image in `www/public` and `docs/assets`. The icon
   and banner are Federico Coscia's work — his attribution must stay intact.
9. **Business identity.** What identifiable operator, contact route and jurisdiction does the
   site publish today? Most disclosure regimes require a real contact route.
10. **Accessibility baseline.** Run a real pass, do not eyeball. Every `<img>` alt; heading
    order (exactly one `<h1>` per page — there is already a gate for this); link text that
    makes sense out of context; visible focus; keyboard reachability of every interactive
    element including anything built on a `div`/`span` with `onClick`; form labels and error
    association if any forms exist; `prefers-reduced-motion` respected; and colour contrast of
    EVERY text/background pair, including the 3D journey component, in both light and dark.
    Report measured ratios. Target WCAG 2.2 AA — 4.5:1 body, 3:1 large text and UI state.

## Phase 2 — implement what the audit shows is needed, and nothing it shows is not

- Legal pages live under `www/app/legal/<slug>/page.tsx`, one per policy, each with a
  `metadata` export carrying a 50–165 character description (there is a gate on this), an
  effective date, and plain language. Mirror into `docs/` ONLY if the manual is the canonical
  home for that content — never publish two divergent copies of a policy; link the manual to
  the apex copy instead.
- Wire every new page into `www/components/site/Footer.tsx`, `www/app/sitemap.ts`,
  `www/app/llms.txt` and `www/app/llms-full.txt`, and `docs/llms.txt` if a docs copy exists.
  A legal page that is not in the sitemap and not linked from the footer is not published.
- Fix accessibility defects in place. Alt text describes function, not appearance; a purely
  decorative image gets `alt=""`.
- Delete fabricated social proof and unverifiable claims outright. Rewrite stale claims to
  what the repo can prove today.
- Add the operator and contact block the disclosure check requires.

## Phase 3 — risk register

`notes/site-legal-risks.md`, one row per risk: what it is, which regime (GDPR/ePrivacy, UK
GDPR, CCPA/CPRA, EU Accessibility Act / EN 301 549, FTC endorsement and substantiation rules,
consumer-contract and distance-selling rules), what was done, what remains, and your confidence.

Include a clearly-marked **Needs a lawyer** section for everything you could not settle from
evidence. You are not a lawyer and this is not legal advice — say so in the register, and do
not claim anywhere that the site is "compliant". Templates are a starting point; jurisdiction
depends on where the operator is established and where users are. Ask the user rather than
guessing.

## Ko-fi support link

Add a Ko-fi support link modelled on how `DevDock-AI/claude-unlimited` does it: a shields.io
badge in the README badge row, and a one-line closing call to action at the bottom of the
README. That repo uses exactly two plain links and NO embedded widget — match that. Do not add
the Ko-fi iframe, the floating button script, or any Ko-fi JavaScript.

The Ko-fi username is a placeholder: `<KOFI_USERNAME>`. Do NOT guess it, do not invent a URL,
and do not commit a live link to a page that does not exist. If the user has not given you the
handle, write the placeholder, keep it in a single named constant per file that needs it, and
list it as a blocking open question in the handoff.

**What to add**

1. `README.md` — a badge in the existing badge row, matching that row's style:
   ```
   [![Support](https://img.shields.io/badge/support-ko--fi-ff5e5b)](https://ko-fi.com/<KOFI_USERNAME>)
   ```
   plus a closing line after the License section. One short sentence. Do not write a
   fundraising pitch, and do not claim what donations fund unless it is true and evidenced.
2. `.github/FUNDING.yml` — `ko_fi: <KOFI_USERNAME>`. This is what turns on GitHub's native
   Sponsor button; it is separate from the README badge and both are wanted.
3. `www/` — a "Support" link in the Footer's "Project" column (`www/components/site/Footer.tsx`,
   the `COLUMNS` constant, `ext: true`). Route the URL through `www/lib/site.ts` as a new `SITE`
   key rather than hardcoding it in the component — `SITE` is already the single source for
   every external destination, and `tools/set_domain.py` and the link tests read it.
4. Package metadata: `pyproject.toml` `[project.urls] Funding`, `package.json` `"funding"`,
   `Cargo.toml` metadata. One line each. These surface a funding link on PyPI, npm and
   crates.io for free.
5. Decide with evidence whether a dedicated `/support` page on `www/` is warranted or whether
   the footer link plus README is enough. Default to the smaller answer — a page holding
   nothing but a link is worse than the link.

**How Ko-fi changes the audit — these supersede the earlier items where they conflict**

- **Item 5** is no longer "nothing is sold, refund policy N/A". Money now moves:
  - A donation is not a sale. There is generally no statutory right of withdrawal on a
    voluntary gift, and Ko-fi — not you — is the payment processor and the party holding the
    payment relationship with the supporter.
  - You still owe a short, plain statement: donations are voluntary, confer no entitlement to
    support, features, priority or any good or service, and are not refundable by the project;
    refund requests go to Ko-fi.
  - **The trigger to watch:** the moment a donation buys anything — a tier, a perk, a member
    role, a private channel, early access, a name in a credits file — it stops being a gift and
    becomes a consumer supply contract, which pulls in distance-selling rules, a right of
    withdrawal, and a real refund policy. Ask the user explicitly whether any tier or perk is
    planned. If yes, that is a materially larger compliance surface and it goes in the risk
    register as such. Recommend donations-only unless the user says otherwise.
- **Item 3 (cookies/consent):** a plain hyperlink to ko-fi.com sets nothing on your origin and
  needs no consent banner. Say so, with that reasoning, in the cookie policy. Re-open this
  finding if a widget is ever added.
- **Item 4 (third-party embeds):** the shields.io badge IS a third-party image request — every
  reader of the README on GitHub or PyPI causes a request to img.shields.io carrying their IP
  and user agent. Note it alongside the raw.githubusercontent images the README already embeds.
  Also record that following the Ko-fi link hands the user to Ko-fi's own privacy policy and
  terms, and that no personal data reaches the project from a donation beyond what Ko-fi chooses
  to show the recipient — verify that last claim against Ko-fi's current documentation rather
  than asserting it.
- **Privacy policy:** add a short "Donations" section naming Ko-fi as a third-party processor,
  linking their privacy policy, and stating what the project does and does not receive.
- **Terms:** state that donations are voluntary and confer no rights, and that the project is
  provided under its existing licence with no warranty regardless of any donation.
- **Item 9 (business identity):** accepting money strengthens the case for publishing a real
  contact route and identifying the operator. Raise it in the risk register with that reasoning.
  Whether a jurisdiction requires more — trader disclosure, tax treatment of gifts, registration
  thresholds — depends on where the operator is established. File it under "Needs a lawyer"; do
  not answer it yourself.
- **Item 10 (accessibility):** the badge `<img>` needs alt text saying what it is ("Support on
  Ko-fi"), the footer link text must make sense read out of context, and a decorative emoji must
  never be the only thing carrying meaning.

## Verify

All of these must pass. Paste the output into the handoff note.

```
cd www && npm run build && npx tsc --noEmit
py -m mkdocs build --strict
py tools/check_site_seo.py --docs --www
py tools/audit_site.py
py -m pytest tests/test_site_links.py tests/test_site_legal.py -q
grep -rn "ko-fi\|ko_fi" README.md .github www docs pyproject.toml packaging
```

That last grep: every hit must use the single constant or the placeholder — no stray literals.

Write `tests/test_site_legal.py` so it fails if a legal page loses its footer link, its sitemap
entry, or its meta description; and so it asserts the footer Support link resolves from `SITE`
and that the donation statement exists in both the privacy policy and the terms page.

## Handoff

`notes/handoff-legal.md` — what changed, what you removed and why, the open questions the user
must answer (Ko-fi handle, jurisdiction, operator identity, contact address, whether any
donation tier or perk is planned), and the CHANGELOG lines an integrator should add.

Do not edit `CHANGELOG.md`. Commit in logical units. End every commit message with:

```
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

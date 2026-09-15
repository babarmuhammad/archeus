# Site legal, privacy and accessibility audit

Both published surfaces, audited 2026-09-16 on branch `legal/site-compliance` at
`e250e0a`. Every answer below is backed by a grep or a measurement taken in this
worktree, because the useful deliverable here is the evidence, not the verdict — a
"no" nobody checked looks exactly like a "no" somebody did.

The two surfaces are one entity: `www/` is the apex (Next.js 16, App Router,
Vercel) and `docs/` is the manual (MkDocs Material, served by Vercel **and** by
GitHub Pages from one build — `docs/CNAME`, `.github/workflows/pages.yml`).

**Headline: the sites collect nothing.** Not "little" — nothing. No form, no
input, no server action, no analytics, no cookie, no device storage, no external
script, no embedded third party. So the work was disclosure and a handful of real
defects, not remediation.

---

## 1. Data collection — none

`grep -rInE "<form|<input|<textarea|<select |mailto:|onSubmit|FormData|'use server'|method: 'POST'|fetch\(|XMLHttpRequest|sendBeacon" www/app www/components www/lib`
returns exactly two hits, and both are the contact link this branch added
(`www/lib/legal.ts:28`, `www/app/legal/[slug]/page.tsx:50`). Before this branch it
returned **zero**.

- No `<form>` element exists on either site. No input, textarea or select.
- No newsletter, waitlist, contact form, comment box, account or login.
- No Server Action anywhere: `'use server'` does not appear in the tree.
- No POST target, no `fetch()` at request time, no beacon. The `POST /v1/messages`
  strings in `www/lib/content.ts` and `www/lib/faq.ts` are prose *about the
  product's* model routing, not a call the site makes.
- The only two client components are clipboard-only and send nothing anywhere:
  `www/components/CopyButton.tsx` and `www/components/journey/CopyLine.tsx`.
- Build-time reads (`www/lib/build-data.ts`) read repository files from disk with
  `node:fs`. No network call lives there, which the module says at its head.

The manual is a static MkDocs build. Material's search is client-side over a JSON
index served from the same host; no query leaves the browser.

## 2. Analytics and tracking — none

- `www/package.json` dependencies are `gray-matter`, `lenis`, `markdown-it`,
  `next`, `react`, `react-dom`, `three`. No analytics package of any kind: no
  `@vercel/analytics`, no `@vercel/speed-insights`, no Plausible, PostHog,
  Sentry, Mixpanel, Segment, Amplitude, Hotjar, Clarity, Fathom, Umami, Matomo.
- `grep -rIn "<script[^>]*src" www/app www/components` returns **nothing**. Every
  `<script>` on the apex is inline `application/ld+json` — 14 of them, all
  structured data.
- `mkdocs.yml` has no `extra.analytics` block and no `plugins:` key at all. The
  only hook is `tools/mkdocs_hooks.py`, which writes `llms-full.txt` and derives
  structured data at build time.
- No first-party logging sets an identifier: there is no server to log to. Both
  hosts serve prerendered files.

## 3. Cookies, localStorage, sessionStorage — no writers, therefore no banner

`grep -rIn "localStorage\|sessionStorage\|document.cookie\|indexedDB\|caches.open"`
over `www/app www/components www/lib` returns **nothing**. No `Set-Cookie` header
is configured in `www/next.config.ts` or in either `vercel.json`.

Classification is therefore vacuous: there is no storage to classify as strictly
necessary or otherwise.

**Consent is not required, and the reason matters more than the conclusion.**
Article 5(3) ePrivacy — in Italy Article 122 of the Codice — attaches consent to
*storing information on, or gaining access to information already stored in,* the
user's terminal equipment. Neither site does either. A banner asking consent for
nothing is not caution; it is noise, and it teaches people to dismiss the ones
that matter. Published as `/legal/cookies`, with that reasoning on the page.

This finding re-opens the moment anything is added that remembers a visitor —
analytics, an embedded Ko-fi widget, a comment system, a theme toggle that
persists. The cookie policy says so in its own last section.

## 4. Third-party embeds and transfers

**On the sites: none.**

- Fonts are the operating system's, not Google's: `www/app/globals.css` declares
  `Segoe UI Variable Text / Segoe UI / Inter / system-ui` and Consolas, and there
  is no `next/font` import in the tree (`www/app/layout.tsx:12` says so and why).
  `mkdocs.yml` sets `font: false` for the same reason.
- Every image is same-origin under `www/public`. `www/next.config.ts` configures
  `images.formats` with no `remotePatterns` and no `domains`, so a remote image
  could not be optimised even if one were added.
- No `<iframe>`, no `<video>`, no `<embed>`, no CDN reference, no shields badge on
  either site.

**On the README, which is the surface most people actually meet.** GitHub and
PyPI both render `README.md`, and rendering it causes third-party requests
carrying the reader's IP and user agent:

- 9 images from `raw.githubusercontent.com` (the wordmark and eight screenshots).
- 6 status badges from `img.shields.io`, now **7** — this branch adds the Ko-fi
  badge, and that is a seventh third-party image request, recorded here rather
  than waved through.

Following any outbound link (GitHub, PyPI, npm, RubyGems, Ko-fi, another
project's docs) hands the reader to that site under its own policies. All of the
above is now in the privacy policy's "Where this project is published" section.

**What the hosts see.** This is the only personal data processed in connection
with the sites, and it was the part with no disclosure at all: Vercel serves the
apex, Vercel and GitHub Pages serve the manual, and a web host records request
data — IP, user agent, path, timestamp — to deliver and protect the service.
Article 6(1)(f) legitimate interests; the logs belong to the hosts and are kept on
their schedules. Now disclosed, with both providers named and linked.

## 5. Payments — donations only, so no refund is owed, and a refund page exists anyway

Before this branch, nothing was sold and nothing collected money: no pricing page,
no payment processor, no account system. `www/lib/content.ts` says archeus "is MIT
licensed, free, and has no subscription and no API key of its own".

This branch adds a Ko-fi link, so money can now move. The analysis:

- A donation is a **gift**, not a sale. Ko-fi is the payment processor and holds
  the payment relationship with the supporter; the project never sees payment
  details and cannot refund anything.
- No statutory right of withdrawal attaches to a voluntary gift, because nothing
  is supplied in return for it. That follows from the facts, not from a term.
- **The trigger to watch:** a tier, perk, member role, private channel, early
  access or a name in a credits file turns the gift into a consumer supply
  contract — distance-selling rules, a 14-day right of withdrawal and a real
  refund procedure. Asked and answered: **no tier or perk is planned.** Ko-fi's
  shop, commissions and memberships stay off. This is in the risk register as the
  single condition that would materially enlarge the surface.
- Published anyway as `/legal/refunds`, because "there are no refunds and here is
  why, and here is who took your money" is the page a donor goes looking for.

## 6. Claims audit

The quantified claims hold up. The "zero runtime dependencies" family (7 places,
from `README.md` to `docs/dashboard.md`) is backed by `pyproject.toml` having no
`dependencies` key at all — a machine-readable fact, not a slogan. Token budgets
(≤250 / ≤600), latencies (<1s local, <0.5s on 500 entities) and counts (32
palettes, 8 skins, 4 worlds; 8 skills; 31 hook templates) are gated by
`tests/test_docs_numbers.py`, which compares the published prose against the code.

No superlative survives inspection as a market claim. There is no "fastest", no
"only", no "100%", no "military-grade", no "guarantee". The one speed comparison
on the site runs *against* the product: `docs/compare.md:31` concedes that
`/resume` "is faster than anything else — including archeus". `docs/compare.md`
has a whole section called "What archeus does not do", and two of its three
"when to use which" rows recommend not using it.

Three things were genuinely wrong, and two of them are the same thing:

1. **`www/app/about/page.tsx` published unmeasured figures as data.** The stats
   grid renders six tiles read from `docs/dashboard.md`; "GitHub stars" and
   "Installs / month" are currently em-dashes there, and a tile reading
   `GitHub stars —` does not read as "not measured", it reads as a claim of none.
   **Fixed:** a tile survives only if its value contains a digit, so each returns
   by itself the week its number does, and the disclosure line now says the
   figures were counted on one date "and not since", and measure the repository
   rather than anybody using it.
2. **`docs/dashboard.md` contradicts itself and the rest of the repo.** It says
   version `2.3.0` where `pyproject.toml` says `2.4.0`, and "Published on PyPI |
   not yet published" where `packaging/README.md:32` records PyPI as ours at
   2.4.0 — checked the same day. **Not fixed here:** that file is generated
   weekly by `tools/gen_metrics.py` and a hand edit would be overwritten by the
   next run. It is in the handoff as an integrator task against the generator.
3. **The README's test badge (`tests-2309`) is asserted by nothing.** It is
   rewritten weekly by `tools/gen_metrics.py`; CI's only floor is 1300
   (`.github/workflows/ci.yml:47`), and `tools/gen_metrics.py` records that the
   badge once went *backwards* across a release that added tests. **Left alone:**
   the number is true when it is written, and a gate on it would fail every pull
   request that adds a test — which is the reason the generator gives for not
   having one. Recorded so it is a known snapshot rather than an implied live
   count.

## 7. Testimonials, reviews, logos — none, so nothing to remove

Grep-backed across both sites for `trusted by`, `testimonial`, `★`, `⭐`,
`loved by`, `#1`, `world's`, `award`, `guarantee`, `10x`, star ratings, user
counts and case studies: **no matches**. No customer logo appears in
`docs/assets/`, `docs/img/` or `www/public`. Third-party projects are named only
in `docs/credits.md` and the README's Credits section, as credits, never as
endorsements.

`docs/compare.md:77` states the opposite of social proof — "It is a young
project. Small user base, and the API surface still moves."

This item is a pass, recorded as one. There was nothing fabricated to delete.

## 8. Images and licences — one real gap

Every screenshot is tool-generated and regenerable: `docs/img/` is written by
`tools/shot_gui.py` and `tools/shot_tui.py`, the WebP siblings by
`tools/optimize_images.py`, and `mkdocs.yml:32` records that the directory holds
only generated screenshots. `www/public/img` is the same set, exported by the same
tool. `tools/optimize_images.py --check` passes: 34 assets checked, nothing
recoverable.

**The gap: the brand artwork has attribution but no recorded licence.**
`docs/credits.md:11-14` credits the mark and the banner lockup to Federico Coscia
(github.com/cosfederico), and `www/components/site/Mark.tsx:4` repeats it. But:

- `LICENSE` carries no asset carve-out, and `docs/credits.md:42` says "archeus
  *itself* is MIT licensed" — "itself" doing load-bearing work with nothing
  behind it.
- No `NOTICE`, `LICENSE` or attribution file exists anywhere under `docs/assets/`
  or `docs/img/`.
- `README.md:2` redistributes `wordmark.png` by `raw.githubusercontent.com` URL,
  which is what PyPI renders, so the artwork is being republished on a third
  registry with no recorded permission.

Attribution is present and stays present. Permission is undocumented. This is the
highest-value unresolved item in the register, and the fix is cheap: one line of
written permission from the artist, recorded in the repository.
`/legal/terms` now states that the mark and banner are artwork credited to their
designer and are not the source code the MIT licence covers, which is accurate
without asserting a grant nobody can point at.

## 9. Business identity — was absent, now published

Before: the author's name appears on every surface (`LICENSE:3`,
`pyproject.toml`, `mkdocs.yml:13`, `www/lib/site.ts`), and **nothing else**. No
jurisdiction, no contact page, no reachable address.

The only email in the repository is `CODE_OF_CONDUCT.md:63`, a GitHub
`users.noreply` alias. Those are **send-only**: mail to one bounces. It could not
be the contact route a privacy notice publishes, and `tests/test_site_legal.py`
now fails if it quietly becomes one.

Now published on all four policy pages and in `www/lib/site.ts`: **Babar Muhammad
Anas, an individual established in Italy, babarh174@gmail.com.** Whether Italian
law additionally requires a geographic address is in the register under "Needs a
lawyer" — it is a judgement with a real personal cost either way, not a detail to
decide from a template.

## 10. Accessibility — measured, not eyeballed

The baseline was already strong, and it is worth saying which parts, because they
are the expensive ones to retrofit:

- Skip link to `#main` (`www/app/layout.tsx`), and `<main id="main">` exists.
- `:focus-visible { outline: 2px solid var(--color-cyan) }` globally
  (`www/app/globals.css`) — an 11.41:1 ring.
- **No `div`/`span` with `onClick` anywhere**, and **no custom key handler
  anywhere**: `onClick` appears exactly twice, both on a real
  `<button type="button">`. Disclosure UI is the native `<details>`/`<summary>`
  element in all three places it appears, so keyboard behaviour is the browser's.
- Every image has non-empty alt text, enforced by the type system:
  `www/components/Shot.tsx` declares `alt: string` non-optional, so an image
  without alt does not compile. No raw `<img>` tag exists on the apex.
- The 3D journey canvas is `aria-hidden="true"` with all copy server-rendered as
  DOM beside it, and `prefers-reduced-motion` is honoured three ways: in JS
  (`Canvas.tsx` — the rAF loop never reschedules while `still`, and it listens for
  the setting *changing at runtime*), in CSS (two blocks in `globals.css`), and by
  failing open to a static wash when WebGL is absent or the context is lost.
- Inline SVG decoration carries `aria-hidden="true"`; the icon-only mobile menu
  carries `aria-label="Menu"`.

### Contrast, measured

All 35 foreground/background pairs the apex actually paints, computed with the
WCAG 2.2 relative-luminance formula, with alpha utilities composited over their
real ground first — a ratio taken against the token rather than the painted pixel
is not the ratio a reader sees. Floors: 4.5:1 body text, 3:1 large text and
non-text UI.

| Pair | Ratio | Floor |
|---|---|---|
| text on bg / bg2 / panel / panel2 | 16.06 / 15.51 / 14.87 / 13.44 | 4.5 |
| dim on bg / bg2 / panel / panel2 | 9.03 / 8.72 / 8.36 / 7.55 | 4.5 |
| dim2 on bg / bg2 / panel / panel2 | 5.63 / 5.43 / 5.21 / **4.71** | 4.5 |
| cyan on bg / panel / panel2 | 11.41 / 10.56 / 9.54 | 4.5 |
| violet on bg / panel / panel2 | 6.25 / 5.79 / 5.23 | 4.5 |
| cyan/80 on bg / panel (station eyebrows) | 7.52 / 7.13 | 4.5 |
| text, dim, dim2 on panel2/60 over bg | 14.61 / 8.21 / 5.11 | 4.5 |
| dim, dim2 on bg2/40 over bg (footer) | 8.91 / 5.55 | 4.5 |
| bg on cyan (primary CTA) / on violet (its hover) | 11.41 / 6.25 | 4.5 |
| text on cyan/10 over bg (primary CTA face) | 13.56 | 4.5 |
| code text on panel-solid | 10.56 | 4.5 |
| white text over the 28% cyan selection | 10.36 | 4.5 |
| focus ring vs bg / vs panel | 11.41 / 10.56 | 3.0 |
| cyan/45 border on panel (CTA hover) | 3.09 | 3.0 |
| cyan/60 border on bg | 4.63 | 3.0 |
| **`line` on panel — control borders** | **1.36** | **3.0** |

`dim2 on panel2` at 4.71:1 is the tightest text pair on the site and it clears.

**One defect, and it was real.** `--color-line` (`#28303d`) is 1.36:1 against a
panel and 1.47:1 against the page ground. As a hairline between table rows or
around a card that is decorative, and 1.4.11 exempts it. But the same token was
the *only* thing marking three controls as controls — the secondary `Cta` button,
the `CopyButton`, and the mobile menu `<summary>` — and the secondary CTA's label
is `text-dim`, exactly the colour of body text, so with the border removed it is
not identifiable as a control at all. That is squarely SC 1.4.11.

**Fixed** by moving those three borders to `border-dim2/70`, composited **3.28:1**
over the page ground. Decorative hairlines keep `--color-line`: the distinction is
whether the boundary is doing identifying work, not whether it is a border.

### Other accessibility notes

- Heading order: exactly one `<h1>` per page, gated on the built HTML by
  `tools/check_site_seo.py` and passing — 22 apex pages and 30 manual pages clean.
  The FAQ's questions are real `<h2>`s inside their `<summary>`, so the 23-entry
  `FAQPage` structured data describes a hierarchy the page actually has.
- The four new policy pages open with a `PageHeader` `<h1>` and use `<h2>` per
  section, with the effective date in a `<time datetime>`.
- The new footer legal links sit in `<nav aria-label="Legal">` so the landmark
  says what it is; link text is the policy's own title, which reads correctly out
  of context.
- External links carry no `target="_blank"`, so there is no `rel="noopener"`
  requirement and no unannounced new window.
- `tools/audit_site.py` passes at 390×844 over all 52 pages of both sites,
  including the new footer row and the four new pages: nothing overflows.
- Dark-mode only, by design (`color-scheme: dark`). Not a WCAG failure; noted in
  the register as a preference the sites do not honour.

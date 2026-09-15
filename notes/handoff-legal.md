# Handoff — Track A: site legal, compliance, accessibility, Ko-fi

Branch `legal/site-compliance`, branched from `e250e0a`. Merges **first** of the
four tracks. Touches no file under `claude_sessions/`, so it should not collide
with the agent working directly on `main`.

Companion notes: `notes/site-legal-audit.md` (the evidence) and
`notes/site-legal-risks.md` (the register, including what still needs a lawyer).

---

## What landed

**Four policy pages on the apex**, one route, from one data table.
`www/lib/legal.ts` holds them as `Doc`s — the same shape `lib/content.ts` uses —
and `www/app/legal/[slug]/page.tsx` prerenders all four with
`generateStaticParams` and `dynamicParams = false`. `/legal/privacy`,
`/legal/terms`, `/legal/cookies`, `/legal/refunds`.

They are wired in from that one array, never restated: the footer
(`Footer.tsx`), `app/sitemap.ts`, `/llms.txt` (a `## Legal` section) and
`/llms-full.txt` (the full text, because a summary of a privacy policy is the one
summary nobody should be quoting). The manual links to the apex copies from
`docs/index.md` and `docs/llms.txt` rather than carrying its own — two copies of a
policy is two policies, and the second one is wrong.

**One new block kind**, `links`, in `lib/content.ts` + `components/doc/Blocks.tsx`
+ `blockText`. A policy has to cite the notices it relies on and no existing block
could carry a link. It is a block rather than inline markup so the other five
block kinds did not each need one.

**Ko-fi, on six surfaces, from one handle.** `https://ko-fi.com/babarmuhammad` —
badge in the README row, one line folded into the README's License section,
`.github/FUNDING.yml` (which is what turns on GitHub's Sponsor button, separate
from the badge and both are wanted), a "Support on Ko-fi" link in the site footer
resolved from `SITE.kofi`, and funding metadata in `pyproject.toml`,
`packaging/npm/package.json` and `packaging/rubygems/archeus.gemspec`. No widget,
no iframe, no Ko-fi JavaScript — an embed would have dragged cookie consent back
in, which is precisely the surface these pages keep closed.

**Operator identity published**: Babar Muhammad Anas, individual, Italy,
babarh174@gmail.com — in `SITE` and on every policy page, with the effective date
in a `<time>` element.

**Two accessibility fixes and one measurement.** All 35 foreground/background
pairs the apex paints were computed (alpha utilities composited over their real
ground first) and tabulated in the audit. Every text pair clears 4.5:1, the
tightest at 4.71:1. One real SC 1.4.11 defect: `--color-line` at 1.36:1 was the
only thing identifying three controls as controls — the secondary `Cta`, the
`CopyButton` and the mobile menu `<summary>` — and the secondary CTA's label is the
same colour as body text, so without the border it is not identifiable as a
control at all. Those three moved to `border-dim2/70`, 3.28:1. Decorative
hairlines keep `--color-line`; the distinction is whether the boundary does
identifying work.

**One claims fix.** `/about`'s stat grid rendered `GitHub stars —` and
`Installs / month —`, which reads as a claim of none rather than as "not
measured". A tile now survives only if its value contains a digit, so each comes
back by itself the week its number does, and the disclosure line says the figures
were counted on one date "and not since" and measure the repository, not its
users.

**A gate fixed, and it was a live hole.**
`tests/test_site_links.py::test_an_apex_link_has_no_trailing_slash` could not tell
a trailing slash from a path separator: its greedy body backtracked to the first
slash it could end on, so the perfectly correct `/legal/privacy` was reported as
`/legal/`. Until these pages landed, no tracked file named a two-level apex URL,
so that half of the regex had never once been exercised. A lookahead fixes it, and
it still catches every real defect — verified against `/features/`,
`/blog/a-post/` and `/legal/privacy/`, all still flagged.

---

## What was deliberately NOT changed

- **No fabricated social proof was removed, because there is none.** Grep-backed
  across both sites: no testimonial, rating, user count, "trusted by", case study
  or third-party logo. `docs/compare.md:77` says the opposite of social proof.
  Recorded in the audit as a pass rather than turned into invented work.
- **`docs/dashboard.md` is wrong and was left alone.** It says version `2.3.0`
  against `pyproject.toml`'s `2.4.0`, and "Published on PyPI | not yet published"
  against `packaging/README.md:32` recording PyPI as ours at 2.4.0 the same day.
  It is generated weekly by `tools/gen_metrics.py`, which is outside this
  branch's fence, so a hand edit would be reverted by the next run.
  **Integrator task, against the generator.**
- **The README test badge (`2309`) stays ungated.** True when written;
  `tools/gen_metrics.py` documents why a gate on it would fail every PR that adds
  a test. Recorded so it is known to be a weekly snapshot.
- **No `/support` page.** A page holding nothing but a link is worse than the
  link. Footer entry plus README plus the GitHub Sponsor button is three surfaces
  already.
- **No funding field in `Cargo.toml`.** crates.io reads no such key, so a
  `[package.metadata]` entry would be decoration that looks like wiring. The line
  went in `packaging/crates/README.md`, which for a pointer crate *is* the
  payload. `tests/test_site_legal.py` asserts the absence, so nobody adds it back
  believing it does something.
- **No security headers added.** `www/next.config.ts` has no CSP,
  Permissions-Policy or frame-ancestors. Out of scope for a legal branch, and a
  CSP interacts with 14 inline JSON-LD blocks, so it is a real task. Register row
  16.
- **No screenshots re-shot, no version bumped, nothing published.**

---

## Open questions for you

1. **The artwork licence — the highest-value item.** The mark and banner are
   credited to Federico Coscia, and no licence or permission is recorded anywhere;
   meanwhile `README.md:2` redistributes `wordmark.png` to PyPI by raw URL. One
   line of written permission from him, committed beside the assets, closes it.
2. **Italian address disclosure.** D.Lgs. 70/2003 art. 7 wants a geographic
   address as well as a name and email. For an individual that means a home
   address. Name, country and a live mailbox are published; the address is not.
   Worth a professional answer before donations become regular.
3. **Tax treatment of donations** in Italy, and whether volume converts this into
   something requiring registration. Not answerable from here.
4. **Confirm the Ko-fi page settings.** The policies state as fact that no tier,
   perk or membership is offered, and that sentence is what keeps a donation a
   gift rather than a consumer supply contract. Shop, commissions and memberships
   must actually be **off** on ko-fi.com, and the Ko-fi page description should not
   contradict what `/legal/refunds` says.
5. **Payouts.** Stripe or PayPal must be connected in Ko-fi settings or the page
   accepts nothing. Nothing in the repo can check this.
6. **One small thing worth knowing:** `README.md` is now 198 lines against
   `test_the_readme_stays_a_pitch_and_does_not_grow_back_into_a_manual`'s limit of
   200. The Ko-fi copy was folded into the existing License section rather than
   given its own heading for exactly this reason. The next README addition needs a
   trim somewhere, not just an append.

---

## Verification — every gate, run on this branch

```
cd www && npm run build            ✓  32 routes, 4 of them /legal/*
npm run lint                       ✓  clean
py -m mkdocs build --strict        ✓  built in 2.39s
py tools/check_site_seo.py --www   ✓  checked 22 apex pages — clean
py tools/check_site_seo.py --docs  ✓  checked 30 docs pages — clean
py tools/audit_site.py --www       ✓  checked 52 pages at 390x844 — nothing overflows
py tools/optimize_images.py --check ✓ images optimized: 34 checked
py -m pytest tests/test_site_legal.py tests/test_site_links.py \
    tests/test_docs_site.py tests/test_docs_numbers.py tests/test_packaging.py \
    tests/test_brand_copy.py tests/test_robots.py tests/test_image_budget.py -q
                                   ✓  118 passed
```

```
npx tsc --noEmit                   ✓  clean
```

`tsc` must run **after** a build, not before. `LayoutProps` is a Next-generated
global that only exists under `.next/types`, so a standalone run in a fresh
worktree reports `app/layout.tsx(144,50): Cannot find name 'LayoutProps'` and a
run after `npm run build` is clean. The order in the verify list above is the
working one.

### The gates were watched failing

A gate nobody has watched fail is not a gate, so each was broken on purpose and
the named test had to go red, then green again on restore. Twelve of them:

| Broken | Test that caught it |
|---|---|
| Footer stops mapping LEGAL (replaced, and commented out) | `test_every_policy_is_linked_from_the_footer` |
| Sitemap line commented out | `test_every_policy_is_in_the_sitemap` |
| `generateStaticParams` commented out | `test_one_route_renders_every_policy` |
| A description cut below 50 characters | `test_every_policy_carries_a_description_a_result_can_show` |
| A policy dropped from `LEGAL` | `test_the_four_policies_are_all_there` |
| The terms stop saying donations buy nothing | `test_the_donation_statement_is_on_the_privacy_page_and_the_terms` |
| One manifest's handle diverges | `test_the_funding_handle_is_the_same_everywhere` |
| Contact reverts to a `users.noreply` alias | `test_a_policy_page_names_who_is_responsible_and_how_to_reach_them` |
| A `[package.metadata.funding]` key added to Cargo | `test_the_package_manifests_declare_funding_where_a_registry_reads_it` |
| The funding URL hardcoded in a component | `test_the_site_reads_the_funding_url_from_one_place` |
| `docs/privacy.md` created | `test_the_policies_are_published_once_not_mirrored_into_the_manual` |
| An apex link written with a trailing slash | `test_an_apex_link_has_no_trailing_slash` |

**One of them did not fail, and that was the point of doing this.** Commenting
out the sitemap's `...LEGAL.map(...)` left the gate green, because a substring
search cannot tell live code from a line somebody disabled — and commenting a
line out is exactly how wiring gets turned off. The three wiring assertions now
read comment-stripped source through a `code()` helper, and all three were
re-verified against a commented-out mutation.

```
py -m pytest -q                    ✓  2352 passed, 1 skipped in 283.27s
```

The single warning in that run is pre-existing: `test_plan_execute.py` raises a
`KeyboardInterrupt` inside a job thread on purpose, to prove a `BaseException`
still forces a terminal job status.

---

## CHANGELOG lines for the integrator

Do not take these verbatim if the release groups differently — but these are the
user-visible facts.

```
### Added
- Privacy policy, terms, cookie policy and refund policy, published at
  /legal/* on claudectl.space and linked from the footer, the sitemap and both
  llms.txt files. Neither site collects anything — no forms, no analytics, no
  cookies — and the privacy policy says what the web hosts log anyway, and why.
- The operator, jurisdiction and a contact address are now published.
- A Ko-fi support link: a README badge, a GitHub Sponsor button, a footer entry,
  and funding metadata on PyPI, npm and RubyGems. Voluntary, and it buys nothing
  — no tier and no perk, which is what keeps a donation a gift.

### Fixed
- Three controls — the secondary button, the copy button and the mobile menu —
  were identified only by a 1.36:1 border, below the 3:1 WCAG 2.2 floor for
  non-text contrast. All 35 palette pairs are now measured and recorded.
- The About page published "GitHub stars —" and "Installs / month —" as if they
  were measurements. A figure appears only once it has been measured.
- The apex trailing-slash gate could not tell a trailing slash from a path
  separator, and flagged correct two-level URLs.
```

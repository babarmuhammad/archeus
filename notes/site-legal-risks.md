# Risk register — published sites, funding, accessibility

Compiled 2026-09-16 alongside `notes/site-legal-audit.md`, which carries the
evidence behind every row.

**This is not legal advice, and nothing in this repository claims either site is
"compliant".** I am not a lawyer. Policy templates are a starting point; which
regimes actually bite depends on where the operator is established and where the
visitors are, and both of those are facts about the world rather than about the
code. Where a question could not be settled from evidence it is in the "Needs a
lawyer" section below and stays there, rather than being answered confidently in
a page somebody might rely on.

Operator of record: **Babar Muhammad Anas**, an individual established in
**Italy**. Contact: **babarh174@gmail.com**. Donations only — no tier or perk.

---

## Register

| # | Risk | Regime | What was done | What remains | Confidence |
|---|---|---|---|---|---|
| 1 | No privacy notice existed on either host, while both hosts log request data | GDPR Arts. 12–14 (EU/Italy), UK GDPR | `/legal/privacy` published: controller named, contact route given, Vercel and GitHub Pages named as hosting processors, Art. 6(1)(f) basis stated, non-EEA transfer noted, rights and the Garante route set out | Nothing blocking. Re-check if a host changes | High |
| 2 | No contact route that receives mail; the only address in the repo is a send-only GitHub `users.noreply` alias | GDPR Art. 13(1)(a)–(b); consumer disclosure | A real mailbox published on all four policy pages and in `SITE.contact`; `tests/test_site_legal.py` fails if a `users.noreply` address is ever put back | Nothing | High |
| 3 | No cookie policy; unclear whether a consent banner was owed | ePrivacy Art. 5(3); Italy, Codice Art. 122 | Verified by grep that nothing writes a cookie, localStorage, sessionStorage or IndexedDB. `/legal/cookies` published stating no consent is required **and why** | Re-opens the moment analytics, an embedded widget or any persistence is added. The page says so in its own last section | High |
| 4 | No terms; the software's warranty position lived only in the LICENSE file | Contract; consumer law | `/legal/terms` published: MIT, as-is, no warranty regardless of any donation, liability carve-outs for what cannot be limited, Italian governing law with mandatory consumer rules preserved | Governing-law and liability wording is conventional and unreviewed — see "Needs a lawyer" | Medium |
| 5 | Money now moves (Ko-fi), with no statement of what a donation is | Consumer-contract and distance-selling rules | `/legal/refunds` published: a gift, not a purchase; no right of withdrawal because nothing is supplied in return; card details never reach the project. Stated identically in the terms and the privacy page, from one constant | Nothing, **while donations stay perk-free**. See row 6 | High |
| 5b | Ko-fi pays out to the creator's OWN Stripe or PayPal account, so the creator CAN in fact reverse a payment | Unfair commercial practices; plain accuracy | The refund page first said the project "cannot" refund because it never received the payment. That is wrong under either payout method and was rewritten: no refunds as policy because nothing was sold, but a mistaken donation is put right where the provider still allows it | Nothing. Re-check the wording if Ko-fi is ever switched to a mode where it holds the funds itself | High |
| 6 | A donation that buys something stops being a gift | Consumer Rights Directive; distance selling; Italy, Codice del Consumo | Confirmed with the operator: no tier, perk, member role, private channel, early access or credits-file name is planned; Ko-fi shop, commissions and memberships stay off | **This is the one condition that materially enlarges the surface.** If a perk is ever offered: a real refund procedure, a 14-day right of withdrawal, pre-contractual information and a rewrite of rows 4 and 5 | High as stated; the risk is a future decision, not a defect |
| 7 | The brand mark and banner have attribution but no recorded licence, and the banner is redistributed to PyPI via raw.githubusercontent | Copyright | `/legal/terms` states the artwork is credited to its designer and is not the source code the MIT licence covers — accurate without asserting a grant | **Open, and the highest-value item here.** Get one line of written permission from Federico Coscia and record it in the repository beside the assets | Medium — attribution is right; permission is undocumented |
| 8 | Unmeasured figures published as if measured (`/about` stat tiles) | FTC substantiation; unfair commercial practices (Dir. 2005/29) | A tile is rendered only if its value contains a digit; the disclosure line now says when it was counted and that it measures the repository, not its users | Nothing | High |
| 9 | `docs/dashboard.md` contradicts itself: version `2.3.0` vs `2.4.0`, and "not yet published" against a PyPI release recorded the same day | Same as row 8 | Nothing — the file is generated weekly by `tools/gen_metrics.py`, which is outside this branch's fence; a hand edit is overwritten by the next run | **Open.** Integrator task against the generator, not the page | High that it is wrong; the fix is elsewhere |
| 10 | README test badge (`2309`) asserted by nothing; CI's only floor is 1300 | Substantiation | Left as-is deliberately. It is true when written, and `tools/gen_metrics.py` documents why a gate on it would fail every PR that adds a test | Accepted. Worth knowing it is a weekly snapshot, not a live count | High |
| 11 | Control borders at 1.36:1 — the only thing identifying three controls as controls | WCAG 2.2 AA SC 1.4.11; EN 301 549; EU Accessibility Act | Secondary CTA, copy button and mobile menu moved to a 3.28:1 border. All 35 palette pairs measured and tabulated; every text pair clears 4.5:1, tightest 4.71:1 | Nothing found outstanding. The measurement is the deliverable — re-run it when the palette changes | High |
| 12 | Whether the EAA applies at all to a free, non-commercial personal project | EU Accessibility Act (Dir. 2019/882), in force June 2025 | Treated as applying and met on the merits rather than argued away: the audit measured rather than asserted | Micro-enterprise and non-economic-activity carve-outs exist and were not relied on. If the project ever becomes commercial this stops being academic | Medium |
| 13 | No accessibility statement is published | EAA / EN 301 549 expect one for in-scope services | Not published — see row 12; publishing a formal statement asserts a scope determination that has not been made | Decide with row 12 | Low urgency |
| 14 | US visitors: no "do not sell/share" notice or privacy-rights section | CCPA/CPRA and the other state laws | Nothing collected, nothing sold, nothing shared, no cross-context behavioural advertising — the notice-and-opt-out duties have no subject matter. The privacy policy states the facts that make this so | Revisit if analytics is ever added. Applicability thresholds are unlikely to be met regardless | Medium-high |
| 15 | The sites publish the author's personal social profiles (LinkedIn, Instagram) in every page's JSON-LD `sameAs` | Not a compliance defect — a deliberate choice | Unchanged. It is the entity-disambiguation mechanism the SEO work depends on (`notes/seo.md`) | Worth a conscious re-confirmation now that a real email is published beside it: name, country, mailbox and five profiles are now one linkable identity | N/A — operator's call |
| 16 | `www/next.config.ts` sets HSTS, nosniff and Referrer-Policy but no CSP, Permissions-Policy or frame-ancestors | Security hardening, not a legal duty | Nothing — out of scope for this branch, and a CSP interacts with the 14 inline JSON-LD blocks, so it is a real task rather than a one-liner | **Open**, low severity. A `Permissions-Policy` denying geolocation/camera/microphone is close to free; a CSP needs hashes or a nonce strategy | High that it is absent; low that it matters here |
| 17 | The manual is served by two hosts from one build | GDPR processor disclosure | Both named in the privacy policy rather than only the one people think of | Nothing | High |
| 18 | Dark-mode only; no light theme on the apex | Preference, not a WCAG AA failure | Nothing. Every pair clears AA in the one theme that exists | Noted so it is a decision rather than an oversight | High |

---

## Needs a lawyer

These could not be settled from evidence, and guessing at them in a published page
would be worse than leaving them open.

**Italian trader / information-society-service disclosure.** D.Lgs. 70/2003 art. 7
requires a provider of information society services to publish its name, its
geographic address and an email address. A free, donation-supported personal
project sits awkwardly against "service normally provided for remuneration", and
accepting donations makes the question sharper rather than clearer. A real
geographic address for an individual means publishing a home address, which has a
genuine personal cost. **Recommendation: get this answered before donations become
regular.** Name, country and a live mailbox are published today; the address is
not.

**Tax treatment of donations, and any registration threshold.** How gifts to an
individual are treated in Italy, whether a volume of them converts the activity
into something requiring registration or invoicing, and what the reporting duty is.
Depends on facts nobody in this repository knows.

**The artwork licence (register row 7).** Not a question of law so much as a
missing document. One line of written permission, recorded in the repository,
closes it. Until then the banner is being redistributed to a third registry on an
undocumented basis.

**Governing law and liability wording in `/legal/terms`.** Conventional and
unreviewed. It is written to preserve mandatory consumer protections rather than to
exclude them, which is the safe direction, but "safe direction" is not the same as
"checked".

**Whether the EAA applies (rows 12–13).** The accessibility work was done on the
merits either way, so nothing turns on the answer today. It would matter for
whether a formal accessibility statement is owed.

---

## What would re-open this whole file

In rough order of how likely each is:

1. Any analytics, error reporter or embedded widget — including a Ko-fi widget in
   place of the plain link. Rows 3 and 14 both turn over.
2. A donation tier or perk. Rows 4, 5 and 6.
3. A form of any kind — a newsletter, a contact form, a comment box. Rows 1 and 3.
4. Selling anything at all.
5. A palette change. Row 11 — re-run the contrast measurement, do not eyeball it.

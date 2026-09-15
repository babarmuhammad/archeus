/**
 * The legal pages, as Docs.
 *
 * Same shape as lib/content.ts, and deliberately not part of DOCS: those are
 * derived into NAV, the sitemap's main set and the llms.txt "Pages" section,
 * and a policy belongs in none of them. The one route at app/legal/[slug]
 * renders whatever is listed here, so adding a policy is adding an entry — the
 * footer, the sitemap, both plain-text files and the tests all read this array.
 *
 * Written in plain language on purpose. Every factual claim here was checked
 * against the repository rather than copied from a template: the sites really do
 * run no analytics, set no cookie and collect nothing, and the honest content of
 * a privacy notice for a site like this is what the HOSTS log, not what the site
 * asks for. Nothing here claims the sites are "compliant" — see
 * notes/site-legal-risks.md for what remains open.
 */

import type { Doc } from './content';
import { links, p, ul } from './content';
import { SITE } from './site';

/** Shown on every policy page and used as the "last updated" line. */
export const EFFECTIVE = '2026-09-16';
export const EFFECTIVE_LABEL = '16 September 2026';

export const legalPath = (slug: string) => `/legal/${slug}`;

const MAILTO = `mailto:${SITE.contact}`;

/* The one sentence that keeps a donation a gift. It is asserted on the privacy
   page, the terms and the refund policy, so it is written once. */
const NO_PERKS =
  'Donations are voluntary. They buy nothing: there is no tier, no perk, no member role, no private channel, no early access and no name in a credits file, and nothing about the software or the support you receive changes because you did or did not give.';

const PRIVACY: Doc = {
  slug: 'privacy',
  title: 'Privacy policy',
  description:
    'What the archeus websites do and do not collect: no analytics, no cookies, no forms — and what the hosts log when your browser asks for a page.',
  intro:
    'These websites collect nothing from you. There is no form, no account, no newsletter and no analytics. What follows is mostly about the one thing that does happen anyway — a web server writing down that a request arrived.',
  sections: [
    {
      id: 'who',
      heading: 'Who is responsible',
      lead: `${SITE.operator}, an individual established in ${SITE.operatorCountry}, operates ${SITE.url} and ${SITE.docs} and is the data controller for them.`,
      blocks: [
        links([
          { label: SITE.contact, href: MAILTO, note: 'the contact route for anything on this page' },
        ]),
        p(
          'There is no company behind this, no marketing department and no data team. It is one person publishing a free, MIT-licensed tool.',
        ),
      ],
    },
    {
      id: 'collected',
      heading: 'What the sites collect: nothing',
      lead:
        'Not "nothing much" — nothing. This is a static site and it has nowhere to put anything you typed.',
      blocks: [
        ul([
          'No form, input field, contact form, newsletter, waitlist or comment box exists on either site.',
          'No account, no login, no profile.',
          'No analytics, no tag manager, no pixel, no session recorder, no A/B tool, no error reporter.',
          'No advertising, no profiling, no automated decision-making, and nothing is sold or shared with a data broker.',
          'The two "copy" buttons run entirely in your browser and send nothing anywhere.',
        ]),
        p(
          'The pages are built ahead of time and served as files. Fonts come from your own operating system, and every image is served from the same domain as the page, so simply reading the site contacts nobody else.',
        ),
      ],
    },
    {
      id: 'logs',
      heading: 'What the hosts log',
      lead:
        'A request has to reach a server, and a server writes down that it happened. This is the only personal data processed in connection with these sites.',
      blocks: [
        p(
          `${SITE.url} is served by Vercel. ${SITE.docs} is served by Vercel and by GitHub Pages from the same build. Like any web host, they record request data — typically the IP address, the user agent your browser sends, the page requested and the time — to deliver the page, keep the service available and defend it against abuse.`,
        ),
        p(
          'That processing rests on legitimate interests under Article 6(1)(f) GDPR: a website cannot be delivered or protected without it. The logs are the hosts’, not this project’s — they are kept and deleted on the hosts’ own schedules, and are not used here to build any profile of a visitor. Because those providers operate globally, serving a page can involve a transfer outside the EEA under the safeguards described in their notices.',
        ),
        links([
          { label: 'Vercel privacy notice', href: 'https://vercel.com/legal/privacy-policy' },
          { label: 'GitHub privacy statement', href: 'https://docs.github.com/en/site-policy/privacy-policies/github-privacy-statement' },
        ]),
      ],
    },
    {
      id: 'cookies',
      heading: 'Cookies',
      lead: 'There are none, which is why there is no consent banner.',
      blocks: [
        p(
          'Neither site sets a cookie or writes anything to your device — no cookie, no local storage, no session storage, no database in the browser. The cookie policy says so at more length, and says what would have to change for that to stop being true.',
        ),
        links([{ label: 'Cookie policy', href: legalPath('cookies') }]),
      ],
    },
    {
      id: 'donations',
      heading: 'Donations',
      lead:
        'If you choose to support the project, you do that on Ko-fi, and the payment is taken there rather than here.',
      blocks: [
        p(
          'The Support link is an ordinary hyperlink. There is no Ko-fi widget, button script or iframe on these sites, so nothing about Ko-fi loads or runs until you click through. Once you do, you are on Ko-fi’s website and their privacy policy and terms govern what happens there. Your card details go to their payment provider and never reach this project.',
        ),
        p(
          'What a recipient can see about a supporter is decided by Ko-fi, not here. Read their notice for the current answer rather than taking a description of it on trust.',
        ),
        links([
          { label: 'Ko-fi privacy policy', href: 'https://more.ko-fi.com/privacy' },
          { label: 'Ko-fi terms', href: 'https://more.ko-fi.com/tos' },
          { label: 'The project on Ko-fi', href: SITE.kofi },
        ]),
        p(NO_PERKS),
      ],
    },
    {
      id: 'elsewhere',
      heading: 'Where this project is published, and what that costs you',
      lead:
        'The sites load nothing from anyone else. The README does, and it is worth being explicit about it, because most people meet this project on GitHub or PyPI rather than here.',
      blocks: [
        ul([
          'The README’s status badges are images fetched from img.shields.io, and its screenshots are fetched from raw.githubusercontent.com. Whenever a page renders that README — on GitHub, on PyPI, or in another tool — your browser requests those images, and that request carries your IP address and user agent to those third parties.',
          'Following any outbound link — GitHub, PyPI, npm, RubyGems, Ko-fi, the documentation of another project — takes you to somebody else’s site, under their policies.',
          'The software itself is separate from these websites: it runs on your machine, and what it does with your data is described in the manual, not here.',
        ]),
      ],
    },
    {
      id: 'rights',
      heading: 'Your rights',
      lead:
        'Under the GDPR you can ask for access to your personal data, and for it to be corrected, erased or restricted; you can object to processing based on legitimate interests; and you can ask for a copy in a portable form.',
      blocks: [
        p(
          `In practice there is very little to ask about, because this project holds nothing: no list, no database, no mailing list, no visitor record. Requests about the hosts’ own server logs are best made to them, and the notices linked above say how. Anything else, write to ${SITE.contact} and you will get an answer.`,
        ),
        p(
          `If you are not satisfied you can complain to a supervisory authority — in ${SITE.operatorCountry} that is the Garante per la protezione dei dati personali, and you may also complain to the authority where you live or work.`,
        ),
        links([
          { label: 'Garante per la protezione dei dati personali', href: 'https://www.garanteprivacy.it/' },
          { label: `Email ${SITE.contact}`, href: MAILTO },
        ]),
      ],
    },
    {
      id: 'changes',
      heading: 'Changes to this policy',
      blocks: [
        p(
          `This policy is effective from ${EFFECTIVE_LABEL}. If the sites ever start collecting something — an analytics script, a form, a Ko-fi widget — this page changes before that ships, and its effective date changes with it. The history of every change is public in the repository.`,
        ),
        links([{ label: 'This page in the repository', href: `${SITE.repo}/blob/main/www/lib/legal.ts` }]),
      ],
    },
  ],
};

const COOKIES: Doc = {
  slug: 'cookies',
  title: 'Cookie policy',
  description:
    'The archeus websites set no cookies and store nothing on your device, which is why there is no consent banner. What that means, and when it would change.',
  intro:
    'Short version: there are no cookies, so there is nothing to consent to and no banner asking you to.',
  sections: [
    {
      id: 'none',
      heading: 'This site stores nothing on your device',
      lead:
        'Not a necessary cookie, not an analytics cookie, not a preference cookie. Nothing.',
      blocks: [
        ul([
          'No cookie is set by either site.',
          'Nothing is written to local storage, session storage or an in-browser database.',
          'There is no analytics, no tag manager and no third-party script of any kind, so nothing else gets the chance to set one either.',
          'There is no login and no preference to remember, because there is nothing to log in to and nothing to configure.',
        ]),
      ],
    },
    {
      id: 'why-no-banner',
      heading: 'Why there is no consent banner',
      lead:
        'Consent is required for storing information on your device or reading information already there. Nothing here does either.',
      blocks: [
        p(
          'The rule people mean when they say "cookie law" — Article 5(3) of the ePrivacy Directive, in Italy Article 122 of the Codice in materia di protezione dei dati personali — attaches to the act of storing or accessing information on a user’s device. This site does neither, so there is no consent to collect.',
        ),
        p(
          'A banner asking you to agree to nothing is not caution, it is noise, and it trains people to click through the ones that matter. If that changes, the banner arrives with the thing that made it necessary.',
        ),
      ],
    },
    {
      id: 'still-happens',
      heading: 'What still happens anyway',
      blocks: [
        ul([
          'Your browser caches pages and images, as it does for every site. That is your browser’s own storage, under your control, and nothing here reads it.',
          'The web hosts log that a request arrived. That is a record on their servers, not storage on your device, and the privacy policy covers it.',
          'Other sites you reach from here — GitHub, PyPI, npm, RubyGems, Ko-fi — set their own cookies once you are on them. A link to a site is not an embed of it: nothing of theirs runs until you click.',
        ]),
        links([{ label: 'Privacy policy', href: legalPath('privacy') }]),
      ],
    },
    {
      id: 'changes',
      heading: 'If this changes',
      blocks: [
        p(
          `Effective from ${EFFECTIVE_LABEL}. Adding analytics, an embedded Ko-fi widget, a comment system or anything that remembers you between visits would re-open this question, and this page and its date would change first.`,
        ),
      ],
    },
  ],
};

const TERMS: Doc = {
  slug: 'terms',
  title: 'Terms',
  description:
    'The terms for using the archeus websites and software: an MIT licence, no warranty, and donations that are voluntary and buy nothing.',
  intro:
    'archeus is free software published by one person. These terms cover the two websites and set out what the software is and is not promised to do.',
  sections: [
    {
      id: 'who',
      heading: 'Who you are dealing with',
      lead: `${SITE.operator}, an individual established in ${SITE.operatorCountry}, publishes the software and operates ${SITE.url} and ${SITE.docs}.`,
      blocks: [links([{ label: SITE.contact, href: MAILTO }])],
    },
    {
      id: 'software',
      heading: 'The software',
      lead:
        'archeus is licensed under the MIT licence. You may use, copy, modify and redistribute it on those terms, and the licence text is the agreement — this page does not add to it.',
      blocks: [
        p(
          'The MIT licence provides the software "as is", without warranty of any kind, and its authors are not liable for any claim or damage arising from it. That applies whether you paid nothing, which is the normal case, or chose to donate.',
        ),
        p(
          'It is a young project and the interfaces still move. It reads and writes files belonging to other tools on your machine, and the manual says which; read that before pointing it at work you cannot afford to lose, and keep backups you would have kept anyway.',
        ),
        links([
          { label: 'The MIT licence', href: `${SITE.repo}/blob/main/LICENSE` },
          { label: 'The manual', href: SITE.docs },
        ]),
      ],
    },
    {
      id: 'sites',
      heading: 'The websites',
      blocks: [
        ul([
          'Everything on these sites is published for information. It is written as accurately as it can be and it is not a promise about anything.',
          'Pages change, move and are rewritten without notice. Nothing here guarantees the sites are available, complete or up to date.',
          'The sites collect nothing from you. There is no account to hold, no content to submit and no order to place.',
        ]),
      ],
    },
    {
      id: 'donations',
      heading: 'Donations',
      lead: 'A donation is a gift. It is not a purchase, and it does not buy a product, a service or a promise.',
      blocks: [
        p(NO_PERKS),
        p(
          'Donations are collected through Ko-fi and handled by its payment provider; your card details never reach this project. Giving does not change the licence the software is under, does not create a support contract, does not grant priority on issues or feature requests, and does not extend or alter the warranty disclaimer above, which remains exactly as it is.',
        ),
        links([
          { label: 'Refund policy', href: legalPath('refunds') },
          { label: 'The project on Ko-fi', href: SITE.kofi },
        ]),
      ],
    },
    {
      id: 'names',
      heading: 'Names and artwork',
      blocks: [
        p(
          'archeus is not affiliated with, endorsed by, or supported by Anthropic. Claude and Claude Code are Anthropic’s trademarks, and OpenAI Codex, pi and every other product named on these sites belong to their own owners. They are named to say what the software works with, which is a statement of fact, not a claim of association.',
        ),
        p(
          'The archeus mark and the banner lockup were designed by Federico Coscia and are credited in the documentation. They are artwork, not source code, and the MIT licence on this repository covers the software.',
        ),
        links([{ label: 'Credits', href: `${SITE.docs}/credits/` }]),
      ],
    },
    {
      id: 'liability',
      heading: 'Liability and law',
      blocks: [
        p(
          'To the fullest extent the law allows, no liability is accepted for any loss arising from using these sites or the software. Nothing here limits liability that cannot lawfully be limited — including for death or personal injury caused by negligence, or for fraud — and if you are a consumer, nothing here takes away the rights your own country’s law gives you.',
        ),
        p(
          `These terms are governed by Italian law. If you are a consumer resident elsewhere in the EU, you keep the protection of the mandatory rules of your own country.`,
        ),
      ],
    },
    {
      id: 'changes',
      heading: 'Changes',
      blocks: [
        p(
          `Effective from ${EFFECTIVE_LABEL}. These terms change when the project does, and every version is in the repository’s history.`,
        ),
      ],
    },
  ],
};

const REFUNDS: Doc = {
  slug: 'refunds',
  title: 'Refund policy',
  description:
    'A donation to archeus is a voluntary gift, not a purchase. What that means for refunds, who actually took your payment, and how to reach them.',
  intro:
    'Nothing is sold here. The only way money moves is a voluntary donation on Ko-fi, and this page says plainly what that does and does not entitle you to.',
  sections: [
    {
      id: 'gift',
      heading: 'A donation is a gift, not a purchase',
      lead:
        'Nothing is supplied in return for it, which is the whole reason it stays simple.',
      blocks: [
        p(NO_PERKS),
        p(
          'Because no goods or services are supplied in exchange, a donation is not a consumer contract and the statutory right of withdrawal that comes with buying something online does not attach to it. That is not a term being imposed on you — it follows from there being nothing bought.',
        ),
      ],
    },
    {
      id: 'refunds',
      heading: 'Refunds',
      blocks: [
        ul([
          'As a matter of policy no refunds are offered, because nothing was sold. A gift given freely is not an order that can be cancelled.',
          'A donation made by mistake is a different thing, and it is not treated as final. Write to the address below, or raise it with Ko-fi, and it will be sorted out where the payment provider still allows it.',
          'Ask quickly. Whether a payment can be reversed at all is decided by Ko-fi and the card or PayPal rules behind it, and every one of those is a clock.',
          'This project never sees or holds your card details; they stay with the payment provider.',
        ]),
        links([
          { label: `Email ${SITE.contact}`, href: MAILTO },
          { label: 'Ko-fi terms', href: 'https://more.ko-fi.com/tos' },
          { label: 'Ko-fi help centre', href: 'https://help.ko-fi.com/' },
        ]),
      ],
    },
    {
      id: 'help',
      heading: 'If something went wrong',
      blocks: [
        p(
          `Write to ${SITE.contact}. A real person reads that mailbox. A donation made by accident, twice over, or for far more than you meant is worth writing about rather than shrugging at — say what happened and roughly when, and it will either be put right or you will be told plainly why it cannot be.`,
        ),
        links([{ label: `Email ${SITE.contact}`, href: MAILTO }]),
      ],
    },
    {
      id: 'would-change',
      heading: 'What would change this',
      blocks: [
        p(
          'If the project ever offered something in return for money — a membership tier, a perk, early access, priority support, anything at all — that would stop being a gift and become a sale. A sale brings a right of withdrawal, a real refund procedure and a good deal else with it. None of that is offered today, and if it ever is, this page and the terms change before it goes live, not after.',
        ),
        p(`Effective from ${EFFECTIVE_LABEL}.`),
      ],
    },
  ],
};

/** The four policies, in the order they are listed everywhere. */
export const LEGAL: Doc[] = [PRIVACY, TERMS, COOKIES, REFUNDS];

export const LEGAL_BY_SLUG = new Map(LEGAL.map((d) => [d.slug, d]));

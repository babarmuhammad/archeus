# The SEO runbook

Two hosts publish this project and they are ONE entity: the apex (`www/`, Next.js,
Vercel) and the manual (`docs/`, MkDocs Material, Vercel **and** GitHub Pages from
one build). Everything here exists because an unrelated Rust project ships under
the same name and out-ranks a Python package structurally — crates.io, docs.rs and
lib.rs are three high-authority domains we are never granted. The answer is one
corroborated entity, not more keywords.

The rules and their reasons live in `CLAUDE.md`; this is what to RUN, and the
one-off browser work nothing in the repository can do.

## Every change to `docs/` or `www/` ends with this

```bash
py -m mkdocs build --strict          # resolves relative links; writes site/
cd www && npm run build && cd ..     # type-checks and prerenders; writes www/.next
py tools/check_site_seo.py --docs --www
py tools/audit_site.py               # every page at 390x844, nothing past the right edge
py tools/optimize_images.py --check
py -m pytest tests/test_site_links.py tests/test_docs_site.py -q
```

A build is not a check. `mkdocs --strict` and `next build` have no opinion about a
description too long to render, a page with two `<h1>`, an image with no
dimensions, or a link that 308s before it arrives — every one of those shipped
live at some point, and each of these three tools found a real defect the first
time it ran. They read what the sites SERVE; the `tests/` gates read source, on
purpose, because the `test` CI job installs pytest and nothing else.

`check_site_seo.py` counts what it checked and fails below a floor (25 docs pages,
15 apex), because a checker that stops finding pages otherwise reports success.

## Writing a page

- **A meta description is 50-165 characters.** Gated. Over the cap it is truncated
  in the result, under the floor it says nothing worth indexing.
- **One `<h1>` per page.** A rendered repository file (`CONTRIBUTING.md`,
  `CHANGELOG.md`) carries its own, so the site strips it — and in JavaScript `.`
  does not match a newline, which is how that strip silently did nothing on the
  files git had given CRLF endings.
- **The two hosts have OPPOSITE URL shapes.** The apex serves `/features`, the
  manual serves `/installation/`. A link written with the other one's convention
  costs a 308 on every visit; `tests/test_site_links.py` asserts both, and
  `mkdocs --strict` cannot see an absolute URL at all.
- **A docs page must appear in `mkdocs.yml`'s `nav`.** Any `.md` under `docs_dir`
  is published; one not in the nav is an orphan, and a test fails on it.
- **Structured data is derived from the page, never written beside it.**
  `overrides/main.html` emits `TechArticle` + `BreadcrumbList` for every docs page
  under the apex's `@id`s, and `tools/mkdocs_hooks.py` builds a `FAQPage` from
  Troubleshooting's symptom headings and a `HowTo` from Quickstart's numbered
  steps. A page whose headings are not steps produces NOTHING, which is the guard:
  structured data that does not match the page is worse than none.
- **Images:** never hand-edit anything under `docs/img/` — `tools/shot_gui.py` and
  `tools/shot_tui.py` write the PNGs, `tools/optimize_images.py` derives the WebP,
  and the PNG stays the master because `README.md` embeds it by
  raw.githubusercontent URL, which is what PyPI renders. `www/public/img` gets no
  WebP at all: `next/image` negotiates the format per request.

## The entity graph

This is the disambiguation mechanism, and it is the half that actually moved the
needle on a new domain — a three-day-old site with perfect technical SEO returned
zero Search Console results while the corroboration did the work.

- `PROFILES` in `www/lib/site.ts` is the author's `sameAs` set. Add a URL only once
  it exists AND links back here; a dead or one-way profile weakens the graph.
- The application's own `sameAs` in `www/app/layout.tsx` names every registry that
  carries the name — the repository, PyPI, npm, RubyGems and the docs host. A new
  registry publish belongs there and in `SITE`, which is one line each.
- `docs/llms.txt` and the apex's `/llms.txt` route are written for a reader that
  has only that file. A new distribution channel gets a line there too.
- Never disparage the name collision, and never mention it outside the FAQ entry
  that disambiguates it. Corroboration wins that; comparison does not.

## After a release, or after adding pages

```bash
py tools/indexnow.py --submit
```

Pushes both sitemaps to Bing, Yandex, Seznam and Naver — the engines that accept
a push. Google does not participate: it is reached by crawling and by Search
Console, so there is nothing to run for it. Not on a deploy hook on purpose; 48
URLs re-submitted on every push is how a host gets its quota cut.

## Browser work no script can do

- **Search Console:** `notes/search-console.md`. Use a **Domain** property — a
  URL-prefix property on the apex reports nothing for `docs.` and silently hides
  more than half the known URLs. Submit both sitemaps; they are separate hosts.
- **Changing the domain:** `notes/domain-change.md`, and `tools/set_domain.py`
  rewrites the ~110 places the host is written. The per-path 301s stay up for a
  year and HSTS must not be preloaded before the move.

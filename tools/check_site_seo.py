"""Read the BUILT sites and fail if a page is missing what it was given.

    py -m mkdocs build --strict && py tools/check_site_seo.py          # the manual
    py tools/check_site_seo.py --www                                    # the apex
    py tools/check_site_seo.py --docs --www                             # both

A site is checked only when it is named, and a named site with no build is an
error rather than a skip — the two CI jobs build one site each, so "check
whatever happens to be there" would have each of them quietly checking nothing.
No flag means `--docs`, which is what the docs job has always called.

Everything in `tests/` reads source files, on purpose: the `test` CI job installs
pytest and nothing else, so a gate that needed MkDocs would skip on five of the
six matrix entries. That covers a template losing a block. It does not cover the
template *rendering wrong* — a Jinja expression that silently evaluates to empty,
a title with a quote in it breaking the JSON, a page whose front matter has no
description falling back to nothing. Those only exist in the output.

So this is the built-site half, and it runs in the `docs` job right after the
build that produces the thing it reads.

Both published sites are read, because they fail the same way and neither build
notices. The apex's four longest descriptions were 182-402 characters against a
snippet that renders about 160 — found by pointing this at `www/.next` after it
had already found the same thing on nineteen pages of the manual. Two sites, one
check, rather than one check and a second site nobody measured.

The type lists are per site, because they are different kinds of site: the manual
is a set of articles under one application, the apex is that application's own
site and adds `FAQPage` and `BlogPosting` where the manual adds `TechArticle`.

It counts what it checked and fails below a floor, because a checker that stops
finding pages reports success — this repo has already shipped one tool that
printed "FAILURES: none" while executing zero checks.
"""

import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(ROOT, 'site')
WWW = os.path.join(ROOT, 'www', '.next', 'server', 'app')

#: Fewer pages than this means the walk broke, not that the site shrank.
PAGE_FLOOR = 25
#: 12 apex routes plus 7 blog posts; the floor sits under both.
WWW_PAGE_FLOOR = 15

#: The schema nodes each site must carry on every page.
DOCS_TYPES = ('Person', 'WebSite', 'SoftwareApplication', 'TechArticle',
              'BreadcrumbList')
WWW_TYPES = ('Person', 'WebSite', 'SoftwareApplication')

#: A search result renders about 160 characters. Past that the end of the
#: sentence is written for nobody.
DESC_MAX = 165
DESC_MIN = 50

LD = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)
META = re.compile(r'<meta\s+(?:name|property)="([^"]+)"\s+content="([^"]*)"')
CANON = re.compile(r'<link rel="canonical" href="([^"]+)"')
H1 = re.compile(r'<h1[ >]')
IMG = re.compile(r'<img\b[^>]*>')


def _pages():
    """The manual: MkDocs writes one `index.html` per page directory."""
    for dirpath, _dirs, files in os.walk(SITE):
        for name in files:
            if name == 'index.html':
                yield os.path.join(dirpath, name)


def _www_pages():
    """The apex: Next prerenders `<route>.html` under .next/server/app.

    `_`-prefixed files are the framework's own (`_not-found`, `_global-error`)
    and are not routes anyone reaches by link."""
    for dirpath, _dirs, files in os.walk(WWW):
        for name in sorted(files):
            if name.endswith('.html') and not name.startswith('_'):
                yield os.path.join(dirpath, name)


def _check(path, base, types, problems, images=True):
    rel = os.path.relpath(path, base).replace(os.sep, '/')
    with open(path, encoding='utf-8') as f:
        html = f.read()
    meta = dict(META.findall(html))

    def bad(msg):
        problems.append('%s: %s' % (rel, msg))

    # --- one h1, and it is the page's own ---------------------------------
    n = len(H1.findall(html))
    if n != 1:
        bad('%d <h1> elements' % n)

    # --- canonical --------------------------------------------------------
    canon = CANON.search(html)
    if not canon:
        bad('no canonical link')
    elif not canon.group(1).startswith('https://'):
        bad('canonical is not absolute: %s' % canon.group(1))

    # --- description ------------------------------------------------------
    desc = meta.get('description', '')
    if not desc:
        bad('no meta description')
    elif len(desc) > DESC_MAX:
        bad('description is %d chars (>%d, a search result truncates)'
            % (len(desc), DESC_MAX))
    elif len(desc) < DESC_MIN:
        bad('description is %d chars (<%d, too thin to be a snippet)'
            % (len(desc), DESC_MIN))

    # --- social card ------------------------------------------------------
    for key in ('og:title', 'og:description', 'og:url', 'og:image',
                'twitter:card', 'twitter:image'):
        if not meta.get(key):
            bad('no %s' % key)

    # --- structured data --------------------------------------------------
    blocks = LD.findall(html)
    if not blocks:
        bad('no JSON-LD at all')
    seen = set()
    for raw in blocks:
        try:
            data = json.loads(raw)
        except ValueError as exc:
            bad('JSON-LD does not parse: %s' % exc)
            continue
        nodes = data.get('@graph', [data]) if isinstance(data, dict) else data
        for node in nodes:
            if not isinstance(node, dict):
                continue
            seen.add(node.get('@type'))
            for key in ('name', 'headline', 'description'):
                if key in node and not str(node[key]).strip():
                    bad('JSON-LD %s has an empty %s' % (node.get('@type'), key))
    for want in types:
        if want not in seen:
            bad('JSON-LD is missing %s' % want)

    # --- images -----------------------------------------------------------
    if images:
        for tag in IMG.findall(html):
            if 'alt=' not in tag:
                bad('an <img> has no alt: %s' % tag[:80])
            # Not the theme's own header logo, which is one small mark. The
            # content images are the ones that reflow the text under them.
            if '/img/' in tag or 'graph-real' in tag:
                for attr in ('width=', 'height=', 'loading='):
                    if attr not in tag:
                        bad('an <img> has no %s: %s' % (attr.rstrip('='), tag[:80]))


def main(argv):
    want_www = '--www' in argv
    want_docs = '--docs' in argv or not want_www

    problems = []
    docs = []
    if want_docs:
        if not os.path.isdir(SITE):
            print('no site/ — run `py -m mkdocs build --strict` first')
            return 1
        docs = sorted(_pages())
        for path in docs:
            _check(path, SITE, DOCS_TYPES, problems)

        for name in ('sitemap.xml', 'robots.txt', 'llms.txt', 'llms-full.txt',
                     'CNAME'):
            if not os.path.isfile(os.path.join(SITE, name)):
                problems.append('site/%s was not built' % name)
        if len(docs) < PAGE_FLOOR:
            problems.append('only %d docs pages checked — expected at least %d, so '
                            'the walk is broken rather than the site being small'
                            % (len(docs), PAGE_FLOOR))

    www = []
    if want_www:
        if not os.path.isdir(WWW):
            print('www/.next is missing — run `npm run build` in www/ first')
            return 1
        www = sorted(_www_pages())
        for path in www:
            # next/image rewrites every <img> into a srcset at request time, so
            # the prerendered markup is not what a reader is served. The apex's
            # image discipline is enforced at the component instead:
            # components/Shot.tsx cannot be constructed without width and height.
            _check(path, WWW, WWW_TYPES, problems, images=False)
        if len(www) < WWW_PAGE_FLOOR:
            problems.append('only %d apex pages checked — expected at least %d'
                            % (len(www), WWW_PAGE_FLOOR))

    print('checked %s' % ' and '.join(
        x for x in ('%d docs pages' % len(docs) if want_docs else '',
                    '%d apex pages' % len(www) if want_www else '') if x))
    if problems:
        print('\n%d problems:' % len(problems))
        for p in problems:
            print('  ' + p)
        return 1
    print('clean')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))

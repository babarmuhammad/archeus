"""Two hosts, one crawl policy.

archeus publishes on two origins — the marketing site on the apex and the manual
on `docs.` — and they are two separate deployments built by two different
toolchains, so the policy is written twice: once as a Next.js route
(`www/app/robots.ts`) and once as a static file (`docs/robots.txt`). Two
statements of one policy is two chances for them to disagree, and a disagreement
here is invisible: nothing 404s, no build fails, one host is just quietly
excluded from an index the other is in.

So the list is compared rather than trusted, in both directions — a crawler
named on one host and not the other fails either way round.
"""

import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROBOTS_TS = os.path.join(ROOT, 'www', 'app', 'robots.ts')
ROBOTS_TXT = os.path.join(ROOT, 'docs', 'robots.txt')


def _read(path):
    with open(path, encoding='utf-8') as f:
        return f.read()


def _apex_crawlers():
    """The `CRAWLERS` array from the Next route, minus its comments."""
    body = re.search(r'const CRAWLERS = \[(.*?)\];', _read(ROBOTS_TS), re.S)
    assert body, 'www/app/robots.ts no longer declares a CRAWLERS array'
    return [m.group(1) for m in re.finditer(r"'([^']+)'", body.group(1))]


def _docs_crawlers():
    """Every `User-agent:` group in the static file except the wildcard, and
    only from lines that are not commented out."""
    out = []
    for line in _read(ROBOTS_TXT).splitlines():
        line = line.strip()
        if line.startswith('#'):
            continue
        m = re.match(r'User-agent:\s*(\S+)', line, re.I)
        if m and m.group(1) != '*':
            out.append(m.group(1))
    return out


def test_both_hosts_name_the_same_crawlers():
    apex, docs = _apex_crawlers(), _docs_crawlers()
    assert sorted(apex) == sorted(docs), (
        'the two robots files disagree — only on the apex: %s; only on docs: %s'
        % (sorted(set(apex) - set(docs)), sorted(set(docs) - set(apex))))


def test_the_two_opt_in_crawlers_are_named_explicitly():
    """Google-Extended and Applebot-Extended are the only two agents for which
    the wildcard group is not an answer: they control whether Gemini/AI
    Overviews and Apple Intelligence may use the content, and an absent rule
    reads as a refusal rather than as the default. Everything archeus publishes
    is meant to be quotable, so both are named."""
    named = set(_apex_crawlers())
    for agent in ('Google-Extended', 'Applebot-Extended'):
        assert agent in named, '%s has no explicit rule, which reads as a no' % agent


def test_neither_host_disallows_anything_in_production():
    """There is no private path on either site. A `Disallow` here would be a
    typo with a long tail — and the one legitimate blanket disallow, on a Vercel
    preview deployment, is gated on VERCEL_ENV rather than written flat."""
    for line in _read(ROBOTS_TXT).splitlines():
        assert not line.strip().lower().startswith('disallow'), line
    ts = _read(ROBOTS_TS)
    for m in re.finditer(r"disallow:\s*'([^']*)'", ts):
        # The only disallow allowed is the preview-deployment one, and it must
        # sit inside the VERCEL_ENV branch.
        before = ts[:m.start()]
        assert 'VERCEL_ENV' in before.rsplit('return', 1)[0][-400:], \
            'unconditional disallow in www/app/robots.ts: %s' % m.group(0)


def test_the_preview_deployment_is_not_indexable():
    """A Vercel preview serves the whole site on a *.vercel.app origin: the same
    pages, a different host, and nothing on the page says which one is real.
    Two halves, because they catch different entries — robots.txt stops a
    crawl, `X-Robots-Tag` stops a URL someone linked to directly."""
    ts = _read(ROBOTS_TS)
    assert "VERCEL_ENV !== 'production'" in ts, \
        'www/app/robots.ts no longer excludes preview deployments'
    cfg = _read(os.path.join(ROOT, 'www', 'next.config.ts'))
    assert 'X-Robots-Tag' in cfg and 'VERCEL_ENV' in cfg, \
        'next.config.ts no longer sends X-Robots-Tag on preview deployments'


def test_each_robots_file_points_at_its_own_sitemap():
    assert 'Sitemap: https://docs.' in _read(ROBOTS_TXT)
    assert 'sitemap.xml' in _read(ROBOTS_TS)


def test_the_docs_robots_advertises_the_plain_text_summaries():
    """llms.txt is only useful if something finds it. robots.txt is the one file
    every crawler fetches first, and a comment there costs nothing."""
    txt = _read(ROBOTS_TXT)
    assert 'llms.txt' in txt and 'llms-full.txt' in txt

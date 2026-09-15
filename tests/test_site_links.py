"""Every URL this repo publishes, and the two ways one goes quietly wrong.

archeus writes absolute URLs into files that no build ever validates: README.md
(rendered by GitHub and PyPI), `docs/llms.txt` (written for a reader who has only
that file), `pyproject.toml`'s project URLs, two GitHub issue templates, the
blog markdown on the apex. `mkdocs build --strict` cannot see an absolute URL —
an image link is not a page link and an off-host link is not a link it resolves —
and `next build` never looks at markdown it does not render.

Two failures live in that gap, and both had shipped:

**A wrong host.** Two CHANGELOG entries pointed at `babarmuhammad.github.io`,
which is where the manual lived before it had a domain. The rename script skipped
that file by design and the brand gate only looked for `.space` strings, so
nothing was watching the one host that was actually wrong.

**A right host with the wrong shape.** The apex is a Next.js site and serves
`/features`; the manual is MkDocs and serves `/installation/`. Seventeen links
across the README, four docs pages and `llms.txt` were written with the other
one's convention, so every one of them cost a 308 before it arrived. A redirect
hop is not an error anywhere — the page loads, the reader never notices, and the
link equity is spent on the hop.

The third thing here is the domain move. `tools/set_domain.py` swaps the host in
one command; these gates are what keep that command sufficient.
"""

import io
import os
import re
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: Hosts that must never appear in a published link. Both used to.
#:
#: Matched only with the scheme attached (`https://<host>`), never as a bare
#: string. `*.vercel.app` is named in three comments that explain why preview
#: deployments are excluded from the index, and a gate that cannot tell a link
#: from a sentence about links is a gate that gets switched off.
DEAD_HOSTS = (
    # the manual before it had a domain. GitHub Pages redirects to the custom
    # domain, so these still resolve — which is exactly why nobody noticed.
    'babarmuhammad.github.io',
    # a Vercel preview URL is a different origin serving identical content.
    'vercel.app',
)

#: Files whose old URLs are the record, not a mistake.
EXEMPT = {
    'CHANGELOG.md',
    'CLAUDE.md',
    'tools/set_domain.py',
    'tests/test_site_links.py',
    'notes/domain-change.md',
}

#: Directories nobody reads as a page: working notes, captured transcripts,
#: build output, and the test suite — whose docstrings quote the exact broken
#: URLs these gates exist to catch.
EXEMPT_DIRS = ('notes/', '.claude/', '.archeus/', 'site/', 'www/node_modules/',
               'tests/')

BINARY = ('.ico', '.png', '.gif', '.jpg', '.jpeg', '.webp', '.woff', '.woff2',
          '.ttf', '.zip', '.gz', '.pdf', '.lock')


def _tracked():
    out = subprocess.run(['git', 'ls-files'], cwd=ROOT, capture_output=True,
                         text=True, encoding='utf-8', check=True).stdout
    for rel in out.splitlines():
        if rel in EXEMPT or rel.startswith(EXEMPT_DIRS) or rel.lower().endswith(BINARY):
            continue
        # A session transcript committed at the root is a chat log, not a page.
        if rel.startswith('claude-session-'):
            continue
        path = os.path.join(ROOT, rel.replace('/', os.sep))
        try:
            with io.open(path, encoding='utf-8') as f:
                yield rel, f.read()
        except (OSError, UnicodeDecodeError):
            continue


def _set_domain():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        'setdomain', os.path.join(ROOT, 'tools', 'set_domain.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope='module')
def host():
    return _set_domain().CURRENT


def test_no_published_link_points_at_a_host_we_left(host):
    bad = []
    for rel, text in _tracked():
        for dead in DEAD_HOSTS:
            for i, line in enumerate(text.splitlines(), 1):
                if '://' + dead in line or '://' in line and '.' + dead in line:
                    bad.append('%s:%d %s' % (rel, i, line.strip()[:90]))
    assert not bad, bad


def test_an_apex_link_has_no_trailing_slash(host):
    """The apex is Next.js with the default (no trailing slash), so
    `/features/` is a 308 to `/features`. Seventeen links were written the other
    way, all of them by someone who had just written a docs link.

    The lookahead is what tells a trailing slash from a path separator. Without
    it the greedy body backtracks to the FIRST slash it can end on, so the
    perfectly correct `/legal/privacy` reported as `/legal/` — a defect the gate
    could only ever invent, because until the policies landed no tracked file
    named a two-level apex URL and the loose half was never once exercised."""
    pattern = re.compile(
        r'https://%s/[A-Za-z0-9/_-]*[A-Za-z0-9_-]/(?![A-Za-z0-9_-])' % re.escape(host))
    bad = []
    for rel, text in _tracked():
        for i, line in enumerate(text.splitlines(), 1):
            for m in pattern.finditer(line):
                bad.append('%s:%d %s' % (rel, i, m.group(0)))
    assert not bad, ('these 308 before they arrive — drop the trailing slash: %s'
                     % bad)


def test_a_docs_link_keeps_its_trailing_slash(host):
    """And the mirror image. MkDocs publishes directory URLs, so
    `docs.<host>/installation` is a redirect to `docs.<host>/installation/`.
    Both rules exist because the two sites genuinely differ; writing one rule
    for both is what produced the hops in the first place."""
    pattern = re.compile(
        r'https://docs\.%s/([A-Za-z0-9/_-]+)(?![A-Za-z0-9/_.-])' % re.escape(host))
    bad = []
    for rel, text in _tracked():
        for i, line in enumerate(text.splitlines(), 1):
            for m in pattern.finditer(line):
                tail = m.group(1)
                # A file, not a page: llms.txt, sitemap.xml, robots.txt.
                if '.' in tail.rsplit('/', 1)[-1]:
                    continue
                if not m.group(0).endswith('/'):
                    bad.append('%s:%d %s' % (rel, i, m.group(0)))
    assert not bad, ('these redirect before they arrive — add the trailing '
                     'slash: %s' % bad)


def _docs_slugs():
    d = os.path.join(ROOT, 'docs')
    return {n[:-3] for n in os.listdir(d) if n.endswith('.md')}


def _redirected_slugs():
    """Slugs that 301 to a real page, from the docs project's Vercel config."""
    with io.open(os.path.join(ROOT, 'vercel.json'), encoding='utf-8') as f:
        return set(re.findall(r'"source":\s*"/([a-z0-9-]+)/?"', f.read()))


def test_every_docs_url_names_a_page_that_exists(host):
    """`docs/llms.txt` alone carries about thirty-five absolute URLs and is the
    file an answer engine reads first. A renamed page leaves them 404ing with
    nothing anywhere reporting it — `--strict` resolves relative links only."""
    live = _docs_slugs() | _redirected_slugs()
    pattern = re.compile(r'https://docs\.%s/([a-z0-9-]+)/' % re.escape(host))
    missing = []
    for rel, text in _tracked():
        for i, line in enumerate(text.splitlines(), 1):
            for m in pattern.finditer(line):
                if m.group(1) not in live:
                    missing.append('%s:%d /%s/' % (rel, i, m.group(1)))
    assert not missing, 'docs URLs with no page behind them: %s' % missing


def test_the_domain_switch_is_pointed_at_the_domain_we_are_on(host):
    """`tools/set_domain.py` knows the current host as a constant, and every
    gate in this file reads it from there. Change the domain without changing
    that constant and the switch rewrites nothing while every check goes on
    passing — a gate that has stopped watching, which is this repo's most
    expensive recurring bug."""
    with io.open(os.path.join(ROOT, 'mkdocs.yml'), encoding='utf-8') as f:
        assert 'site_url: https://docs.%s/' % host in f.read(), \
            'mkdocs.yml is on a different host from tools/set_domain.py CURRENT'
    with io.open(os.path.join(ROOT, 'www', 'lib', 'site.ts'), encoding='utf-8') as f:
        site = f.read()
    assert "url: 'https://%s'" % host in site
    assert "docs: 'https://docs.%s'" % host in site
    with io.open(os.path.join(ROOT, 'docs', 'CNAME'), encoding='utf-8') as f:
        assert f.read().strip() == 'docs.%s' % host, \
            'docs/CNAME names a host the rest of the repo does not'


def test_the_domain_switch_reaches_every_file_that_names_the_host(host):
    """The switch walks tracked text files and skips a named few. Anything
    naming the host that it cannot reach is a file that would be left on the old
    domain silently — which is the shape of the two CHANGELOG links that were
    wrong for months."""
    mod = _set_domain()
    reachable = set(mod.occurrences())
    everywhere = {rel for rel, text in _tracked() if host in text}
    unreachable = everywhere - reachable
    assert not unreachable, \
        'name the host but set_domain.py will not rewrite them: %s' % sorted(unreachable)

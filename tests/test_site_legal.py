"""The four policies, and the wiring that decides whether they are published.

A legal page is not published because the file exists. It is published because
something links to it, the sitemap names it, and it carries a description a
search result can show. Those three are the failure this file watches, because
each is a silent one: the page still builds, still renders and still 200s, and
nobody finds out it is unreachable until they go looking for it.

The other half is the funding link. It lands in six places at once — the README,
`.github/FUNDING.yml`, three package manifests and the site — and a handle typed
out six times is a handle that will be five the next time it changes. So the
site reads it from one constant, and this file asserts the copies that genuinely
cannot share one (a YAML file, a TOML key, a JSON field) all say the same thing.

None of this is a check that the policies are correct. That is not a thing a
test can know — see `notes/site-legal-risks.md`, which says so at more length,
and says what is still open.
"""

import io
import json
import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: The one true funding destination. Everything else must resolve to it.
KOFI = 'https://ko-fi.com/babarmuhammad'

#: `check_site_seo.py` enforces these on the BUILT html; here they are enforced
#: on the source, because CI's pytest job installs pytest and nothing else and
#: never has a `www/.next` to read.
DESC_MIN, DESC_MAX = 50, 165


def read(*parts):
    with io.open(os.path.join(ROOT, *parts), encoding='utf-8') as fh:
        return fh.read()


@pytest.fixture(scope='module')
def legal_src():
    return read('www', 'lib', 'legal.ts')


@pytest.fixture(scope='module')
def slugs(legal_src):
    """The policies, in the order lib/legal.ts lists them in LEGAL."""
    listed = re.search(r'export const LEGAL: Doc\[\] = \[([^\]]+)\]', legal_src)
    assert listed, 'lib/legal.ts no longer exports a LEGAL array'
    names = [n.strip() for n in listed.group(1).split(',') if n.strip()]
    out = []
    for name in names:
        m = re.search(r'const %s: Doc = \{\s*\n\s*slug: \'([a-z-]+)\'' % name, legal_src)
        assert m, f'{name} is in LEGAL but is not a Doc with a slug'
        out.append(m.group(1))
    assert out, 'LEGAL is empty'
    return out


def test_the_four_policies_are_all_there(slugs):
    """Privacy, terms and cookies are the ask; refunds exists because money moves.

    Named rather than counted: "four policies" would pass if one were renamed to
    another's slug, and the whole point of the refund page is that it is the one
    a donor goes looking for.
    """
    assert set(slugs) == {'privacy', 'terms', 'cookies', 'refunds'}


def test_one_route_renders_every_policy(slugs):
    """There is a single `app/legal/[slug]` route, and it prerenders from LEGAL.

    Four near-identical page files would be four places to forget something. The
    gate is that `generateStaticParams` maps LEGAL — with `dynamicParams` off, a
    slug missing from that array is a 404 rather than a page rendered on demand.
    """
    route = os.path.join(ROOT, 'www', 'app', 'legal', '[slug]', 'page.tsx')
    assert os.path.isfile(route), 'the legal route is gone'
    src = read('www', 'app', 'legal', '[slug]', 'page.tsx')
    assert 'LEGAL.map((d) => ({ slug: d.slug }))' in src
    assert 'export const dynamicParams = false' in src


def test_every_policy_carries_a_description_a_result_can_show(legal_src, slugs):
    """50-165 characters, the same window the built-HTML gate enforces.

    Under the floor it says nothing worth indexing; over the cap it is truncated
    mid-sentence in the result, which on a privacy policy is how you end up with
    a search result that says "the archeus websites do…".
    """
    for slug in slugs:
        block = re.search(
            r"slug: '%s',\s*\n\s*title: '[^']+',\s*\n\s*description:\s*\n?\s*'((?:[^'\\]|\\.)*)'"
            % slug,
            legal_src,
        )
        assert block, f'{slug} has no description'
        desc = block.group(1)
        assert DESC_MIN <= len(desc) <= DESC_MAX, (
            f'{slug}: description is {len(desc)} chars, want {DESC_MIN}-{DESC_MAX}'
        )


def test_every_policy_is_linked_from_the_footer(slugs):
    """A page nothing links to is a page nobody reads and no crawler finds.

    The footer renders LEGAL rather than a hand-written list, so the assertion is
    that it still does: a literal list here would drift the first time a policy
    was added, which is the failure this whole arrangement exists to avoid.
    """
    src = read('www', 'components', 'site', 'Footer.tsx')
    assert "from '@/lib/legal'" in src, 'the footer no longer reads the policy list'
    assert 'LEGAL.map(' in src
    assert 'legalPath(d.slug)' in src


def test_every_policy_is_in_the_sitemap(slugs):
    """Same reasoning as the footer, and the same fix: derived, not restated."""
    src = read('www', 'app', 'sitemap.ts')
    assert "from '@/lib/legal'" in src, 'the sitemap no longer reads the policy list'
    assert 'LEGAL.map((d) => legalPath(d.slug))' in src


def test_a_policy_page_names_who_is_responsible_and_how_to_reach_them():
    """An operator nobody can name and a mailbox nobody can write to is the gap.

    The address in CODE_OF_CONDUCT.md is a GitHub `users.noreply` alias, which is
    send-only: mail to it bounces. It cannot be the contact route a privacy
    notice publishes, and this asserts it never quietly becomes one.
    """
    site = read('www', 'lib', 'site.ts')
    contact = re.search(r"contact: '([^']+)'", site)
    assert contact, 'SITE.contact is gone'
    assert 'users.noreply.github.com' not in contact.group(1), (
        'the contact route is a send-only GitHub alias; mail to it bounces'
    )
    assert re.search(r"operator: '[^']+'", site)
    assert re.search(r"operatorCountry: '[^']+'", site)

    route = read('www', 'app', 'legal', '[slug]', 'page.tsx')
    for token in ('SITE.operator', 'SITE.operatorCountry', 'SITE.contact'):
        assert token in route, f'the policy pages stopped showing {token}'


def test_the_donation_statement_is_on_the_privacy_page_and_the_terms(legal_src):
    """Donations buy nothing, said on both pages, and written once.

    It is the sentence that keeps a donation a gift rather than a consumer supply
    contract, so it may not drift into two versions that say almost the same
    thing. One constant, referenced from both.
    """
    assert re.search(r'^const NO_PERKS =', legal_src, re.M), 'NO_PERKS is gone'
    stated = legal_src[legal_src.index('const PRIVACY'):]
    privacy, rest = stated.split('const TERMS', 1)
    terms = rest.split('const REFUNDS', 1)[0]
    assert 'p(NO_PERKS)' in privacy, 'the privacy page stopped saying donations buy nothing'
    assert 'p(NO_PERKS)' in terms, 'the terms stopped saying donations buy nothing'


def test_there_is_no_consent_banner_and_the_cookie_policy_says_why(legal_src):
    """The unusual answer, and the one a reader will not believe without a reason.

    Consent attaches to storing or reading something on the device. Nothing here
    does either, so a banner would be asking agreement to nothing. That reasoning
    is the page — remove it and what is left is an assertion.
    """
    cookies = legal_src[legal_src.index('const COOKIES'):legal_src.index('const TERMS')]
    assert 'ePrivacy' in cookies
    assert 'consent' in cookies.lower()


@pytest.mark.parametrize(
    'path',
    ['README.md', '.github/FUNDING.yml', 'pyproject.toml',
     'packaging/npm/package.json', 'packaging/rubygems/archeus.gemspec'],
)
def test_the_funding_handle_is_the_same_everywhere(path):
    """Six surfaces, one handle, and no build checks any of them.

    A Ko-fi URL is permanent and it is going into three package registries. These
    five files cannot share a constant — a YAML file, a TOML key, a JSON field, a
    Ruby hash and a markdown badge — so the copies are asserted equal instead.
    """
    text = read(*path.split('/'))
    handle = KOFI.rsplit('/', 1)[1]
    found = re.findall(r'ko-?_?fi[^\s"\']*', text, re.I)
    assert found, f'{path} names no funding link'
    assert handle in text, f'{path} does not name the Ko-fi handle {handle!r}'
    for url in re.findall(r'https://ko-fi\.com/[A-Za-z0-9_-]+', text):
        assert url == KOFI, f'{path} points at {url}, not {KOFI}'


def test_the_funding_manifest_turns_on_the_github_sponsor_button():
    """`.github/FUNDING.yml` is what GitHub reads; the README badge is separate.

    Both are wanted and neither substitutes for the other, which is exactly the
    kind of thing that gets "tidied" into one.
    """
    text = read('.github', 'FUNDING.yml').strip()
    assert text == 'ko_fi: %s' % KOFI.rsplit('/', 1)[1], text


def test_the_package_manifests_declare_funding_where_a_registry_reads_it():
    """PyPI, npm and RubyGems each surface a funding link for free. Cargo has no
    such field, so the crate says it in its README instead — the README IS the
    payload of a pointer crate, and a `[package.metadata]` key crates.io does not
    read would be decoration that looks like wiring.
    """
    assert 'Funding = "%s"' % KOFI in read('pyproject.toml')
    npm = json.loads(read('packaging', 'npm', 'package.json'))
    assert npm['funding'] == KOFI
    assert "'funding_uri' => '%s'" % KOFI in read('packaging', 'rubygems', 'archeus.gemspec')
    assert KOFI in read('packaging', 'crates', 'README.md')
    assert 'metadata.funding' not in read('packaging', 'crates', 'Cargo.toml')


def test_the_site_reads_the_funding_url_from_one_place():
    """`SITE` is the single source for the project's own external destinations,
    and `tools/set_domain.py` and the link tests read it. A second copy of the
    funding URL in a component is a second thing to change when the handle does.

    What is banned is the HANDLE, not the host. `more.ko-fi.com/privacy` and
    `help.ko-fi.com` are citations of Ko-fi's own documents inside a policy, the
    same class as the Vercel and GitHub notices beside them, and those belong
    where they are cited — moving only the Ko-fi ones into SITE would make the
    rule about which company a link points at rather than about what it means.
    """
    assert "kofi: '%s'" % KOFI in read('www', 'lib', 'site.ts')
    strays = []
    for base, dirs, files in os.walk(os.path.join(ROOT, 'www')):
        dirs[:] = [d for d in dirs if d not in ('node_modules', '.next', 'out')]
        for name in files:
            if not name.endswith(('.ts', '.tsx', '.js', '.jsx', '.css')):
                continue
            full = os.path.join(base, name)
            rel = os.path.relpath(full, ROOT).replace(os.sep, '/')
            if rel == 'www/lib/site.ts':
                continue
            with io.open(full, encoding='utf-8') as fh:
                if KOFI in fh.read():
                    strays.append(rel)
    assert not strays, 'the funding URL is hardcoded outside SITE: %s' % ', '.join(strays)


def test_the_policies_are_published_once_not_mirrored_into_the_manual():
    """Two copies of a policy is two policies, and the second one is wrong.

    The manual links to the apex copies instead. This fails if a docs page ever
    grows its own privacy or terms text, which is the tempting thing to do the
    next time somebody wants the manual to be self-contained.
    """
    docs = os.path.join(ROOT, 'docs')
    offenders = [n for n in os.listdir(docs)
                 if n in ('privacy.md', 'terms.md', 'cookies.md', 'refunds.md',
                          'privacy-policy.md', 'cookie-policy.md')]
    assert not offenders, 'the manual grew its own copy of a policy: %s' % offenders
    assert 'claudectl.space/legal/privacy' in read('docs', 'index.md')
    assert 'claudectl.space/legal/privacy' in read('docs', 'llms.txt')

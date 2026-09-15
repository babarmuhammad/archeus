"""Build-time hooks for the docs site. Wired in via `hooks:` in mkdocs.yml.

Two jobs.

**`llms-full.txt`**: every page's Markdown source concatenated into one file,
the companion to the hand-written `docs/llms.txt` index. llms.txt says what
exists and links to it; llms-full.txt is the whole manual as plain text, so a
model that cannot crawl twenty pages can read one.

It is generated rather than committed for the reason `docs/api.md` is generated:
a hand-maintained copy of something the source already states is a copy that
will be wrong. Nothing lands in `docs/`, so it never becomes a stray published
page that `test_every_markdown_page_under_docs_is_in_the_nav` has to know about.

**Structured data built FROM the page, not written beside it.** `overrides/main.html`
gives every page a `TechArticle` and a `BreadcrumbList`; three pages deserve a
richer type, and the honest way to give them one is to derive it from the
headings they already have:

    faq_from_headings: true     ->  FAQPage, one entry per `##`
    howto_from_headings: true   ->  HowTo, one step per `##`

`docs/troubleshooting.md` is the case that makes the argument. Its headings are
the exact strings a user pastes into a search box — `"claude.exe not found"`,
`"No output from Claude"` — and the prose under each is the answer. Marked up,
those are the answers an engine quotes; hand-written into the front matter, they
would be a second copy of the page that stops matching it the first time the
page is edited. The same front-matter key still accepts a literal `jsonld:`
block for anything neither shape fits.
"""

import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# `pymdownx.snippets` runs during Markdown conversion, which is after
# on_page_markdown — so an include would still be a marker line here and the
# page would export as one line of syntax rather than its content.
#
# Nothing uses it today: the two pages that did (docs/changelog.md,
# docs/code-of-conduct.md) moved to the apex site and the extension came out of
# mkdocs.yml with them. The expansion stays because it costs one regex on text
# already in memory, and the export is the file an answer engine reads — a
# silently truncated page here is worse than a dead branch.
INCLUDE = re.compile(r'^-{2}8<-{2}\s+"([^":]+)"\s*$', re.M)

_PAGES = []


def _expand(text):
    def sub(m):
        path = os.path.join(ROOT, m.group(1).replace('/', os.sep))
        try:
            with open(path, encoding='utf-8') as f:
                return f.read()
        except OSError:
            return m.group(0)
    return INCLUDE.sub(sub, text)


def _strip_front_matter(text):
    return re.sub(r'\A---\n.*?\n---\n', '', text, flags=re.S)


# --- structured data derived from the page ---------------------------------

#: How much of a section to quote as an answer. Long enough for the whole of
#: every troubleshooting entry as written; short enough that a page which grows
#: a ten-paragraph section does not put ten paragraphs into a search result.
ANSWER_MAX = 1200

_FENCE = re.compile(r'^\s*(```|~~~)')
_INLINE = [
    (re.compile(r'!\[[^\]]*\]\([^)]*\)'), ''),           # images
    (re.compile(r'\[([^\]]+)\]\([^)]*\)'), r'\1'),       # links -> their text
    (re.compile(r'\{[^}\n]*\}'), ''),                    # attr_list
    (re.compile(r'[*_`]{1,3}'), ''),                     # emphasis, code spans
    (re.compile(r'^\s*[-*+]\s+', re.M), ''),             # list bullets
    (re.compile(r'^\s*!!!.*$', re.M), ''),               # admonition openers
    (re.compile(r'^\s*===.*$', re.M), ''),               # tabbed blocks
]


def _plain(md):
    """A markdown section as the sentence a person would read aloud.

    Fences are unwrapped rather than dropped: for `"claude.exe not found"` the
    command IS the answer, and an answer that omits it is worse than no markup."""
    text = '\n'.join(line for line in md.splitlines() if not _FENCE.match(line))
    for pattern, sub in _INLINE:
        text = pattern.sub(sub, text)
    text = ' '.join(text.split())
    if len(text) > ANSWER_MAX:
        text = text[:ANSWER_MAX].rsplit(' ', 1)[0] + '…'
    return text


def _sections(md):
    """`[(heading, answer text)]` for every `##` in a page, in order.

    The body is flattened here rather than by each caller, so `_plain` runs once
    per section instead of once for the emptiness test and again for the text."""
    parts = re.split(r'^##\s+(.+?)\s*$', _strip_front_matter(md), flags=re.M)
    heads, bodies = parts[1::2], parts[2::2]
    pairs = [(h.strip().strip('"'), _plain(b)) for h, b in zip(heads, bodies)]
    return [(head, answer) for head, answer in pairs if answer]


def _faq(md, page):
    """A FAQPage whose questions are the page's own headings."""
    entries = [{'@type': 'Question', 'name': head,
                'acceptedAnswer': {'@type': 'Answer', 'text': answer}}
               for head, answer in _sections(md)]
    if not entries:
        return None
    return {'@context': 'https://schema.org', '@type': 'FAQPage',
            '@id': (page.canonical_url or '') + '#faq',
            'name': page.title, 'mainEntity': entries}


def _howto(md, page, config):
    """A HowTo whose steps are the page's own numbered headings.

    The numbering is what makes this honest: a page whose `##`s read "1. Install",
    "2. Launch" is already a sequence, and one whose headings are topics is not.
    A page that opts in without numbering its headings gets nothing rather than a
    HowTo claiming its topics are steps."""
    steps = []
    for head, answer in _sections(md):
        m = re.match(r'(\d+)[.)]\s+(.*)', head)
        if not m:
            continue
        steps.append({'@type': 'HowToStep', 'position': int(m.group(1)),
                      'name': m.group(2), 'text': answer,
                      'url': '%s#%s' % (page.canonical_url or '',
                                        re.sub(r'[^a-z0-9]+', '-', head.lower()).strip('-'))})
    if len(steps) < 2:
        return None
    return {'@context': 'https://schema.org', '@type': 'HowTo',
            '@id': (page.canonical_url or '') + '#howto',
            'name': page.title,
            'description': ' '.join(str(page.meta.get('description', '')).split()),
            'totalTime': page.meta.get('totaltime') or None,
            'tool': [{'@type': 'HowToTool', 'name': 'Python 3.10 or newer'},
                     {'@type': 'HowToTool', 'name': 'Claude Code CLI'}],
            'step': steps}


def _derived_jsonld(md, page, config):
    if page.meta.get('faq_from_headings'):
        return _faq(md, page)
    if page.meta.get('howto_from_headings'):
        return _howto(md, page, config)
    return None


def on_pre_build(config, **kw):
    _PAGES.clear()


def on_page_markdown(markdown, page, config, **kw):
    _PAGES.append((page.title, page.canonical_url, _expand(_strip_front_matter(markdown))))
    derived = _derived_jsonld(markdown, page, config)
    if derived is not None:
        # The template reads `page.meta.jsonld`, so a derived block and a
        # hand-written one arrive by the same door and there is one place that
        # emits structured data. `<` is escaped because this lands inside a
        # <script> element, where `</script>` in a string would end it.
        page.meta['jsonld'] = json.dumps(
            {k: v for k, v in derived.items() if v is not None},
            ensure_ascii=False).replace('<', '\\u003c')
    return markdown


def on_post_build(config, **kw):
    parts = ['# %s\n' % config['site_name'],
             '> %s\n' % ' '.join(config['site_description'].split()),
             'The complete archeus documentation as one file. The linked index is at '
             '%sllms.txt.\n' % config['site_url']]
    for title, url, body in _PAGES:
        parts.append('\n---\n\n# %s\n\nSource: %s\n\n%s' % (title, url, body.strip()))
    out = os.path.join(config['site_dir'], 'llms-full.txt')
    with open(out, 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(parts) + '\n')

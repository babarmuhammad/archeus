"""Build-time hooks for the docs site. Wired in via `hooks:` in mkdocs.yml.

Emits `llms-full.txt`: every page's Markdown source concatenated into one file,
which is the companion to the hand-written `docs/llms.txt` index. llms.txt says
what exists and links to it; llms-full.txt is the whole manual as plain text, so
a model that cannot crawl twenty pages can read one.

It is generated rather than committed for the reason `docs/api.md` is generated:
a hand-maintained copy of something the source already states is a copy that
will be wrong. Nothing lands in `docs/`, so it never becomes a stray published
page that `test_every_markdown_page_under_docs_is_in_the_nav` has to know about.
"""

import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# `pymdownx.snippets` runs during Markdown conversion, which is after
# on_page_markdown — so an include is still a marker line here and the page
# (docs/changelog.md, docs/code-of-conduct.md) would otherwise export as one
# line of syntax.
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


def on_pre_build(config, **kw):
    _PAGES.clear()


def on_page_markdown(markdown, page, config, **kw):
    _PAGES.append((page.title, page.canonical_url, _expand(_strip_front_matter(markdown))))
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

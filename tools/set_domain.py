"""Move both published sites to a new domain, in one command.

    py tools/set_domain.py newdomain.dev          # rewrite everything
    py tools/set_domain.py --check                # CI: is the host single-sourced?

archeus publishes on two origins built from this one repo: the marketing site on
the apex (`www/`, Next.js on Vercel) and the manual on `docs.` (MkDocs, deployed
to both Vercel and GitHub Pages). The host string reaches about ninety places
across markdown, YAML, TOML, TypeScript, a CNAME file, two issue templates and
the tests that assert all of the above.

It is spread that way for a reason and consolidating it is not possible: a CNAME
file is one bare hostname and nothing else, `pyproject.toml` needs a literal URL
because a wheel carries no build step, and `docs/llms.txt` is written for a
reader who has only that file. Every one of those is a *published* absolute URL,
and a published URL that is computed is a published URL nobody can read in the
source.

So the answer is not one constant — it is one command, plus a gate
(`tests/test_domain_is_single_sourced.py`) that fails the build if a host
appears anywhere this script does not reach.

What this does NOT do is everything that is not in the repository: DNS, the two
Vercel projects, the GitHub Pages custom domain, the Search Console change of
address, the redirects from the old host. Those are `notes/domain-change.md`,
and the order there matters.
"""

import io
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: The apex the sites are on today. The manual is always `docs.` + this, which
#: is an assumption worth stating: `mkdocs.yml`'s site_url, `docs/CNAME` and
#: `www/lib/site.ts` all have to agree about it, and `test_the_pages_deploy_
#: keeps_the_custom_domain` already fails when two of the three drift.
CURRENT = 'claudectl.space'

#: Files that legitimately name the old host after a move, and are therefore
#: never rewritten. Both are historical records: an entry describing a release
#: that really did point at that host, and the runbook that says what the move
#: was. `--check` reports them rather than ignoring them, because "skipped" and
#: "clean" are the two states this script must never confuse — the two broken
#: `babarmuhammad.github.io` links in CHANGELOG.md survived a whole rename by
#: being in a skip list nobody printed.
SKIP = {
    'CHANGELOG.md',
    'notes/domain-change.md',
    'tools/set_domain.py',
}

#: Extensions that are not text.
BINARY = ('.ico', '.png', '.gif', '.jpg', '.jpeg', '.webp', '.woff', '.woff2',
          '.ttf', '.zip', '.gz', '.pdf', '.mp4', '.webm')


def tracked_text_files():
    out = subprocess.run(['git', 'ls-files'], cwd=ROOT, capture_output=True,
                         text=True, encoding='utf-8', check=True).stdout
    for rel in out.splitlines():
        if rel in SKIP or rel.lower().endswith(BINARY):
            continue
        yield rel


def _read(rel):
    """newline='' on read AND write: the file's real line endings survive.

    Pairing a translating read with a non-translating write is what silently
    converts a CRLF checkout to LF and turns a two-line change into a
    whole-file diff. Learned in tools/_rename_brand.py, which does the same."""
    path = os.path.join(ROOT, rel.replace('/', os.sep))
    try:
        with io.open(path, encoding='utf-8', newline='') as f:
            return f.read()
    except (OSError, UnicodeDecodeError):
        return None


def occurrences(host=CURRENT):
    """`{file: [line numbers]}` for every tracked file naming the host."""
    found = {}
    for rel in tracked_text_files():
        src = _read(rel)
        if src is None or host not in src:
            continue
        found[rel] = [i for i, line in enumerate(src.splitlines(), 1) if host in line]
    return found


def skipped_occurrences(host=CURRENT):
    """The same, for the files this script refuses to touch."""
    found = {}
    for rel in sorted(SKIP):
        src = _read(rel)
        if src is not None and host in src:
            found[rel] = [i for i, line in enumerate(src.splitlines(), 1) if host in line]
    return found


def rewrite(new_host, old_host=CURRENT):
    """Swap the host everywhere, and return the files changed."""
    changed = []
    for rel, _lines in occurrences(old_host).items():
        path = os.path.join(ROOT, rel.replace('/', os.sep))
        src = _read(rel)
        txt = src.replace(old_host, new_host)
        if txt != src:
            with io.open(path, 'w', encoding='utf-8', newline='') as f:
                f.write(txt)
            changed.append(rel)
    return changed


def main(argv):
    if '--check' in argv:
        found = occurrences()
        print('%s is named in %d tracked files, %d lines — all reachable.'
              % (CURRENT, len(found), sum(len(v) for v in found.values())))
        held = skipped_occurrences()
        if held:
            print('\nNOT rewritten (in SKIP), fix by hand after a move:')
            for rel, lines in held.items():
                print('  %-28s lines %s' % (rel, ', '.join(map(str, lines))))
        return 0

    args = [a for a in argv[1:] if not a.startswith('-')]
    if len(args) != 1:
        print(__doc__.strip().splitlines()[0])
        print('\nusage: py tools/set_domain.py <new-apex-host>')
        print('       py tools/set_domain.py --check')
        return 2
    new_host = args[0].strip().lower().rstrip('/')
    if not re.fullmatch(r'[a-z0-9-]+(\.[a-z0-9-]+)+', new_host):
        print('%r does not look like a bare hostname (no scheme, no path)' % new_host)
        return 2
    if new_host == CURRENT:
        print('already on %s' % new_host)
        return 0

    changed = rewrite(new_host)
    print('%s -> %s in %d files' % (CURRENT, new_host, len(changed)))
    for rel in changed:
        print('  ' + rel)

    held = skipped_occurrences()
    if held:
        print('\nSTILL NAMING %s, by design — read each and decide:' % CURRENT)
        for rel, lines in held.items():
            print('  %-28s lines %s' % (rel, ', '.join(map(str, lines))))

    print('\nCURRENT in this file is still %r. Change it to %r in the same commit,'
          % (CURRENT, new_host))
    print('or the gate stops watching the host you are actually on.')
    print('Then: notes/domain-change.md — DNS, Vercel, Pages, Search Console.')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))

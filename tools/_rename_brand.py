"""One-shot: claudectl -> archeus across every tracked text file.

ONE string is still HELD BACK deliberately and restored after the substitution:

  claudectl.space              the domain is not bought yet; the site and the
                               docs still deploy there until it is.

`babarmuhammad/claudectl` was held here too until the GitHub repo was renamed.
It is released now. Nothing was broken by the rename — GitHub redirects the old
path, and that covers `raw.githubusercontent.com` too, so the README's
screenshots kept resolving (checked, not assumed). The links are updated anyway
for two reasons: an address should name the thing it points at rather than lean
on a shim, and that shim dies the moment anything else occupies the old path —
which only this account can do, but this account is exactly who would do it.

CHANGELOG.md is skipped entirely: its entries describe releases that really
were named claudectl.

Run from the repo root:  py tools/_rename_brand.py
"""
import io
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: Files that legitimately keep the old name, and are therefore never rewritten.
#:
#: `tests/test_no_old_brand_string.py` imports THIS set as its allowlist. They
#: were two lists for one concept exactly once, and the second run of this
#: script rewrote `migrate.py` to `OLD = 'archeus'` — a migration that finds
#: nothing, moves nothing, and still writes its done flag, which would have
#: stranded every existing user's settings and memory graph under the old name
#: permanently. Nothing failed; the tests were rewritten in the same pass, so
#: they went on passing. One list, or this happens again.
SKIP = {
    'CHANGELOG.md',                    # releases that really were named that
    '.gitignore',                      # keeps old machine-local state unstageable
    # the "Coming from claudectl" section — instructions that name the old
    # package because that is the thing being uninstalled. Verified to contain
    # no held string, so skipping the whole file cannot strand the domain.
    'docs/installation.md',
    'claude_sessions/migrate.py',      # the one module that must know both names
    'tests/test_migration.py',
    'tests/test_no_old_brand_string.py',
    'tools/_rename_brand.py',
    'tools/_mut_migration.py',
    'tools/_e2e_migration.py',
}

#: substring -> placeholder. Placeholders use a character that cannot occur in
#: source text, so restoring them cannot collide with anything real.
HOLD = {
    'claudectl.space': '\x00HOLD-DOMAIN\x00',
    # The README's one deliberate mention. It is HELD rather than the whole file
    # being SKIPped, because the same file carries a dozen repository URLs that
    # do have to change — and skipping it turned "Formerly claudectl" into
    # "Formerly archeus", which says nothing at all.
    'Formerly <code>claudectl</code>': '\x00HOLD-FORMERLY\x00',
}

SUBS = (('claudectl', 'archeus'),
        ('Claudectl', 'Archeus'),
        ('CLAUDECTL', 'ARCHEUS'))


def tracked_text_files():
    out = subprocess.run(['git', 'ls-files'], cwd=ROOT, capture_output=True,
                         text=True, encoding='utf-8', check=True).stdout
    for rel in out.splitlines():
        if rel in SKIP or rel.endswith(('.ico', '.png', '.gif', '.jpg', '.woff',
                                        '.woff2', '.ttf', '.zip', '.gz', '.pdf')):
            continue
        yield rel


def main():
    changed = []
    for rel in tracked_text_files():
        path = os.path.join(ROOT, rel.replace('/', os.sep))
        try:
            # newline='' on BOTH read and write: read it and the string keeps
            # the file's real '\r\n', write it and they go back untouched.
            # Pairing a translating read with a non-translating write is what
            # silently converts a CRLF checkout to LF and churns the diff.
            with io.open(path, encoding='utf-8', newline='') as f:
                src = f.read()
        except (OSError, UnicodeDecodeError):
            continue
        if 'claudectl' not in src.lower():
            continue
        txt = src
        for real, ph in HOLD.items():
            txt = txt.replace(real, ph)
        for old, new in SUBS:
            txt = txt.replace(old, new)
        for real, ph in HOLD.items():
            txt = txt.replace(ph, real)
        if txt != src:
            with io.open(path, 'w', encoding='utf-8', newline='') as f:
                f.write(txt)
            changed.append(rel)
    print('%d files rewritten' % len(changed))
    for rel in changed:
        print('  ' + rel)
    return 0


if __name__ == '__main__':
    sys.exit(main())

"""One-shot: claudectl -> archeus across every tracked text file.

Two strings are HELD BACK deliberately and restored after the substitution:

  claudectl.space              the domain is not bought yet; the site and the
                               docs still deploy there until it is.
  babarmuhammad/claudectl      the GitHub repo has not been renamed yet, so
                               every link to it must keep resolving.

Both are one `sed` away once those two moves happen. CHANGELOG.md is skipped
entirely: its entries describe releases that really were named claudectl.

Run from the repo root:  py tools/_rename_brand.py
"""
import io
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SKIP = {'CHANGELOG.md', 'tools/_rename_brand.py'}

#: substring -> placeholder. Placeholders use a character that cannot occur in
#: source text, so restoring them cannot collide with anything real.
HOLD = {
    'claudectl.space': '\x00HOLD-DOMAIN\x00',
    'babarmuhammad/claudectl': '\x00HOLD-REPO\x00',
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

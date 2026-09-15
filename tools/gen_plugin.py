"""Regenerate the plugin's bundled skills from the package's own templates.

The templates live in `claude_sessions/skills_templates/<name>/SKILL.md`
because the wheel ships them from inside the package — `package-data` cannot
reach outside it. The plugin needs the same files at `plugin/skills/<name>/`.
Rather than maintain two copies, this copies one to the other and a test fails
when they differ.

    py -3 tools/gen_plugin.py            # sync plugin/skills/
    py -3 tools/gen_plugin.py --check    # exit 1 if out of sync
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, 'claude_sessions', 'skills_templates')
DST = os.path.join(ROOT, 'plugin', 'skills')

NOTE = ('<!-- Generated from claude_sessions/skills_templates by '
        'tools/gen_plugin.py — do not edit here. -->\n')


def _templates():
    for name in sorted(os.listdir(SRC)):
        p = os.path.join(SRC, name, 'SKILL.md')
        if os.path.isfile(p):
            yield name, open(p, encoding='utf-8').read().replace('\r\n', '\n')


def _wanted():
    """{relative path: content} — what plugin/skills/ should contain."""
    out = {}
    for name, text in _templates():
        lines = text.split('\n')
        # the note goes after the frontmatter, which must stay the first thing
        if lines and lines[0].strip() == '---':
            end = lines.index('---', 1)
            text = '\n'.join(lines[:end + 1]) + '\n' + NOTE + '\n'.join(lines[end + 1:])
        else:
            text = NOTE + text
        out[os.path.join(name, 'SKILL.md')] = text
    return out


def _have():
    out = {}
    for root, _dirs, names in os.walk(DST):
        for n in names:
            p = os.path.join(root, n)
            out[os.path.relpath(p, DST)] = open(
                p, encoding='utf-8').read().replace('\r\n', '\n')
    return out


def main(argv):
    wanted = _wanted()
    if not wanted:
        print('no templates found in', SRC)
        return 1
    if '--check' in argv:
        if _have() != wanted:
            print('plugin/skills is out of sync — run tools/gen_plugin.py')
            return 1
        print('plugin/skills is current (%d skills)' % len(wanted))
        return 0
    for rel, text in wanted.items():
        p = os.path.join(DST, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, 'w', encoding='utf-8', newline='\n') as f:
            f.write(text)
    for rel in set(_have()) - set(wanted):
        os.remove(os.path.join(DST, rel))
    print('synced %d skills into %s' % (len(wanted), DST))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))

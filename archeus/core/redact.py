"""What no event, checkpoint, brief or hand-off artifact may carry
(p11-design-gate §19; p12-design-gate D6): one pattern list, shared by every
writer of text that leaves a process."""

import re

from archeus.core.domain.ids import TOKEN_PREFIXES

# redact() is for free text. A JSON document goes through redact_json, which
# redacts the parsed strings and so can never cut a quote or an escape. Every
# pattern stays linear: a start is anchored or has a bounded prefix, and each
# repeat has one way to match. A PEM runs to its END line, or to the end of the
# text when it has none, whatever the key's lines carry (a Read tool's arrows, a
# docker prefix, `> `) and however long it is: a bound would leave the rest of an
# oversized key in the text, so the scan fails closed instead. A key cut over the
# lines of a stream is followed by pem_open and close_pem.
_PEM_END = r'-----END [A-Z ]{0,32}PRIVATE KEY-----'
_PEM_END_AT = re.compile(_PEM_END)
_PEM_MARK = re.compile(r'-----(BEGIN|END) [A-Z ]{0,32}PRIVATE KEY-----')
_PEM = r'-----BEGIN [A-Z ]{0,32}PRIVATE KEY-----[\s\S]*?(?:%s|\Z)' % _PEM_END
# What may stand before a token: a character that cannot continue it, or the
# `n` or `t` of a literal backslash-n or backslash-t, which a string escaped
# twice has in place of a newline or a tab.
_EDGE = r'(?:(?<![A-Za-z0-9_\-])|(?<=\\[nrt]))'
_QUOTE = r'''(?:\\*["'])?'''

# The minted token prefixes come from ids, so a new credential kind cannot be
# left out. A bare 40-character AWS secret has no marker, so only the keyed form
# is caught.
_PARTS = (
    r'(?:%s)_[A-Za-z0-9_\-]{8,}' % '|'.join(TOKEN_PREFIXES.values()),
    r'sk-[A-Za-z0-9_\-]{8,}', r'(?i:sk-ant)-[A-Za-z0-9_\-]{8,}',
    r'(?:gsk|sk_live|sk_test|rk_live|npm)_[A-Za-z0-9]{16,}',
    r'gh[pousr]_[A-Za-z0-9]{8,}', r'github_pat_[A-Za-z0-9_]{8,}', r'glpat-[A-Za-z0-9_\-]{12,}',
    r'(?:AKIA|ASIA)[0-9A-Z]{12,}', r'AIza[0-9A-Za-z_\-]{30,}', r'xox[abprs]-[A-Za-z0-9\-]{8,}',
    r'(?i:bearer)\s+[A-Za-z0-9._~+/=\-]{8,}',
    r'(?i:authorization\s*[:=]\s*basic)\s+[A-Za-z0-9+/=]{8,}',
    _EDGE + r'eyJ[A-Za-z0-9_\-]{4,}\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+',
    _PEM,
    r'(?<=://)[^\s/:@]+:[^\s/@]+(?=@)',
    r'(?:(?<!\S)|(?<=\\[nrt]))(?:-u|--user)[\s=]+[A-Za-z_][^\s:"\\]*:[^\s"\\]+',
    r'(?P<keep>(?i:aws_secret_access_key)' + _QUOTE + r'\s*[=:]\s*' + _QUOTE + r')[^\s"\'\\]+',
)
SECRET = re.compile('(' + '|'.join(_PARTS) + ')')


def redact(text):
    return SECRET.sub(lambda m: (m.group('keep') or '') + '[redacted]', text)


def pem_open(text, inside=False):
    """Whether *text*, a fragment of a stream that starts *inside* a private key
    or not, ends inside one."""
    for m in _PEM_MARK.finditer(text):
        inside = m.group(1) == 'BEGIN'
    return inside


def close_pem(text, inside):
    """(*text* with the tail of a key it starts inside of redacted, whether it ends
    inside one). A fragment with no END line is redacted whole."""
    if not inside:
        return text, pem_open(text)
    m = _PEM_END_AT.search(text)
    if m is None:
        return '[redacted]', True
    return '[redacted]' + text[m.end():], pem_open(text[m.end():])


def redact_json(obj):
    """*obj* (parsed JSON) with every string and key redacted. The structure
    cannot change: only strings are matched, never their JSON spelling. Iterative,
    so a deep document costs no stack."""
    root = [None]
    todo = [(obj, root, 0)]
    while todo:
        v, dst, k = todo.pop()
        if isinstance(v, str):
            dst[k] = redact(v)
        elif isinstance(v, list):
            dst[k] = new = [None] * len(v)
            todo.extend((x, new, i) for i, x in enumerate(v))
        elif isinstance(v, dict):
            dst[k] = new = {}
            names = [redact(k) if isinstance(k, str) else k for k in v]
            # two keys that redact to one name must stay two fields: when that happens, every
            # key that is or holds `[redacted` takes its position, so no name can repeat
            clash = len(set(names)) < len(names)
            for i, (key, x) in enumerate(v.items()):
                name = shown = names[i]
                if clash and isinstance(key, str) and (name != key or '[redacted' in key):
                    shown = '%s #%d' % (name, i)
                if isinstance(key, str) and isinstance(x, str):
                    # a secret named by its key (`aws_secret_access_key`, `Authorization: Basic`)
                    # is matched on the pair, as it reads in text
                    pair = redact('%s: %s' % (key, x))
                    new[shown] = pair[len(name) + 2:] if pair.startswith(name + ': ') else '[redacted]'
                else:
                    new[shown] = None
                    todo.append((x, new, shown))
        else:
            dst[k] = v
    return root[0]

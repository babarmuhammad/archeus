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
# oversized key in the text, so the scan fails closed instead. A key cut over
# several strings (stream lines, JSON values) is followed by scrub. Not caught by
# any pattern: a marker obfuscated on purpose (zero-width characters, Unicode
# hyphens, a `\u002d` spelled out), a key body that lost its marker, or a token or
# marker cut in two by the string boundary itself (`"sk-ABCD"`, `"EFGHIJKL"`): each
# string is scrubbed alone, so no piece of it is carried to the next.
_MARK = r'(?<!-)-{4,}(?i:(%s)\s+(?:[A-Z0-9]+\s+){0,4}PRIVATE\s+KEY)-*'
_PEM_END = _MARK % 'END'
_PEM_END_AT = re.compile(_PEM_END)
_PEM_MARK = re.compile(_MARK % 'BEGIN|END')
_PEM = _MARK % 'BEGIN' + r'[\s\S]*?(?:%s|\Z)' % _PEM_END
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
    r'(?i:authorization)' + _QUOTE + r'\s*[:=]\s*' + _QUOTE + r'(?i:basic)\s+[A-Za-z0-9+/=]{8,}',
    _EDGE + r'eyJ[A-Za-z0-9_\-]{4,}\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+',
    # a JWT glued to a word, or one with no signature: from the dot before its
    # payload, which is a JSON object too
    r'\.eyJ[A-Za-z0-9_\-]{4,}\.[A-Za-z0-9_\-]*',
    _PEM,
    r'(?<=://)[^\s/:@]+:[^\s/@]+(?=@)',
    r'(?<=://)[^\s/:@]{8,}(?=@)',
    r'(?:(?<!\S)|(?<=\\[nrt]))(?:-u|--user)[\s=]*' + _QUOTE + r'''[A-Za-z_][^\s:"'\\]*:[^\s"'\\]+''',
    r'(?P<keep>(?i:aws_secret_access_key)' + _QUOTE + r'\s*[=:]\s*' + _QUOTE + r')[^\s"\'\\]+',
)
SECRET = re.compile('(' + '|'.join(_PARTS) + ')')


def redact(text):
    return SECRET.sub(lambda m: (m.group('keep') or '') + '[redacted]', text)


# A key's lines may come as several strings: stream lines, or JSON values. The
# state between them is the channel the open key began in (`stderr` for plain
# stream lines, `json` for JSON strings), or None. In its own stderr channel a key
# runs to its END line whatever the lines say. Anywhere else a string is masked
# while it looks like key material (a line ending in 16 base64 characters, or a
# string of nothing but base64 lines however short: the last line of a key);
# prose (three words, not a `Name: value` header) ends a key of the json channel
# and is let through in the other one. An END in the other channel leaves the key
# open: a mention there is not where the key was printed. A field name is masked
# by the first rule only: a short one is a word of the event's own structure.
_BODY = re.compile(r'[A-Za-z0-9+/=]{16}[ \t\r]*$', re.M)
_LINE = re.compile(r'[A-Za-z0-9+/=]+')
_PROSE = re.compile(r'^(?![ \t]*[A-Za-z][A-Za-z0-9-]*:)[ \t]*\S+[ \t]+\S+[ \t]+\S', re.M)


def last_mark(text):
    """'BEGIN', 'END' or None: the last key marker in *text*."""
    last = None
    for last in _PEM_MARK.finditer(text):
        pass
    return last and last.group(1).upper()


def _short(text):
    lines = [x.strip() for x in text.splitlines() if x.strip()]
    return bool(lines) and all(_LINE.fullmatch(x) for x in lines)


def after(state, channel, mark, text=None):
    """The state after a string of *channel* whose last marker is *mark*. *text*
    is the string, when a marker-less one may end a json key."""
    if mark == 'BEGIN':
        return channel
    if mark == 'END':
        return None if state in (None, channel) else state
    if state is None or state == channel == 'stderr' or text is None or _BODY.search(text):
        return state
    return None if state == channel and _PROSE.search(text) else state


def scrub(text, state=None, channel='json', plain=None, name=False):
    """(*text* redacted, the state after it), *state* being the one before it.
    *plain* is the text's own redaction, used when no open key masks it; *name*
    marks a field name."""
    plain = redact(text) if plain is None else plain
    if state is not None:
        m = _PEM_END_AT.search(text)
        if m is not None:
            plain = '[redacted]' + redact(text[m.end():])
        elif state == channel == 'stderr' or _BODY.search(text) or not name and _short(text):
            plain = '[redacted]'
    return plain, after(state, channel, last_mark(text), text)


_CONTAINERS = (list, tuple, set, frozenset, dict)
_KEY = object()


def _name(k, state):
    if isinstance(k, str):
        return scrub(k, state, 'json', name=True)
    return (k if k is None or isinstance(k, (int, float)) else redact(str(k))), state


def scrub_json(obj, state=None, max_depth=None):
    """(*obj* with every string and key redacted, the state after it): its strings
    and field names are one json channel, taken in document order from *state*. Only
    strings are matched, never their JSON spelling, so the structure cannot change;
    a tuple or a set comes back a list, bytes a string. Iterative, so a deep document
    costs no stack, and a container met twice (shared, or a cycle) is walked once. A
    level deeper than *max_depth* is a RecursionError."""
    root = [None]
    todo = [(obj, root, 0, None, 0)]
    seen, dicts = {}, []
    while todo:
        v, dst, k, key, depth = todo.pop()
        if max_depth is not None and depth > max_depth:
            raise RecursionError('nested over %d levels' % max_depth)
        if key is _KEY:
            dst[k], state = _name(v, state)
            continue
        if isinstance(v, (bytes, bytearray)):
            v = v.decode('utf-8', errors='replace')
        if isinstance(v, str):
            plain = None
            if isinstance(key, str):
                # a secret named by its key (`aws_secret_access_key`, `Authorization: Basic`)
                # is matched on the pair, as it reads in text
                name = redact(key)
                pair = redact('%s: %s' % (key, v))
                plain = pair[len(name) + 2:] if pair.startswith(name + ': ') else '[redacted]'
            dst[k], state = scrub(v, state, 'json', plain)
        elif isinstance(v, _CONTAINERS) and id(v) in seen:
            dst[k] = seen[id(v)]
        elif isinstance(v, dict):
            dst[k] = seen[id(v)] = new = {}
            slots = [[None, None] for _ in v]
            dicts.append((new, slots, list(v)))
            entries = []
            for slot, (key, x) in zip(slots, v.items()):
                entries += [(key, slot, 0, _KEY, depth + 1), (x, slot, 1, key, depth + 1)]
            todo.extend(reversed(entries))
        elif isinstance(v, _CONTAINERS):
            items = list(v)
            dst[k] = seen[id(v)] = new = [None] * len(items)
            todo.extend((items[i], new, i, None, depth + 1) for i in reversed(range(len(items))))
        else:
            dst[k] = v
    for new, slots, keys in dicts:
        names = [name for name, _ in slots]
        # two keys that redact to one name must stay two fields: when that happens, every
        # key that is or holds `[redacted` takes its position, so no name can repeat
        clash = len(set(names)) < len(names)
        for i, (name, value) in enumerate(slots):
            if clash and isinstance(name, str) and (name != keys[i] or '[redacted' in name):
                name = '%s #%d' % (name, i)
            new[name] = value
    return root[0], state


def redact_json(obj):
    """*obj* with every string and key redacted, a key cut over its strings too."""
    return scrub_json(obj)[0]

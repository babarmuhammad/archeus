"""One matcher for the places an account home can be spelled (T-144 design §2).

A home is written many ways: another case, `C:/` for `C:\\`, MSYS `/c/`, a
`file:///` URL, a UNC or `\\\\?\\` long path, an 8.3 short name, doubled or
trailing separators. `Homes` holds one compiled pattern per home and
`scrub_text` replaces a contained home with `its home`, keeping the separator
and the rest of the path. A default account's key (`<harness>:<canonical
home>`) becomes a stable opaque public id. Both are idempotent.

Ceilings: dot-segment spellings inside free text (`C:\\a\\..\\.claude-work`),
symlink or junction aliases, and a home that has a space-containing sibling are
not matched in contained text. `norm_path` does handle dot segments in a whole
value.
"""

import hashlib
import hmac
import os
import posixpath
import re
import sys
from urllib.parse import quote, unquote

REPLACEMENT = 'its home'
_SEP = r'[\\/]+'
_LEFT = r'(?:(?<![\w/.~])|(?<=\\[ntr]))'
_RIGHT = r'(?![\w~-]|\.\w)'
_FILE = re.compile(r'file:(?://([^/]*))?(/.*)?$', re.I)
_LONG = re.compile(r'[\\/]{2}[?.][\\/](UNC[\\/])?', re.I)
_MSYS = re.compile(r'/(?:cygdrive/|mnt/)?([A-Za-z])(?:/|$)')
_DRIVE = re.compile(r'([A-Za-z]):[\\/]')


def _windows_style(p):
    return bool(_DRIVE.match(p) or re.match(r'[\\/]{2}', p))


def _canon(s, *, platform=None, path_flavour=None):
    """The case-kept canonical spelling of an absolute path, or None."""
    if not isinstance(s, str):
        return None
    s = s.strip()
    m = _FILE.match(s)
    if m:
        host, path = m.group(1) or '', unquote(m.group(2) or '')
        s = '//%s%s' % (host, path) if host and host.lower() != 'localhost' else path
        if re.match(r'/[A-Za-z]:', s):
            s = s[1:]
    m = _LONG.match(s)
    if m:
        s = ('//' if m.group(1) else '') + s[m.end():]
    if re.match(r'^[A-Za-z]:(?![\\/])', s):
        return None
    if _windows_style(s):
        s = s.replace('\\', '/')
    m = _MSYS.match(s)
    if m and (path_flavour in ('windows', 'msys', 'cygwin', 'wsl') or path_flavour is None and platform == 'win32'):
        s = '%s:/%s' % (m.group(1), s[m.end():])
    s = posixpath.normpath(s)
    if re.fullmatch(r'[A-Za-z]:', s):
        s += '/'
    return s if s.startswith('/') or _DRIVE.match(s) else None


def norm_path(s, *, platform=None, path_flavour=None):
    """The whole-value canonical form of an absolute path, None if it is not one."""
    p = _canon(s, platform=platform, path_flavour=path_flavour)
    return p.lower() if p and _windows_style(p) else p


def _win_short(path):
    if sys.platform != 'win32':
        return None
    import ctypes
    from ctypes import wintypes
    f = ctypes.WinDLL('kernel32').GetShortPathNameW
    f.argtypes, f.restype = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD], wintypes.DWORD
    buf = ctypes.create_unicode_buffer(32768)
    n = f(path.replace('/', '\\'), buf, 32768)
    return buf.value if 0 < n < 32768 else None


def _comp(c, short=None):
    forms = [c, quote(c), short]
    return '(?:%s)' % '|'.join(re.escape(f) for f in dict.fromkeys(forms) if f)


def _win(win, rx):
    return '(?i:%s)' % rx if win else rx


def public_account_id(key):
    from ..infra.discovery import public_account_secret
    return 'account:' + hmac.new(public_account_secret(), key.encode('utf-8'), hashlib.sha256).hexdigest()


def account_key_map(default_accounts):
    return {key: public_account_id(key) for _, key, home in default_accounts
            if '/' in key or '\\' in key}


class Homes:
    """`registered_homes`: home_ref strings as stored. `default_accounts`:
    current and historical (harness_id, key, home_ref), never probed.
    `shorts(path)` probes registered homes only; tests inject it.
    MSYS aliases require Windows-compatible platform or path_flavour metadata."""

    def __init__(self, registered_homes=(), default_accounts=(), shorts=None, *,
                 platform=None, path_flavour=None):
        self.platform, self.path_flavour = platform, path_flavour
        default_accounts = tuple(default_accounts)
        self._shorts = _win_short if shorts is None else shorts
        registered_homes = [h for h in registered_homes if isinstance(h, str) and h.strip()]
        default_homes = [a[2] for a in default_accounts if isinstance(a[2], str) and a[2].strip()]
        homes = registered_homes + default_homes
        sources = [(h, True) for h in registered_homes] + [(h, False) for h in default_homes]
        self.patterns = [re.compile(_LEFT + '(?:%s)' % '|'.join(alts) + _RIGHT)
                         for h, probe in sources
                         if (alts := self._alts(h, probe=probe))]
        self.norms = {n for h in homes for sp in _spellings(h)
                      if (n := self.norm_path(sp))}
        self.keys = account_key_map(default_accounts)
        self._key_rx = re.compile('(?<!\\w)(?:%s)%s' % ('|'.join(
            re.escape(k)
            for k in sorted(self.keys, key=len, reverse=True)), _RIGHT)
        ) if self.keys else None

    def norm_path(self, s):
        return norm_path(s, platform=self.platform, path_flavour=self.path_flavour)

    def _short(self, prefix):
        try:
            s = self._shorts(prefix)
        except Exception:
            return None
        return s.replace('\\', '/').rsplit('/', 1)[-1] if s else None

    def _alts(self, home, *, probe=True):
        out = []
        for sp in _spellings(home):
            c = _canon(sp, platform=self.platform, path_flavour=self.path_flavour)
            if c is None:
                if sp.startswith('~'):
                    parts = [p for p in re.split(r'[\\/]+', sp) if p]
                    if parts[0] == '~' and len(parts) > 1:
                        out.append(_win(os.name == 'nt', '~' + ''.join(_SEP + _comp(p) for p in parts[1:])))
                continue
            m = _DRIVE.match(c)
            unc = re.match(r'//([^/]+)/([^/]+)(?:/|$)', c)
            if m:
                head, rest, anchor = m.group(1), c[m.end():], c[:m.end()].rstrip('/')
                prefixes = ['%s:' % head, '/%s' % head, '/cygdrive/%s' % head, '/mnt/%s' % head,
                            r'[\\/]{2}[?.][\\/]%s:' % head, r'file:(?://localhost)?/{1,3}%s(?::|%%3A)' % head]
            elif unc:
                srv, shr = (re.escape(g) for g in unc.groups())
                rest, anchor, head = c[unc.end():], c[:unc.end()].rstrip('/'), None
                prefixes = [r'[\\/]{2}%s%s%s' % (srv, _SEP, shr), r'file:/{2}%s%s%s' % (srv, _SEP, shr),
                            r'[\\/]{2}[?.][\\/]UNC[\\/]%s%s%s' % (srv, _SEP, shr)]
            else:
                rest, anchor, head, prefixes = c[1:], '', None, ['']
            comps = [x for x in rest.split('/') if x]
            if not comps:
                sep = _SEP if m or unc else '/+'
                root = '(?:%s)' % '|'.join(prefixes) + '(?=%s)' % sep
                out.append(_win(bool(m or unc), root))
                continue
            win = m or unc
            parts, cur = [], anchor
            for x in comps:
                cur = cur + '/' + x
                parts.append(_comp(x, self._short(cur) if m and probe else None))
            sep = _SEP if win else '/+'
            out.append(_win(bool(win), '(?:%s)' % '|'.join(prefixes) + ''.join(sep + p for p in parts)))
        return list(dict.fromkeys(out))


def _spellings(home):
    home = home.strip()
    if re.match(r'^[A-Za-z]:(?![\\/])', home):
        return [home]
    out = [home, os.path.expanduser(home)]
    if _canon(out[1]) is None:
        out.append(os.path.abspath(out[1]))
    return list(dict.fromkeys(out))


def scrub_text(text, homes):
    if not isinstance(text, str) or not text:
        return text
    if homes._key_rx:
        text = homes._key_rx.sub(lambda m: homes.keys[m.group(0)], text)
    for p in homes.patterns:
        text = p.sub(REPLACEMENT, text)
    return text


def cut_safe(text, homes, n):
    """`text[:n]`, moved back to the start of any home or default key the cut would
    split: a cut home no longer matches, so its readable prefix would survive a
    later scrub. The text stays raw."""
    cut = n
    if len(text) > n:
        spans = [m.span() for p in (*homes.patterns, *([homes._key_rx] if homes._key_rx else ()))
                 for m in p.finditer(text)]
        while any(a < cut < b for a, b in spans):
            cut = min(a for a, b in spans if a < cut < b)
    return text[:cut]


def public_value(x, homes, *, text_keys=(), path_keys=(), _key=None, _text=False):
    """A projected copy: a default key (whole value) becomes its handle at any
    depth; a registered home's path under a `path_keys` key becomes None; strings
    under `text_keys` go through `scrub_text`. Every other string is untouched."""
    if isinstance(x, dict):
        return {k: public_value(v, homes, text_keys=text_keys, path_keys=path_keys,
                                _key=k, _text=_text or k in text_keys) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [public_value(v, homes, text_keys=text_keys, path_keys=path_keys, _key=_key,
                             _text=_text) for v in x]
    if not isinstance(x, str):
        return x
    handle = homes.keys.get(x.strip())
    if handle:
        return handle
    if _key in path_keys and homes.norm_path(x) in homes.norms:
        return None
    return scrub_text(x, homes) if _text else x

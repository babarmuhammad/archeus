"""What no event, checkpoint, brief or hand-off artifact may carry
(p11-design-gate §19; p12-design-gate D6): one pattern list, shared by every
writer of text that leaves a process."""

import re

from archeus.core.domain.ids import TOKEN_PREFIXES

# redact() also runs over json.dumps output, so no match may reach a `"` or a
# `\`: eating a closing quote, or the backslash of `\"`, breaks the JSON. Every
# pattern stays linear: a start is anchored or has a bounded prefix, and each
# repeat has one way to match. A PEM body is base64 plus the `\n` escapes a
# dumped newline leaves, and ends at its END line or at the first character that
# cannot belong to it.
_PEM_UNIT = r'(?:[A-Za-z0-9+/=:,.\s\-]|\\{1,2}[nrt])'
_PEM = (r'-----BEGIN [A-Z ]{0,32}PRIVATE KEY-----' + _PEM_UNIT + r'*?'
        r'(?:-----END [A-Z ]{0,32}PRIVATE KEY-----|(?!' + _PEM_UNIT + '))')

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
    r'(?<![A-Za-z0-9_\-])eyJ[A-Za-z0-9_\-]{4,}\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+',
    _PEM,
    r'(?<=://)[^\s/:@"\\]+:[^\s/@"\\]+(?=@)',
    r'(?<!\S)(?:-u|--user)[\s=]+[A-Za-z_][^\s:"\\]*:[^\s"\\]+',
    r'(?P<keep>(?i:aws_secret_access_key)["\']?\s*[=:]\s*["\']?)[^\s"\'\\]+',
)
SECRET = re.compile('(' + '|'.join(_PARTS) + ')')


def redact(text):
    return SECRET.sub(lambda m: (m.group('keep') or '') + '[redacted]', text)

"""What no event, checkpoint, brief or hand-off artifact may carry
(p11-design-gate §19; p12-design-gate D6): one pattern list, shared by every
writer of text that leaves a process."""

import re

from archeus.core.domain.ids import TOKEN_PREFIXES

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
    r'-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?(?:-----END [A-Z ]*PRIVATE KEY-----|\Z)',
    r'(?<=://)[^\s/:@]+:[^\s/@]+(?=@)',
    r'(?<!\S)(?:-u|--user)[\s=]+[A-Za-z_][^\s:]*:\S+',
    r'(?i:aws_secret_access_key)\s*[=:]\s*\S+',
)
SECRET = re.compile('(' + '|'.join(_PARTS) + ')')


def redact(text):
    return SECRET.sub('[redacted]', text)

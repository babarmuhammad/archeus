"""What no event, checkpoint, brief or hand-off artifact may carry
(p11-design-gate §19; p12-design-gate D6): one pattern list, shared by every
writer of text that leaves a process."""

import re

SECRET = re.compile(r'(hook_[A-Za-z0-9_\-]{8,}|dev_[A-Za-z0-9_\-]{8,}|node_[A-Za-z0-9_\-]{8,}'
                    r'|sk-[A-Za-z0-9_\-]{8,}|gh[pousr]_[A-Za-z0-9]{8,}|github_pat_[A-Za-z0-9_]{8,}'
                    r'|AKIA[0-9A-Z]{12,}|(?i:bearer)\s+[A-Za-z0-9._\-]{8,})')


def redact(text):
    return SECRET.sub('[redacted]', text)

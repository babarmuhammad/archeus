"""Content-addressed blobs: `<ARCHEUS_HOME>/artifacts/ab/cd/<sha256>` (domain-model §7.9).

The address IS the content's sha256, so a blob is immutable, writing the same
bytes twice stores them once, and a reader can verify what it got. A blob is
written under a temporary name and renamed into place, so a crash never leaves
a partial file at a real address. Files only: the `Artifact` row that describes
a blob (media type, producer, label) arrives with the first phase that records
one, in the same command as the event that produced it.
"""

import hashlib
import os
import re

from .. import paths

_SHA = re.compile(r'[0-9a-f]{64}')


def root(home=None):
    return os.path.join(paths.archeus_home() if home is None else home, 'artifacts')


def path_for(sha, home=None):
    if not (isinstance(sha, str) and _SHA.fullmatch(sha)):
        raise ValueError('not a sha256: %r' % (sha,))
    return os.path.join(root(home), sha[:2], sha[2:4], sha)


def put(data, home=None):
    """Store *data* (bytes); returns its sha256."""
    sha = hashlib.sha256(data).hexdigest()
    dest = path_for(sha, home)
    if not os.path.exists(dest):
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        tmp = '%s.%d.tmp' % (dest, os.getpid())
        with open(tmp, 'wb') as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, dest)
    return sha


def get(sha, home=None):
    """The bytes at *sha*, verified: a blob that no longer hashes to its
    address is reported, never returned."""
    with open(path_for(sha, home), 'rb') as f:
        data = f.read()
    if hashlib.sha256(data).hexdigest() != sha:
        raise ValueError('artifact %s is corrupt on disk' % sha)
    return data

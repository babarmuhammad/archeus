"""Identifiers: ULIDs, prefixed by kind (domain-model §1 rule 5).

A ULID is 48 bits of milliseconds + 80 bits of randomness in Crockford base32,
26 characters, so ids sort by creation time as plain strings — which is what
lets an id double as an ordering key before SQLite hands out `events.seq`.

`new_ulid()` is monotonic within the process: two ids minted in the same
millisecond differ by incrementing the random part, so they still sort in the
order they were made. Tests pin the output with `at_ms` + `entropy`.
"""

import secrets
import threading
import time

ALPHABET = '0123456789ABCDEFGHJKMNPQRSTVWXYZ'   # Crockford: no I, L, O, U
_MAX_RAND = (1 << 80) - 1
_MAX_MS = (1 << 48) - 1

#: kind -> prefix. The ONE list of id-bearing kinds: entities, and anything
#: else that is minted here. Entities whose identity is not a ULID (harness
#: `claude_code`, model `claude-opus-5-5`, artifact sha256, a bare event ULID)
#: are deliberately absent.
PREFIXES = {
    'user': 'usr', 'identity': 'idn', 'principal': 'prn', 'device': 'dvc',
    'workspace': 'ws', 'organization': 'org', 'person': 'per', 'project': 'prj',
    'repository': 'rep', 'repository_inspection': 'rin', 'system': 'sys',
    'idea': 'ida', 'meeting': 'mtg', 'decision': 'dec',
    'knowledge_item': 'kno', 'relation': 'rel',
    'conversation': 'cnv', 'message': 'msg', 'intent': 'int',
    'mission': 'msn', 'plan': 'pln', 'task': 'tsk', 'execution': 'exe',
    'session': 'ses', 'checkpoint': 'chk', 'verification': 'ver',
    'review': 'rev', 'feedback': 'fbk',
    'account': 'acc', 'resource_policy': 'rpo', 'usage_snapshot': 'usn',
    'usage_ledger': 'ulg', 'route_decision': 'rte', 'execution_node': 'nod',
    'policy_rule': 'pol', 'policy_decision': 'pdc', 'approval': 'apr',
    'automation': 'aut', 'automation_run': 'arn',
    'context_package': 'ctx',
}
assert len(set(PREFIXES.values())) == len(PREFIXES), 'two kinds share a prefix'

#: Credential kind -> token prefix (api-and-realtime §5.3). A token is a SECRET,
#: never an id, so its prefixes are a namespace of their own and may not reuse an
#: id prefix: `exe_…` is always an Execution id, and the execution-scoped
#: credential is the hook token (`hook_…`, delivered as ARCHEUS_HOOK_TOKEN).
#: Minting and verifying tokens arrives with P2/P3.5; the namespace is fixed now.
TOKEN_PREFIXES = {'device': 'dev', 'node': 'node', 'execution': 'hook'}
assert not set(TOKEN_PREFIXES.values()) & set(PREFIXES.values()), \
    'a token prefix collides with an id prefix'

#: The reserved workspace for global rows (domain-model §1 rule 8).
GLOBAL_WORKSPACE = 'ws_global'

_lock = threading.Lock()
_last = [0, 0]          # [ms, rand] of the previous new_ulid()


def encode(ms, rand):
    """The 26-character ULID for a millisecond timestamp and 80 random bits."""
    if not (0 <= ms <= _MAX_MS and 0 <= rand <= _MAX_RAND):
        raise ValueError('ULID component out of range')
    n = (ms << 80) | rand
    return ''.join(ALPHABET[(n >> (5 * i)) & 31] for i in range(25, -1, -1))


def new_ulid(*, at_ms=None, entropy=None):
    """A fresh ULID. `at_ms`/`entropy` pin it (tests); otherwise it is the
    current time and `secrets` randomness, monotonic within this process."""
    if at_ms is not None or entropy is not None:
        ms = int(time.time() * 1000) if at_ms is None else at_ms
        rand = secrets.randbits(80) if entropy is None else entropy
        return encode(ms, rand)
    with _lock:
        ms = int(time.time() * 1000)
        if ms <= _last[0]:
            # same (or a stepped-back) millisecond: stay ahead of the last id
            ms, rand = _last[0], _last[1] + 1
            if rand > _MAX_RAND:
                ms, rand = ms + 1, secrets.randbits(79)
        else:
            rand = secrets.randbits(80)
        _last[:] = [ms, rand]
    return encode(ms, rand)


def is_ulid(value):
    return (isinstance(value, str) and len(value) == 26
            and value[0] in '01234567'      # 48-bit time: first char <= 7
            and all(c in ALPHABET for c in value))


def ulid_ms(value):
    """The millisecond timestamp a ULID carries."""
    if not is_ulid(value):
        raise ValueError('not a ULID: %r' % (value,))
    n = 0
    for c in value:
        n = n * 32 + ALPHABET.index(c)
    return n >> 80


def new_id(kind, **pin):
    """`<prefix>_<ULID>` for an entity kind, e.g. new_id('mission') -> 'msn_01J…'."""
    return '%s_%s' % (PREFIXES[kind], new_ulid(**pin))


def is_id(value, kind):
    """True when *value* is a well-formed id of *kind*. The reserved
    `ws_global` counts as a workspace id."""
    if kind == 'workspace' and value == GLOBAL_WORKSPACE:
        return True
    prefix = PREFIXES[kind] + '_'
    return (isinstance(value, str) and value.startswith(prefix)
            and is_ulid(value[len(prefix):]))


def token_kind(value):
    """The credential kind a token's prefix names (`hook_…` -> 'execution'), or
    None. Never true of an id: the two namespaces share no prefix."""
    head, sep, tail = str(value).partition('_')
    if not (sep and tail):
        return None
    for kind, prefix in TOKEN_PREFIXES.items():
        if prefix == head:
            return kind
    return None


def kind_of(value):
    """The kind an id belongs to, or None."""
    if value == GLOBAL_WORKSPACE:
        return 'workspace'
    head, _, tail = str(value).partition('_')
    for kind, prefix in PREFIXES.items():
        if prefix == head and is_ulid(tail):
            return kind
    return None

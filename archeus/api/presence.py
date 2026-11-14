"""Presence (p15-design-gate §5, D4): what THIS Core process observes about a
client's connectivity, now — and nothing else.

    connected   at least one open event stream
    recent      no stream, an authenticated request within RECENT_S
    absent      neither, since this Core process started
    revoked     the client can no longer authenticate

Held in memory (the stream pool and `Api.seen`), so a Core restart makes every
client `absent` until it reconnects, which is true. It claims nothing about a
person ("available", "active" are not modelled, D6), and nothing in
`archeus/core` reads it: a client's presence cancels, pauses or decides nothing.
"""

import time

RECENT_S = 60.0


def of(api, device):
    """The presence of one `queries.devices` row."""
    seen = api.seen.get(device['id'])
    last = seen[1] if seen else None
    if device['state'] == 'REVOKED':
        return {'state': 'revoked', 'connections': 0, 'last_seen_at': last}
    conns = api.sse.connections(device['id'])
    if conns:
        state = 'connected'
    elif seen and time.monotonic() - seen[0] < RECENT_S:
        state = 'recent'
    else:
        state = 'absent'
    return {'state': state, 'connections': len(conns), 'last_seen_at': last}

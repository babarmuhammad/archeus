"""The T-1076 mutation suite: break each rule of the hidden-tab notification
(clients/app/src/state/notify.ts), run the test that guards it, and require it to fail.

    py tools/mutate_t1076.py              every mutation
    py tools/mutate_t1076.py W01 W04      only these

The runner is tools/mutate_p18.py's (tools/mutate_p11.py's snippet engine): each
mutation replaces exact snippets (each must occur once), runs its tests, and
restores the files whatever happens; a mutation the tests do not catch
("survived") fails the run. It edits sources: run it with nothing else running
against the tree.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mutate_p18  # noqa: E402  (its runner)

N = 'clients/app/src/state/notify.ts'
T = 'node:test/notify.test.ts'

MUTATIONS = [
    ('W01', 'the first read notifies', [(N,
     "    const baseline = this.seen === undefined;\n",
     "    const baseline = false;\n")], [T]),
    ('W02', 'an item is not remembered, so it notifies every read', [(N,
     "      seen.add(n.key);\n", "")], [T]),
    ('W03', 'a visible tab notifies', [(N,
     " || !this.host.hidden()) return;", ") return;")], [T]),
    ('W04', 'the setting is ignored', [(N,
     "baseline || !this.host.enabled() || ", "baseline || ")], [T]),
    ('W05', 'every kind of item notifies', [(N,
     "NOTIFY_KINDS.includes(i.kind) ? noteOf(i) : null", "noteOf(i)")], [T]),
    ('W06', 'the same read counts again', [(N,
     "seq <= this.at", "seq < this.at")], [T]),
    ('W07', 'an id is shown in the body', [(N,
     "p.kind.replace(/_/g, ' ')", "p.id")], [T]),
    ('W08', 'the body has no length cap', [(N,
     "    body: text.length > BODY_MAX ? `${text.slice(0, BODY_MAX - 1)}…` : text,\n",
     "    body: text,\n")], [T]),
    ('W09', 'the browser\'s grant is not required', [(N,
     "wanted && permission === 'granted'", "wanted && permission !== 'denied'")], [T]),
    ('W10', 'the setting is on until switched off', [(N,
     "s?.getItem(NOTIFY_KEY) === 'on'", "s?.getItem(NOTIFY_KEY) !== 'off'")], [T]),
    ('W11', 'a blocked browser reads as off, offering a prompt it cannot show', [(N,
     "permission === 'denied' ? 'blocked' : ", "")], [T]),
]


if __name__ == '__main__':
    mutate_p18.MUTATIONS = MUTATIONS
    sys.exit(mutate_p18.run(sys.argv[1:]))

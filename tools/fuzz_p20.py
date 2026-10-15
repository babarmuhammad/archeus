"""P20 D12: a stdlib fuzz harness for the command routes and the canonicaliser.

    py tools/fuzz_p20.py                     seed 0, budget 2000 per target
    py tools/fuzz_p20.py --seed 7 --budget 50000

Two targets, one property: nothing answers 500 or raises.

- Every command route (each route with a request schema) gets bodies built from
  its own schema and then mutated: a field's type swapped, a required field
  dropped, an unknown field added, a string made huge or full of control
  characters, a number pushed out of range, a value nested deep. The recorded
  junk bodies of the endpoint floor (tests/v1/integration/test_api_errors.py)
  are the corpus' other half, and RECORDED holds valid bodies for the routes
  whose schema types a field as a bare object, so mutation reaches its values.
  Each request runs through the real route table
  and the real `server.Handler._serve`, in process: no socket per request, so
  a large budget does not exhaust Windows' ephemeral ports (p11-design-gate
  D31). The peer is attested as the user because attestation is not what is
  fuzzed here; it is tested where it is built (T-057).
- `canonicalise()` over every tool ADR-0052's mapping names (plus Skill, the
  aliases and unknown names), with mutated inputs. For an input it cannot
  parse it must answer the conservative class: one unclassified `exec`. That
  holds for every parsed tool: a path tool with its path missing (Glob and
  Grep may omit theirs), empty or not a string, a fetch whose URL has no host,
  a command that is not a string shlex can split.

Run on demand it builds its own Core in a temporary ARCHEUS_HOME on the fake
harness; tests/v1/integration/test_p20_fuzz.py runs both targets in CI with a
fixed seed and a small budget.
"""
import argparse
import io
import json
import os
import random
import shlex
import shutil
import socket
import sys
import tempfile
from types import SimpleNamespace

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from archeus.api import auth, routes, schemas, server  # noqa: E402
from archeus.core.execution import canonical  # noqa: E402
from archeus.harnesses.claude_code import tools as cc_tools  # noqa: E402

JUNK = [b'', b'{}', b'[]', b'null', b'{"idempotency_key": null}', b'\x00\x01', b'{"a":',
        json.dumps({'idempotency_key': 'k', 'title': ['x'], 'objective': {'o': 1}}).encode(),
        json.dumps({'idempotency_key': 'k', 'code': 5, 'platform': 'web'}).encode(),
        json.dumps({'idempotency_key': 'k' * 5000}).encode()]
WEIRD = ['', ' ', 'x' * 70000, '\x00', '\u202e\u200b', '../../etc', 'C:\\Windows', '%s%n',
         '{"a": 1}', 'null', '😀' * 50, 'msn_' + 'A' * 26, '\ud800'.encode('utf-8', 'surrogatepass')
         .decode('utf-8', 'replace')]
NUMBERS = [0, -1, 2 ** 63, -2 ** 63, 10 ** 400, 1.5, float('1e308'), True]
#: valid bodies, as the integration tests send them, for the routes whose schema
#: types a field as a bare object: example() can only fill such a field with {},
#: so without a real body to corrupt, mutation never reaches a value inside it
RECORDED = {
    '/v1/plans/{id}/edit': {'tasks': [{
        'key': 't1', 'title': 'Fix it', 'kind': 'research', 'objective': 'Do: fix it',
        'action_classes': ['read'], 'refs': [{'kind': 'note', 'id': 'n1'}],
        'inputs': [{'what': 'the log', 'from_task': 't0'}],
        'acceptance': [{'text': 'tests pass', 'check': 'automatic'}]}]},
    '/v1/projects/{id}/constraints': {'statement': 's', 'kind': 'forbid_dependency',
                                      'spec': {'from': 'a/**', 'to': 'b/**'}},
    '/v1/knowledge/forget': {'selector': {'ids': ['kn_x'], 'type': 'lesson'}},
    '/v1/resource-policies/{id}': {'priority': 2, 'fallback': 'allow',
                                   'budgets': {'tokens_per_day': 1000}},
    '/v1/policies/rules': {'scope_level': 'USER', 'action_class': 'deploy',
                           'decision': 'ALLOW_WITHIN_BOUNDARY',
                           'match': {'environment': 'dev'}, 'boundary': {'paths': ['src/**']}},
    '/v1/policies/simulate': {
        'action': {'class': 'git_push', 'target': 'origin', 'branch': 'main',
                   'host': 'github.com'},
        # ws_global is the simulation mission's own workspace: that rule is on the
        # chain, so a corrupted value inside it reaches the engine
        'extra_rules': [{'scope_level': 'WORKSPACE', 'scope_ref': 'ws_global',
                         'action_class': 'git_push', 'decision': 'ALLOW',
                         'match': {'branch_glob': 'main'}, 'expires_at': '2099-01-01T00:00:00Z'},
                        {'scope_level': 'USER', 'action_class': 'read', 'decision': 'ASK'}]},
    '/v1/automations': {'name': 'follow up',
                        'trigger': {'type': 'mission.created', 'where': {'title': 'seed'}},
                        'template': {'title': 'follow up {subject.id}', 'objective': 'look at it'}},
}


def example(rnd, schema, depth=0):
    """A value of *schema*'s shape (shapes.validate's subset)."""
    if 'ref' in schema:
        schema = dict(schemas.TYPES[schema['ref']], nullable=schema.get('nullable'))
    if schema.get('nullable') and rnd.random() < 0.1:
        return None
    if 'enum' in schema:
        return rnd.choice(schema['enum'])
    t = schema.get('type')
    if t == 'object':
        props = schema.get('properties', {})
        need = set(schema.get('required', ()))
        return {k: example(rnd, v, depth + 1) for k, v in props.items()
                if k in need or (depth < 4 and rnd.random() < 0.5)}
    if t == 'array':
        return [example(rnd, schema['items'], depth + 1)
                for _ in range(0 if depth > 4 else rnd.randint(0, 3))]
    if t == 'string':
        return rnd.choice(['k%d' % rnd.randint(0, 9), 'Fix the flaky test', 'msn_x',
                           'a' * rnd.randint(1, 40)])
    if t == 'integer':
        return rnd.randint(-2, 100)
    if t == 'number':
        return rnd.uniform(-1, 100)
    if t == 'boolean':
        return rnd.random() < 0.5
    return {}


def mutate(rnd, value, depth=0):
    """*value* with one structural change somewhere inside it."""
    if isinstance(value, dict) and value and rnd.random() < 0.7:
        k = rnd.choice(sorted(value))
        out = dict(value)
        op = rnd.randrange(4)
        if op == 0:
            del out[k]
        elif op == 1:
            out['zz_' + rnd.choice(WEIRD)[:20]] = rnd.choice(NUMBERS + WEIRD)
        else:
            out[k] = mutate(rnd, out[k], depth + 1)
        return out
    if isinstance(value, list) and value and rnd.random() < 0.7:
        out = list(value)
        i = rnd.randrange(len(out))
        out[i] = mutate(rnd, out[i], depth + 1)
        return out
    return rnd.choice([None, [], {}, [value] * 3, {'x': value}, rnd.choice(NUMBERS),
                       rnd.choice(WEIRD), nest(rnd.randint(50, 400))])


def poke(rnd, value):
    """Replace one leaf of *value*, chosen uniformly at any depth, in place: what
    reaches a value inside a recorded body that mutate() mostly walks past."""
    slots = []

    def walk(v):
        for k in (sorted(v) if isinstance(v, dict) else range(len(v))
                  if isinstance(v, list) else ()):
            if isinstance(v[k], (dict, list)) and v[k]:
                walk(v[k])
            else:
                slots.append((v, k))
    walk(value)
    if slots:
        parent, k = rnd.choice(slots)
        parent[k] = rnd.choice(NUMBERS + WEIRD + [None, [], {}, ['x'], {'x': 1}])


def nest(n):
    v = 1
    for _ in range(n):
        v = {'a': [v]}
    return v


def body(rnd, route):
    if rnd.random() < 0.1:
        return rnd.choice(JUNK)
    recorded = RECORDED.get(route.path)
    if recorded and rnd.random() < 0.85:
        # only leaf pokes: a structural mutation mostly breaks the body before
        # the value it carries is ever read
        b = json.loads(json.dumps(recorded))
        for _ in range(rnd.choice([1, 1, 2])):
            poke(rnd, b)
    else:
        b = example(rnd, route.request_schema)
        for _ in range(rnd.choice([0, 1, 1, 2, 3])):
            b = mutate(rnd, b)
    if isinstance(b, dict) and route.idempotent == 'required' and rnd.random() < 0.9:
        b['idempotency_key'] = 'fz%d' % rnd.getrandbits(40)
    try:
        return json.dumps(b, allow_nan=False).encode('utf-8', 'surrogatepass')
    except (ValueError, OverflowError):
        return json.dumps(b, allow_nan=True).encode('utf-8', 'surrogatepass')


class _Request(server.Handler):
    """One request through the real `_serve`, without a socket."""

    def __init__(self, api, method, path, raw, token):
        self.server = SimpleNamespace(api=api)
        self.command, self.path, self.request_version = method, path, 'HTTP/1.1'
        self.requestline, self.close_connection = '%s %s HTTP/1.1' % (method, path), True
        self.headers = {'Host': api.origin.host, 'Content-Length': str(len(raw)),
                        'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'}
        self.rfile, self.wfile = io.BytesIO(raw), io.BytesIO()
        self.client_address = ('127.0.0.1', 0)
        self._serve()


def fill(rnd, path, ids):
    while '{id}' in path:
        path = path.replace('{id}', rnd.choice(ids), 1)
    return path


def fuzz_routes(api, token, seed, budget):
    """Failures as (method, path, raw, status); [] when the property holds."""
    rnd = random.Random(seed)
    api.attestor = lambda peer: auth.USER
    commands = [r for r in routes.ROUTES if r.request_schema is not None]
    made = _Request(api, 'POST', '/v1/missions', json.dumps(
        {'title': 'fuzz', 'objective': 'o', 'idempotency_key': 'fz-seed'}).encode(), token)
    real = json.loads(made.wfile.getvalue().split(b'\r\n\r\n', 1)[1])['id']
    ids = [real, 'x', 'msn_', '..', 'msn_' + 'A' * 300, '%E2%98%83']
    failures = []
    for i in range(budget):
        route = commands[i % len(commands)] if i < len(commands) else rnd.choice(commands)
        path, raw = fill(rnd, route.path, ids), body(rnd, route)
        try:
            status = _Request(api, route.method, path, raw, token)._status
        except Exception as e:                      # _serve answers every exception
            failures.append((route.method, path, raw[:200], repr(e)))
            continue
        # 503 is Core saying busy or stopping, which the fuzz itself can cause
        if status is None or (status >= 500 and status != 503):
            failures.append((route.method, path, raw[:200], status))
    return failures


CTX = {'workdir': os.getcwd(), 'branch': 'archeus/m/t', 'remotes': {'origin': 'github.com'}}
PARSED = set(canonical.READ_TOOLS + canonical.WRITE_TOOLS) | {'WebFetch', 'WebSearch', 'Bash'}


def tool_names():
    names = {t for ts in cc_tools.TOOLS.values() for t in ts}
    return sorted(names | {cc_tools.SKILL} | set(cc_tools.ALIASES) | {'Unknown', '', 'bash'})


def tool_input(rnd, tool):
    base = {'command': rnd.choice(['git status', 'ls -la', 'npm install x', 'echo "a;b"',
                                   "cat 'unterminated", 'git push --force origin main',
                                   'python -c "print(1)"', 'a=1 ls', '']),
            'file_path': rnd.choice(['src/a.py', '../../x', '~/.ssh/id', 'C:\\x', '']),
            'url': rnd.choice(['https://example.com', 'http://[::1', '', 'example.com/a'])}
    v = mutate(rnd, base) if rnd.random() < 0.6 else base
    return v if rnd.random() < 0.9 else rnd.choice([None, 'git status', 42, [], ['ls']])


def fuzz_canonical(seed, budget):
    """Failures as (tool, input, why); [] when the property holds."""
    rnd = random.Random(seed)
    names, failures = tool_names(), []
    for i in range(budget):
        tool = names[i % len(names)] if i < len(names) else rnd.choice(names)
        inp = tool_input(rnd, tool)
        try:
            actions, unclassified = canonical.canonicalise(tool, inp, CTX)
        except Exception as e:
            failures.append((tool, inp, repr(e)))
            continue
        why = conservative(tool, inp, actions, unclassified)
        if why:
            failures.append((tool, inp, why))
    return failures


def conservative(tool, inp, actions, unclassified):
    """Why the answer is less strict than the conservative one, or None."""
    if not actions:
        return 'no action'
    if unclassified and [a.action_class for a in actions] != ['exec']:
        return 'unclassified but not one exec action'
    if tool not in PARSED and not unclassified:
        return 'a tool it does not parse was classified'
    if not unclassified and not parseable(tool, inp if isinstance(inp, dict) else
                                          {'command': inp}):
        return 'an input it cannot parse was classified'
    return None


def parseable(tool, inp):
    """Whether *inp* carries what *tool* needs, judged without the canonicaliser:
    a non-empty string path (Glob and Grep may omit theirs), a URL with a host,
    a command shlex can split."""
    def text(v):
        return isinstance(v, str) and bool(v)
    if tool in canonical.READ_TOOLS or tool in canonical.WRITE_TOOLS:
        given = [inp[k] for k in canonical.PATH_FIELDS if k in inp]
        return text(given[0]) if given else tool in ('Glob', 'Grep')
    if tool == 'WebFetch':
        url = inp.get('url')
        return text(url) and canonical.host_of(url) is not None
    if tool == 'Bash':
        cmd = inp.get('command')
        try:
            return text(cmd) and bool(shlex.split(cmd, posix=True))
        except ValueError:
            return False
    return True


def free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--seed', type=int, default=0)
    ap.add_argument('--budget', type=int, default=2000)
    args = ap.parse_args(argv)
    home = tempfile.mkdtemp(prefix='fuzz-p20-')
    os.environ['ARCHEUS_HOME'] = home
    from archeus.core import engine, ports, runtime
    from archeus.harnesses.fake import FakeHarness
    core = runtime.Core(port=free_port(), ports=runtime.Ports(
        brain=ports.FixedPlanBrain(engine.SKELETON_PLAN), executors=[FakeHarness()],
        verifier=ports.ScriptedVerifier(), reviewer=ports.ScriptedReview())).start()
    try:
        bad = fuzz_routes(core.api, core.local['token'], args.seed, args.budget)
    finally:
        core.stop(drain=False)
        shutil.rmtree(home, ignore_errors=True)
    bad += fuzz_canonical(args.seed, args.budget)
    for f in bad[:50]:
        print('FAIL', f)
    print('%d failures (seed %d, budget %d per target)' % (len(bad), args.seed, args.budget))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())

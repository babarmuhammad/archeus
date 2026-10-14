// A paired client's privileged refusal on the loopback Host (T-053 Q4-A) is
// not the local-only one: it names the remote connection it needs.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { explain } from '../src/data/commands.ts';

const LOCAL_ONLY = 'Only from the computer running Archeus.';

test('a paired client refused on the loopback Host is told it needs its remote connection', () => {
  const why = { why: 'a paired client does this through its remote host' };
  const text = explain({ status: 403, code: 'remote_host_required', detail: why });
  assert.equal(text, 'Only through the configured remote connection to Archeus.');
  assert.notEqual(text, LOCAL_ONLY);
});

test('a local-only refusal keeps its meaning', () => {
  assert.equal(explain({ status: 403, code: 'host_not_allowed', detail: {} }), LOCAL_ONLY);
});

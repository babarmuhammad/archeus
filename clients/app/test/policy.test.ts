// The Resources form's draft (rulebook §43; D-7): its own problems are said
// before anything is sent; only filled budgets are set, a blank one removed.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { draftBudgets, policyProblem, type PolicyDraft } from '../src/state/policy.ts';

const ok: PolicyDraft = { priority: '1', allocation_pct: '80', reserve_pct: '10', brain_reserve_pct: '5', tokens_per_day: '', cost_per_day: '', concurrency: '2' };

test('a sound draft has no problem', () => {
  assert.equal(policyProblem(ok), null);
  assert.equal(policyProblem({ ...ok, priority: '-3' }), null);
});

test('each problem is said in words before anything is sent', () => {
  assert.equal(policyProblem({ ...ok, priority: '1.5' }), 'The priority is a whole number.');
  assert.equal(policyProblem({ ...ok, allocation_pct: '120' }), 'The allocation ceiling is at most 100%.');
  assert.equal(policyProblem({ ...ok, reserve_pct: '-1' }), 'A share is a whole number from 0 to 100.');
  assert.equal(policyProblem({ ...ok, reserve_pct: '50', brain_reserve_pct: '40' }), 'The two reserves together cannot exceed the allocation ceiling.');
  assert.equal(policyProblem({ ...ok, concurrency: '-2' }), 'A budget is a number of 0 or more, or blank for none.');
});

test('only filled budgets are set; a blank one is removed', () => {
  assert.deepEqual(draftBudgets(ok), { concurrency: 2 });
  assert.deepEqual(draftBudgets({ ...ok, concurrency: ' ' }), {});
  assert.deepEqual(draftBudgets({ ...ok, cost_per_day: '0' }), { cost_per_day: 0, concurrency: 2 });
});

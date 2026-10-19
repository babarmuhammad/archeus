# T-021 · One early isolation decision for A1 and A2

Prepared by Claude, 2026-10-12. Planning only: no code, no test run, no OS call, no design ruling.

Sources, all read in worktree `D:\archeus-pv20-s2-l`, branch `pv20-s2`, HEAD `8997446`:
- `archeus/core/execution/manager.py`: `_spawn` 175-275, `_resume` 574-585, `_isolation_record` 701-707, the other node probes at 759 and 775;
- `archeus/node/local.py`: `LocalNode.__init__` 45, `spawn` 49-80, `_isolate` 81;
- `archeus/node/isolation.py`: `production_dispatch_enabled` 79-83, `is_test_harness` 353-357, `Isolation.requested` 552-563, `record` 567-595, `request_for` 639-647, `establish` 667-692, the `SpawnFailed` conversion 1169-1170;
- `archeus/harnesses/claude_code/adapter.py` 147 and `archeus/harnesses/fake.py` 78 (`inventory(self, spec)`);
- the T-016 note §2 and §4 W0; the T-017 note §2 C2 and C4; `reviews/T-016-analysis.md` finding 2; `reviews/T-017-analysis.md` finding 2.

This note replaces T-016's W0 and the decision half of T-017's C2. Both notes say so in their dated corrections. The other half of C2 (what an isolated inventory excludes) stays with T-017 and consumes the decision defined here.

## 1. The problem, in one trace

Today, inside `_spawn` (manager.py), in order:

| # | Step | Line | Knows whether the execution is isolated? |
|---|---|---|---|
| 1 | adapter, provider terms, task, account | 176-186 | no |
| 2 | `self._workspace(e, m, t)` chooses workdir and branch | 188 | **no** |
| 3 | spec built, including `hook_settings=(sys.executable, HOOK)` | 208-217 (213) | **no** |
| 4 | `adapter.inventory(spec)` taken and stored | 224-235 (226) | **no** |
| 5 | `X.prepare_process` records workdir, branch, inventory digest | 236-240 | no |
| 6 | e-stop check, stream offset | 241-248 | no |
| 7 | `self.node.spawn(adapter, spec, resume_state=...)` | 255 | decided **inside** it: `isolated is None` → `self.isolation.requested(...)` (local.py 59-60), then `_isolate` → `request_for` → `default_plan(spec)` (local.py 61-62, isolation.py 639-647) |

Steps 2, 3 and 4 produce things an isolated execution must get differently: the workspace (A1, T-016 W2/W3), the hook interpreter and script (staged copies, T-017 C4, which edits line 213), and the inventory (A2 exclusions, T-017 C2). None of them can, because the decision is taken at step 7. `_resume` (574-585) goes through the same `_spawn`, so resume has the same order.

`requested` itself is already the single authority, and it is read in one place today (local.py 60). The defect is **when** it is read, not **how**.

## 2. The decision, as it exists (reused, not replaced)

`Isolation.requested(execution_id, adapter)` (isolation.py 552-563):
- an execution with a record is isolated, always (R7: resumes keep their identity);
- otherwise isolated only if Core's `authorize` callback says so, and never for a non-test harness while `production_dispatch_enabled()` is False (`PRODUCTION_DISPATCH_ENABLED = False`, isolation.py 79);
- `LocalNode` builds its `Isolation` with no `authorize` (local.py 45), so no production execution is isolated today.

It already fails closed on an unreadable record: `record()` turns a record that exists but cannot be read or trusted into state `invalid` (isolation.py 579-588), `requested` then answers True, and `establish` refuses an `invalid` prior record with `record_unsettled` before any write (isolation.py 684-691), which reaches the manager as `base.SpawnFailed` (isolation.py 1169-1170) and a `binding` refusal (manager.py 256-266). So "unreadable" never becomes "unisolated" on that path.

What is **not** fail-closed today: an exception raised by `requested` itself (an `authorize` callback that raises, a malformed id) is not a `SpawnFailed`. It escapes `node.spawn` at manager.py 255 after `prepare_process` has already recorded the workdir and process sequence (236-240). What the pass then does with it is not traced here.

No input decides isolation today: not `spec.env`, opt-ins, `task_contract`, a setting or a file in the execution's directory. `is_test_harness` reads the registered adapter's `id` and `test_harness` attribute (isolation.py 353-357), which are Core's registry objects, not execution input. The slice must keep it that way.

## 3. Proposed slice D1

One change, in two files.

1. **`manager._spawn`**, immediately after the provider-terms refusal (after 186) and before `_workspace` (188):
   - `iso = getattr(self.node, 'isolation', None)`; `isolated = bool(iso is not None and iso.requested(e.id, adapter))`.
   - Any exception from that line: `X.refuse(stop_reason='binding', reason='the isolation decision could not be taken: <type>')`, return. Nothing is chosen, inventoried, recorded or started. `binding` is the existing refusal for an isolation failure (manager.py 256-266); whether a persistent one should be charged instead is §6 Q1.
   - Pass `isolated=isolated` to `self.node.spawn` at 255.
   - The value is a local of `_spawn`. Nothing stores it on the spec, the Execution row or the environment, so nothing downstream can read a second copy that disagrees.
2. **`LocalNode.spawn`** (local.py 49): `isolated` becomes keyword-only **with no default**, and the `isolated is None` branch that calls `requested` (59-60) is deleted. A caller that forgets the argument fails with `TypeError` instead of silently re-deciding. Today's only callers are manager.py 255 and one test that already passes `isolated=True` (test_pv20_isolation.py 646).

What D1 does **not** do: change `_workspace`, `adapter.inventory` or `hook_settings`. Each consumer reads the same local when its own slice lands (T-016 W2/W3/W4/W7, T-017 C2's exclusions, T-017 C4's staged hook). Adding unused parameters now would be scaffolding. D1 alone changes no behaviour: `requested` gives the same answer one step earlier.

**Reach of the probe.** `getattr(self.node, 'isolation', None)` follows the pattern of the three existing node probes (manager.py 706, 759, 775): a node with no isolation authority (a remote node, a test double) answers "unisolated", exactly as `_isolation_record` already treats it. A remote node that can run isolated would need the same attribute; that is T-017's question 6, not decided here.

## 4. Ordering after D1

| # | Step | Line today | Decision known |
|---|---|---|---|
| 1 | adapter, terms, task, account | 176-186 | — |
| 1a | **`isolated = iso.requested(e.id, adapter)`, once; exception → refuse, return** | new | yes |
| 2 | `_workspace` (W2 later reads `isolated`) | 188 | yes |
| 3 | spec, `hook_settings` (C4 later reads `isolated`) | 208-217 | yes |
| 4 | `adapter.inventory` (C2 later passes `isolated`) | 226 | yes |
| 5-6 | `prepare_process`, e-stop, offset | 236-248 | yes |
| 7 | `node.spawn(..., isolated=isolated)`; the node calls `_isolate` iff True and asks nothing | 255; local.py 61-62 | yes, the same value |

Resume (`_resume` → `_spawn`, 585) takes exactly the same path, so a PAUSED or AWAITING_APPROVAL resume is decided once, at 1a, and `requested` answers True for any execution that has a record.

Not covered by D1: a resume of an execution that ran **unisolated** and that `authorize` now approves. `requested` would answer True and the old workdir would be reused. That is T-016 W7's migration rule (PV-20 §3.7), which reads the D1 value; D1 neither allows nor refuses it.

## 5. Files and focused fake tests

Files: `archeus/core/execution/manager.py` (`_spawn` only), `archeus/node/local.py` (`spawn` only), `tests/v1/unit/test_execution_units.py`.

Tests: a fake node exposing `isolation.requested` and a fake adapter, each appending to one shared call log.
- `test_isolation_is_decided_once_before_the_workspace_and_the_inventory`: the log reads `requested`, `workspace`, `inventory`, `spawn`, with `requested` exactly once.
- `test_the_spawn_receives_the_decision_that_was_taken`: parametrized True/False; `node.spawn` got `isolated=` equal to what `requested` returned.
- `test_a_resume_takes_the_same_single_decision`: through `_resume`; `requested` once, `spawn` got `resume_state` and the same `isolated`.
- `test_an_isolation_decision_that_raises_starts_nothing`: `requested` raises `OSError`; one `X.refuse` with `stop_reason='binding'`; no `_workspace`, no `inventory`, no `prepare_process`, no `spawn`.
- `test_a_node_without_an_isolation_authority_spawns_unisolated_as_today`: no `isolation` attribute; `spawn(isolated=False)`, and workdir, branch and argv equal today's.
- `test_no_spec_or_environment_value_decides_isolation`: `requested` returns False while the environment, opt-ins and `task_contract` carry isolation-shaped keys; `spawn` still gets `isolated=False`. Same with `requested` True and keys saying "unisolated".
- `test_node_spawn_has_no_default_isolation_decision`: calling `LocalNode.spawn` without `isolated` raises `TypeError`. This test belongs beside `test_pv20_isolation.py`'s `node.spawn` test (line 646). If that file is still claimed, it waits; see §6.

Mutants, each to be caught: move 1a after `_workspace` (test 1); restore the node's `isolated=None` default and call it without the argument (tests 1 and 7); default to False on an exception (test 4); read `isolated` from `spec.env` (test 6).

Verify, once authorized: from the worktree, `py -m pytest -m "not real_process" tests/v1/unit/test_execution_units.py tests/v1/unit/test_pv20_isolation.py -q`, plus the T-003 S2 set.

## 6. Dependencies and open points

| Card | Shared file | Edge |
|---|---|---|
| T-019 | `test_pv20_isolation.py` (claimed until done) | D1's test 7 waits for T-019, or moves to a separate test file |
| T-015 | `manager.py` (T-015 edits `_collect` 499-535 and passes `isolated` to `record_end`; D1 edits `_spawn`), `test_execution_units.py`, `test_pv20_isolation.py` | same files, different functions; the protocol allows one `doing` card per file, so they serialize. Either order works. T-015 decides isolation **at the end** from Core's record (`_isolation_record`), which is right there and is not a second `requested` probe |
| T-016 W2, W3, W4, W7 | `manager.py` | consume D1's value; land after D1 |
| T-016 W5 | `work.py` | **not** served by D1: W5 needs a dispatch-time fact, before any Execution exists. D1 decides per execution at spawn. T-016's Q1 stays open |
| T-017 C1 | `paths.py`, `base.py`, `adapter._env` | no overlap. C1 reads `spec.isolation is not None`, which the node still sets in `_isolate` from the same value |
| T-017 C2 (exclusions) | `sources.py`, `adapter.py` 147, `fake.py` 78 | after D1; passes the D1 value into `inventory` |
| T-017 C4 | `manager.py` 213 | after D1; reads the D1 value when building `hook_settings` |

Questions for the owner (not answered here):
1. A decision that raises: uncharged `binding` (re-dispatched under the bounded retry policy, like an establishment failure) or charged like an inventory that cannot be taken (manager.py 218-223 explains why a persistent failure there is charged)?
2. Should D1 be authorized on its own now, since it changes no behaviour, or only together with its first consumer (W2 or C2)?

# PV-20 fixture protocol tooling

This package never starts processes, loads native libraries, opens listeners or
creates Jobs on import. It contains pure policy/argv generators, fresh UUID-root
creation, strict no-link scans, bounded evidence writers, ordered F0–F9/N1–N5
case catalogs, and controller/watchdog logic over an injected backend.

Native execution remains BLOCKED without a reviewed native backend. No native
probe, disposal command, identity API or independent watchdog executable is
invented here. These are real missing protocol bindings, not successful cases.
No owner should treat this package alone as an executable acceptance package.

## Owner-authorized entry point

`controller.run_stage(manifest, token_file=..., native=True, backend=...)` is the
explicit native step. `native=False`, absent/mismatched tokens, changed artifacts,
missing prerequisites and absent backends refuse before any backend call.
There is no command-line autoload of an arbitrary backend and no subprocess
fallback. The owner supplies a reviewed entry point and backend when the native
bindings are available. Do not use the historical harnesses as that backend.

The owner creates the token separately; no tooling here creates authorization:

```json
{
  "authorization_id": "owner-assigned-label",
  "fixture_only": true,
  "stage": "F1",
  "fixture_parent": "D:\\pv20-fixtures",
  "fixture_uuid": "owner-selected-canonical-uuid",
  "manifest_hash": "sha256-of-controller.digest(manifest)"
}
```

`manifest_hash` is the hexadecimal result of `controller.digest(manifest)`, not
a second hash. Each stage has its own token and fresh direct UUID child root.
The token is an explicit consent interlock, not protection from a hostile host
user capable of creating that file. Never reuse an existing root.

The manifest contains `stage`, `fixture_parent`, `fixture_uuid`, complete ordered
`cases` from `protocol.STAGES`, and `policy` keyword arguments for
`fixtures.policy`. It also freezes the non-observed evidence fields listed in
`protocol.SUMMARY_FIELDS`: candidate/protocol hashes, batch ID, SDK 1.0.1, schema
1.0.0, OS/build, architecture, command IDs, capability and fixture inventories,
and executed-file/runtime hash inventories. Executed-file hashes map absolute
staged paths under the approved fixture parent to SHA-256 digests. Include all
executed code and DLLs. `prerequisites` maps the preceding N stage to `PASS`;
the integration owner must bind that assertion to reviewed evidence. A local
N4 subset never supplies that assertion for N5.

Policy defaults deny network and UI, clear inherited environment, and grant
only enumerated synthetic paths. The explicit `proxy_port` option generates
the F3-observed identity-less loopback proxy variant; it does not assert strict
inbound peer exclusion. `ui=True` is an explicit manifest change, never a retry.
No system-runtime grant is added. P/Q policies are reciprocal; verifier policy
generation and real production N2 policy selection remain backend obligations.

## Backend contract and evidence

All methods must return promptly; controller polling cannot bound a blocking
native call. `arm_watchdog(root, limits)` must establish an independent observer
and pre-spawn limits and return exactly `True` only when verified. That observer
must cover controller hangs/death and teardown, retain no outer Job handle, and
use retained PID/creation-time identities. The local `Watchdog` class is deadline
logic for that observer, not proof of process independence.

`start_case(case_id, root, policy, deadline)` must stage only frozen synthetic
resources, scan every grant again after staging, establish the launcher suspended,
assign/check its Core-held Job, then resume. `poll_case()` returns `None` while
pending or exactly the case-evidence fields in `controller.case_record`.
Report workload observations, not launcher exit. Controls must actually pass;
map each primitive to its concrete acceptance rows. Expanded subcases, both
directions, variants and faults are mandatory within the catalog groups.

`stage_facts()` returns observed backend/tier, effective-policy verification,
principal links, outer Job links and timestamps. Preserve actual host TokenUser
and PSEC findings; never synthesize an AppContainer SID or infer isolation from
directory names. `origin_matches` requires PID plus creation time, live owner,
verified launcher ancestry and Job membership; it supplies no native attestation.

`cancel_owned()` and `begin_cleanup()` act only on retained owned resources.
`poll_cleanup()` returns `None` while pending, then the cleanup schema from ADR
section 2. Every positive cleanup assertion, verified MXC disposal, and an empty
unresolved-resource list are required; uncertainty quarantines the retained root.
No fixture deletion, wildcard cleanup or PID sweep exists here.

Each stage writes a bounded exclusive JSON summary and append-only intent/
completion journal. Unknown observations remain null on failure. Export only
bounded labels and boolean observations; never pass raw output, environments,
prompts, secrets or provider bodies. `run_batch` stops on the first non-PASS and
marks later stages NOT_RUN; `write_batch` exclusively writes its returned ledger.

Scans use lstat on all ancestors and every entry, reject reparse points and
symlinks, and reject regular files unless link count is exactly one, before
grants and immediately before launch. Scans are not an atomic kernel lock:
native integration must exclude concurrent host mutation during grant/launch.

## Validation

Only the coordinator runs tests. From this worktree:

```powershell
py D:\Archeus\.collab\testlock.py -- py -m pytest tests/v1/unit/test_pv20_mxc_tools.py -q
```

The tests use synthetic files, fake stat records, fake clocks and fake backends;
they create no native fixtures or processes.

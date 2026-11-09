# T-1061 · Mapping the nine reported srt limitations to PV-20 threat-model rows and tests

**Card:** T-1061 · **Date:** 2026-11-09 · **Owner:** qwen · analysis note (no code, no tests changed).

**Repository snapshot read:** the `/work/repo` checkout of the MXC integration branch. No commit id
is recorded here because the container has no `git` binary `[?]`; the checkout does contain
`archeus/node/broker_listener.py`, whose rows the threat model assigns to the later `pv20-int4`
branch (`docs/architecture/pv20-threat-model.md:14-17`, which itself records tip `pv20-int2` =
`pv20-mxc 9115445f` plus B0, B4 and the fx5 fixes). Every `file:line` below was re-opened in *this*
checkout, not copied from the threat model (whose own header warns its line numbers drift).

**Source of the nine limitations:** `RESEARCH-trends-2026-11-09.md`, topic 4, on the upstream project
`anthropics/sandbox-runtime` ("srt"). Single secondary source: the upstream README claims were NOT
re-verified by us, and the three quoted bullets are quoted there second-hand. **Nothing in this note
is native evidence** — not of srt's behaviour, and not of any Windows property of Archeus. Per the
threat model's own rule, PV-20 rows are "statements about code and test evidence at the integration
tip, not about a property a real process has" (`docs/architecture/pv20-threat-model.md:6-8`).

**Design frame for every judgement:** Archeus isolates with Microsoft MXC (AppContainer + Job per
ADR-0053), not with a sandbox user, a write-restricted token and a machine-wide WFP filter. The base
container carries the host user's SID and no AppContainer SID: "F1 establishes host-user tokens plus
PSEC, not distinct AppContainer SIDs" (`archeus/node/mxc.py:7`); "the boundary is the MXC process
security environment, token User is the host user's SID, separation was observed only as behaviour,
and the from-inside token read is OPEN (MXC-R13)" (`docs/architecture/pv20-threat-model.md:228-230`).
Tags: `[?]` = not confirmed by reading; `[I]` = my inference.

| # | limitation (short) | threat-model row | pinning test | class | reason (one sentence) |
|---|---|---|---|---|
| 1 | anonymous-token thread creates a socket before the fence applies | none | none | native only | Archeus compiles egress deny into the policy (`archeus/node/mxc.py:160-161`, re-validated at `:233-235`) and grants no capabilities (`archeus/node/isolation.py:34`), but whether an impersonated-token thread inside the container could create a socket outside whatever the MXC runtime filters on is probed nowhere — the word "impersonate" appears in the whole test corpus only once, in an unrelated header comment (`tests/v1/integration/test_execution_security.py:9`) `[?]` |
| 2 | `CreateRestrictedToken` derived token (deny-only user SID) not fenced | none | none | native only | The srt fear is a derived token richer than the sandbox account's, and in Archeus the container token already carries the host user's SID (`archeus/node/mxc.py:7`), so the analogous question is exactly the from-inside token read recorded OPEN as MXC-R13 (`docs/architecture/pv20-threat-model.md:228-230`), which no fake can answer `[I]` |
| 3 | SMB redirector answers loopback share reads/writes for the sandbox | none | `tests/v1/unit/test_node_mxc_policy.py::test_proxy_policy_keeps_egress_deny_and_carries_no_direct_rules` | native only | The only pinnable Archeus-side fact is that the compiled policy carries egress deny and no direct rule (`archeus/node/mxc.py:160-161`; the test exists at `tests/v1/unit/test_node_mxc_policy.py:254`), and whether a system SMB redirector serves loopback share traffic on behalf of a base-container process is a native fact no fake can show `[?]` |
| 4 | WSL service answers a sandboxed process | none | none | native only | H4 measured only CLI viability in the base container (`claude.exe`, node, git, powershell, Git Bash) (`docs/architecture/pv20-threat-model.md:70`); nothing in the repo reads or tests whether `wsl.exe` runs in or the WSL service answers a base container `[?]` |
| 5 | DNS via Dnscache not fenced | none | `tests/v1/unit/test_node_mxc_policy.py::test_egress_other_than_deny_is_refused` | native only | The unit seam pins that only `deny` ever compiles (`archeus/node/mxc.py:160`; refusal test at `tests/v1/unit/test_node_mxc_policy.py:649`), but whether the Dnscache service answers resolution for a container process on the service's network stack instead of the container's is native `[?]` |
| 6 | Schannel clients break in the sandbox | T13 | `tests/v1/unit/test_pv20_isolated_env.py::test_the_block_is_exactly_the_pinned_names_each_from_its_authority` | not applicable to MXC | An isolated execution's model path is plain HTTP to a loopback broker port with the token in env (`archeus/harnesses/base.py:136-139`, `BrokerLaunch` at `:123`; pinned by the test, which exists at `tests/v1/unit/test_pv20_isolated_env.py:96`) and TLS to the provider is the broker's outside the boundary (T13, `docs/architecture/pv20-threat-model.md:102`), with egress deny leaving no in-boundary TLS surface by design (`archeus/node/mxc.py:160-161`); arbitrary Schannel use inside a real container is unprobed `[?]` |
| 7 | per-user tool installs unreachable by the sandbox account | none | `tests/v1/unit/test_pv20_isolated_env.py::test_path_keeps_only_absolute_existing_entries_outside_every_private_tree` | not applicable to MXC | There is no separate sandbox account for a tool install to be unreachable from — the container token is the host user's (`archeus/node/mxc.py:7`; `docs/architecture/pv20-threat-model.md:229`) — and the functional analogue that remains is Core's own PATH narrowing (the test exists at `tests/v1/unit/test_pv20_isolated_env.py:191`; `_isolated_env` at `archeus/harnesses/base.py:531`), which is a deliberate Core-side choice, not an OS-account limit `[I]` |
| 8 | broker/proxy auth token visible in runner argv | T22 | `tests/v1/integration/test_pv20_mxc_agent_path.py::test_an_isolated_agent_launch_compiles_one_policy_and_spawns_once`; `tests/v1/unit/test_pv20_isolated_env.py::test_the_block_is_exactly_the_pinned_names_each_from_its_authority`; `tests/v1/unit/test_broker_execution.py::test_the_digest_is_never_in_a_view` | unit-testable with fakes | The Archeus analogue is closed by construction — the broker token rides only in `ANTHROPIC_AUTH_TOKEN` env (`archeus/harnesses/base.py:138`), the broker records the sha256 alone (`archeus/node/broker.py:151-152`, token from CSPRNG at `:147-148`; T22, `docs/architecture/pv20-threat-model.md:121`) — and a fake-seam test could pin the missing rule "the token never appears in the compiled `commandLine`" over the argv/env capture that already exists (`tests/v1/integration/test_pv20_mxc_agent_path.py:86-87`, `commandLine == subprocess.list2cmdline(argv)` asserted at `:393`) |
| 9 | session self-test refuses to start when a probe escapes | T10 | `tests/v1/integration/test_g06_os_isolation.py::test_row_10_with_a_condition_unmet_nothing_is_launched_and_nothing_falls_back`; `tests/v1/unit/test_pv20_isolation.py::test_unmet_condition_raises_and_records`; `tests/v1/unit/test_mxc_boundary.py::test_a_boundary_given_nothing_is_unavailable_and_launches_nothing` | unit-testable with fakes | Item 9 is **not** an upstream limitation but the srt design feature "self-test refuses to start" quoted above `[?]`, and its nearest Archeus analogue is the establishment invariant refusing before any spawn (`check_invariant` at `archeus/node/isolation.py:235`, `Isolation.requested` at `:656`; T10, `docs/architecture/pv20-threat-model.md:89`) plus the closed admission flags making the boundary unavailable (`archeus/node/mxc.py:24`, guard at `:305`; the boundary test exists at `tests/v1/unit/test_mxc_boundary.py:196`) |

## (a) Gaps: threat-model row `none`, class not `not applicable to MXC`

- **Row 1** (anonymous-token thread) — matters to Archeus's egress posture; no row covers an
  in-container token-impersonation escape; the closest residual is the G3 network-egress bullet,
  which has no row id (`docs/architecture/pv20-threat-model.md:225-227`).
- **Row 2** (derived token) — matters; carried only by the register entry MXC-R13, not by a row
  (`docs/architecture/pv20-threat-model.md:230`).
- **Row 3** (SMB redirector loopback) — matters (it is a reach path around the path grants and the
  egress deny); no row names a system service answering for the container.
- **Row 4** (WSL service) — matters to H4's viability question only if WSL is even reachable in the
  base container; no row; also a candidate for the H3 question of "a process the execution causes to
  exist" outside every Core Job (`docs/architecture/pv20-threat-model.md:69`).
- **Row 5** (Dnscache) — matters as an exfiltration/reach question; no row.

## (b) Threat-model row present, pinning test `none`

- None. Rows 6, 8 and 9 each carry at least one existing test (verified by `grep -n "def test_..."`
  in the cited file); rows 1-5 carry `none` but are also row-`none` rows and are listed in (a).

## (c) Rows I could not decide, each with the one fact needed

- **Row 1** — is the MXC container's network filter keyed to the container *process* (survives
  in-process impersonation) or to the token at socket-creation time? No document in this repo states
  it; the token behaviour is recorded OPEN/UNVERIFIED throughout (`docs/architecture/pv20-threat-model.md:228-230`) `[?]`.
- **Row 2** — what does the base-container process token actually contain when read from inside
  (MXC-R13)? Until that native read exists, no classification of a derived-token escape is decidable
  (`docs/architecture/pv20-threat-model.md:230`) `[?]`.

## Provenance caveats

- The three upstream bullets and the nine-item split come from one secondary source
  (`RESEARCH-trends-2026-11-09.md`, topic 4); upstream was not re-verified `[?]`.
- Every class judgment is about how Archeus's *committed, switch-closed* code is built
  (`docs/architecture/pv20-threat-model.md:3-8`: production dispatch, native run and broker dispatch
  are all closed — `archeus/node/isolation.py:50`, `archeus/node/mxc.py:24`,
  `archeus/node/broker.py:67`); none is a statement that any control holds on a real Windows host.
- Row-9 classification depends on treating a quoted *design feature* as the item to map, which is
  the card's instruction, not an upstream limitation `[I]`.

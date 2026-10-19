# T-010 · Creator-controlled access: options for the owner decision on S2-G

Prepared by Claude, 2026-10-12. Analysis only: no code, no Windows call, no decision. Input to T-004.

Sources: Codex's `S2G-ARCHITECTURE-READINESS-2026-10-11.md` (reported results, Codex-authored and Codex-run, not independently verified), PV-20 design §3.3 and §7 R7, and the S2 worktree at `ef42204` for the writers listed below.

## 1. What is actually open

Codex's readiness record reports two things that are easy to merge and should not be:

- **Unilateral access is not shown.** Nothing reported shows execution Q reading or changing a default-created file of execution P, or changing a Core-created class directory.
- **Consensual access is shown.** When P creates an object with an explicit descriptor naming Q, Q can read and write it. Removing WRITE_DAC/WRITE_OWNER from P's grant does not stop this, because the descriptor is chosen at creation, not changed afterwards.

So the open question is narrow: **does R7's "other executions inaccessible" have to hold when the owning execution itself grants the access?** Every option below is an answer to that question.

## 2. Where an execution creates objects today

From `default_plan` (isolation.py) and the hook, at `ef42204`:

| Surface | Access | Who creates objects there | Could Core create them instead? |
|---|---|---|---|
| workspace (`spec.workdir`, or `own/work` with no project) | rw | Claude Code edits, git, shell children, build tools, package managers | No. Arbitrary names and counts, created by third-party programs |
| `own/state` (class 7) | rw | the harness runtime's own state and caches | No for arbitrary runtime state; yes only for a fixed known file set |
| `req/` (class 1) | rw | the hook: `<seq>.lock` (O_CREAT\|O_EXCL), `<seq>.req.json.part` then `os.replace`, `halted.json`, `precompact.json` | Yes. A small, fixed protocol that Core owns at both ends |
| the profile's own AppContainer storage | OS-defined | whatever the runtime writes under its package folder | No |
| `CLAUDE_CONFIG_DIR` (the account home, set by the adapter) | not in the plan | the real CLI's transcripts and settings | Open: real-CLI feasibility is already listed as unverified |

## 3. Options

### A. Core creates every object (Codex's family 1)
- **req/**: feasible. Core pre-creates fixed request slots with its own descriptors, and the execution gets write-data on them but no add-file on `req/`. The hook writes into an existing slot instead of create-then-rename, and Core checks completeness (length prefix or checksum) instead of relying on the rename's atomicity. The cost is a hook protocol change, fake tests, and one Windows run showing the execution cannot create in `req/`.
- **workspace, `own/state`, package storage**: not reachable from a user-mode Core. Mediating every create made by git, shells and build tools needs a filesystem filter or a full broker, which is a different product.
- **Verdict**: closes class 1 only, so it cannot satisfy R7 as written on its own.

### B. A namespace peers cannot reach (Codex's family 2)
- This needs a boundary that holds even when a descendant's own descriptor admits the peer. Directory ACLs on ancestors are not that boundary: Codex's W-1 reports leaf access that does not depend on the parent's metadata being readable.
- The mechanisms that do provide such a namespace (separate machine accounts with separate profiles, silos or containers, a VM per execution) need administrator rights, Hyper-V or both. Each one changes the deployment model (install-time setup, a privileged service) far more than S2-G's scope does.
- **Verdict**: the strict reading of R7 is reachable only with a privileged-component decision. That decision would need its own spike.

### C. Narrow R7 by ADR to non-consensual access, and keep it strict there
- **R7 becomes**: no execution can read or change another execution's objects *without that execution's own action*, and no execution can change a Core-created class directory or Core's state.
- **Why it is defensible**: an execution that wants to hand data to a peer already has channels Core cannot close: the shared workspace when two executions share a project, the user's own files, timing. Exclusion of a consenting pair is not a property a user-mode sandbox delivers on any platform.
- **What still has to be true**:
  - creation-time descriptors cannot reach Core's own objects or class directories;
  - revocation after the execution ends removes every ACE Core applied;
  - the evidence for non-consensual exclusion is independent, not only Codex-run.
- **Cost**: the ADR, plus a review of R7's wording in the design. S2-G proceeds on the retained contract.

### A + C together
- Apply A to `req/`, so the mailbox protocol is Core-created end to end. This is cheap and closes the one surface Core fully owns.
- Accept C for the workspace and runtime state.
- This is the smallest change that leaves no surface where Core *could* control creation and does not.

## 4. Evidence each option would still need

| Option | Before S2-G code | Windows runs |
|---|---|---|
| A (req/ only) | hook slot protocol, fake tests | 1: the execution cannot create in `req/`, and can write its slot |
| B | privileged-component design, deployment decision | a spike per mechanism |
| C | ADR text, R7 wording | independent rerun of non-consensual exclusion (Q against a default-created file of P, Q against a class directory) |
| A + C | both of the above | both of the above |

## 5. Not decided here

- Which option to take. That is the owner's call, with Codex's architecture review.
- Whether `CLAUDE_CONFIG_DIR` becomes a planned surface. It is a prerequisite for any real-CLI isolated run under every option.
- Creator/owner evidence beyond what Codex reported. Finding 3, C6 and Gap B stay open under every option.

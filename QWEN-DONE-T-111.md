STATUS: BLOCKED BY OWNER

Card: T-111 · T-004 evidence E1: two-worker temp fixture under T-100's choice O1
Owner of card: qwen · Byline: Qwen (pi · spark/qwen3.8-flash-next) · Date: 2026-10-19

## Why blocked (the block, in its first words: the card needs the owner's workspace back)

**The `D:\Claude` workspace was deleted and replaced with an archeus-app project
scaffold at 14:33:32–14:33:34 local on 2026-10-19, mid-card.** Not a classifier
refusal — an external, programmatic deletion by another process while this card
was in its native-test debug loop. Evidence, all read-only observations:

- Native `dir /a D:\Claude` (14:35, 14:37): only `.archeus\`, `.claude\`,
  `AGENTS.md`, `CLAUDE.md` remain — all created or rewritten 14:33–14:35 by the
  archeus app (`D:\Claude\.archeus\workspace-manifest.json`, `"generated_at":
  "2026-10-19T12:33:34+00:00"`, `"project_path": "D:\\Claude"`;
  `.archeus\snapshots\index.json`: memory_graph `removed 30814, added 6607`).
- `.git` is gone (`dir D:\Claude\.git` → File Not Found). The main repo object
  store lived there: sibling checkouts still carry
  `gitdir: D:/Claude/.git/worktrees/archeus-pv20-int5` in their `.git` files.
- The deletion bypassed the Recycle Bin (`D:\$RECYCLE.BIN\S-1-5-21-…-1001`
  holds nothing from 2026-10-19). Nothing was renamed to `D:\` root (no new
  root entries).
- The deleted tree took the whole uncommitted/never-committed T-111 state with
  it: the modified `tests/v1/integration/test_pv20_isolation_windows.py`, the
  `.collab` directory (board, cards, notes, both run logs
  `.collab/t111-native-run1.log`/`run2.log`), and the earlier QWEN-DONE files.
  This status file is a fresh recreation of that path's T-111 entry.

Only the owner can unblock: restore `D:\Claude` (git objects, working tree,
`.collab`, branch `archeus-v1-rearchitecture`). Nothing about T-111 can run,
commit or be verified against a tree that is not there, and the hard rules
forbid me from reconstructing or touching anything beyond preserving my own
work (below). Do not let any session run `git init` over the scaffold.

## Commits

**None.** No commit was made for this card: the implementation was staged in
the working tree only (per the loop: run first, encode observed results, then
commit) when the wipe removed the repository itself. `git log` for the card is
empty by fact, not by choice; SHAs: —.

## What ran, with exact results (all pre-wipe, all under the card's auth)

1. `py -m pytest tests/v1/unit/test_pv20_isolation.py -k "windows_module or acl_mutation or static_gate" -q`
   → **18 passed, 501 deselected** (structural gates and the S1 ACL static gate
   green with the E1 block in the module).
2. Native run 1: `ARCHEUS_REAL_BOUNDARY=1 py -m pytest tests/v1/integration/test_pv20_isolation_windows.py -k t111 -rP --basetemp=D:/t111 -x`
   → collection error `AttributeError: module 'ctypes.wintypes' has no attribute 'PSID'`. Fixed (`ctypes.c_void_p`).
3. Native run 2 (same command) → `OSError: ConvertStringSecurityDescriptor(...) winerror=1337`
   — the SDDL parser rejects the `LX` alias alongside label flags. Fixed to
   `S:(ML;;NWNRNX;;;S-1-16-1024)` (conversion + application verified in a
   scratch probe: ACEs and label read back via `icacls`).
4. Native run 3 (same command) → `OSError: SetNamedSecurityInfoW(D:\t111) winerror=5`
   at the first prefix descriptor. Root cause found by direct probing:
   **`SetNamedSecurityInfoW` given the self-relative SD from
   `ConvertStringSecurityDescriptorToSecurityDescriptorW` writes a NULL DACL
   and answers 0** (observed on `D:\t111`: NULL DACL on the root, empty
   inherited DACL on the numbered dir — undeletable by pytest and `rm`). The
   verified working call is `SetFileSecurityW` with the same SD (DACL+label
   applied exactly, `SE_DACL_PROTECTED` confirmed by read-back). `_e1_set_sd`
   was rewritten to it with a mandatory read-back — then the wipe came.
5. Cleanup of the card's own fixture wreckage: `D:\t111` fully removed
   (owner-WRITE_DAC sweep + bottom-up rmdir; `errors: []`, gone confirmed).

No AppContainer profile, Job or process was ever started by runs 1–4 (each
died before `_e1_worker`). The icacls digests and profile-list evidence the
test itself carries never got to run.

## What did NOT run

- **The E1 evidence itself**: none of cases (a), (b1), (b2), (d), (e) completed;
  T-100 §4's decision-rule result does not exist. **T-004's blocking reason is
  therefore not answered either way — do not let any card act on E1 as if it
  had a result.**
- The mechanism assertions (to be encoded from the first full observation, per
  the T-064 pattern), the commit, and the single Codex call the card's `review:`
  line anticipates — all correctly still ahead.
- Nothing outside the card's auth was executed at any point: no ACL write
  outside the pytest-owned fixture tree, no elevation, no production switch,
  no push, no fetch.

## Where the surviving work is (preserve these)

`D:\t111-src\` — created by this session, contents by this session:
- `base708.py` — verbatim HEAD copy of the native module (taken via `git show HEAD:` before editing),
- `t111_e1_block.py` — the complete E1 section with fixes 2–4 applied, `ast.parse`-verified,
- `T-111-preservation-note.md` — rebuild recipe, the verified API facts, and a recovery copy of the deleted card.

After the owner restores the workspace, the card resumes at the rebuild recipe
in the note and the first full native run; no design work remains.

*Signed by Qwen (`pi`, `spark/qwen3.8-flash-next`) — the work above is mine;
the deletion is not.*

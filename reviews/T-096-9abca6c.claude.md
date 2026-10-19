VERDICT: CHANGES

Scope: a2be0f4 (I-F1) and 9abca6c (I-F2) in D:/archeus-p20-f (base 853f63f). Read: the T-096 card, the T-089 card, reviews/T-093-853f63f.claude.md (findings 5 and I-F1/I-F2), p20-design-gate.md §1.3, D1, D9, §4.1, §6, §9, slice C items 25-28 and slice I items 109-112, p19-design-gate B8 and items 80-81, ADR-0044 item 3. File:line refers to 9abca6c.

Findings:
1. Medium, required. Upgrade path: a page token saved by a pre-change shell stays live and stays on disk. This is question (4): it is not already the effect, and it should be.
   - In memory mode `authenticate` deletes the stored IndexedDB key and never revokes the token (clients/app/src/api/transport.ts:92).
   - The new slot cannot reach that token. `register_device` revokes only an ACTIVE device whose `supersede` equals the slot (core/application/commands.py:131-135). A device redeemed before this change has `supersede = None`, the same limit slice C recorded for pre-P20 shell rows (p20 item 26). So the old credential keeps observe+control+approve+admin with no expiry.
   - The delete does not take the bytes off disk. I ran a probe in real QtWebEngine with a persistent profile, a fake value, and exactly the transport's DB, store and key (`archeus`/`auth`/`device-token`). Put, then delete, then two more open/close cycles: the value was in `IndexedDB/http_127.0.0.1_<port>.indexeddb.leveldb/000003.log` after every phase, while the API read `undefined`.
   - Result: on every install that ran a pre-change `archeus gui`, a live admin token can still be read from the profile under ARCHEUS_HOME. That is the exposure I-F2 named, unchanged for those installs. The accept "after a shell session ends no device token remains in the Qt profile" fails there. The card's note (b) records the server-side half, but "deleted" holds only at the API level.
   - Required change: in memory mode, when a stored token exists, revoke its own device before deleting it. It holds `admin`: `GET /v1/sync` gives `client.id`, then `POST /v1/devices/{id}/revoke` with an idempotency key. A 401 means the token is already dead, so proceed. Whatever stays in the LevelDB log is then a dead token.
   - Test for it: a node case where a stored token leads to a revoke of the synced id before the delete, plus its mutant (no revoke).
2. Low, required. Nothing records the as-built change, and three canonical texts are now stale.
   - target-architecture §5.1's T-089 amendment says the check warns when a broad principal "may write". It now also warns on read, and on the token file.
   - p20 item 109 still describes the old state in two places: the local-token Protection cell ("may write the home") and the page-token row (IndexedDB, plaintext). Item 111 lists no disposition for I-F1 or I-F2.
   - The new `supersede` value `desktop shell page` is API surface (api-reference.md regenerated). The reload behaviour (`?r=N`, a fresh launch code) is new too. And D1's stated cost now reaches the page: a second concurrent `archeus gui` also signs out the first window's page. None of these has a §12 item.
   - Required change: an append-only §12 item for I-F1/I-F2 as built, and a dated append to the §5.1 amendment. Nothing reworded.
3. Low, optional. Two reviewer mutants survived:
   - A4: `_read_like` also counting READ_CONTROL (0x20000) survives. That would give a false-positive warning. Fix: add a parametrized case where READ_CONTROL, FILE_READ_ATTRIBUTES or FILE_READ_EA alone gives None.
   - C2: `clearToken` not resetting `held` survives. After a self-revoke in Control the page would keep a dead token in memory, which exposes nothing. Fix: one node case.
4. Note for the owner, on question (3). The page token is not a D1 violation: D1 does not cover that credential.
   - D1's problem is item 86, the "desktop shell" row (§1.3; D1 "Problem"). "The shell keeps exactly its observe + control scopes" (§4.1) is that row's grant. Slice C item 25 built it ("Its scopes stay exactly observe + control"), and p19 B8 and line 486 describe it the same way.
   - The page's grant comes from p19 B8: "mint a launch code with D2 scopes (observe+control+approve+admin)", that is p16 D2, cited at cli/main.py:258. `core --open` gets the same grant.
   - So the fork's finding (a), admin scope and no expiry, is correctly left as recorded. Changing it needs a new owner decision, not a correction under D1.
   - The other side of this: D1's "never persisted to disk" covers that same shell row, so it does not cover the page token either. The card's authority ("D1 ... applied to the second token") therefore extends D1, and it reverses p19 item 81's as-built "The device token ... survive[s] a restart there". Item 111 left I-F2's disposition to the owner, and its options were "document as accepted" or "memory-only". The owner should confirm that this is the disposition they chose.
   - Separately, the card's "D9 (a)" is the board's PV-20 D9 (T-089 auth, BOARD.md:1064). p20-design-gate's own D9 is the Codex adapter, moved to P23. This is wording only.
5. Evidence claims, Low. The e2e reads the IndexedDB key through the page's JS while the page is live. It does not read the profile's files after the session ends, so "no device token remains in the Qt profile" claimed more than what ran.
   - For the new path my own byte scan supports the claim. I scanned the e2e's profile after both runs and the in-session reload: 77 files, ASCII and UTF-16LE, every `dev_`+43-character string hashed against `tokens.token_hash`. It found 0 token-shaped strings.
   - Also clean in that profile: History holds no URLs, and the service worker never caches `/v1/` (public/sw.js). The snapshot keeps reads only (data/snapshot.ts), and sessionStorage holds the flag "1" only.
   - For the upgrade path the claim is refuted (finding 1).

I-F1 judged correct:
- The read mask (isolation.py:1698) is GENERIC_READ | GENERIC_ALL | FILE_READ_DATA. It covers FILE_GENERIC_READ (0x120089) and read+execute (0x1200A9), which both carry FILE_READ_DATA. GENERIC_READ covers inherit-only ACEs that keep generic bits. READ_CONTROL, attributes, EA and FILE_EXECUTE are correctly excluded, since none of them reads data.
- Inheritance flags are ignored, as `broad_writer` does. This is conservative: a "this folder only" LIST ACE or a container-only ACE warns even though it never reaches the token file. Deny ACEs are not weighed. Both match T-089's qualification.
- There is no second DACL parser: `_broad` is shared and sits on the same `self.dacl()`/`parse_ace`.
- It still only warns: `token_protection` returns `(True, warning)` on Windows. Write is reported before read.
- No ACL is written. `test_no_acl_mutation_primitive_exists_in_production_code` and the static-gate tests were in the passing run.
- The token is read only once it exists. On a first-ever start, `token_protection` (runtime.py:411) runs before `write_local_token` (:546), so only the home is checked. That is fine, because the token inherits the home's ACL.

Ran (git archive 9abca6c extracted to D:/trv-T096s; -p no:cacheprovider --basetemp=D:/trv-T096):
- `py -m pytest tests/v1/unit/test_pv20_isolation.py tests/v1/integration/test_core_lifecycle.py tests/v1/integration/test_gui_shell.py -m "not real_process"`: 555 passed, 1 skipped. That equals the card's 533 + 22.
- `npm ci --ignore-scripts --offline` and `npm run build` in clients/app. The bundle hash, index-GvBKHNaC.js, is the same as the checkout's build. `node --experimental-strip-types --test test/transport.test.ts`: 3 passed.
- `ARCHEUS_E2E=1 QT_QPA_PLATFORM=offscreen py -m pytest tests/v1/e2e/test_gui_qt.py`: 1 passed, in real QtWebEngine.
- The profile byte scan described in finding 5 (scratchpad t096_scan_profile.py, test data only).
- The IndexedDB residue probe from finding 1 (scratchpad t096_idb_residue.py, fake value, own throwaway profile under D:/trv-T096q).
- 12 reviewer mutants, each applied, run and restored byte for byte (scratchpad t096_mut.py). 10 were caught:
  - A1: GENERIC_READ dropped from the mask.
  - A2: inherit-only ACEs skipped.
  - A3: the token never checked.
  - A5: a missing token read anyway.
  - B1: no `memory=1`.
  - B2: the page with no slot.
  - B3: the slot missing from SUPERSEDE_SLOTS.
  - C1: saveToken persists in memory mode.
  - C3: the flag never set.
  - D1: the reload handler off, caught in real Qt.
  
  2 survived: A4 and C2 (finding 3).
- `ruff check` on the 11 changed Python files: clean. `git diff --stat 853f63f 9abca6c -- docs`: only api-reference.md.
- D:/trv-T096, D:/trv-T096s and D:/trv-T096q deleted with shutil afterwards.

Not checked:
- The full tests/v1, POSIX, and a real display.
- A real Qt reload while Core is down. Only the node test covers it.
- `test_mutation_suites_parse -k "p19 or p20"`: it did not finish inside a 300 s limit, so the P116 re-anchor is unverified here.
- The fork's own mutant runs, beyond the overlapping ones I reproduced.
- A real pre-change profile, where the token may already have been compacted into an .ldb table rather than the log. Chromium may also compact at some later open; two reopens did not.
- The user's own Qt profile, which was not opened.

Reviewer: independent Claude agent (general-purpose), 2026-10-15

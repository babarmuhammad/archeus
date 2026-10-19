# T-018 · Arrival announcement vs the polite rate limiter

Prepared by Claude, 2026-10-12. Analysis only: no code change, no browser, no test run, no decision.

Sources, all at `f6abc4d` on `archeus-v1-rearchitecture`:
- code: `clients/app/src/a11y/announce.ts`, `src/state/arrival.ts`, `src/App.tsx`, `src/surfaces/Now.tsx`, `src/surfaces/Attention.tsx`, `src/state/thread.ts`, `src/state/motion.ts`, `src/data/connection.ts`;
- tests: `clients/app/test/shell.test.ts`, `test/arrival.test.ts`, `tests/v1/e2e/test_spa_arrival.py` (T-006 diff);
- contracts: `docs/architecture/p16-design-gate.md` §9, §17 and M19; the rulebook `docs/design/ARCHEUS_V1_VISUAL_ARCHITECTURE_RECONCILIATION.md` §17, §20, §21 (A-08) and §46.2; `docs/architecture/testing-strategy.md` line 236; `docs/architecture/p19-design-gate.md` item 48;
- `reviews/T-006-f6abc4d.md`.

## 1. What was observed, and the mechanism

*Extended by C-1012-T018 §1: two further ways an arrival is lost (the re-armed flush timer and the offer fast path).*

**Observed (T-006, reported in the `f6abc4d` commit message, not re-run here).** In 4 of 8 failing probe runs of `test_spa_arrival.py`, the polite region held "Archeus updated mission …, approval" where the test waited for "1 thing needs you". The same test was already recorded as a full-suite timeout ("the arrival is still announced") in p19 gate item 48. T-006 made the test wait out the window (`_quiet`); it did not change the product. The same commit message names a second, separate cause: an attention read that lands after the mission settled is a baseline, not a rise. That one comes from A-08's baseline rule (`arrival.ts:4-5`) and is not an announcement question.

**How the code produces it:**

| Step | Where | What happens |
|---|---|---|
| boot | `connection.ts:33`, `App.tsx:230-233` | The initial state is `connecting`. `BANNER.connecting` = "Connecting…" goes to `announce`. |
| window opens | `announce.ts:19-24` | Nothing was said before, so the banner is written immediately and `last` = now. For the next 5000 ms (`POLITE_EVERY_MS`, `announce.ts:6`), every offer is held as `pending`. |
| arrival | `App.tsx:179`, `arrival.ts:27-33`, host wiring `App.tsx:510` | A read of Attention at a newer seq with a higher count calls `announce(needsYou(count))`. It is inside the window, so it becomes `pending`. |
| thread update | `Now.tsx:310-316`, `thread.ts:36` | The same Core event adds an Archeus message with links. Once the names resolve (an async `Promise.all`, so it usually comes after the arrival), `announce(threadWords(names))` runs. It is inside the window, so `pending = text` **replaces** the arrival (`announce.ts:25`). |
| flush | `announce.ts:56-60`, `28-36` | The timer flushes the latest pending text. The arrival is never said. |

**When it happens (by reading, not observed beyond the initial window):** the arrival is lost whenever two or more offers follow it inside one window. Two offers alone (arrival plus thread update, outside any window) are both said, the second up to 5 s later. Cases where it can happen:
- the boot window (observed);
- a reconnect, where the "Back — everything on screen was read again." banner opens a window just as the re-reads land;
- two missions reaching approval within 5 s;
- a graph-focus announcement (`GraphView.tsx:375`) in the same window.

**What still reaches the user when it is dropped:**
- the badge and its label, and the count in the tab name (`motion.ts:391` lists these with the announcement as A-08's equivalents);
- for an approval, the assertive "An approval waits for you: …" (`Attention.tsx:111`). That fires only where an `ApprovalCard` is mounted: Attention, the inspector, and Now's top three (`Now.tsx:75`). It does not fire on Work, World or Control, and does not fire for verification, knowledge or planning items.

## 2. What the contracts say

**The rate limit (p16 §17).** `p16-design-gate.md:845`:
> live updates | one polite live region, rate-limited to one announcement per 5 s ("Mission *X* is now verifying"); one assertive announcement per new approval; nothing announces per execution progress frame | unit (rate limiter)

The §9 summary (`:590-591`) says "polite rate-limited". The mutant M19 (`:1293`) is "rate limit removed (announces every frame)".

**The arrival (A-08):**
- rulebook §17 (`:535`): "one 240 ms pulse on the badge when the count increases";
- rulebook §20 (`:586`): "attention pulse | count in the tab name + polite announce";
- rulebook §21 (`:613`): A-08's equivalent column is "announce";
- §46.2 (`:1319`): "Fully specified (… announced; the count in the tab name)";
- `testing-strategy.md:236`: a rise "says the new count in the polite live region".

**The competing announcement (A-05, thread T1).** Rulebook §20 (`:579`): "polite live region "Archeus updated *Dashboard*"; the card/link". `motion.ts:306` gives the same.

**Reading:**
- §17 requires a **rate** (at most one per 5 s). It says nothing about what happens to the offers that rate turns away.
- **"Latest wins" is not in any canonical text** I found. It exists only in the code: the comment at `announce.ts:2` ("the latest wins") and the unit test name at `shell.test.ts:51` ("the latest (M19)"). M19 itself only kills a removed rate limit.
- A-08 requires the rise to be announced. A-05 requires the thread update to be announced. Both use the same polite region.
- So §17 and A-08 do not conflict as written. The conflict is between A-08 (and A-05) and the implementation's unstated latest-wins choice.
- The contracts say nothing about **priority**: which polite announcement gives way when the rate forces one out. Choosing that is a design decision, not a bug fix.

## 3. Options

*Superseded in part by C-1012-T018 §2 and §3: option B as written below does not hold an arrival under a burst, and its "Fixes: every window" and "A-05's polite words can be dropped" understate what it costs.*

| | Change | Cost | Contract touched | Fixes |
|---|---|---|---|---|
| **A. Leave as is, record it** | none in code; a dated gate note that A-08's announcement is best-effort under §17 | zero code; the e2e test keeps `_quiet` | A-08 "announced" and testing-strategy:236 become "usually announced"; needs owner acceptance | nothing |
| **F. Don't announce the boot banner** | skip `BANNER.connecting` while `gen` is 0, the same kind of rule as p16 item 7 ("a resync before anything is shown is not announced") | one condition; screen-reader users lose "Connecting…" at load | §17 untouched; changes the boot announcement | the observed boot case only; reconnect and two-missions cases remain |
| **B. An arrival is not replaced while pending** | `offer(text, now, keep)`: a pending kept offer is replaced only by another kept offer (a newer count wins); a plain offer arriving while one is kept is dropped. Arrival's host passes `keep`. | about 6 lines in `announce.ts`, the call at `App.tsx:510`, one unit test, one mutant | §17 unchanged (still one per 5 s); latest-wins becomes "latest, except over an arrival"; A-05's polite words can be dropped in that window (its card/link stays) | every window |
| **E. Coalesce** | when an arrival and other text share a window, flush "1 thing needs you. Archeus updated …" | the limiter learns kinds and joins texts; a longer utterance | §17 holds (one announcement); rulebook copy for the joined form | every window, nothing dropped |
| **C. Bounded FIFO queue** | keep up to N pending offers, say one per 5 s | late, stale speech under bursts; N to choose | replaces latest-wins for every announcement | every window, with delay |
| **D. Arrival in the assertive region** | `write('live-assertive', …)` for arrivals | small code | **conflicts with §17**: the assertive region is "one … per new approval"; an approval rise would be said assertively twice | every window |

## 4. Recommendation

*Superseded in part by C-1012-T018 §2 and §3: B is a candidate, not a resolution; it needs the timer contract and burst test of §2, and it gives up A-05, the graph focus announcement and the banners' spoken text in the window.*

**B** is the smallest option that makes A-08's announcement hold in every window without touching §17's rate. F is smaller but only fixes the case that was seen. A costs nothing but turns "announced" into "best effort". D conflicts with §17 and should be ruled out.

B is a priority change: it decides that an arrival outranks a thread update. Per the card it is not made silently; it waits for the decision below.

**Acceptance test for B.** Pure limiter, explicit `now` values, `node --test`, no timers and no wall clock. It goes next to the M19 test in `clients/app/test/shell.test.ts`.

```ts
test('an arrival pending in the polite window is not replaced by a later update, and the rate holds (A-08, §17)', () => {
  const l = limiter(5000);
  assert.equal(l.offer('Connecting…', 0), 'Connecting…');                     // the boot banner opens the window
  assert.equal(l.offer('1 thing needs you', 1000, true), null);              // the arrival waits
  assert.equal(l.offer('Archeus updated mission M, approval', 1200), null);  // the same event's thread update
  assert.equal(l.flush(4999), null);                                         // still one per 5 s
  assert.equal(l.flush(5000), '1 thing needs you');                          // said, not replaced
  assert.equal(l.flush(10000), null);                                        // the dropped update is not said late
  assert.equal(l.offer('2 things need you', 10001, true), '2 things need you');
  assert.equal(l.offer('3 things need you', 11000, true), null);
  assert.equal(l.offer('Archeus updated mission N', 11500), null);
  assert.equal(l.flush(15001), '3 things need you');                         // a newer count replaces an older one
});
```

- The existing M19 test stays unchanged, so plain offers remain latest-wins.
- Mutant for `tools/mutate_p19_5.py`: drop the kept-offer guard. The test then fails at `flush(5000)` with the thread text.
- Once B lands, `_quiet` in `test_spa_arrival.py` can be removed in its own card, which would give the e2e check of the real case. Not proposed here.

## 5. Decision needed from the owner

*Superseded by C-1012-T018 §4: option (b) below names only A-05; the restated decision lists everything (b) gives up.*

> When the polite region's 5 s rate limit (p16 §17) forces one announcement out, which one gives way? Choose one:
> (a) the latest offer wins, as built: an attention arrival (A-08) may go unannounced, and A-08's "announced" is recorded as best-effort;
> (b) an attention arrival is never replaced by a non-arrival announcement while it waits: a thread update (A-05) in the same window may go unsaid (option B);
> (c) the two are joined into one announcement (option E).

Until the owner chooses, nothing changes in the product. T-006's scoped test repair stands as approved.

## 6. Not claimed

- T-006 does not show that announcements are free of collisions. It moved the test out of the boot window. The collision remains in the product, as the T-006 review says.
- The reconnect, two-missions and graph-focus cases in §1 come from reading the code. None was run.
- The second T-006 cause (a late first read is a baseline) is A-08 working as specified. This note does not touch it.

## Correction C-1012-T018 (2026-10-12, after reviews/T-018-analysis.md)

Prepared by Claude, 2026-10-12. Same limits as the note: no code change, no browser, no test run, no decision. Sections 1-6 stay as written; where they conflict with this correction, this correction holds. Source: `clients/app/src/a11y/announce.ts` at `661adb2` (unchanged on `archeus-v1-rearchitecture` since), and the four polite callers found by grepping `announce(` in `clients/app/src`.

### 1. What the DOM writer does (review finding 1)

`announce(text)` (`announce.ts:51-62`):
- calls `polite.offer(text, Date.now())`; when the window is open the text is written (`:53-54`);
- otherwise it **clears and re-arms** the flush timer for a full `POLITE_EVERY_MS` from *this* offer (`:56-60`). Each held offer pushes the flush another 5 s out. While offers keep arriving less than 5 s apart, the timer never fires.

`offer` itself (`:19-27`) has a fast path: the first offer at or after `last + 5000` is said at once and sets `pending = null` (`:22`), **discarding whatever was held**.

So under a burst of polite offers, such as a keyboard walk over the graph (`GraphView.tsx:375`, one offer per focus move), nothing held is flushed. The burst's own next offer after the window is said instead, and the held item is dropped. That loses an arrival under today's code. It **also loses it under option B as written in §3**: B's keep guard protects the arrival from replacement by `pending = text` (`:25`), but neither from the re-armed timer nor from the `:22` discard. The §4 unit test cannot see this because it calls `flush` by hand and never makes a plain offer after the window. Even without a burst, one held offer at `last + 4999` is flushed at about `last + 9999`, because the delay is counted from the offer rather than from `last`. That is later than §17's rate requires, though not in conflict with it.

A precision on §1: one plain offer after an arrival, inside an already-open window, is enough to replace the arrival. That is the boot case: the banner opened the window, then the arrival, then the thread update.

### 2. Option B, amended: a timer and deadline contract, and a burst test

B holds an arrival only with all three of these:
- **B1 (rate, unchanged).** At most one polite write per 5000 ms (§17).
- **B2 (one timer per window).** The flush timer is armed when the window first holds something, for `last + POLITE_EVERY_MS - now`. A later held offer does not re-arm it.
- **B3 (no fast-path discard of a kept item).** When `offer` finds the window open and a kept item pending, it says a newer kept item if that is what arrived. Otherwise it says the pending kept item, and the incoming plain one is dropped.

Deadline these establish, under the fake clock only: an arrival held in the window that opened at `last` is written no later than `last + 5000 + 30` ms. The 30 ms is `write`'s clear-then-set delay, `:48`. That is a bound on timer scheduling, not a guarantee of speech: it says nothing about timers that fire late (a hidden or throttled tab), or whether a screen reader speaks the region.

Burst test. It goes in its own file, `clients/app/test/announce.test.ts`, because `announce`'s limiter and timer are module state. It uses `node:test` `mock.timers` for `setTimeout` and `Date`; `package.json` requires Node ≥ 22. Not run.

```ts
import { test } from 'node:test';
import assert from 'node:assert/strict';

test('a kept arrival is written by its window deadline under a burst of plain offers (A-08, §17)', async (t) => {
  t.mock.timers.enable({ apis: ['setTimeout', 'Date'], now: 0 });
  const writes: [number, string][] = [];
  const el = { get textContent() { return ''; }, set textContent(v: string) { if (v) writes.push([Date.now(), v]); } };
  (globalThis as any).document = { getElementById: (id: string) => (id === 'live-polite' ? el : null) };
  const { announce } = await import('../src/a11y/announce.ts');
  announce('Connecting…');                                    // t=0 opens the window
  t.mock.timers.tick(1000);
  announce('1 thing needs you', true);                        // t=1000: held, kept
  for (let at = 1200; at <= 12000; at += 300) {               // a keyboard walk: one plain offer per 300 ms
    t.mock.timers.tick(at - Date.now());
    announce(`Task T${at}, 2 relationships.`);
  }
  t.mock.timers.tick(10000);
  const arrival = writes.find(([, v]) => v === '1 thing needs you');
  assert.ok(arrival, 'the arrival is said');
  assert.ok(arrival[0] <= 5030, `by the deadline of the window it was held in, not at ${arrival[0]}`);
  for (let i = 1; i < writes.length; i++) assert.ok(writes[i][0] - writes[i - 1][0] >= 5000, 'one per 5 s'); // §17
});
```

Mutants, each must fail this test:
- **restart-on-every-offer** (today's `:56-60`): no flush fires during the burst, so the arrival is not written by 5030.
- **fast-path discard** (today's `:22` applied to a kept item): the walk text is said at 5100, and the arrival never is.

The §4 limiter test and the M19 test stay as they are. B's signature becomes `announce(text, keep?)`, and the arrival host at `App.tsx:510` passes `keep`. The size estimate in §3 (about 6 lines) is withdrawn. B2 and B3 add a timer-state check and a fast-path branch. No new estimate is given until the code is written.

### 3. What B gives up (review finding 2)

There are four polite callers in `clients/app/src` (grep of `announce(`; the assertive `announceApproval` is separate). While an arrival is held, B drops **every** plain offer for the rest of that window, at most 5000 ms per held arrival:

| Dropped under B | Caller | What requires it | What still reaches the user |
|---|---|---|---|
| the thread update (A-05) | `Now.tsx:316` | rulebook §20 `:579`, §21 `:610` ("live region") | the card and link; the drawn line |
| the graph focus announcement | `GraphView.tsx:375` | p16 `:1115-1116`: the canvas "announces the focused node and its relation count" | the off-screen list mirror (p16 `:1116`). A screen-reader user walking the canvas hears nothing for their key presses until the window closes, and the last of them is never said. |
| the connection banners' spoken text | `App.tsx:231-232`, `connection.ts:83-91` | p16 §13.1 (`:636-646`) specifies the banner as on-screen UI. Speaking it is the implementation's choice; I found no canonical text requiring it (a search of p16 and the rulebook, not exhaustive). | the visual banner. "Offline — nothing you do here is sent" and the signed-out text are the ones that tell the user their actions are not reaching Archeus. |

Under (a), as built, the reverse holds: the arrival is the thing that can be dropped, and these kinds already replace one another under latest-wins. **B does not satisfy A-08 and A-05 together**, nor A-08 and the graph focus contract: inside a window, B makes A-08 win over both. Section 2's claim that "the contracts do not conflict as written" still holds for the texts, but the rate makes them compete, and choosing who loses is the decision. B is one candidate, not a resolution.

(c), coalescing, gives up nothing outright, but it needs the same B2/B3 timer contract. It must also bound what it joins: a walk produces an offer per key press, so "join everything" grows without limit. The natural bound is the arrival plus the latest plain offer.

### 4. The decision, restated

> When the polite region's 5 s rate limit (p16 §17) forces announcements out, which give way? Choose one:
> (a) the latest offer wins, as built: an attention arrival (A-08) may go unannounced, and A-08's "announced" is recorded as best-effort;
> (b) an attention arrival is kept and written by the end of the window it was held in (the B1-B3 contract above); every other polite announcement offered while it waits goes unsaid: the thread update (A-05), the graph focus announcement (p16 :1115-1116), and the connection banners' spoken text;
> (c) the arrival and the latest other announcement in that window are joined into one announcement, under the same timer contract.

Nothing changes in the product until the owner chooses. Under today's code, whatever option is chosen, a held polite item is postponed for as long as offers keep coming (`:56-60`), and is then discarded by the next offer after the window (`:22`). That holds under (a) too, for whatever happens to be latest. It is recorded here, not decided.

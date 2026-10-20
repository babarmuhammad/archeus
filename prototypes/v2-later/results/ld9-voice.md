# LD-9: "the honest record" — the language layer, tested on real V1 strings (2026-10-05)

**Result: the language layer is the cheapest, highest-value change in this phase, and it is
mostly deletion.** 0.51 KB marginal (`le6`), and on every screen the probe walked it took the
count of machine strings at the first two depths from 3 kinds (ISO timestamps, policy grammar,
policy enums — on V1's Now and Attention) to **0** without hiding anything: the raw policy record
is one level down, in mono, in a "Policy record" disclosure. Whether the sentences are *right* is
a human test (§4). The personality direction itself (P2) is a recommendation, not a measurement.

## 1. Before and after, string by string

Left: what V1 prints today (D-captures, `prototypes/v2-later/v1-diagnosis/`). Right: what the lab
prints from the same record (`lab/ia.js`, `language` fence).

| Where | V1 today | Lab (B/C) | Rule |
|---|---|---|---|
| Now, hero | "Archeus is idle. 4 need you." | "3 need you · 2 running · 2 stopped" + "Fix the flaky date test (archeus) is on step 4 of 7: run the date suite 50 times." | Verdict, not greeting; the running work named (rulebook §5) |
| Approval, title | "Approve this plan version for Deploy release notes to staging · plan v1" | "**Approve plan v2** for Deploy release notes to staging" | Verb first, version in the verb |
| Approval, consequence | (none on the row) | "3 tasks · includes a deploy · expires in 8 min" | Consequence from the record only (LE-2 §2) |
| Policy, twice | `ASK — ASK deploy: profile:standard@2:USER:deploy (ASK, USER); builtin:floor:deploy-prod (ASK, GLOBAL, locked)` (Policy **and** Why it asks) | "Deploying is an action your policy asks about every time, and deploying to production is locked." Raw string once, at depth 3 | No machine language at depth 1–2 (§10) |
| Expiry | `2026-10-06T09:54:11.148Z (in 24 h)` | "expires in 8 min" · "expires tomorrow" | Words, never ISO |
| Task / class / target | `work · Do the work` · `deploy` · `task:work` | The planner's one-sentence summary, **labelled as the planner's** | Model-written text says so |
| If you approve / reject | "the plan runs; its tasks dispatch under it" / "the mission is cancelled" | The buttons: Reject · Ask for changes · Approve | Named verbs; consequence already said |
| Running row | "● Active · Deploy… · (empty status line) · just now" | "Fix the flaky date test · Run the date suite 50 times · step 4 of 7 · 20 min" | Present tense for what is happening |
| Blocked row | "■ Blocked · Write the migration…" | "blocked because check “rollback” failed (exit 1): test_migration_rollback" | Failed: what broke, from the record |
| Since you looked | "verification.started · Rename… · seq 31" | "15:00 · Rename the billing module — verification started" | Events in words with a clock time |
| Decided for you | (absent: silence) | "Decided for you by policy today · 3" (collapsed) | Silence is not a record (§14) |
| Done | "✓ Done" | "verified 10:51" | Done means verified, said plainly |

## 2. Voice, as applied

Plain, precise, impersonal, slightly dry; no exclamation marks; no effort adjectives ("working
hard…"); numbers and nouns. Tone by state: *done* — "verified 10:51"; *needs you* — verb + object
+ consequence + expiry; *failed* — what broke, from the record, then the next actions with the
first focused; *offline* — not exercised in this lab (A §O already specifies "as of hh:mm").

## 3. Two things the voice work exposed

1. **"Honest" constrains the copy, not just the light.** The most natural sentence is often one
   the record cannot support ("deploys to staging", "changes 14 files", a third *because*). The
   lab's first draft wrote three of them; all three were removed (LE-2 §2). A copy rule is
   needed: *every clause in a sentence names the field it comes from.*
2. **The planner's prose is not Archeus's voice.** "Plan v2 is ready: 3 tasks; the last one
   deploys" is model-written. It is useful and it must be attributed ("It said", "The planner's
   summary").

## 4. Human test owed

A comprehension check on the decision page, cold: show the V1 approval card and the lab's
decision page for the same plan (randomised order) to the user and ≥ 2 others, and ask
"what happens if you press Approve?" and "why is it asking you?". Pass: the lab's answer is
correct and faster for every participant. Not run.

## 5. Classification

Direction (P2 + the voice table): **recommend accept as the direction for copy work**. Each
string still lands with the screen it belongs to, and the "every clause names its field" rule
becomes a rulebook entry if approved.

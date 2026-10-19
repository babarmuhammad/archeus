STATUS: review
1 - p20 open-questions table row re-cited to p20-design-gate.md:2233 (was 2770); verified the "O7 (deferred)" row is at 2233 in the b73f875 checkout.
2 - P14 backoff idiom re-cited to p14-design-gate.md:461-462 (was 469-470); verified the "next pass after its backoff ... floor, not a schedule" text is at 461-462.
3 - Section 3.3 pairing unlock corrected to monotonic clock: clock=time.monotonic at auth.py:212, unlock check now=self.clock()/now<self._locked_until at :223-225 (was "wall clock :224-225").
4 - Section 3.4 manual-recovery claim demoted to a candidate model; decision requires "recovery/reconciliation" but does not decide manual-vs-automatic, cross-referenced to open Q5.
5 - Section 4 Case B step 4: removed "every pass"/"never" scheduling claims; kept indefinite uncounted redispatch (manager.py:116-141, runtime.py:293-295), noted a no-work pass may still take EXEC_S wait.
6 - Section 4 Case C: Isolation.requested() qualified to a fresh production request; existing records return True first at isolation.py:690-691, production switch gates only new requests at :694-695.
7 - Added owner question Q10 (restart-reconcilable retry state: which counters/deadlines/OPEN survive or are reconstructed; whether restart may replenish the retry budget); section 5 updated to Q1-Q10.
8 - Section 5 minimum decision set now includes Q4 (bounded backoff) and Q8 (enforcement location), plus Q10; Q9 noted as gating where it may be built.
Note: a "## 2b. Correction 2026-10-19 (Qwen) - reviews/T-110-analysis.md" section was added to the note answering all 8 findings by number with new file:line.

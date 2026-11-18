# P19.5 travelling marker — handoff (work in progress, uncommitted)

Base: `687aaaf` on `archeus-v1-rearchitecture`. Nothing committed or pushed for this slice.
Stopped at the user's request mid-slice.

## Source/target finding (the prompt's STOP condition does NOT apply)

The existing data gives an authoritative source → target, the same one the built pulse uses:
the SSE frame's `data.subject` (an `execution`) and Core's recorded `executions.task_id` edge in
the graph read. Source = the execution's visible (lifted) node, target = the other end of that
drawn edge (the task, or its visible ancestor). No geometry, adjacency or guess. No Core change.

## Done in the working tree

- `src/graph/model.ts`: `Travel`, `markerFor(f, model, vis, drawn, live)` (execution.* frame,
  loaded execution, drawn LIVE `executions.task_id` edge; one per frame = per output batch;
  reduced motion left to the timeline), `markerTarget` / `travelOf` (JSON `[edge, from, to]`).
- `src/graph/render.ts`: `Scene.marker?` (markerTarget → p); `drawMarkers` after `drawPulses` in
  both `draw` and `frame`; linear head at p along the straight edge from→to, `MARKER_HEAD` 3 px
  disc + `MARKER_TAIL` 12 px tail (screen px, `--thread` ink, rulebook §38 token), tails one path,
  heads one path; skipped if the drawn edge no longer joins its two ends; degraded → the A-02
  pulse form (whole-edge opacity step, `--state-active`), per rulebook §21-§22 "degraded → pulse".
  `marker` is NOT in `staticSig` (correct: it is over the layer).
- `src/graph/mirror.ts`: an `executions.task_id` edge whose execution is haloed (live) gets
  `live: true` and the text suffix " — live now" (the registry's text equivalent).
- `src/graph/GraphView.tsx`: `modelRef`/`visRef`; in `store.onFrame`, marker started via
  `timeline.start('travelling-marker', markerTarget(t), f.id, now, host.reduced())` then
  `loop.animate('travelling-marker')` (independent of the pulse, before it); scene reads
  `timeline.progress('travelling-marker', now)`; `data-graph-markers` count; mirror edge `<li>`
  gets `data-live`.
- `tokens/motion.json`: `travelling-marker` → `built`, trigger/reduced/equivalent reworded,
  surfaces narrowed to `["graph"]` (operations map not built); 600 ms / cap 8 / drop-oldest /
  linear unchanged. `src/state/motion.ts` regenerated (`gen_ui --check` passes).
- Verified so far: `tsc` clean, client tests 94/94 (existing tests only).

## Not done yet

1. `test/motion-harness.ts`: `renderAt` must also pass `marker: tl.progress('travelling-marker', t)`.
2. `test/marker.test.ts`: the prompt's 18 unit cases (no event → none; eligible → marker at source,
   mid, reaches target, gone after 600 ms; no replay; reconnect/remount/route = same timeline;
   reduced motion recorded-not-drawn; cap 8 + oldest dropped; newer event new marker; idle loop
   0 frames; completion → parked; two pairs independent; unrelated nodes unchanged; unrelated
   event (non-execution / no live edge / not loaded) → none; degraded → pulse form; mirror words).
3. `tests/v1/e2e/test_spa_marker.py` (model on `test_spa_motion.py`'s replay test, `slow`
   fixture): positive control, same seq again mid-marker and after 600 ms → no new marker
   (`data-graph-markers`), older seq → none, newer → one; stream-lost/stream-open/resync → no
   restart; remount → no replay; reduced-motion page → 0 markers and 0 frames but live edge;
   framebuffer probe of thread-ink pixels near source at start, mid-edge at 300 ms, near target
   at ~590 ms, none after; 9 frames of distinct seqs → at most 8 drawn. Run 3×.
4. `tools/mutate_p19_5.py`: N38+ for every mutation the prompt lists (not rendered, duration,
   >600, cap≠8, oldest-drop, replay, reconnect replay, random path, reduced motion, perpetual,
   survives completion, wrong source/target (swap from/to), unrelated event, idle loop).
5. Docs: design system §8 "travelling marker as built", testing-strategy §7 rows (caps, no replay
   → built for the marker, a marker row), reference ADR-0024.
6. Full validation list from the prompt (design gates, P16/P18 e2e, V1 suite, ruff, build, gen_ui)
   then ONE commit; do not push; do not start the next slice.

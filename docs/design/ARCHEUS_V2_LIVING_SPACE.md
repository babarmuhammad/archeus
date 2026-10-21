## Round 10f phone (2026-10-22): Overview polish and the two sheets

All three phone frames are now concept rasters with the live layer on top: the Overview (phone-1), the decision sheet (phone-2)
and the chat sheet (phone-3). Text floor: 11 CSS px at each master width, with the owner-approved 10 px list for the three
sub-lines Review plan, Codex and Verifying only. Glows are live SVG blur filters measured from the concept. The decision sheet is
the first step of the two-step decision (What / Why / Core consequence, then Open decision, then the explicit confirm). The chat
sheet opens from the Tell bar and starts with the Start card for Export backup. README round 10f lists the residuals with numbers.

## Round 10d phone (hybrid, 2026-10-22): concept raster as the art

Status: complete with residual differences. README round 10d lists them with measured numbers.

Method changed from the traced SVG to the hybrid the owner chose. The phone Overview's picture is the concept raster with every live element removed (`clients/v2-prototype/art/phone-1-base.webp`, rebuilt by `tools/build_phone_art.py`). The live layer sits on the concept's measured units: text in vendored EB Garamond and Inter, the mission marks, the Review button, the chip, the Tell bar and Stop.

Frame: 1:1 at 402 css px wide (804 x 1373 units, DPR 2). On taller phones the header is anchored to the top, the Tell bar and Stop to the bottom, and the art is centred between them with its background extended from its edge rows.

Measured full-frame mean absolute difference against the master: 5.59 (scene 5.79), unblurred, full resolution.



## Round 10c phone (partial, 2026-10-21): SVG Overview in the concept units

Status: partial. The phone Overview is one SVG in the concept units (804 x 1373, the file on disk; the brief said 804 x 1748, see the README). Labels are SVG text with a halo, 32 units minimum (14 CSS px at 360). Overlap probe zero at 360 to 440. Luminance MAD 7.5 to 7.9 across iterations, not falling after iteration 2 (README table). Remaining differences are numbered in the README round 10c section. Desktop and the other screens are unchanged.

## Round 10b (partial, 2026-10-21): measured Overview layout

Status: partial. Desktop and phone Overview were driven from a measured table (`CONCEPT_LAYOUT`) read from labelled grids over the Codex concepts. Phone-2 and phone-3 were not compared in this round. Known open items: the phone Archeus project label collides with the Codex label at 360 to 440 CSS px (a breach of the zero-overlap rule, stated plainly in the README). Owner decisions kept: Uncertain 09:24 and Needs you 09:25 amber; Verification and Results as blue chain dots.

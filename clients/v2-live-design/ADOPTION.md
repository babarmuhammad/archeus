# Adopting the design kit into clients/v2-live

Status: verified by render (tools/v2_live_design_probe.py), not yet adopted. Nothing in clients/v2-live changed in this branch.

The kit is namespaced: every class is `ds-*`, tokens are the same variables v2-live already defines. v2-live uses bare classes (`.btn`, `.card`, `.badge`). Merge by renaming the kit selector to the app selector as you move each piece, or by adding the kit file next to app.css and migrating view by view. Do not load both rules for the same element.

| Kit piece | v2-live file | Action | Notes |
|---|---|---|---|
| tokens.css | css/tokens.css | none | Identical values (checked: only blank lines differ). Keep the app copy. |
| dom.js | js/dom.js | none | Same `h`, `s`, `clear`. |
| fonts/ | fonts/ | none | Same Libre Caslon Text TTF and OFL. |
| icons.js (81 icons, `icon(name, size)`) | js/icons.js | replace | Superset of the 22 existing keys, same API, same 24 px grid. Drop-in: existing callers keep working. Default size is 22 as before. |
| components.css, buttons (`.ds-btn`, `primary`, `quiet`, `danger`, `danger outline`) | css/app.css `.btn*` (l. 153-160) | extend | Amber primary inside decision/approval cards and sheets, solid red `danger` for Stop, outline for Reject. Forced-colors rules included. |
| components.css, badges and chips | css/app.css `.badge`, `.chip`, `.chips` | extend | Kit adds a glyph per state; the app already sets `data-role` colours, keep its `present()` mapping and swap only the look. |
| components.css, cards (7 recipes) | css/app.css `.card`, `.cardbox`, `.band` and js/views.js `attentionItem`, `missionRow`, `cardNode` | extend | Recipes: mission, decision, approval, status, plan, idea, knowledge. Map to the existing `kind` values. |
| components.css, `.ds-spine` | js/spine.js and css `.spine*` | keep app | ADR-0054 spine stays the source (drawn per size, static). The kit spine is a DOM reference for the 6 stations, labels and the narrow-width rule: at under 480 px the station names go to screen readers and the sentence stays. |
| components.css, frame, rail, bottom bar, inspector, sheet | css/app.css `.rail`, `.bottombar`, `.inspector`, `.pane` and js/app.js | extend | Kit uses a container named `ds`; the app uses `dev` and `view`. Rename when merging. Sheet focus trap and inert background stay in app.js (the kit sheet is a specimen). |
| components.css, inputs, chat, slash | css/app.css `.composer`, `.slash*`, `.sel-wrap` and js/views2.js `viewChat` | extend | |
| components.css, usage meter | js/views.js `meter` | extend | Marks at 20/40/60/80/100, hatched unknown state. |
| components.css, tables, lists, toast, banner, tooltip, skeleton, empty | `.toast`, `.empty`, `.tl*`, `.row-line` | extend | Tooltip uses `display:none` (a hidden absolutely placed tooltip stretched the page). Skeleton stays static (ADR-0055). |
| brand.js `coreMark(running, count)` | js/views.js `coreMark(live, n)` (l. 68) and css `.core*` (l. 259-272) | replace | Same hook: `data-core='idle'`/`'breath'` and `data-live`. New 8-ray star; the breath rule moves to `.ds-core[data-core='breath'][data-live='true'] > .core-breath`. Only infinite animation. The `.core-txt` running count becomes `.ds-core-static`. |
| brand.js `wordmark()`, `lockup()` | css `.tb-brand`, `.rail-head` | replace | |
| favicon.svg, pwa-icon.svg | icon-192.png, index.html `<link rel=icon>` | replace after owner review | Needs a 192 px PNG render. |
| illustrations.js `illustration(name)` and `facet()` | js/views.js `empty()` | extend | Five empty states: missions, clear, offline, error, first. `facet()` also draws the polyhedron nodes in js/map.js. |
| gallery.* | none | keep as dev tool | Run `?specimen=1`; probe below. |
| DESIGN.md | docs/architecture | reference | |

## Order that conflicts least

1. icons.js (pure superset), fonts untouched.
2. Buttons and badges (`css/app.css` only, no markup change).
3. Core mark and brand (js/views.js `coreMark`, `.core*` css).
4. Cards and empty states (views.js, views2.js).
5. Map nodes (js/map.js) using `facet()`.
6. Icon, favicon and PWA assets after the owner approves the new star.

## Guard

Run `py -I tools/v2_live_design_probe.py` after each step; it also works against a merged tree if you pass `--css-dir` pointing at a folder that serves gallery.html. The existing `tools/v2_live_layout_probe.py` stays the gate for the app itself.

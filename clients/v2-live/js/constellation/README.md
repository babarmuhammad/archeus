# V2 Live constellation

Standalone SVG renderer. Plain ES modules, no dependencies, no build, no network resources. The prototype and main V2 Live app are untouched. The demo is explicitly a fixture simulation, not evidence of Core activity. Light styling is a review candidate awaiting owner sign-off.

## Run

From the worktree root:

```powershell
py -m http.server 8000
```

Open `http://localhost:8000/clients/v2-live/js/constellation/demo.html` (add `?embed=1` for the bare map filling the window). ES modules require HTTP rather than a `file:` URL.

## API

Give the container an explicit height. Import `map.css` once.

```js
import {createMap, edgeId} from './clients/v2-live/js/constellation/map.js';

const map = createMap(container, {
  seed: 'workspace-id',
  theme: 'dark',
  reducedMotion: false,
  label: 'Your work constellation',
  live: false,
  fresh: true
});
map.update({
  nodes: [{id: 'mission-1', kind: 'Mission', label: 'Review sources',
    state: 'needs-you', project: 'project-1', weight: 4}],
  edges: [],
  projects: [{id: 'project-1', label: 'Research'}]
});
const unsubscribe = map.on('select', id => console.log(id));
map.setSelection('mission-1');
map.fitView();
unsubscribe();
// When unmounting:
map.destroy();
```

`createMap(container, options)` returns:

| Method | Behavior |
| --- | --- |
| `update(graph)` | Copies input, validates unique node IDs, diffs the DOM by node and edge id (elements are reused and their attributes patched; only a changed id, kind, project, weight or crystal state lays out again), and deterministically lays out structural changes. Exact repeated input is skipped. Missing edge endpoints are ignored. |
| `setSelection(id)` | Selects a node; `null` clears. Reveals offscreen selection. Emits `select`. |
| `setTheme(name)` | `dark`, `light`, `dark-high-contrast`, `light-high-contrast`, `system`; `high-contrast` aliases dark high contrast. |
| `setReducedMotion(bool)` | Enables or disables Quiet explicitly; before it is called (or when `reducedMotion` is not an option) the system preference decides. |
| `resize()` | Measures container and relays out when dimensions change; also called by `ResizeObserver`. Resizing resets camera. |
| `fitView()` | Fits node envelopes inside viewport with room for controls. |
| `pulse(edgeId)` | One 600 ms travelling marker; returns false when missing, hidden, reduced, destroyed, or already at eight simultaneous markers. |
| `on(event, fn)` | Subscribe; returns unsubscribe function. Events: `select` (ID or null), `update` (`{nodes}`), `resize` (`{width,height}`), `viewchange` (`{x,y,k}`), `pulse` (edge ID). |
| `setLive(bool)` | Switches the core breath on or off after creation (the host passes a playing simulation with fresh output). |
| `setAmbient(bool)` | Switches the ambient motion (drift, rings, travelling markers) on or off; the host passes whether the simulation is playing. |
| `element` | The map's root element. |
| `destroy()` | Disconnects observer and external listeners, cancels animations, removes owned DOM. Idempotent. |

Edges accept optional `id`. Otherwise `edgeId(edge)` returns `from->to:kind`, with `relation` as the default kind. Parallel edges with identical endpoints and kind need distinct explicit IDs. Node IDs are strings, unique within one map. Data strings are inserted through DOM text/attributes, never HTML. Missing projects group under Unassigned. Weights clamp to 0.25–100. Node kinds: Mission (disc, or a faceted crystal when it is running or needs you, drawn about three times larger), Project (hexagon), Knowledge (square), Idea (sparkle), Execution (triangle), Decision (diamond). `options.t(string)` translates every fixed string (state and kind words, controls, table headings, status text). Supported states are `idle`, `running`, `needs-you`, `blocked`, `done`, `paused`, `thinking`; capitalization and spaces/underscores normalize, and `waiting`, `attention`, `active`, `completed` are accepted aliases.

V2 Live adds ambient motion on top of the core breath (owner decision 2026-10-27; the real V2 app still follows ADR-0055). While `data-ambient="on"` (a playing simulation, full motion, a visible tab and map, not the calm scene) nodes drift 1.5 to 3 px (`am-drift`, 9 to 17 s, seeded by id), needs-you and running nodes send out a soft ring (`am-ring`, 3.6 s), and running relations carry a marker (`am-travel`, 3.7 to 7 s). All loops are transform or opacity, under 0.3 Hz, and never the only carrier of a state. Nodes lift 7 percent under the pointer or keyboard focus, new nodes grow in from 90 percent over 160 ms (staggered 30 ms), and the hairlines of the selected or hovered node brighten. Reduced motion shows the static twin. The layout probe checks the allowed list.

The core mark: scale 1 → 1.018 → 1 in 6000 ms. `live: true`, `fresh !== false`, a Running node, visible document, and full motion are all required. Defaults are static. Demo opts into simulated live work explicitly because the task requests it; ADR-0055 forbids fixture-driven liveness in the real app. Integration must pass real freshness/liveness; recreate the map when those options change. Quiet shows a static count at the core. Hidden tabs cancel transient effects and stop breath. Re-reading does not replace the core DOM element or restart its animation.

`MOTION` exports the local duration registry: appear 160 ms, relation 240 ms, label 160 ms, travel 600 ms, breath 6000 ms. The label duration is 160 ms (ADR-0055). Selection, focus, layout, pan and zoom are instant. No frame loop, large blur, backdrop filter, or external asset is used.

## Layout and visual treatment

`geometry.js` holds the DOM-free functions. The look follows the concept art: a near-black violet ground with a faint haze, a seeded scatter of static dust stars, thin ivory hairlines, faceted project hulls, a faceted eight-point core with a letter-spaced serif wordmark, and serif labels with a small-caps eyebrow. Nothing is a raster. Glow is an SVG radial gradient; there is no filter, blur or backdrop filter anywhere.

Layout. Project IDs sort; each project is a cluster of its members, ordered Project kind first, then by weight, then ID, laid on a golden-angle spiral (phyllotaxis) around the cluster centre, with a seeded jitter per node. The clusters sit on an ellipse around the fixed core. The module searches twelve rotations of the ring and bisects the node spacing for each, keeps the rotation that allows the widest spacing (spacing capped between 14u and 66u), and then relaxes four passes of pairwise separation. `u = clamp(sqrt(w*h)/900, .9, 1.6)` scales node radii, the core and type with the container. Output is a pure function of graph, size and seed; nodes are returned sorted by ID so input order never matters. The bottom 60 px is reserved for the controls.

Hulls. Each cluster gets a convex polygon (the hull of the member centres grown by the padding, every corner an octagon, so thin clusters get faceted ends and never spikes) with rounded corners, a radial tint fill, a hairline, tiny corner dots and, from 480 px up, an inset facet polygon with spokes. The hairline turns amber when any member needs you, blue when any member runs. Clusters are pushed apart as real polygons until no two hulls touch and none touches the core star or its wordmark. Thin spokes join the core to every cluster. Edges are quadratic curves, bent more between projects than inside one; an edge touching a needs-you or running node takes that colour.

Nodes. The body shape tells the kind: disc Mission, hexagon Project, hollow square Knowledge, four-point sparkle Idea. State is never colour alone: Done solid with a check, Running hollow with four ticks, Needs you a static diamond ring with a mark and an amber glow, Blocked hollow with a cross, Idle hollow with a dot, Paused bars, Thinking a diamond. Running and needs-you missions are large faceted crystals (40 px radius at desktop, 24 on phones) with vertex dots and a small inner mark on a background plate (a ring and dot for running, an exclamation mark for needs you). The selected node gets a dashed focus ring.

Camera. The core lives in the world layer, so it pans and zooms with the stars and the spokes stay attached. Wheel and pinch zoom around their midpoint, drag pans, zoom clamps to 0.5 to 4 and pan to one scaled viewport beyond the origin. Fit and Reset are separate. A click selects the node nearest the pointer within 22 px (24 px under 480 px wide), so overlapping 44 px targets never steal a tap; the invisible hit circles remain for keyboard focus and for assistive technology, and a click without coordinates (assistive activation) selects its own target.

## Label placement

Labels are screen-space SVG text with a background-coloured halo, no box; a soft background-coloured gradient plate under each label fades the edges that run behind it, and a hairline leader joins a label that sits far from its star. Metrics come from a canvas using the same serif stack, cached per call. Priority is selected, then Needs you, then Running, then weight, then ID. Candidates try right, left, above and below at three distances (five for mandatory labels); a mandatory label may also fall back to a shortened title with an ellipsis. Every accepted rectangle avoids earlier labels (4 px gap), every node disc (3 px gap, found through a 64 px spatial hash), the core mark with its wordmark, and the controls. Below 480 px at most five ordinary labels show, below 1280 px thirteen, from 1280 px thirty with a small-caps kind and state eyebrow. Selected and Needs you bypass the budget. If a mandatory label still cannot fit, it is omitted, `data-label-overflow` on the map records the count and a status message points to the full node table.

## Accessibility and theming

The single SVG has an image title and summary. Every star has a focusable named target, Enter/Space selects, and arrows find the closest forward node with an angular penalty. Focus auto-reveals offscreen nodes. Native Tab visits all nodes and controls. SVG image descendants are inconsistently exposed by screen readers, so an external visually hidden HTML table also contains every full node label, kind, state, project, and selection button. Focusing a table button exposes the table as an opaque panel. Selection returns focus to the star. A live status announces label overflow.

Palette defaults follow the supplied visual-language document, including green Done, `#F07178` Blocked, and `#FFF3CF` dark focus. All styling is scoped to `.archeus-map`. Override `--am-*` custom properties on that element. Explicit high contrast, system color scheme, `prefers-contrast: more`, `prefers-reduced-motion`, and forced colors are supported. Forced colors uses system ink, canvas and highlight, removes glows, and preserves glyph distinctions. No remote fonts: labels use the `--am-serif` stack (Libre Caslon Text if the host loads it, else Iowan Old Style, Palatino, Georgia) and the eyebrow uses system sans. The serif for labels is a design choice taken from the concepts; the owner decision names the serif for the state sentence only, so confirm before the real app adopts it.

## Probe

`tools/v2_livemap_probe.py` (repository root `tools/`) drives `demo.html?embed=1` in Chromium at 320x640, 390x844, 768x1024, 1280x720, 1440x900, 2000x930 and 2560x1440, in dark, light and both high-contrast themes, plus reduced motion, forced colours and DPR 2. Serve the repository root (`py -m http.server 8861 --bind 127.0.0.1`) and run it through the shared lock: `py D:Archeus.collab	estlock.py -- py tools2_livemap_probe.py`. It checks label/label and label/node overlap, labels clear of the core and controls, every priority label shown, targets of at least 44 px (also zoomed out), one running animation at idle (the core breath, 6000 ms, scale 1 to 1.018 to 1) and none under reduced motion, a single finite marker per pulse, vector-only output at DPR 2, Tab, Enter and arrow keys, a click on every node, wheel, drag, Fit and Reset, label text contrast, no console errors, and 200-node update time. Unit tests: `py D:Archeus.collab	estlock.py -- node --test clients/v2-live/js/constellation/map.test.mjs`.

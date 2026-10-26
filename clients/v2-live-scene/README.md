# V2 Live scene art

Self-contained ES modules, no packages, build, remote requests, animation, filters, gradients, nebula or bloom. All displayed work is a concept fixture, not Core telemetry. Existing V2 Live files are untouched.

## Integration

Load `scene.css`, then import `sceneNow`, `sceneCalm` or `sceneMission` from `scenes.js`. Give the container a width and height.

```js
const scene = sceneNow(container, {
  theme: 'dark',
  t: (key, fallback) => translations[key] ?? fallback,
  onselect: id => openInspector(id),
  onreview: id => openReview(id)
});
// Later:
scene.setTheme('light-hc');
scene.destroy();
```

Options: `width` and `height` optionally pin layout dimensions; otherwise ResizeObserver reads the container. `theme` accepts dark, light, dark-hc and light-hc. Omit it to inherit app tokens. Return value exposes `element`, `resize()`, `setTheme()` and `destroy()`. Bubbling `scene-select` and `scene-review` CustomEvents carry `{id}`. Callbacks and events both fire: choose one integration route. Review only requests a review surface; it never approves work.

`nodeart.js` exports DOM factories: `missionPoly({seed,sides,state,icon,size})`, `projectPoly(options)`, `executionTriangle({size,state})`, `core({scale,t,tagline})`, `projectHexagon({title,items,t})`, `decisionMarker()` and `reviewButton({t,onactivate})`. Geometry is centred at the origin; place it in a translated SVG group. Factories do not insert nodes into the document. `s`, `text`, `line`, `icon`, `icons` and `randomSeed` are also exported. Icons contain twelve 24-grid line drawings, stroke 1.5. Size is the silhouette diameter in SVG units. Project items accept `{title,key,state}`; done items use small green dots, other items neutral dots. Standalone geometry is decorative until wrapped with accessible interaction by its caller; scenes supply that wrapper.

Styles use `--ink`, `--ink-dim`, `--blue`, `--amber`, `--green`, `--red`, falling back to app tokens and their dark palette. `--bg`, `--font`, `--serif` and `--focus` are supported. Explicit light/high-contrast themes provide local overrides. Actual forced colors use Canvas, CanvasText and Highlight, with opaque strokes. Titles/subtitles use Libre Caslon Text when supplied by the host; no font is fetched here. Gallery falls back to Georgia when that font is unavailable. Eyebrows and tracked ARCHEUS wordmark are sans serif, per this brief.

## Visual changes

The old map's small outline polygons, glow fields and label plates are replaced by large open mesh silhouettes, centre icons and clear labels outside geometry. Seeded outer vertices, jittered inner rings and triangle fans form deterministic facets; faint rear chords suggest depth. States change ink only. An opaque ground-colour disk keeps centre icons legible without illumination. The core consists of crossing threads and long axial spikes. Only its mark has `.core-mark`; no breath is installed.

Now follows concept 02's amber left mission, blue right mission, Notes upper right and Codex below. Calm follows concept 07's five hexagonal project panels, retained item rows and square relation joints. Mission follows concept 03's blue central mission, execution, verification, knowledge suite and results with six labelled causality arrows. Relations are fixture composition data, not inferred production relationships.

Below 600 CSS pixels, scenes switch to a vertical column with a small core and separated labels. The SVG keeps readable logical dimensions and scrolls vertically inside the container rather than squeezing all work into a phone frame. Desktop composition uses a 1320 × 840 viewBox, letterboxed at portrait tablet ratios. This preserves composition but leaves generous vertical space on tablets. The art module intentionally excludes app navigation, headline, inspector, safety controls and approval forms. Hosts must supply those surfaces.

## Review gallery and limits

Open `gallery.html` through the existing local static app server. ES-module loading from file URLs depends on browser policy; no server or network client is included. Gallery has 18 frames: three scenes × three sizes × dark/light, plus a high-contrast toggle. Exact frame sizes are 1440 × 900, 768 × 1024 and 390 × 844. Page scroll permits native-size screenshots; phone frames have internal vertical scroll. No concept PNGs are copied or loaded.

These are vector approximations, not pixel matches. Facets are ring/fan geometry with rear chords, not a true projected 3D geodesic solid. Fixture labels and spacing are authored, not a general arbitrary-graph label solver. Long translations may need wrapping or revised positions. Mobile relation lines preserve reading order rather than reproduce all desktop causality; desktop mission arrows show full labels. Gallery chrome is English; scene strings and accessible names accept `t(key,fallback)`. No browser or tests were run, as required by the task.

## Claude hand-off

- Render all 18 frames. Compare scene regions against 02, 03 and 07, using 04, 08, 13 and 15 for semantic context. Check dark ground, facet density, relative scale, core star, line hierarchy and serif font availability.
- Check labels, icons and polygons at every frame size; check translated long strings and browser zoom. Confirm no clipped labels, collisions or horizontal overflow inside the scenes. Page-level horizontal gallery scrolling is intentional.
- Measure node and Review hit rectangles in CSS pixels, including tablet letterboxing. Confirm minimum 44 × 44, no competing hit regions and visible focus. Exercise Tab, Enter, Space and click. Check event IDs and that Review never approves.
- Measure text contrast and active/amber strokes in dark/light/high-contrast. Faint rear facets are decorative; essential silhouettes and relation lines need visual review. Verify state words remain understandable without colour.
- Enable real Windows forced colors; check CanvasText/Highlight strokes, background masks, focus and state words. High-contrast toggle is not a forced-colors simulation.
- Resize live containers across 599/600 px, remove scenes with `destroy()`, verify observer cleanup and scrolling. Check reduced-motion mode remains entirely still.
- Wire only recorded data and authorised navigation in the host. Confirm ownership of Review routing, translated fixture names, and whether tablet letterboxing should be replaced with a distinct portrait composition.

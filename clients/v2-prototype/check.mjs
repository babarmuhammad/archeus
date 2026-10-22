import { readFileSync, existsSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';

const dir = dirname(fileURLToPath(import.meta.url));
const read = (f) => readFileSync(join(dir, f), 'utf8');
const failures = [];
const check = (ok, msg) => { if (!ok) failures.push(msg); };

const html = read('index.html');
const css = read('style.css');
const js = read('app.js');
const sw = read('sw.js');

const refs = [...html.matchAll(/(?:href|src)="([^"#:]+)"/g)].map((m) => m[1]).filter((r) => !r.startsWith('data:'));
refs.push('sw.js');
for (const r of [...new Set(refs)]) check(existsSync(join(dir, r)), `missing referenced file: ${r}`);
for (const r of ['index.html', 'style.css', 'app.js', 'sw.js', 'manifest.json', 'README.md']) check(existsSync(join(dir, r)), `missing file: ${r}`);

check(!/(src|href)="https?:/.test(html), 'index.html loads an external http(s) resource');
check(!/<script[^>]*type="module"/.test(html), 'index.html uses a module script (breaks file://)');
check(!/^\s*(import|export)\s/m.test(js) && !/^\s*(import|export)\s/m.test(sw), 'app.js or sw.js uses import/export');

let manifest;
try { manifest = JSON.parse(read('manifest.json')); } catch (e) { failures.push(`manifest.json does not parse: ${e.message}`); }
if (manifest) {
  check(manifest.display === 'standalone', 'manifest display is not standalone');
  check(Array.isArray(manifest.icons) && manifest.icons.length > 0, 'manifest has no icons');
  for (const icon of manifest.icons || []) {
    const path = join(dir, icon.src);
    check(icon.type === 'image/png' && existsSync(path), `manifest icon missing or not PNG: ${icon.src}`);
    if (!existsSync(path)) continue;
    const buf = readFileSync(path);
    const size = Number(icon.sizes.split('x')[0]);
    check(buf.subarray(1, 4).toString('ascii') === 'PNG' && buf.readUInt32BE(16) === size && buf.readUInt32BE(20) === size, `icon ${icon.src} is not a ${size}px PNG`);
  }
  check((manifest.icons || []).some((i) => i.purpose === 'maskable'), 'no maskable icon');
  for (const icon of ['icon-192.png', 'icon-512.png', 'icon-maskable-512.png']) check(sw.includes(`'./${icon}'`), `service worker does not cache ${icon}`);
  check(typeof manifest.start_url === 'string', 'manifest start_url missing');
}

for (const [name, src] of [['app.js', js], ['sw.js', sw]]) {
  try { new vm.Script(src, { filename: name }); } catch (e) { failures.push(`${name} does not parse: ${e.message}`); }
}

check(/serviceWorker/.test(js) && /\^https\?:\$/.test(js), 'app.js must register the service worker only over http(s)');

const tokens = {};
for (const m of css.matchAll(/--([\w-]+):\s*(#[0-9A-Fa-f]{6})/g)) tokens[m[1]] = m[2];
const hex = (h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16) / 255);
const lin = (c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
const lum = (h) => { const [r, g, b] = hex(h).map(lin); return 0.2126 * r + 0.7152 * g + 0.0722 * b; };
const ratio = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05); };
const mix = (fg, alpha, bg) => {
  const f = hex(fg), b = hex(bg);
  const out = f.map((c, i) => Math.round((c * alpha + b[i] * (1 - alpha)) * 255).toString(16).padStart(2, '0'));
  return '#' + out.join('');
};

const pairs = [
  ['text', 'bg'], ['text', 'surface-2'], ['text-2', 'surface-2'], ['text-2', 'surface'], ['text-3', 'surface-2'],
  ['amber', 'bg'], ['amber', 'surface-2'], ['blue', 'surface'], ['green', 'surface'], ['slate', 'surface'],
  ['bg', 'ivory'], ['ivory', 'bg']
];
for (const [a, b] of pairs) {
  check(tokens[a] && tokens[b], `token missing: ${a} or ${b}`);
  if (!tokens[a] || !tokens[b]) continue;
  const r = ratio(tokens[a], tokens[b]);
  check(r >= 4.5, `contrast ${a} on ${b} is ${r.toFixed(2)}, below 4.5`);
}
const sheetBg = mix(tokens.surface, 0.94, tokens.bg);
check(ratio(tokens.text, sheetBg) >= 4.5, 'translucent review sheet fails 4.5:1 for text');
check(ratio(tokens['text-2'], sheetBg) >= 4.5, 'translucent review sheet fails 4.5:1 for secondary text');
const barBg = mix(tokens.bg, 0.42, tokens.surface);
check(ratio(tokens.text, barBg) >= 4.5, 'translucent chat bar fails 4.5:1 for typed text');
check(ratio(tokens['text-2'], barBg) >= 4.5, 'translucent chat bar fails 4.5:1 for placeholder text');
check(ratio(tokens.focus, tokens.bg) >= 3, 'focus ring fails 3:1 against background');
check(!/webgl/i.test(js), 'app.js uses WebGL (the prototype is Canvas 2D only)');
check(/devicePixelRatio/.test(js), 'canvas does not size to devicePixelRatio');
check(/document\.hidden/.test(js), 'animation does not pause when the tab is hidden');
check(/reduce\.matches/.test(js), 'animation does not read prefers-reduced-motion');
check(!/https?:\/\//.test(css) && !/@import/.test(css), 'style.css loads an external resource');
check(/--serif/.test(css) && /--sans/.test(css), 'type pairing missing');

// Round 10e (desktop Now frame) and round 10c replay: the desktop frames keep the concept's sizes, minimum 11 px (10 px only
// on the named sub-lines); every other view keeps the 14 px minimum.
const fontSizes = (text) => [...text.matchAll(/font(?:-size)?:[^;}]*?(\d+(?:\.\d+)?)px/g)].map((m) => Number(m[1]));
const FRAME_RE = /frame-now|frame-replay/;
const frameRules = [...css.matchAll(/([^{}]+)\{([^{}]*)\}/g)].filter((m) => FRAME_RE.test(m[1]));
const otherCss = css.replace(/([^{}]+)\{([^{}]*)\}/g, (m, sel) => (FRAME_RE.test(sel) ? '' : m));
const frameSizes = fontSizes(frameRules.map((m) => m[0]).join('\n'));
const sizes = fontSizes(otherCss);
check(sizes.length > 0 && Math.min(...sizes) >= 14, `font size below 14px outside the desktop frames: ${Math.min(...sizes)}`);
// Round 10g (owner answer 3): 10 px is allowed on the frame only for the concept's own small sub-lines, named here.
const TEN_PX_SELECTORS = ['data-lid="m-read"] .s', 'data-lid="m-index"] .s', 'data-lid="ideas"] .s', 'data-lid="m-date"] .s', 'data-lid="m-search"] .s', 'data-lid="m-done"] .s'];
const tenPxBreaches = frameRules.filter((m) => fontSizes(m[2]).some((v) => v < 11) && !TEN_PX_SELECTORS.some((sel) => m[1].includes(sel)));
const tenPxRules = frameRules.filter((m) => fontSizes(m[2]).some((v) => v < 11));
check(tenPxBreaches.length === 0, `frame font below 11px outside the named sub-lines: ${tenPxBreaches.map((m) => m[1].trim()).join(' | ')}`);
check(tenPxRules.every((m) => fontSizes(m[2]).every((v) => v >= 10)), 'frame font below 10px');
check(frameSizes.length > 0 && Math.min(...frameSizes) >= 10, `font size below 10px on the desktop frames: ${Math.min(...frameSizes)}`);
check(/\.btn\s*\{[^}]*min-height:\s*48px/.test(css), '.btn is not 48px tall');
check(/#s-now \.ov-art \.ov-btn \{/.test(css) && /#s-now \.ov-art \.ov-chip-text \{/.test(css), 'Review and chip labels must not inherit the halo (specificity)');
check(/linear-gradient\(180deg, #2C2932 0%, #312C36 50%, #2F2B35 100%\)/.test(css), 'Stop fill gradient missing (measured from the concept)');
check(/prefers-reduced-motion:\s*reduce/.test(css), 'no reduced-motion rule');
check(/prefers-reduced-transparency:\s*no-preference/.test(css), 'no translucency gate');
check(/:focus-visible/.test(css), 'no visible focus rule');
check(/PROTOTYPE · fake data/.test(html), 'prototype label missing');
check(/Simulated: scripted replies, no model call/.test(html), 'chat simulated tag missing');
check(!/id="s-start"|href="#\/start"/.test(html), 'Start screen is still linked (the chat replaces it)');
check(/data-promote/.test(js) && /gen-tag">General<\/span> not project memory/.test(js), 'general thread or promote control missing');
check(/approve-confirm/.test(js) && /plan-confirm/.test(js) && /step 2 of 2/.test(js), 'two-step decision screen missing');
check(/nocolor/.test(js) && /term\.color \&\& cls/.test(js), 'terminal colour or NO_COLOR handling missing');
const termStart = js.indexOf('Terminal: the same fixture');
const termEnd = js.indexOf('function runCommand(text)');
const termJs = termStart >= 0 && termEnd > termStart ? js.slice(termStart, termEnd) : '';
check(termJs.length > 2000, 'terminal block not found in app.js');
check(!/Harbor|Lantern/.test(termJs), 'terminal shows a non-approved fixture name (Harbor or Lantern)');
check(/projects\[1\]\.name/.test(termJs) && /projects\[2\]\.name/.test(termJs), 'terminal Notes and Ideas boxes missing');
check(/'CONCEPT FIXTURE'/.test(termJs) && /Not stopped · accepts new work/.test(termJs), 'terminal header or CONCEPT FIXTURE missing');
check(/needs you/.test(termJs) && /verifying/.test(termJs) && /'amber'/.test(termJs) && /'blue'/.test(termJs), 'terminal headline colours missing');
check(/'j\/k select'/.test(termJs) && /'Enter open'/.test(termJs) && /'s Stop'/.test(termJs), 'terminal key bar differs from the concept');
check(/CONCEPT_TERM/.test(termJs) && /tools\/term_layout\.py/.test(termJs), 'terminal layout table or its generator note missing');
check(/> Tell Archeus\.\.\./.test(termJs) && /'Why:'/.test(termJs) && /\[Enter\] Open decision/.test(termJs), 'terminal Why line or command line missing');
check(/plainOverview/.test(termJs) && /\[?&\]nocolor/.test(js), 'plain-line mode or ?nocolor missing');
check(/\.term-svg \.strip/.test(css) && /Roboto Mono/.test(css) && /fonts\/RobotoMono-wght\.ttf/.test(css), 'terminal strip or vendored mono missing');
check(/\.term-svg text\.amber/.test(css) && /\.term-svg text\.blue/.test(css), 'terminal state colour rules missing');
check(/Codex · execution/.test(js) && /openFeed/.test(js), 'phone Codex label or chat open-at-card missing');
check(/Proposed · not run/.test(js) && /confirmBox\(title \+ '\?'/.test(js), 'effects must be proposed and confirmed');
for (const word of ['Intended', 'Recorded', 'Verified', 'Uncertain', 'Needs you', 'Reconcile', 'Not every external effect can be reversed']) {
  check(html.includes(word) || js.includes(word), `replay state or action missing: ${word}`);
}
check(/Tell Archeus what to do/.test(html), 'Tell box label missing');
check(/confirmBox\('Approve plan/.test(js) && /data-kind="approve"/.test(html), 'approve must go through a confirm step');

check(/Start and plan /.test(js) && /data-card="start"/.test(js), 'chat-created missions must show the Start card');
check(/Keep as mission/.test(js), 'Start card needs Keep as mission');
check(/rp-rows/.test(html) && /rp-panel/.test(html), 'replay panel missing');
check(/feed/.test(css) && /chatbar/.test(css), 'chat feed or bar styles missing');

// Round 10c replay: the concept frame (art base, live labels, rows, chips, markers, Reconcile, footer) and the phone form.
for (const word of ['orchestrates', 'executes', 'verifies', 'produces', 'Open evidence', 'Operator']) check(js.includes(word), `replay verb or button missing: ${word}`);
for (const t of ['09:00', '09:12', '09:18', '09:24', '09:25']) check(js.includes(t), `replay row time missing: ${t}`);
check(/id="replay-stage"/.test(html) && /class="rc-stage"/.test(html) && /id="rc-labels"/.test(html), 'replay stage markup missing');
check(/data-rp-back/.test(html) && /\.rp-back\s*\{/.test(css), 'replay Back control missing');
check(/#s-replay/.test(css) && /\.rp-wrap/.test(css), 'replay layout styles missing');
const rp = js.slice(js.indexOf('Replay (round 10c replay)'), js.indexOf('function renderShared'));
check(rp.length > 0 && !/requestAnimationFrame|setInterval|setTimeout/.test(rp), 'replay must not animate or auto-play');
check(/RP_MASTER/.test(rp) && /RP_LABEL/.test(rp) && /RP_ROWS_GEOM/.test(rp), 'replay master frame or layout table missing');
check(/body\.frame-replay \.shell[^{]*\{[^}]*art\/replay-base\.webp/.test(css), 'replay desktop frame must use the base art');
check(/frame-replay/.test(rp) && /--k/.test(rp), 'replay frame scale class missing');
check(existsSync(join(dir, 'art/replay-base.webp')), 'replay base art missing');
check(/Simulated: fake data, scripted replay/.test(html), 'replay simulated strip missing');
check(/Reconcile is page-only/.test(html), 'Reconcile must be stated as page-only');
check(/\.rp-actions \.btn[^}]*min-height:\s*4[48]px/.test(css) && /\.rp-actions \.btn[^}]*height:\s*4[48]px/.test(css), 'Reconcile buttons below 44px');
for (const word of ['Libre Caslon V2', 'Source Sans V2']) check(css.includes(word), `replay font missing: ${word}`);
for (const f of ['fonts/LibreCaslonText-wght.ttf', 'fonts/SourceSans3-wght.ttf']) check(existsSync(join(dir, f)), `replay font file missing: ${f}`);

check(/viewport-fit=cover/.test(html), 'phone viewport must use viewport-fit=cover');
check(css.includes('env(safe-area-inset-bottom)') && css.includes('env(safe-area-inset-top)'), 'safe-area insets missing');
check(/id="s-terminal"/.test(html) && /SIMULATED/.test(html), 'terminal section or simulated tag missing');
check(/terminal: renderTerminal/.test(js) && /data-tsize="120"/.test(html), 'terminal route or 120x40 size missing');
check(/Places/.test(html) && /data-act="menu"/.test(html), 'phone Places menu missing');

// Round 10d (hybrid): the phone Overview is the concept raster (art/phone-1-base.webp, 804 x 1373 units, live
// content removed, extended above and below by its edge rows) with a live layer on the concept's measured anchors.
const artDir = join(dir, 'art');
const webpPath = join(artDir, 'phone-1-base.webp');
check(existsSync(webpPath), 'art/phone-1-base.webp missing (run tools/build_phone_art.py)');
if (existsSync(webpPath)) {
  const bytes = readFileSync(webpPath);
  check(bytes.subarray(0, 4).toString('ascii') === 'RIFF' && bytes.subarray(8, 12).toString('ascii') === 'WEBP', 'phone art is not a WebP file');
  check(bytes.length < 400 * 1024, `phone art is ${bytes.length} bytes, over the 400 KB budget`);
}
// The data files set window.X; read them with a window stub.
const readGlobal = (f, name) => {
  const ctx = { window: {} };
  try { vm.runInNewContext(read(f), ctx, { filename: f }); } catch (e) { failures.push(`${f} does not run: ${e.message}`); }
  return ctx.window[name];
};
const layout = readGlobal('art/phone-1-layout.js', 'ARCHEUS_LAYOUT');
const type = readGlobal('art/phone-1-type.js', 'ARCHEUS_TYPE');
check(layout && layout.size && layout.size[0] === 804 && layout.size[1] === 1373, 'layout is not the 804 x 1373 concept');
check(layout && layout.pad > 0, 'layout has no background extension');
for (const key of ['wordmark', 'fixture', 'status_text', 'headline_1', 'headline_2', 'label_search', 'label_review_plan', 'label_fix', 'label_codex', 'chip_text', 'review_label', 'bar_text', 'stop_text']) {
  check(type && type[key] && type[key].size > 0, `live text missing from the type data: ${key}`);
}
for (const key of ['shapes', 'marks']) check(layout && layout[key], `layout ${key} missing`);
check(/Archeus Serif/.test(css) && /Archeus Sans/.test(css), 'live text must use the vendored @font-face families');
check(/@font-face\s*\{[^}]*fonts\/LibreCaslonText-VF\.ttf/.test(css) && /@font-face\s*\{[^}]*fonts\/Inter-VF\.ttf/.test(css), 'vendored font files are not declared');
check(existsSync(join(dir, 'fonts', 'LibreCaslonText-VF.ttf')) && existsSync(join(dir, 'fonts', 'Inter-VF.ttf')), 'vendored font files missing');
check(existsSync(join(dir, 'fonts', 'OFL-LibreCaslonText.txt')) && existsSync(join(dir, 'fonts', 'OFL-Inter.txt')), 'font licence texts missing');
check(existsSync(join(dir, 'fonts', 'README.md')), 'fonts/README.md (sources and hashes) missing');
check(/SIL Open Font License/.test(read('fonts/OFL-LibreCaslonText.txt')) && /SIL Open Font License/.test(read('fonts/OFL-Inter.txt')), 'font licence text is not the SIL OFL');
check(/src="art\/phone-1-layout\.js"/.test(html) && /src="art\/phone-1-type\.js"/.test(html), 'index.html does not load the layout and type data');
check(/class="ov-base"[^>]*src="art\/phone-1-base\.webp"/.test(html), 'index.html does not show the art layer');
check(/viewBox="0 0 804 1373"/.test(html) && /id="ov-art"/.test(html) && /id="ov-head"/.test(html), 'live layers missing from index.html');
check(/CONCEPT FIXTURE/.test(html), 'concept fixture label missing');
check(!/class="menu-btn"[^>]*>\s*<svg/.test(html), 'the hamburger icon is still drawn on the phone');
check(/data-act="menu"/.test(html) && /aria-label="Places"/.test(html), 'Places navigation must stay reachable (on the wordmark)');
check(/OV_NAMES = \[/.test(js) && /'Archeus'/.test(js) && /'Notes'/.test(js) && /'Ideas'/.test(js), 'project names missing from the Overview');
check(/·/.test(js) && !/�/.test(html + js + css), 'middle dot missing or a replacement character (mojibake) is in the source');
check(/function buildOverview/.test(js) && /function overviewSvg/.test(js) && /function headSvg/.test(js), 'overview builders missing');
check(/href="#\/plan\/m-search"/.test(js), 'Review link must open the decision');
check(/data-open="m-search"/.test(js) && /data-open="m-date"/.test(js), 'missions must open the detail sheet from the live marks');
check(/' more projects'/.test(js) && /\(projects\.length - 1\)/.test(js), 'chip count must come from the project list');
check(/data-act="stop"/.test(html) && /id="chat-input"/.test(html), 'Stop or the tell input missing from the phone overview');
check(/\.chat-stop/.test(css) && /height: calc\(var\(--u\) \* 99\)/.test(css), 'phone Stop and bar must be 44 px or taller');
check(/prefers-reduced-motion/.test(css), 'reduced motion rule missing');
check(/ovMode\(\)\) buildOverview\(\)/.test(js), 'the phone Overview is not rebuilt with the screen state');
check(/min-height: 48px/.test(css), 'touch targets below 48px rule missing');

// Round 10f: frame type floors and sub-lines. Sizes are in frame units (2 units = 1 CSS px at each master width),
// so 22 units is 11 CSS px. The 10 px sub-lines (20 units) are exactly the three listed keys.
const SUBLINE_KEYS = ['label_review_plan', 'label_codex', 'label_verifying'];
for (const [name, key] of [['phone-1', 'ARCHEUS_TYPE'], ['phone-2', 'PH2_TYPE'], ['phone-3', 'PH3_TYPE']]) {
  const t = readGlobal(`art/${name}-type.js`, key);
  check(t && typeof t === 'object', `${name} type data missing`);
  if (!t) continue;
  for (const [k, v] of Object.entries(t)) {
    const floor = SUBLINE_KEYS.includes(k) ? 20 : 22;
    check(v.size >= floor - 0.01, `${name} ${k} is ${v.size.toFixed(2)} units, below the ${floor / 2} CSS px floor`);
    check(!SUBLINE_KEYS.includes(k) || v.size < 22, `${name} ${k} should be a 10 px sub-line`);
  }
}
const lay1 = readGlobal('art/phone-1-layout.js', 'ARCHEUS_LAYOUT');
check(lay1 && lay1.shapes.chip[2] - lay1.shapes.chip[0] <= 170, 'phone-1 chip is wider than the concept (161 units)');
for (const name of ['phone-2', 'phone-3']) {
  const L = readGlobal(`art/${name}-layout.js`, name === 'phone-2' ? 'PH2_LAYOUT' : 'PH3_LAYOUT');
  check(L && L.size[0] === 724 && L.size[1] === 1573, `${name} layout is not the 724 x 1573 concept`);
  check(L && L.glows && L.glows.amber_diamond && L.glows.blue_star, `${name} glows missing from the layout`);
  check(existsSync(join(artDir, `${name}-base.webp`)), `${name} art missing`);
  const wb = readFileSync(join(artDir, `${name}-base.webp`));
  check(wb.subarray(0, 4).toString('ascii') === 'RIFF' && wb.length < 400 * 1024, `${name} art is not a WebP under 400 KB`);
}
check(/id="ph2-chat"/.test(html) && /data-act="open-decision"/.test(html) && /open-decision/.test(js), 'decision sheet Open decision button missing');
check(/approve-confirm/.test(js) && /step 2 of 2/.test(js), 'two-step decision confirm missing after Open decision');
check(/ph3-back/.test(html) && /setPhoneFrame\(3\)/.test(js) && /What does exit code 137 mean\?/.test(js), 'chat sheet frame, Back or seeded general thread missing');
check(/data-promote/.test(js) && /Promote to project memory/.test(js), 'promote switch missing');
check(/gen-tag">General<\/span> not project memory/.test(js), 'general tag missing');
check(/ov-glow/.test(js) && /feGaussianBlur/.test(js), 'soft glow filters missing');
check(/archeus-v2-proto-ph2/.test(sw) && !/archeus-v2-proto-13/.test(sw), 'service worker cache name is not archeus-v2-proto-ph2');
check(/art\/phone-2-base\.webp/.test(sw) && /art\/phone-3-base\.webp/.test(sw), 'service worker does not cache the phone-2 and phone-3 art');
check(/art\/phone-2-layout\.js/.test(html) && /art\/phone-3-type\.js/.test(html), 'index.html does not load the phone-2 and phone-3 data');


// Round 10c desktop Overview: scene from the concept box, knot star, dense facets, fixed label anchors, one-line Start card.
check(/DESK_FILL = 0\.88/.test(js) && /function deskMap|dm = function/.test(js) || /var dm = function/.test(js), 'desktop scene is not mapped from the concept box');
check(/function drawKnot/.test(js) && /sc\.knot/.test(js), 'desktop knot star missing');
check(/function deskFacetsFor/.test(js) && /p\.desk/.test(js), 'desktop hull facets missing');
check(/labelFix/.test(js) && /archeus: \{ hide: true \}/.test(js), 'desktop label anchors missing');
check(/function drawDeskExec/.test(js) && /function drawDeskMark/.test(js), 'desktop Codex triangle or marks missing');
check(/card-body/.test(js) && /\.feed \.msg-card \.card-body/.test(css), 'Start card is not a one-line body');
check(/\.now-tag \{ display: block/.test(css) && /id="s-now"/.test(html), 'desktop footer note rule missing');


if (failures.length) {
  console.error('FAIL');
  for (const f of failures) console.error(' - ' + f);
  process.exit(1);
}
console.log(`OK: ${refs.length} references, manifest parses, app.js and sw.js parse, ${pairs.length + 2} contrast pairs, min font ${Math.min(...sizes)}px outside the Now frame, ${Math.min(...frameSizes)}px on it (10px only on named sub-lines)`);

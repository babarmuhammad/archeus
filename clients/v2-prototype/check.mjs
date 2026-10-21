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

// Round 10e: the Now frame (body.frame-now rules) keeps the concept's sizes, minimum 11 px (owner rule); every other
// view keeps the 14 px minimum.
const fontSizes = (text) => [...text.matchAll(/font(?:-size)?:[^;}]*?(\d+(?:\.\d+)?)px/g)].map((m) => Number(m[1]));
const frameRules = [...css.matchAll(/([^{}]+)\{([^{}]*)\}/g)].filter((m) => /frame-now/.test(m[1]));
const otherCss = css.replace(/([^{}]+)\{([^{}]*)\}/g, (m, sel) => (/frame-now/.test(sel) ? '' : m));
const frameSizes = fontSizes(frameRules.map((m) => m[0]).join('\n'));
const otherSizes = fontSizes(otherCss);
check(otherSizes.length > 0 && Math.min(...otherSizes) >= 14, `font size below 14px outside the Now frame: ${Math.min(...otherSizes)}`);
// Round 10g (owner answer 3): 10 px is allowed on the frame only for the concept's own small sub-lines, named here.
const TEN_PX_SELECTORS = ['data-lid="m-read"] .s', 'data-lid="m-index"] .s', 'data-lid="ideas"] .s', 'data-lid="m-date"] .s', 'data-lid="m-search"] .s', 'data-lid="m-done"] .s'];
const tenPxBreaches = frameRules.filter((m) => fontSizes(m[2]).some((v) => v < 11) && !TEN_PX_SELECTORS.some((sel) => m[1].includes(sel)));
const tenPxRules = frameRules.filter((m) => fontSizes(m[2]).some((v) => v < 11));
check(tenPxBreaches.length === 0, `frame font below 11px outside the named sub-lines: ${tenPxBreaches.map((m) => m[1].trim()).join(' | ')}`);
check(tenPxRules.every((m) => fontSizes(m[2]).every((v) => v >= 10)), 'frame font below 10px');
check(frameSizes.length > 0 && Math.min(...frameSizes) >= 10, `font size below 10px on the Now frame: ${Math.min(...frameSizes)}`);
check(/\.btn\s*\{[^}]*min-height:\s*48px/.test(css), '.btn is not 48px tall');
check(/prefers-reduced-motion:\s*reduce/.test(css), 'no reduced-motion rule');
check(/prefers-reduced-transparency:\s*no-preference/.test(css), 'no translucency gate');
check(/:focus-visible/.test(css), 'no visible focus rule');
check(/PROTOTYPE · fake data/.test(html), 'prototype label missing');
check(/Simulated: scripted replies, no model call/.test(html), 'chat simulated tag missing');
check(!/id="s-start"|href="#\/start"/.test(html), 'Start screen is still linked (the chat replaces it)');
check(/data-promote/.test(js) && /gen-tag">General<\/span> not project memory/.test(js), 'general thread or promote control missing');
check(/approve-confirm/.test(js) && /plan-confirm/.test(js) && /step 2 of 2/.test(js), 'two-step decision screen missing');
check(/nocolor/.test(js) && /colourise/.test(js), 'terminal colour or NO_COLOR handling missing');
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

check(/viewport-fit=cover/.test(html), 'phone viewport must use viewport-fit=cover');
check(css.includes('env(safe-area-inset-bottom)') && css.includes('env(safe-area-inset-top)'), 'safe-area insets missing');
check(/id="s-terminal"/.test(html) && /SIMULATED/.test(html), 'terminal section or simulated tag missing');
check(/terminal: renderTerminal/.test(js) && /data-tsize="120"/.test(html), 'terminal route or 120x40 size missing');
check(/Places/.test(html) && /data-act="menu"/.test(html), 'phone Places menu missing');
check(/min-height: 48px/.test(css), 'touch targets below 48px rule missing');


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
console.log(`OK: ${refs.length} references, manifest parses, app.js and sw.js parse, ${pairs.length + 2} contrast pairs, min font ${Math.min(...otherSizes)}px outside the Now frame, ${Math.min(...frameSizes)}px on it (10px only on named sub-lines)`);

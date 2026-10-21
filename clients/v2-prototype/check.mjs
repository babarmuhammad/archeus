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
  ['text', 'bg'], ['text-2', 'surface-2'], ['text-2', 'surface-1'], ['text-3', 'surface-2'],
  ['attention', 'bg'], ['active', 'surface-1'], ['done', 'surface-1'], ['paused', 'surface-1'],
  ['blocked', 'bg'], ['on-primary', 'primary'], ['attention', 'surface-2']
];
for (const [a, b] of pairs) {
  check(tokens[a] && tokens[b], `token missing: ${a} or ${b}`);
  if (!tokens[a] || !tokens[b]) continue;
  const r = ratio(tokens[a], tokens[b]);
  check(r >= 4.5, `contrast ${a} on ${b} is ${r.toFixed(2)}, below 4.5`);
}
const sheetBg = mix(tokens['surface-1'], 0.94, tokens.bg);
check(ratio(tokens.text, sheetBg) >= 4.5, 'translucent review sheet fails 4.5:1 for text');
check(ratio(tokens['text-2'], sheetBg) >= 4.5, 'translucent review sheet fails 4.5:1 for secondary text');
check(ratio(tokens.focus, tokens.bg) >= 3, 'focus ring fails 3:1 against background');

const sizes = [...css.matchAll(/font(?:-size)?:[^;}]*?(\d+(?:\.\d+)?)px/g)].map((m) => Number(m[1]));
check(sizes.length > 0 && Math.min(...sizes) >= 14, `font size below 14px: ${Math.min(...sizes)}`);
check(/\.btn\s*\{[^}]*min-height:\s*48px/.test(css), '.btn is not 48px tall');
check(/prefers-reduced-motion:\s*reduce/.test(css), 'no reduced-motion rule');
check(/prefers-reduced-transparency:\s*no-preference/.test(css), 'no translucency gate');
check(/:focus-visible/.test(css), 'no visible focus rule');
check(/PROTOTYPE · fake data/.test(html), 'prototype label missing');
check(/Tell Archeus what to do/.test(html), 'Tell box label missing');
check(/confirmBox\('Approve plan/.test(js) && /data-kind="approve"/.test(html), 'approve must go through a confirm step');

if (failures.length) {
  console.error('FAIL');
  for (const f of failures) console.error(' - ' + f);
  process.exit(1);
}
console.log(`OK: ${refs.length} references, manifest parses, app.js and sw.js parse, ${pairs.length + 2} contrast pairs, min font ${Math.min(...sizes)}px`);

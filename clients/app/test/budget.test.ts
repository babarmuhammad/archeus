// The bundle budget (ARCHEUS_V2_VISUAL_LANGUAGE.md §11): the built JS and CSS stay under a
// gzip -9 ceiling and the display font under its own byte ceiling. It measures the build
// output, so `npm run build` runs first (the CI client job builds before `npm test`).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { gzipSync } from 'node:zlib';

export const CEILING = 180_000;
export const FONT_CEILING = 40_000;

type Asset = { name: string; bytes: Buffer };

export function measure(assets: Asset[]) {
  const sum = (xs: Asset[], f: (b: Buffer) => number) => xs.reduce((n, a) => n + f(a.bytes), 0);
  return {
    code: sum(assets.filter((a) => /\.(js|css)$/.test(a.name)), (b) => gzipSync(b, { level: 9 }).length),
    font: sum(assets.filter((a) => /\.woff2$/.test(a.name)), (b) => b.length),
  };
}

export function problems(assets: Asset[]): string[] {
  const m = measure(assets);
  return [
    ...(m.code > CEILING ? [`JS plus CSS is ${m.code} B gzip-9, over the ${CEILING} B ceiling`] : []),
    ...(m.font > FONT_CEILING ? [`fonts are ${m.font} B, over the ${FONT_CEILING} B budget`] : []),
  ];
}

const DIR = new URL('../../../archeus/api/static/assets/', import.meta.url);

function built(): Asset[] {
  assert.ok(existsSync(DIR), 'build first: run `npm run build` in clients/app (archeus/api/static/assets is absent)');
  return readdirSync(DIR).map((name) => ({ name, bytes: readFileSync(new URL(name, DIR)) }));
}

// bytes that do not compress, the same on every run
const noise = (n: number) => {
  const out: Buffer[] = [];
  for (let h = createHash('sha256').update('budget'), got = 0; got < n; got += 32) {
    const d = h.copy().digest();
    out.push(d);
    h = createHash('sha256').update(d);
  }
  return Buffer.concat(out).subarray(0, n);
};

test('the build holds the bundle and font budgets', () => {
  const assets = built();
  const m = measure(assets);
  assert.ok(m.code > 0, 'the build holds no JS or CSS');
  assert.deepEqual(problems(assets), []);
});

test('the budget refuses a bundle padded past the ceiling and a font past its budget', () => {
  const assets = built();
  assert.equal(problems([...assets, { name: 'pad.js', bytes: noise(CEILING) }]).length, 1);
  assert.equal(problems([...assets, { name: 'pad.woff2', bytes: noise(FONT_CEILING + 1) }]).length, 1);
  assert.equal(problems([...assets, { name: 'pad.png', bytes: noise(CEILING) }]).length, 0, 'images are not code');
});

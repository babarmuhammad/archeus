// Minify JS and CSS with the minifiers the V1 SPA build itself uses (Vite 8 = rolldown + oxc
// for JS, lightningcss for CSS), so prototype byte counts compare with the shipped bundle.
// Prototype tooling, not product code. Reads {js, css} JSON on stdin, writes {js, css} JSON.
// Run with cwd = clients/app so the modules resolve.
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';
const require = createRequire(process.cwd() + '/package.json');
const { transform } = require('lightningcss');
const { rolldown } = await import(pathToFileURL(require.resolve('rolldown')).href);

let raw = '';
for await (const c of process.stdin) raw += c;
const req = JSON.parse(raw);
const out = { js: '', css: '' };
if (req.js) {
  const b = await rolldown({
    input: 'entry',
    treeshake: false,
    plugins: [{ name: 'v', resolveId: (id) => (id === 'entry' ? id : null), load: (id) => (id === 'entry' ? req.js : null) }],
  });
  const { output } = await b.generate({ format: 'esm', minify: true });
  out.js = output[0].code;
}
if (req.css) {
  out.css = transform({ filename: 'x.css', code: Buffer.from(req.css), minify: true }).code.toString();
}
process.stdout.write(JSON.stringify(out));

// Checks mutated TypeScript for the mutation runners (tools/mutate_p11.py
// parse_error / ts_errors). A mutant of an SPA source is type-checked exactly as
// the build's `tsc --noEmit -p .` would, with the mutated text substituted in
// memory (nothing is written); any other .ts file is checked for syntax. A
// mutant that fails either fails every test that loads it whatever the test
// asserts, so the runner treats it as BROKEN, never as a kill.
//   stdin: {"app": "<clients/app>", "items": [{"path": "...", "text": "..."}]}
//   stdout: one message per item, "" when it checks clean
const path = require('path');

let input = '';
process.stdin.setEncoding('utf8').on('data', (d) => (input += d)).on('end', () => {
  const { app, items } = JSON.parse(input);
  const ts = require(require.resolve('typescript', { paths: [app] }));
  const norm = (p) => {
    const r = path.resolve(app, p);
    return process.platform === 'win32' ? r.toLowerCase() : r;
  };
  // `{ noEmit: true }` is the build's own command line: `tsc --noEmit -p .`
  const cfg = ts.getParsedCommandLineOfConfigFile(path.join(app, 'tsconfig.json'), { noEmit: true }, { ...ts.sys, onUnRecoverableConfigFileDiagnostic: () => {} });
  const inProgram = new Set(cfg.fileNames.map(norm));
  const host = ts.createCompilerHost(cfg.options);
  const original = host.getSourceFile.bind(host);
  const words = (ds) => ds.map((d) => ts.flattenDiagnosticMessageText(d.messageText, ' ')).join('; ');
  let program;
  const out = items.map(({ path: p, text }) => {
    const me = norm(p);
    if (!inProgram.has(me)) {
      const r = ts.transpileModule(text, { fileName: p, reportDiagnostics: true, compilerOptions: { jsx: ts.JsxEmit.Preserve } });
      return words(r.diagnostics);
    }
    host.getSourceFile = (n, lang, ...rest) => (norm(n) === me ? ts.createSourceFile(n, text, lang, true) : original(n, lang, ...rest));
    program = ts.createProgram(cfg.fileNames, cfg.options, host, program); // reuses what did not change
    return words(ts.getPreEmitDiagnostics(program));
  });
  process.stdout.write(JSON.stringify(out));
});

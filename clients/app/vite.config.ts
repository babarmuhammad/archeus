import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { defineConfig, type Plugin } from 'vite';

// The appearance boot (ADR-0044 §4, p19-design-gate B9) must run before the
// stylesheet paints, which only a classic parser-blocking script promises and
// a module never does — so it is not bundled. The build emits it as a
// content-hashed asset (cached like every other, offline too) and points
// index.html's tag at it; the dev server serves the source as it is.
const BOOT = '/src/state/appearance.js';

function appearanceBoot(): Plugin {
  const source = readFileSync(new URL('.' + BOOT, import.meta.url), 'utf8');
  const fileName = `assets/appearance-${createHash('sha256').update(source).digest('hex').slice(0, 8)}.js`;
  return {
    name: 'archeus-appearance-boot',
    apply: 'build',
    generateBundle() {
      this.emitFile({ type: 'asset', fileName, source });
    },
    transformIndexHtml: (html) => html.replace(`src="${BOOT}"`, `src="/${fileName}"`),
  };
}

// The build is what the wheel ships (p3.5b design gate §18.2): Core serves it
// from its own package, so it goes straight into archeus/api/static, which is
// git-ignored by archeus/api/.gitignore. No source maps. `public/` holds the
// PWA's files (p16-design-gate D6): sw.js and manifest.webmanifest at the root
// (Core serves both by name), the icons under assets/.
export default defineConfig({
  publicDir: 'public',
  plugins: [appearanceBoot()],
  build: {
    outDir: '../../archeus/api/static',
    emptyOutDir: true,
    assetsDir: 'assets',
    sourcemap: false,
    modulePreload: { polyfill: false },
  },
});

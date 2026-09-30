import { defineConfig } from 'vite';

// The build is what the wheel ships (p3.5b design gate §18.2): Core serves it
// from its own package, so it goes straight into archeus/api/static, which is
// git-ignored by archeus/api/.gitignore. No source maps. `public/` holds the
// PWA's files (p16-design-gate D6): sw.js and manifest.webmanifest at the root
// (Core serves both by name), the icons under assets/.
export default defineConfig({
  publicDir: 'public',
  build: {
    outDir: '../../archeus/api/static',
    emptyOutDir: true,
    assetsDir: 'assets',
    sourcemap: false,
    modulePreload: { polyfill: false },
  },
});

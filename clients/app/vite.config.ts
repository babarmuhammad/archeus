import { defineConfig } from 'vite';

// The build is what the wheel ships (p3.5b design gate §18.2): Core serves it
// from its own package, so it goes straight into archeus/api/static, which is
// git-ignored by archeus/api/.gitignore. No source maps and no public/ copy:
// the wheel carries exactly index.html and the hashed assets it references.
export default defineConfig({
  publicDir: false,
  build: {
    outDir: '../../archeus/api/static',
    emptyOutDir: true,
    assetsDir: 'assets',
    sourcemap: false,
    modulePreload: { polyfill: false },
  },
});

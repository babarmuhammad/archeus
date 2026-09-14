import type { NextConfig } from 'next';
import { DOC_REDIRECTS, SITE } from './lib/site';

/** Pages that were renamed in the same move that sent them to the subdomain. */
const RENAMED: Record<string, string> = {
  install: 'installation',
  gui: 'desktop',
  graph: 'architecture',
  health: 'projects',
  'token-economy': 'usage',
};

const docsUrl = (slug: string) => `${SITE.docs}/${RENAMED[slug] ?? slug}/`;

const nextConfig: NextConfig = {
  // lib/build-data.ts reads the repository (pyproject.toml, CHANGELOG.md,
  // docs/dashboard.md) at build time, so the trace root is the repo, not www/.
  outputFileTracingRoot: __dirname + '/..',

  async redirects() {
    return [
      // Everything under /docs/ moved to the subdomain, whole subtree.
      {
        source: '/docs',
        destination: SITE.docs,
        permanent: true,
      },
      {
        source: '/docs/:path*',
        destination: `${SITE.docs}/:path*`,
        permanent: true,
      },
      // The pages that used to be documentation pages on this host. The
      // trailing-slash form needs no entry: Next normalises it to this one.
      ...DOC_REDIRECTS.map((slug) => ({
        source: `/${slug}`,
        destination: docsUrl(slug),
        permanent: true,
      })),
    ];
  },
};

export default nextConfig;

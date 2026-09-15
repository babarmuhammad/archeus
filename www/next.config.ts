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

  // AVIF first. Next's default is WebP only, and every image on this site is a
  // UI screenshot — flat colour with hard edges, which is what AVIF is best at.
  // The one animated asset (`/graph-real.webp`) is served `unoptimized`, since
  // no format is animated through the optimizer.
  images: { formats: ['image/avif', 'image/webp'] },

  async headers() {
    return [
      {
        source: '/:path*',
        headers: [
          // Vercel already redirects http -> https; HSTS is what stops the
          // first request ever going out in the clear. `preload` is NOT here
          // on purpose: the preload list is effectively permanent and a domain
          // move is pending — see notes/domain-change.md.
          {
            key: 'Strict-Transport-Security',
            value: 'max-age=63072000; includeSubDomains',
          },
          { key: 'X-Content-Type-Options', value: 'nosniff' },
          { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
          // A preview deployment serves the whole site on a *.vercel.app host:
          // same content, different origin, and nothing else tells a crawler
          // which one is real. robots.ts disallows it too; this is the half
          // that works for a URL someone linked to directly.
          ...(process.env.VERCEL_ENV && process.env.VERCEL_ENV !== 'production'
            ? [{ key: 'X-Robots-Tag', value: 'noindex, nofollow' }]
            : []),
        ],
      },
    ];
  },

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

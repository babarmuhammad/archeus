import type { MetadataRoute } from 'next';
import { HOME } from '@/lib/content';
import { SITE } from '@/lib/site';

/** A web manifest is not here to make the site installable — it is a second
 *  machine-readable statement of the same identity the JSON-LD makes, which is
 *  worth having when an unrelated project publishes under this name. */
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: `${SITE.name} — ${SITE.tagline}`,
    short_name: SITE.name,
    description: HOME.description,
    start_url: '/',
    display: 'browser',
    background_color: '#0a0c10',
    theme_color: '#0a0c10',
    // PNG, not the ICO this used to name. An ICO in a manifest is legal and
    // nothing reads it: the ICO held one 256px frame inside 115 KB, and the
    // favicon is 16/32/48 now, so the entry described a size that no longer
    // exists in the file it pointed at.
    icons: [
      { src: '/icon-192.png', sizes: '192x192', type: 'image/png' },
      { src: '/icon-512.png', sizes: '512x512', type: 'image/png' },
    ],
  };
}

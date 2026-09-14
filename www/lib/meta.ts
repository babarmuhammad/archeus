import type { Metadata } from 'next';
import { SITE, url } from './site';

/** One place that knows the canonical/OG/Twitter shape every route needs. */
export function meta({
  title,
  description,
  path = '/',
  type = 'website',
  publishedTime,
  tags,
}: {
  title: string;
  description: string;
  path?: string;
  type?: 'website' | 'article';
  publishedTime?: string;
  tags?: string[];
}): Metadata {
  const canonical = url(path);
  const images = [{ url: url(SITE.ogImage), width: 1200, height: 630, alt: title }];
  return {
    title,
    description,
    alternates: { canonical },
    openGraph: {
      type,
      url: canonical,
      title,
      description,
      siteName: SITE.name,
      images,
      ...(publishedTime ? { publishedTime } : {}),
      ...(tags ? { tags } : {}),
    },
    twitter: { card: 'summary_large_image', title, description, images },
  };
}

/** Render a JSON-LD block. Server-rendered, so crawlers see it in view-source. */
export function jsonLd(data: object) {
  return {
    type: 'application/ld+json',
    // Only "<" needs escaping to keep the payload out of parser trouble.
    text: JSON.stringify(data).replace(/</g, '\\u003c'),
  };
}

export const breadcrumbs = (items: { name: string; path: string }[]) => ({
  '@context': 'https://schema.org',
  '@type': 'BreadcrumbList',
  itemListElement: items.map((it, i) => ({
    '@type': 'ListItem',
    position: i + 1,
    name: it.name,
    item: url(it.path),
  })),
});

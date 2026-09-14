/**
 * The two things a rendered post needs that markdown-it does not give it: a
 * reading estimate, and anchored <h2>s to hang a table of contents off.
 *
 * Both run at build time on the string lib/blog.ts already produced — no second
 * markdown pass, and nothing here reaches the client.
 */

/** 220 wpm is the usual prose figure; the number is a hint, not a measurement. */
export const readingTime = (text: string): number =>
  Math.max(1, Math.round(text.trim().split(/\s+/).length / 220));

/** en-GB gives "1 September 2026" — unambiguous for both readings of 09/01. */
export const humanDate = (iso: string): string =>
  new Date(`${iso}T00:00:00Z`).toLocaleDateString('en-GB', {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
    timeZone: 'UTC',
  });

export type Heading = { id: string; text: string };

/**
 * The heading text is going back into JSX, which escapes what it renders — so the
 * entities markdown-it wrote have to be decoded here or the TOC reads
 * `Why &quot;just write a bigger CLAUDE.md&quot; stops working`. Only the five
 * markdown-it actually emits; this is not a general HTML parser.
 */
const ENTITIES: Record<string, string> = {
  '&amp;': '&', '&lt;': '<', '&gt;': '>', '&quot;': '"', '&#39;': "'",
};
const decode = (s: string): string =>
  s.replace(/&(?:amp|lt|gt|quot|#39);/g, (e) => ENTITIES[e]);

const slugify = (s: string): string =>
  s
    .replace(/<[^>]+>/g, '')
    .replace(/&[a-z#0-9]+;/gi, ' ')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');

/**
 * Collect the <h2>s and give each one an id, since markdown-it is configured
 * without an anchor plugin. A heading that already carries an id keeps it —
 * rewriting one would break a link somebody already has.
 */
export function withHeadingIds(html: string): { html: string; headings: Heading[] } {
  const headings: Heading[] = [];
  const seen = new Map<string, number>();

  const out = html.replace(
    /<h2([^>]*)>([\s\S]*?)<\/h2>/g,
    (whole, attrs: string, inner: string) => {
      const text = decode(inner.replace(/<[^>]+>/g, '')).trim();
      const existing = attrs.match(/\bid="([^"]*)"/);

      let id = existing?.[1] ?? slugify(text);
      if (!id) return whole; // an empty heading anchors nothing
      if (!existing) {
        // Two sections called "The short answer" must not share an anchor.
        const n = seen.get(id) ?? 0;
        seen.set(id, n + 1);
        if (n) id = `${id}-${n + 1}`;
      }

      headings.push({ id, text });
      return existing ? whole : `<h2${attrs} id="${id}">${inner}</h2>`;
    },
  );

  return { html: out, headings };
}

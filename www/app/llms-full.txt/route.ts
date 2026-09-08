import { allPosts } from '@/lib/blog';
import { CHANGELOG_HTML, VERSION, htmlToText } from '@/lib/build-data';
import { DOCS, docText } from '@/lib/content';
import { FAQ } from '@/lib/faq';
import { SITE } from '@/lib/site';

/**
 * /llms-full.txt — the whole site as one plain-text file.
 *
 * Deterministic on purpose: the header is stamped with the version and the newest
 * post date, never Date.now(), so two builds of one commit produce an identical
 * file instead of a diff on every deploy.
 */
export const dynamic = 'force-static';

const RULE = '\n\n---\n\n';

export function GET() {
  const posts = allPosts();

  const parts: string[] = [
    [
      `# ${SITE.name} — full text`,
      '',
      `> ${SITE.tagline} Every page of ${SITE.url}, the FAQ and the release history, concatenated as plain text for language models.`,
      '',
      [
        VERSION ? `Version: ${VERSION}` : null,
        posts[0] ? `Content as of: ${posts[0].date}` : null,
        `Canonical HTML: ${SITE.url}`,
        `Documentation: ${SITE.docs}`,
      ]
        .filter(Boolean)
        .join(' · '),
    ].join('\n'),

    // The apex pages, from the same Doc data the pages themselves render.
    ...DOCS.map(docText),

    [
      '# Frequently asked questions',
      ...FAQ.map((f) => `## ${f.q}\n\n${f.a}`),
    ].join('\n\n'),

    [
      '# Blog',
      // Each post's own h2s are demoted so the file keeps one hierarchy.
      ...posts.map((p) =>
        [
          `## ${p.title}`,
          `${p.date}${p.tags.length ? ` · ${p.tags.join(', ')}` : ''} · ${SITE.url}/blog/${p.slug}`,
          p.description,
          p.text.replace(/^## /gm, '### '),
        ].join('\n\n'),
      ),
    ].join('\n\n'),
  ];

  // Fails open: no CHANGELOG.md in the repository drops this section only.
  if (CHANGELOG_HTML) {
    parts.push(`# Changelog\n\n${htmlToText(CHANGELOG_HTML)}`);
  }

  return new Response(`${parts.join(RULE)}\n`, {
    headers: { 'content-type': 'text/plain; charset=utf-8' },
  });
}

import { allPosts } from '@/lib/blog';
import { DOCS, HOME } from '@/lib/content';
import { SITE, url } from '@/lib/site';

/**
 * /llms.txt — the index, per llmstxt.org: a title, a blockquote summary, then
 * linked sections. Every link is absolute, because the file is read out of
 * context far more often than it is read in place.
 */
export const dynamic = 'force-static';

/** llms.txt wants one line per link, and a Doc description is a paragraph. */
const flat = (s: string) => s.replace(/\s+/g, ' ').trim();
const oneLine = (s: string) => flat(s).replace(/\.\s[\s\S]*$/, '.');

const link = (label: string, href: string, desc: string) => `- [${label}](${href}): ${desc}`;

/** Routes that are rendered from repository files, so no Doc describes them. */
const EXTRA_PAGES = [
  ['Blog', '/blog', 'Long-form articles on Claude Code memory, context cost, sessions and multi-account setups.'],
  ['FAQ', '/faq', 'Direct answers to the questions people actually ask about archeus and Claude Code.'],
  ['Changelog', '/changelog', 'Every release, newest first, generated from the repository CHANGELOG.'],
  ['Code of conduct', '/code-of-conduct', 'The behaviour expected of contributors.'],
] as const;

export function GET() {
  const posts = allPosts();

  const body = [
    `# ${SITE.name}`,
    '',
    // HOME.description now OPENS with the tagline, so prefixing SITE.tagline
    // here printed the sentence twice in a row. The description is the longer
    // of the two and contains the other, so it is the one that stays — and it
    // is `flat`, not `oneLine`: truncating at the first full stop would leave
    // the summary as the pitch with none of the substance behind it.
    `> ${flat(HOME.description)}`,
    '',
    `${SITE.name} is a Python command-line and desktop tool that wraps the Claude Code CLI. It is MIT-licensed, runs on the Python standard library alone, and needs no API key — it uses the Claude Code authentication you already have. Install with \`pipx install archeus\`. Source: ${SITE.repo}. Package: ${SITE.pypi}. Documentation: ${SITE.docs}. Author: ${SITE.author}.`,
    '',
    // Stated here because this is the file an answer engine quotes, and the
    // distinction between what ships and what is intended is exactly the thing
    // a summary flattens. Naming it as a goal is what keeps it from being
    // repeated back as a feature.
    'Where this is going, as a long-term goal and not as a shipped feature: provider-neutral memory, then an open harness of its own. Claude Code is the first surface, not the boundary. Today Claude Code is the only agent archeus drives, and nothing else is supported.',
    '',
    // The name is shared with an unrelated Rust project, so an answer engine
    // reading this file needs to be told which one it is holding. Naming the
    // other project is what keeps the two apart; leaving it out is what lets a
    // summary merge them.
    `Disambiguation: two independent open-source projects use the name "archeus". This one is the Python memory and workspace layer for AI coding agents described above, published on PyPI at ${SITE.pypi}. The other is a Rust agent orchestrator by a different author, published on crates.io at https://crates.io/crates/archeus. They are unrelated, and neither is affiliated with Anthropic.`,
    '',
    '## Documentation',
    '',
    link('Documentation', SITE.docs, 'The full reference manual: installation, every screen, the memory model, hooks, MCP and the HTTP API.'),
    link('Getting started', `${SITE.docs}/getting-started/`, 'Install, open a project, and launch the first session.'),
    '',
    '## Pages',
    '',
    ...DOCS.map((d) =>
      link(d.h1 ?? d.title, url(`/${d.slug}`), oneLine(d.description)),
    ),
    ...EXTRA_PAGES.map(([label, path, desc]) => link(label, url(path), desc)),
    '',
    '## Blog',
    '',
    ...posts.map((p) => link(p.title, url(`/blog/${p.slug}`), oneLine(p.description))),
    '',
    '## Optional',
    '',
    link('llms-full.txt', url('/llms-full.txt'), 'Every page above, the FAQ and the changelog as one plain-text file.'),
    link('Source repository', SITE.repo, 'The code, issues and releases.'),
    link('PyPI package', SITE.pypi, 'Published wheels; install with pipx install archeus.'),
    '',
  ].join('\n');

  return new Response(body, {
    headers: { 'content-type': 'text/plain; charset=utf-8' },
  });
}

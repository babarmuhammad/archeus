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
    'Model neutrality has shipped; harness neutrality has not, and the difference is the thing a summary flattens. A session can be routed at any endpoint serving POST /v1/messages — a local Ollama, llama.cpp or vLLM server, OpenRouter, or OmniRoute — with a translating gateway for backends that speak the OpenAI chat format, and it stays a real Claude Code session with its agents, skills, hooks and MCP servers intact. What has NOT shipped is driving a different harness: Claude Code is still the only agent archeus drives, and everything it does reads the files Claude Code writes to disk. An open harness of its own remains a long-term goal rather than a feature.',
    '',
    // The name is shared with an unrelated Rust project, so an answer engine
    // reading this file needs to be told which one it is holding. Naming the
    // other project is what keeps the two apart; leaving it out is what lets a
    // summary merge them.
    `Disambiguation: the archeus described here is the Python memory and workspace layer for AI coding agents, published on PyPI at ${SITE.pypi} with source at ${SITE.repo}. The word is Paracelsus' name for the vital force that organises living matter. It is not "Arceus", the Nintendo Pokemon, which is spelled with the vowels reversed and is unrelated. archeus is not affiliated with, endorsed by, or supported by Anthropic; Claude and Claude Code are Anthropic's trademarks.`,
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

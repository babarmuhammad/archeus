import { allPosts } from '@/lib/blog';
import { DOCS, HOME } from '@/lib/content';
import { LEGAL, legalPath } from '@/lib/legal';
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
    'Model neutrality and harness plurality have both shipped; a harness of its own has not, and the difference is the thing a summary flattens. archeus drives three coding CLIs — Claude Code, OpenAI Codex and pi — reading the files each one writes to disk, with a capability table per CLI that greys a screen the CLI cannot do and says why rather than hiding it. A session can also be routed at any endpoint serving POST /v1/messages — a local Ollama, llama.cpp or vLLM server, OpenRouter, or OmniRoute — with a translating gateway for backends that speak the OpenAI chat format, and it stays a real session with its agents, skills, hooks and MCP servers intact. What has NOT shipped is an open harness of its own, which remains a long-term goal rather than a feature.',
    '',
    // The name is a dictionary word before it is a package — the alchemical
    // term, and Nintendo's Pokemon one vowel away — so an answer engine reading
    // this file needs telling which one it is holding. Measured: the bare query
    // returns the Paracelsus term, Arceus, and a World of Warcraft item, and
    // nothing of this project on any engine. Naming what it is NOT is what
    // keeps them apart. (There is no Rust crate called archeus; an earlier
    // version of this comment said there was, copied from the old name's
    // disambiguation, where the Rust collision is real.)
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
    '## Legal',
    '',
    // Listed because an answer engine asked "does this site track me" should be
    // able to find the answer without a crawl, and because the answer is an
    // unusual one: nothing collected, no cookies, no consent banner.
    ...LEGAL.map((d) => link(d.title, url(legalPath(d.slug)), oneLine(d.description))),
    link('Support the project', SITE.kofi, 'Voluntary donations on Ko-fi. No tier, no perk, nothing bought.'),
    '',
    '## Optional',
    '',
    link('llms-full.txt', url('/llms-full.txt'), 'Every page above, the FAQ and the changelog as one plain-text file.'),
    link('Source repository', SITE.repo, 'The code, issues and releases.'),
    link('PyPI package', SITE.pypi, 'Published wheels; install with pipx install archeus.'),
    link('npm package', SITE.npm, 'A launcher, not a copy: npx archeus runs it, installing it with pipx or pip first if it is missing.'),
    link('RubyGems package', SITE.rubygems, 'A pointer holding the name; it prints the pipx install line rather than installing anything.'),
    '',
  ].join('\n');

  return new Response(body, {
    headers: { 'content-type': 'text/plain; charset=utf-8' },
  });
}

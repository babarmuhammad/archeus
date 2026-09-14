/**
 * Everything read from the repository at BUILD TIME. Never at request time, and
 * never from a client component.
 *
 * No network calls live here on purpose: a flaky API must not be able to fail a
 * deploy. The numbers come from docs/dashboard.md, which the repo's own metrics
 * workflow regenerates weekly and commits.
 *
 * Every reader fails open. A missing file degrades one section of one page; it
 * never throws during the build.
 */
import fs from 'node:fs';
import path from 'node:path';
import MarkdownIt from 'markdown-it';

const REPO = path.join(process.cwd(), '..');

/**
 * turbopackIgnore: this path is built at runtime, so static analysis gives up and
 * traces the WHOLE repository into the server output — every source file and the
 * public folder, on a site whose every route is static and needs none of it. The
 * reads happen during the build, when the repository is on disk by definition.
 */
function read(rel: string): string | null {
  try {
    return fs.readFileSync(path.join(/* turbopackIgnore: true */ REPO, rel), 'utf8');
  } catch {
    return null;
  }
}

/* ── version ───────────────────────────────────────────────────────────────── */

export const VERSION: string =
  read('pyproject.toml')?.match(/^version\s*=\s*"([^"]+)"/m)?.[1] ?? '';

/* ── metrics, parsed out of docs/dashboard.md ──────────────────────────────── */

export type Metrics = {
  version: string;
  pypiVersion: string;
  releases: string;
  downloadsDay: string;
  downloadsWeek: string;
  downloadsMonth: string;
  stars: string;
  forks: string;
  tests: string;
  pythonFiles: string;
  linesOfPython: string;
  commits: string;
  docPages: string;
  generated: string;
};

/**
 * The dashboard is a markdown table, so every number is `| label | value |` or a
 * single header row of three. Anything not found stays an empty string and the
 * component renders a dash — a stale metrics run must not break the page.
 */
function parseMetrics(): Metrics {
  const md = read('docs/dashboard.md') ?? '';
  const cell = (label: string) => {
    const m = md.match(
      new RegExp(`^\\|\\s*${label}\\s*\\|\\s*\\**([^|*]+?)\\**\\s*\\|`, 'im'),
    );
    return m ? m[1].trim() : '';
  };
  // Downloads: the one three-column table, `| 146 | 279 | 410 |`.
  const dl =
    md.match(/\|\s*Last day\s*\|[^\n]*\n\|[-\s|]+\n\|([^\n]+)\|/i)?.[1] ?? '';
  const [day = '', week = '', month = ''] = dl.split('|').map((s) => s.trim());

  return {
    version: cell('Version in this repository') || VERSION,
    pypiVersion: cell('Published on PyPI'),
    releases: cell('Releases to date'),
    downloadsDay: day,
    downloadsWeek: week,
    downloadsMonth: month,
    stars: cell('Stars'),
    forks: cell('Forks'),
    tests: cell('Tests'),
    pythonFiles: cell('Python files'),
    linesOfPython: cell('Lines of Python'),
    commits: cell('Commits'),
    docPages: cell('Documentation pages'),
    generated: md.match(/\*Generated ([^*]+?)\.?\*/)?.[1]?.trim() ?? '',
  };
}

export const METRICS: Metrics = parseMetrics();

/* ── markdown files rendered as pages ──────────────────────────────────────── */

const md = new MarkdownIt({ html: false, linkify: true, typographer: false });

/** Render a repository markdown file to HTML, or null when it does not exist. */
export function renderRepoMarkdown(rel: string): string | null {
  const src = read(rel);
  if (src === null) return null;
  // Drop the leading H1 — every page supplies its own, and two would be wrong
  // for both the outline and the screen reader.
  return md.render(src.replace(/^#\s+.+\n/, ''));
}

export const CHANGELOG_HTML = renderRepoMarkdown('CHANGELOG.md');
export const CONDUCT_HTML = renderRepoMarkdown('CODE_OF_CONDUCT.md');
/* The repository file is the source of truth; the CONTRIBUTING Doc in
   lib/content.ts is the fallback for when it cannot be read. */
export const CONTRIBUTING_HTML = renderRepoMarkdown('CONTRIBUTING.md');

/** One `<h2>` and everything under it. */
export type HtmlSection = { id: string; title: string; html: string };

/**
 * Split rendered markdown at its `<h2>` boundaries.
 *
 * The routes that render a repository file straight to HTML — changelog,
 * contributing, code of conduct — had no sections at all, so they were the only
 * pages with nothing for the section rail to show. A release IS a section; so is
 * "Running the tests". This is what gives them one without duplicating the
 * source file as hand-written data.
 *
 * Anything before the first heading (a preamble) becomes a leading section with
 * no title, rather than being dropped.
 */
export function splitHeadings(html: string | null): HtmlSection[] {
  if (!html) return [];
  const parts = html.split(/(?=<h2\b)/);
  const seen = new Set<string>();
  const out: HtmlSection[] = [];
  for (const part of parts) {
    let body = part.trim();
    if (!body) continue;
    const open = body.match(/<h2\b([^>]*)>([\s\S]*?)<\/h2>/);
    const title = htmlToText(open?.[2] ?? '');
    // A heading that already carries an id keeps it — blog posts anchor theirs
    // before this runs, and rewriting one breaks a link somebody already has.
    const existing = open?.[1].match(/\bid="([^"]*)"/)?.[1];
    // Slug collision is real without one: CHANGELOG.md repeats "Fixed" under
    // every release, and two elements with one id sends half the anchors nowhere.
    let id = existing
      ?? (title.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')
        || `part-${out.length}`);
    while (seen.has(id)) id = `${id}-${out.length}`;
    seen.add(id);
    // The id goes on the HEADING, never on a wrapper: the caller renders these
    // side by side with the original markup on some routes, and two elements
    // claiming one anchor is the same bug as a collision.
    if (open && !existing) {
      body = body.replace(/<h2\b([^>]*)>/, `<h2$1 id="${id}">`);
    }
    out.push({ id, title, html: body });
  }
  return out;
}

/** Plain text of a rendered markdown page, for /llms-full.txt. */
export function htmlToText(html: string): string {
  return html
    .replace(/<\/(h[1-6]|p|li|tr|pre|blockquote)>/g, '\n')
    .replace(/<li>/g, '- ')
    .replace(/<[^>]+>/g, '')
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

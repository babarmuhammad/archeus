import Link from 'next/link';
import { SITE } from '@/lib/site';
import { LEGAL, legalPath } from '@/lib/legal';
import { VERSION } from '@/lib/build-data';

const COLUMNS: { title: string; links: { href: string; label: string; ext?: boolean }[] }[] = [
  {
    title: 'Product',
    links: [
      { href: '/features', label: 'Features' },
      { href: '/download', label: 'Download' },
      { href: '/architecture', label: 'Architecture' },
      { href: '/changelog', label: 'Changelog' },
    ],
  },
  {
    title: 'Learn',
    links: [
      { href: SITE.docs, label: 'Documentation', ext: true },
      { href: `${SITE.docs}/getting-started/`, label: 'Getting started', ext: true },
      { href: '/blog', label: 'Blog' },
      { href: '/faq', label: 'FAQ' },
    ],
  },
  {
    title: 'Project',
    links: [
      { href: '/about', label: 'About' },
      { href: '/community', label: 'Community' },
      { href: '/contributing', label: 'Contributing' },
      { href: '/code-of-conduct', label: 'Code of conduct' },
      { href: SITE.kofi, label: 'Support on Ko-fi', ext: true },
    ],
  },
  {
    title: 'Elsewhere',
    links: [
      { href: SITE.repo, label: 'GitHub', ext: true },
      { href: SITE.pypi, label: 'PyPI', ext: true },
      { href: `${SITE.repo}/issues`, label: 'Issues', ext: true },
      { href: '/llms.txt', label: 'llms.txt', ext: true },
    ],
  },
];

export function Footer() {
  return (
    <footer className="hairline mt-24 bg-bg2/40">
      <div className="mx-auto max-w-6xl px-5 py-14">
        <div className="grid grid-cols-2 gap-8 sm:grid-cols-4">
          {COLUMNS.map((col) => (
            <div key={col.title}>
              <h2 className="mb-3 text-[0.7rem] font-semibold uppercase tracking-[0.14em] text-dim2">
                {col.title}
              </h2>
              <ul className="space-y-2 text-sm">
                {col.links.map((l) => (
                  <li key={l.label}>
                    {l.ext ? (
                      <a
                        href={l.href}
                        className="text-dim no-underline transition-colors hover:text-text"
                      >
                        {l.label}
                      </a>
                    ) : (
                      <Link
                        href={l.href}
                        className="text-dim no-underline transition-colors hover:text-text"
                      >
                        {l.label}
                      </Link>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        {/* The policies get their own row rather than a fifth column: four
            columns already wrap to two on a phone, and a fifth would have made
            it three ragged ones. A legal row at the foot is also where a reader
            looks for them. */}
        <div className="hairline mt-12 pt-6 text-xs text-dim2">
          <nav aria-label="Legal">
            <ul className="flex flex-wrap gap-x-5 gap-y-2">
              {LEGAL.map((d) => (
                <li key={d.slug}>
                  <Link
                    href={legalPath(d.slug)}
                    className="text-dim no-underline transition-colors hover:text-text"
                  >
                    {d.title}
                  </Link>
                </li>
              ))}
            </ul>
          </nav>

          <div className="mt-4 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <p>
              {SITE.license}-licensed · built by{' '}
              <a href={SITE.authorGithub} className="text-dim no-underline hover:text-text">
                {SITE.author}
              </a>
              {VERSION ? ` · v${VERSION}` : ''}
            </p>
            <p>Not affiliated with Anthropic. Claude and Claude Code are their trademarks.</p>
          </div>
        </div>
      </div>
    </footer>
  );
}

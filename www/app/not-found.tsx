import Link from 'next/link';
import { SITE } from '@/lib/site';

/* No `metadata` export: a 404 must not be indexable, and Next already sends
   noindex with the 404 status. */

const LINKS = [
  { href: '/features', label: 'Features', desc: 'What archeus does, screen by screen.' },
  { href: '/download', label: 'Download', desc: 'pipx install archeus, and the requirements.' },
  { href: '/blog', label: 'Blog', desc: 'Notes on Claude Code memory and context cost.' },
  { href: '/faq', label: 'FAQ', desc: 'The questions people actually ask.' },
];

export default function NotFound() {
  return (
    <div className="mx-auto max-w-2xl px-5 py-24 sm:py-32">
      <p className="font-mono text-[0.72rem] uppercase tracking-[0.16em] text-cyan/80">404</p>
      <h1 className="mt-3 text-balance text-3xl font-semibold tracking-tight text-text sm:text-4xl">
        That page is not here
      </h1>
      <p className="mt-4 text-pretty text-lg leading-[1.65] text-dim">
        The link may be out of date. The documentation moved to{' '}
        <a href={SITE.docs} className="text-cyan no-underline hover:text-violet">
          docs.claudectl.space
        </a>
        , and everything else is one of these.
      </p>

      <ul className="mt-10 space-y-3">
        {LINKS.map((l) => (
          <li key={l.href}>
            <Link
              href={l.href}
              className="panel block p-4 no-underline transition-transform duration-200 hover:-translate-y-0.5"
            >
              <span className="font-semibold text-text">{l.label}</span>
              <span className="mt-1 block text-[0.9rem] text-dim">{l.desc}</span>
            </Link>
          </li>
        ))}
      </ul>

      <p className="mt-10">
        <Link href="/" className="text-[0.9rem] text-cyan no-underline hover:text-violet">
          ← Back to the home page
        </Link>
      </p>
    </div>
  );
}

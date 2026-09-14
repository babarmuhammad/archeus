import type { Heading } from './prose';

const Items = ({ headings }: { headings: Heading[] }) => (
  <ol className="space-y-1.5 text-[0.85rem] leading-snug">
    {headings.map((h) => (
      <li key={h.id}>
        <a
          href={`#${h.id}`}
          className="block text-dim2 no-underline transition-colors hover:text-cyan"
        >
          {h.text}
        </a>
      </li>
    ))}
  </ol>
);

/**
 * Two presentations, because "collapsed below lg, expanded above" is not a state
 * CSS can set on a <details> — and a JS toggle for a list of links would be a
 * client component for nothing. The caller decides which breakpoint shows which.
 */
export function TocDetails({ headings }: { headings: Heading[] }) {
  if (!headings.length) return null;
  return (
    <details className="panel px-4 py-3">
      <summary className="cursor-pointer font-mono text-[0.7rem] uppercase tracking-[0.14em] text-dim2">
        On this page
      </summary>
      <nav aria-label="On this page" className="mt-3">
        <Items headings={headings} />
      </nav>
    </details>
  );
}

export function TocRail({ headings }: { headings: Heading[] }) {
  if (!headings.length) return null;
  return (
    <nav
      aria-label="On this page"
      className="sticky top-24 max-h-[calc(100vh-8rem)] overflow-y-auto"
    >
      <p className="mb-3 font-mono text-[0.7rem] uppercase tracking-[0.14em] text-dim2">
        On this page
      </p>
      <Items headings={headings} />
    </nav>
  );
}

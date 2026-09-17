import Link from 'next/link';
import { NAV, SITE } from '@/lib/site';
import { CoffeeCup } from './CoffeeCup';
import { Mark } from './Mark';

/**
 * The site header. Server-rendered, so every nav link is in view-source.
 *
 * The narrow-viewport menu is a <details>, not React state: the platform already
 * has a disclosure widget with keyboard and screen-reader behaviour built in,
 * and using it keeps the whole header a server component.
 */
export function Header() {
  return (
    // Opaque, not translucent. The usual trick for a sticky bar is a translucent
    // background over backdrop-filter: blur() — the one property this project
    // will not ship, because it forces a GPU readback and tears the compositor.
    // Without the blur, translucent just means the page scrolls visibly through
    // the nav labels.
    <header className="sticky top-0 z-40 border-b border-line/70 bg-bg">
      <div className="mx-auto flex h-14 max-w-6xl items-center gap-6 px-5">
        <Link
          href="/"
          className="flex shrink-0 items-center gap-2 text-text no-underline"
          aria-label={`${SITE.name} home`}
        >
          <Mark className="h-6 w-6" />
          <span className="font-mono text-[0.95rem] font-semibold tracking-tight">
            archeus
          </span>
        </Link>

        {/* The links appear at `lg`, not `md`. Six of them are 627px wide, and
            beside the wordmark, Docs, the donation button and GitHub that is
            996px of header in a 768px tablet — the bar scrolled sideways from
            768 to 895px before the donation button existed and to 995 after it.
            Below `lg` the same links are in the disclosure menu, which is why
            this is a breakpoint and not a cut. */}
        <nav className="hidden flex-1 items-center gap-5 text-sm lg:flex">
          {NAV.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className="text-dim no-underline transition-colors hover:text-text"
            >
              {item.label}
            </Link>
          ))}
        </nav>

        <div className="ml-auto flex items-center gap-3 lg:ml-0">
          <a
            href={SITE.docs}
            className="hidden text-sm text-dim no-underline transition-colors hover:text-text sm:inline"
          >
            Docs
          </a>
          {/* The donation link lives here rather than on /support, which is a
              footer page nobody arrives at. A plain link, never a Ko-fi widget:
              their embed loads a script and would drag cookie consent back onto
              a site that has none.

              It is the one warm, filled control in a header of blue text links,
              which is the whole of its emphasis — see --color-kofi. */}
          <a
            href={SITE.kofi}
            rel="noopener"
            className="hidden items-center gap-2 rounded-lg bg-kofi px-3 py-1.5 text-sm font-medium text-kofi-ink no-underline transition-colors hover:bg-kofi-hover sm:inline-flex"
          >
            <CoffeeCup className="h-4 w-4" />
            Buy me a Coffee
          </a>
          <a
            href={SITE.repo}
            className="rounded-lg border border-line px-3 py-1.5 text-sm text-dim no-underline transition-colors hover:border-cyan/50 hover:text-text"
          >
            GitHub
          </a>

          <details className="relative lg:hidden">
            <summary
              className="flex h-8 w-8 cursor-pointer list-none items-center justify-center rounded-lg border border-dim2/70 text-dim"
              aria-label="Menu"
            >
              <svg viewBox="0 0 24 24" className="h-4 w-4" aria-hidden="true">
                <path
                  d="M4 7h16M4 12h16M4 17h16"
                  stroke="currentColor"
                  strokeWidth="1.6"
                  strokeLinecap="round"
                  fill="none"
                />
              </svg>
            </summary>
            <div className="panel-solid absolute right-0 top-10 flex w-48 flex-col gap-1 p-2">
              {NAV.map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  className="rounded-md px-3 py-2 text-sm text-dim no-underline hover:bg-panel2 hover:text-text"
                >
                  {item.label}
                </Link>
              ))}
              <a
                href={SITE.docs}
                className="rounded-md px-3 py-2 text-sm text-dim no-underline hover:bg-panel2 hover:text-text"
              >
                Documentation
              </a>
              <a
                href={SITE.kofi}
                rel="noopener"
                className="mt-1 flex items-center gap-2 rounded-md bg-kofi px-3 py-2 text-sm font-medium text-kofi-ink no-underline"
              >
                <CoffeeCup className="h-4 w-4" />
                Buy me a Coffee
              </a>
            </div>
          </details>
        </div>
      </div>
    </header>
  );
}

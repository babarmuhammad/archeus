import Link from 'next/link';
import { NAV, SITE } from '@/lib/site';
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

        <nav className="hidden flex-1 items-center gap-5 text-sm md:flex">
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

        <div className="ml-auto flex items-center gap-3 md:ml-0">
          <a
            href={SITE.docs}
            className="hidden text-sm text-dim no-underline transition-colors hover:text-text sm:inline"
          >
            Docs
          </a>
          <a
            href={SITE.repo}
            className="rounded-lg border border-line px-3 py-1.5 text-sm text-dim no-underline transition-colors hover:border-cyan/50 hover:text-text"
          >
            GitHub
          </a>

          <details className="relative md:hidden">
            <summary
              className="flex h-8 w-8 cursor-pointer list-none items-center justify-center rounded-lg border border-line text-dim"
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
            </div>
          </details>
        </div>
      </div>
    </header>
  );
}

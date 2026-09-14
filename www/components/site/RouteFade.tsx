'use client';

import type { ReactNode } from 'react';
import { usePathname } from 'next/navigation';

/**
 * One short entrance per route.
 *
 * The App Router swaps the DOM instantly, and the site's own `.reveal` is a
 * native view timeline — which does nothing at all for content that is already
 * in frame when it mounts. So a navigation read as a hard cut: the header and
 * the scene carried on, and the whole page under them changed between two
 * frames.
 *
 * The `key` is the entire mechanism. Changing it remounts the wrapper, which
 * restarts the animation; without it CSS has no event to fire on, because the
 * element never left. Transform and opacity only, and `prefers-reduced-motion`
 * removes it in globals.css.
 */
export function RouteFade({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  return (
    <div key={pathname} className="page-in">
      {children}
    </div>
  );
}

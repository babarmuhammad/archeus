'use client';

import { usePathname } from 'next/navigation';
import { JourneyCanvas } from '@/components/journey/Canvas';

/**
 * One canvas for the whole site, mounted in the layout.
 *
 * The landing page drives it with scroll; every other route gets the same
 * constellation parked and drifting. It lives here rather than in each page so
 * navigating between two inner pages does not tear down a GL context and build
 * a new one — the mode only changes when you cross the landing page.
 */
export function Backdrop() {
  const pathname = usePathname();
  return <JourneyCanvas mode={pathname === '/' ? 'journey' : 'ambient'} />;
}

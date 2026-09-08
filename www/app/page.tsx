import { Stations } from '@/components/journey/Stations';

/**
 * The landing page is one scroll down a constellation: six geodesic cages, each
 * holding a population of its own, joined by a curve that draws itself as you go,
 * with the copy for each station beside its cluster.
 *
 * The canvas is decoration and the stations are the page. Remove the canvas —
 * no WebGL, reduced motion, JavaScript off — and every word is still here,
 * server-rendered, over the static wash in globals.css.
 */
export default function Home() {
  return (
    // The canvas is mounted once for the whole site in app/layout.tsx; this route
    // is what puts it in journey mode.
    <Stations />
  );
}

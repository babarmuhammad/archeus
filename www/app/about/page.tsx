import { ABOUT } from '@/lib/content';
import { METRICS } from '@/lib/build-data';
import { breadcrumbs, jsonLd, meta } from '@/lib/meta';
import { SITE } from '@/lib/site';
import { Cta, DocSections, PageHeader } from '@/components/Page';

export const metadata = meta({
  title: ABOUT.title,
  description: ABOUT.description,
  path: '/about',
});

const CRUMBS = breadcrumbs([
  { name: 'Home', path: '/' },
  { name: 'About', path: '/about' },
]);

/** Read out of the repository's own weekly metrics run at build time. Any field
 *  may be missing — a stale or absent dashboard drops the tile, never shows a
 *  zero and never raises.
 *
 *  A tile survives only if its value actually contains a digit. The dashboard
 *  writes an em-dash for a figure it could not measure, and a tile reading
 *  "GitHub stars —" is not a measurement a reader can use: it reads as a claim
 *  of none. Filtering on the value rather than on a hand-kept list of which
 *  metrics are live means each tile comes back by itself the week its number
 *  does. */
const STATS = [
  { label: 'Tests', value: METRICS.tests },
  { label: 'Lines of Python', value: METRICS.linesOfPython },
  { label: 'Commits', value: METRICS.commits },
  { label: 'GitHub stars', value: METRICS.stars },
  { label: 'Installs / month', value: METRICS.downloadsMonth },
  { label: 'Releases', value: METRICS.releases },
].filter((s) => /\d/.test(s.value));

export default function AboutPage() {
  return (
    <>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: jsonLd(CRUMBS).text }}
      />

      <PageHeader eyebrow="About" title={ABOUT.h1 ?? ABOUT.title} lead={ABOUT.intro}>
        <Cta href={SITE.repo} primary>
          GitHub
        </Cta>
        <Cta href={SITE.pypi}>PyPI</Cta>
        <Cta href={`${SITE.repo}/blob/main/LICENSE`}>MIT licence</Cta>
      </PageHeader>

      {STATS.length ? (
        <div className="mx-auto max-w-4xl px-5 pt-10">
          <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
            {STATS.map((s) => (
              <div key={s.label} className="panel px-3 py-3.5 text-center">
                <dt className="text-[0.68rem] uppercase tracking-[0.1em] text-dim2">{s.label}</dt>
                <dd className="mt-1 font-mono text-lg tabular-nums text-text">{s.value}</dd>
              </div>
            ))}
          </dl>
          {METRICS.generated ? (
            <p className="mt-3 text-[0.78rem] text-dim2">
              Counted on {METRICS.generated} by the repository&rsquo;s own weekly metrics run, and
              not since. Each one measures this repository, not anybody using it.
            </p>
          ) : null}
        </div>
      ) : null}

      {/* Three short sections, so the solids circle one point rather than
          marching down a rail nothing needs. */}
      <DocSections doc={ABOUT} layout="orbit" />
    </>
  );
}

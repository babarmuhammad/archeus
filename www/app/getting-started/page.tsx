import { breadcrumbs, jsonLd, meta } from '@/lib/meta';
import { SITE, url } from '@/lib/site';
import { Cta, PageHeader } from '@/components/Page';
import { Shot, ShotPair } from '@/components/Shot';
import { TourPlayer } from '@/components/TourPlayer';
import { TOUR_LONG, TOUR_SHORT } from '@/lib/tour';

/**
 * The guided tour, on the web.
 *
 * Not a copy of the manual and not a second Doc in lib/content.ts: the steps are
 * generated from `claude_sessions/tour.py`, which is the same source the desktop
 * app's overlay and the terminal UI's screen read. A product with three
 * interfaces and three explanations of itself has three products.
 *
 * It is the one place the tour can be walked WITHOUT having installed anything,
 * which is what makes it worth having on the apex at all — so it carries the
 * screenshots, and the two in-app surfaces link here.
 */

const DESCRIPTION =
  'A guided tour of archeus, step by step: the first five minutes, then every ' +
  'function it has and what each one is for. The same tour runs inside the app.';

export const metadata = meta({
  title: 'Getting started with archeus',
  description: DESCRIPTION,
  path: '/getting-started',
});

const CRUMBS = breadcrumbs([
  { name: 'Home', path: '/' },
  { name: 'Getting started', path: '/getting-started' },
]);

/* `HowTo`, derived from the short tour rather than written beside it — the same
   rule the manual's structured data follows. The long tour is a reference, not
   a procedure, so it contributes nothing here: structured data that does not
   match the page is worse than none. */
const HOWTO = {
  '@context': 'https://schema.org',
  '@type': 'HowTo',
  '@id': `${url('/getting-started')}#howto`,
  name: 'Get started with archeus',
  description: DESCRIPTION,
  url: url('/getting-started'),
  totalTime: 'PT5M',
  tool: { '@type': 'HowToTool', name: 'archeus' },
  author: { '@id': `${SITE.url}/#author` },
  step: TOUR_SHORT.map((s, i) => ({
    '@type': 'HowToStep',
    position: i + 1,
    name: s.title,
    text: s.body,
    url: `${url('/getting-started')}#short-${i + 1}`,
  })),
};

export default function GettingStartedPage() {
  return (
    <>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: jsonLd(CRUMBS).text }}
      />
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: jsonLd(HOWTO).text }} />

      <PageHeader
        eyebrow="Getting started"
        title="A guided tour of archeus"
        lead={
          `Two tours of the same product: the first five minutes, and all ` +
          `${TOUR_LONG.length} of its functions with what each one is for. The same ` +
          `steps run inside the desktop app, which points at the screen it is ` +
          `describing, and inside the terminal UI.`
        }
      >
        <Cta href="/download" primary>
          Install it
        </Cta>
        <Cta href={`${SITE.docs}/quickstart/`}>Quickstart</Cta>
        <Cta href={`${SITE.docs}/`}>The manual</Cta>
      </PageHeader>

      {/* The recording first, the walkable tour under it. Both are generated
          from the same steps — `tools/capture_tour.py` drives the real app
          through them — so a reader who wants to watch and a reader who wants
          to read are not being shown two different products.

          `unoptimized`: these are animated WebP, and the optimizer would either
          strip the animation or spend the build re-encoding it. Same reason the
          architecture-graph animation carries it. */}
      <div className="mx-auto mt-10 max-w-4xl px-5">
        <ShotPair>
          <Shot
            src="/img/tour-gui-short.webp"
            width={1152}
            height={720}
            sizes="(min-width: 936px) 420px, (min-width: 640px) 45vw, 100vw"
            alt="The guided tour running inside the archeus desktop app, opening each screen as it describes it."
            caption="The desktop app, walking its own tour."
            unoptimized
          />
          <Shot
            src="/img/tour-tui-short.webp"
            width={836}
            height={246}
            sizes="(min-width: 936px) 420px, (min-width: 640px) 45vw, 100vw"
            alt="The same tour in the archeus terminal UI, one step per screen."
            caption="The same steps in the terminal."
            unoptimized
          />
        </ShotPair>
      </div>

      <div className="pt-10">
        <TourPlayer />
      </div>

      <div className="mx-auto max-w-4xl px-5 pb-16 pt-12">
        <div className="panel-solid p-6">
          <h2 className="text-lg font-semibold text-text">Run it in the app instead</h2>
          <p className="mt-2 text-pretty leading-[1.7] text-dim">
            Both tours ship with archeus. In the desktop app they run as an overlay that opens
            each screen as it describes it — the <span className="font-mono text-cyan">?</span>{' '}
            button at the foot of the sidebar, then <em>Guided tour</em>. In the terminal UI they
            are a screen of their own: <span className="font-mono text-cyan">Getting started</span>{' '}
            on the main menu, <span className="font-mono text-cyan">←</span>{' '}
            <span className="font-mono text-cyan">→</span> to move.
          </p>
        </div>
      </div>
    </>
  );
}

import { ARCHITECTURE } from '@/lib/content';
import { breadcrumbs, jsonLd, meta } from '@/lib/meta';
import { SITE } from '@/lib/site';
import { Cta, DocSections, PageHeader } from '@/components/Page';
import { Shot } from '@/components/Shot';

export const metadata = meta({
  title: ARCHITECTURE.title,
  description: ARCHITECTURE.description,
  path: '/architecture',
});

const CRUMBS = breadcrumbs([
  { name: 'Home', path: '/' },
  { name: 'Architecture', path: '/architecture' },
]);

export default function ArchitecturePage() {
  return (
    <>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: jsonLd(CRUMBS).text }}
      />

      <PageHeader
        eyebrow="Architecture"
        title={ARCHITECTURE.h1 ?? ARCHITECTURE.title}
        lead={ARCHITECTURE.intro}
      >
        <Cta href={SITE.repo} primary>
          Read the source
        </Cta>
        <Cta href={`${SITE.docs}/architecture/`}>Architecture docs</Cta>
      </PageHeader>

      {/* A page about layers: one column, and the three solids nest front to
          back inside it rather than travelling across the page. */}
      <DocSections
        doc={ARCHITECTURE}
        layout="depth"
        after={{
          graph: (
            <Shot
              src="/graph-real.gif"
              width={800}
              height={460}
              unoptimized
              sizes="(min-width: 936px) 856px, 100vw"
              alt="The archeus architecture graph expanding from repository level down to individual files, with dependency edges between modules."
              caption="The graph archeus draws of a real repository — one self-contained HTML file, written into the project and opened locally."
            />
          ),
        }}
      />
    </>
  );
}

import { CONTRIBUTING } from '@/lib/content';
import { CONTRIBUTING_HTML, splitHeadings } from '@/lib/build-data';
import { breadcrumbs, jsonLd, meta } from '@/lib/meta';
import { SITE } from '@/lib/site';
import { DocView } from '@/components/doc/Blocks';
import { Cta, PageHeader, ProseSections } from '@/components/Page';

export const metadata = meta({
  title: CONTRIBUTING.title,
  description: CONTRIBUTING.description,
  path: '/contributing',
});

const CRUMBS = breadcrumbs([
  { name: 'Home', path: '/' },
  { name: 'Contributing', path: '/contributing' },
]);

/* The repository file links to CODE_OF_CONDUCT.md as a sibling path, which
   resolves against this route and 404s. It is the only relative link in the
   file, so it is rewritten rather than a link-rewriting pass being built. */
const HTML = CONTRIBUTING_HTML?.replace(
  /href="CODE_OF_CONDUCT\.md"/g,
  'href="/code-of-conduct"',
);

/** Each step of the contribution flow is a section. */
const STEPS = splitHeadings(HTML ?? null);

export default function ContributingPage() {
  return (
    <>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: jsonLd(CRUMBS).text }}
      />

      {STEPS.length > 1 ? (
        <>
          <PageHeader
            eyebrow="Contributing"
            title={CONTRIBUTING.h1 ?? CONTRIBUTING.title}
            lead={CONTRIBUTING.intro}
          >
            <Cta href={`${SITE.repo}/issues`} primary>
              Open issues
            </Cta>
            <Cta href={`${SITE.repo}/blob/main/CONTRIBUTING.md`}>This file on GitHub</Cta>
            <Cta href="/code-of-conduct">Code of conduct</Cta>
          </PageHeader>
          <ProseSections sections={STEPS} />
        </>
      ) : (
        /* No PageHeader here: DocView renders the h1 and intro itself, and two
           h1s would be wrong for the outline and for a screen reader. */
        <DocView doc={CONTRIBUTING} />
      )}
    </>
  );
}

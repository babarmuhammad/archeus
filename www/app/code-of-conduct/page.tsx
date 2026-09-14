import { CONDUCT_HTML, splitHeadings } from '@/lib/build-data';
import { breadcrumbs, jsonLd, meta } from '@/lib/meta';
import { SITE } from '@/lib/site';
import { Cta, PageBody, PageHeader, ProseSections } from '@/components/Page';

/** The Covenant's own clauses are the sections — nothing to invent. */
const CLAUSES = splitHeadings(CONDUCT_HTML);

export const metadata = meta({
  title: 'Code of conduct',
  description:
    'The Contributor Covenant archeus follows, and how it applies to the issue tracker, discussions and pull requests.',
  path: '/code-of-conduct',
});

const CRUMBS = breadcrumbs([
  { name: 'Home', path: '/' },
  { name: 'Code of conduct', path: '/code-of-conduct' },
]);

export default function CodeOfConductPage() {
  return (
    <>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: jsonLd(CRUMBS).text }}
      />

      <PageHeader
        eyebrow="Community"
        title="Code of conduct"
        lead="archeus follows the Contributor Covenant. It applies to the issue tracker, discussions and pull requests, and to anyone taking part in them."
      >
        <Cta href={`${SITE.repo}/blob/main/CODE_OF_CONDUCT.md`} primary>
          This file on GitHub
        </Cta>
        <Cta href="/contributing">Contributing</Cta>
      </PageHeader>

      {CLAUSES.length > 1 ? (
        <ProseSections sections={CLAUSES} />
      ) : (
        <PageBody>
          {/* Read from the repository at build time, so a checkout without the
              file degrades to a link instead of failing the route. */}
          <div className="panel p-6">
            <h2 className="text-lg font-semibold text-text">Read it on GitHub</h2>
            <p className="mt-2 text-[0.95rem] leading-[1.7] text-dim">
              The full text could not be read for this build. It is the{' '}
              <a
                href="https://www.contributor-covenant.org/version/2/1/code_of_conduct.html"
                className="text-cyan no-underline underline-offset-[3px] hover:underline"
              >
                Contributor Covenant
              </a>
              , and the copy this project ships is{' '}
              <a
                href={`${SITE.repo}/blob/main/CODE_OF_CONDUCT.md`}
                className="text-cyan no-underline underline-offset-[3px] hover:underline"
              >
                in the repository
              </a>
              .
            </p>
          </div>
        </PageBody>
      )}
    </>
  );
}

import { COMMUNITY } from '@/lib/content';
import { breadcrumbs, jsonLd, meta } from '@/lib/meta';
import { SITE } from '@/lib/site';
import { Cta, DocSections, PageHeader } from '@/components/Page';

export const metadata = meta({
  title: COMMUNITY.title,
  description: COMMUNITY.description,
  path: '/community',
});

const CRUMBS = breadcrumbs([
  { name: 'Home', path: '/' },
  { name: 'Community', path: '/community' },
]);

export default function CommunityPage() {
  return (
    <>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: jsonLd(CRUMBS).text }}
      />

      <PageHeader
        eyebrow="Community"
        title={COMMUNITY.h1 ?? COMMUNITY.title}
        lead={COMMUNITY.intro}
      >
        <Cta href={`${SITE.repo}/issues/new`} primary>
          Report a bug
        </Cta>
        <Cta href={`${SITE.repo}/discussions`}>Discussions</Cta>
        <Cta href="/contributing">Contributing</Cta>
        <Cta href="/code-of-conduct">Code of conduct</Cta>
      </PageHeader>

      {/* Chorded to each other rather than chained: a community is a mesh, not
          a queue. */}
      <DocSections doc={COMMUNITY} layout="triad" />
    </>
  );
}

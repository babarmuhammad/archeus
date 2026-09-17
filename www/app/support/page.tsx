import { SUPPORT } from '@/lib/content';
import { breadcrumbs, jsonLd, meta } from '@/lib/meta';
import { SITE } from '@/lib/site';
import { Cta, DocSections, PageHeader } from '@/components/Page';

export const metadata = meta({
  title: SUPPORT.title,
  description: SUPPORT.description,
  path: '/support',
});

const CRUMBS = breadcrumbs([
  { name: 'Home', path: '/' },
  { name: 'Support', path: '/support' },
]);

export default function SupportPage() {
  return (
    <>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: jsonLd(CRUMBS).text }}
      />

      <PageHeader
        eyebrow="Support"
        title={SUPPORT.h1 ?? SUPPORT.title}
        lead={SUPPORT.intro}
      >
        {/* No Donate button here: it is in the site header, on every page. A
            second one at the top of the page that explains the first is the
            call to action competing with its own rationale. The Ko-fi link is
            still in the prose below, where someone who read the argument
            finds it. */}
        <Cta href={`${SITE.repo}/issues/new`}>Report a bug</Cta>
        <Cta href="/contributing">Contributing</Cta>
        <Cta href="/legal/refunds">Donations and refunds</Cta>
      </PageHeader>

      <DocSections doc={SUPPORT} layout="zigzag" />
    </>
  );
}

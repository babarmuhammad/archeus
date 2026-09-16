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
        {/* A plain link, never an embed: a Ko-fi widget would load their script
            and drag cookie consent back onto a site that has none. */}
        <Cta href={SITE.kofi} primary>
          Donate on Ko-fi
        </Cta>
        <Cta href={`${SITE.repo}/issues/new`}>Report a bug</Cta>
        <Cta href="/contributing">Contributing</Cta>
        <Cta href="/legal/refunds">Donations and refunds</Cta>
      </PageHeader>

      <DocSections doc={SUPPORT} layout="zigzag" />
    </>
  );
}

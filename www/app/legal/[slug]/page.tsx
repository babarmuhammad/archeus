import { notFound } from 'next/navigation';
import { SectionView } from '@/components/doc/Blocks';
import { PageHeader } from '@/components/Page';
import { EFFECTIVE, EFFECTIVE_LABEL, LEGAL, LEGAL_BY_SLUG, legalPath } from '@/lib/legal';
import { breadcrumbs, jsonLd, meta } from '@/lib/meta';
import { SITE } from '@/lib/site';

/* Next 16: `params` is a Promise on both the page and generateMetadata. */
type Props = { params: Promise<{ slug: string }> };

export const dynamicParams = false;

export function generateStaticParams() {
  return LEGAL.map((d) => ({ slug: d.slug }));
}

export async function generateMetadata({ params }: Props) {
  const { slug } = await params;
  const doc = LEGAL_BY_SLUG.get(slug);
  if (!doc) return meta({ title: 'Not found', description: '', path: legalPath(slug) });
  return meta({ title: doc.title, description: doc.description, path: legalPath(doc.slug) });
}

export default async function LegalPage({ params }: Props) {
  const { slug } = await params;
  const doc = LEGAL_BY_SLUG.get(slug);
  if (!doc) notFound();

  const CRUMBS = breadcrumbs([
    { name: 'Home', path: '/' },
    { name: doc.title, path: legalPath(doc.slug) },
  ]);

  return (
    <>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: jsonLd(CRUMBS).text }}
      />

      <PageHeader eyebrow="Legal" title={doc.h1 ?? doc.title} lead={doc.intro} />

      {/* Who and when, on every policy, immediately under the heading. A date
          buried at the foot of a policy is a date nobody reads, and an operator
          nobody can name is the gap these pages exist to close. */}
      <p className="mx-auto max-w-4xl px-5 pt-6 text-sm text-dim2">
        Effective <time dateTime={EFFECTIVE}>{EFFECTIVE_LABEL}</time> · {SITE.operator},{' '}
        {SITE.operatorCountry} ·{' '}
        <a
          href={`mailto:${SITE.contact}`}
          className="text-dim no-underline underline-offset-[3px] hover:text-text hover:underline"
        >
          {SITE.contact}
        </a>
      </p>

      {/* A plain column, not the Spine showcase the marketing routes wear: a
          policy is read top to bottom, and a layout that moves the column about
          is the wrong kind of interesting here. */}
      <div className="reveal mx-auto max-w-4xl space-y-14 px-5 py-14">
        {doc.sections.map((s) => (
          <SectionView key={s.id} section={s} />
        ))}
      </div>

      <p className="mx-auto max-w-4xl px-5 pb-16 text-sm text-dim2">
        This is a plain description of how these sites work, not legal advice.
      </p>
    </>
  );
}

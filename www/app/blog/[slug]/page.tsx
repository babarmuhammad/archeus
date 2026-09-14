import Link from 'next/link';
import { notFound } from 'next/navigation';
import { allPosts } from '@/lib/blog';
import { TocDetails, TocRail } from '@/components/blog/Toc';
import { humanDate, readingTime, withHeadingIds } from '@/components/blog/prose';
import { splitHeadings } from '@/lib/build-data';
import { ProseSections } from '@/components/Page';
import { breadcrumbs, jsonLd, meta } from '@/lib/meta';
import { SITE, url } from '@/lib/site';

/* Next 16: `params` is a Promise on both the page and generateMetadata. */
type Props = { params: Promise<{ slug: string }> };

export const dynamicParams = false;

export function generateStaticParams() {
  return allPosts().map((p) => ({ slug: p.slug }));
}

export async function generateMetadata({ params }: Props) {
  const { slug } = await params;
  const post = allPosts().find((p) => p.slug === slug);
  if (!post) return meta({ title: 'Not found', description: '', path: `/blog/${slug}` });
  return meta({
    title: post.title,
    description: post.description,
    path: `/blog/${post.slug}`,
    type: 'article',
    publishedTime: post.date,
    tags: post.tags,
  });
}

export default async function PostPage({ params }: Props) {
  const { slug } = await params;
  // One read: the neighbours come from the same list the post does.
  const posts = allPosts();
  const i = posts.findIndex((p) => p.slug === slug);
  if (i === -1) notFound();

  const post = posts[i];
  const newer = posts[i - 1];
  const older = posts[i + 1];
  const { html, headings } = withHeadingIds(post.html);
  const canonical = url(`/blog/${post.slug}`);

  const ld: object[] = [
    {
      '@context': 'https://schema.org',
      '@type': 'BlogPosting',
      headline: post.title,
      description: post.description,
      datePublished: post.date,
      dateModified: post.date,
      author: { '@type': 'Person', name: post.author, url: SITE.authorGithub },
      publisher: { '@type': 'Person', name: SITE.author, url: SITE.authorGithub },
      mainEntityOfPage: { '@type': 'WebPage', '@id': canonical },
      url: canonical,
      image: url(SITE.ogImage),
      keywords: post.tags.join(', '),
      isAccessibleForFree: true,
    },
    breadcrumbs([
      { name: 'Home', path: '/' },
      { name: 'Blog', path: '/blog' },
      { name: post.title, path: `/blog/${post.slug}` },
    ]),
  ];

  // Only when the post actually carries questions — a FAQPage describing
  // nothing on the page is exactly what Google penalises.
  if (post.faq.length > 0) {
    ld.push({
      '@context': 'https://schema.org',
      '@type': 'FAQPage',
      mainEntity: post.faq.map((f) => ({
        '@type': 'Question',
        name: f.q,
        acceptedAnswer: { '@type': 'Answer', text: f.a },
      })),
    });
  }

  return (
    <div className="mx-auto max-w-6xl px-5 py-16 sm:py-20">
      {ld.map((obj, n) => (
        <script
          key={n}
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: jsonLd(obj).text }}
        />
      ))}

      <div className="lg:grid lg:grid-cols-[minmax(0,1fr)_15rem] lg:gap-12">
        <article className="min-w-0">
          <Link
            href="/blog"
            className="font-mono text-[0.72rem] uppercase tracking-[0.14em] text-dim2 no-underline transition-colors hover:text-cyan"
          >
            ← Blog
          </Link>

          <h1 className="mt-5 text-balance text-3xl font-semibold tracking-tight text-text sm:text-[2.35rem] sm:leading-[1.15]">
            {post.title}
          </h1>
          <p className="mt-4 text-pretty text-lg leading-[1.65] text-dim">
            {post.description}
          </p>

          <p className="mt-5 flex flex-wrap items-center gap-x-2 gap-y-1 font-mono text-[0.72rem] uppercase tracking-[0.1em] text-dim2">
            <time dateTime={post.date}>{humanDate(post.date)}</time>
            <span aria-hidden="true">·</span>
            <span>{readingTime(post.text)} min read</span>
            <span aria-hidden="true">·</span>
            <span>{post.author}</span>
          </p>

          {post.tags.length > 0 && (
            <p className="mt-4 flex flex-wrap gap-2">
              {post.tags.map((t) => (
                <span
                  key={t}
                  className="rounded-full border border-line bg-panel2/60 px-2.5 py-0.5 font-mono text-[0.7rem] text-cyan/80"
                >
                  {t}
                </span>
              ))}
            </p>
          )}

          <div className="mt-10 lg:hidden">
            <TocDetails headings={headings} />
          </div>

          {/* The post's own <h2>s become sections on the rail. Its prose fills
              the column, exactly like /changelog, so it gets the same answer:
              the column moves right and the solids run down the left. The TOC
              rail stays — the spine shows you where you are, the TOC is how you
              jump. `withHeadingIds` has already anchored every heading, and
              splitHeadings keeps those ids rather than minting new ones. */}
          <div className="mt-10">
            <ProseSections sections={splitHeadings(html)} />
          </div>

          {post.faq.length > 0 && (
            <section className="mt-16">
              <h2 className="border-t border-line pt-6 text-2xl font-semibold tracking-tight text-text">
                Frequently asked
              </h2>
              <dl className="mt-6 space-y-4">
                {post.faq.map((f) => (
                  <div key={f.q} className="panel p-5">
                    <dt className="font-semibold text-text">{f.q}</dt>
                    <dd className="mt-2 text-[0.95rem] leading-[1.7] text-dim">{f.a}</dd>
                  </div>
                ))}
              </dl>
            </section>
          )}

          {(newer || older) && (
            <nav
              aria-label="More posts"
              className="hairline mt-16 grid gap-4 pt-8 sm:grid-cols-2"
            >
              {[
                { post: newer, label: 'Newer' },
                { post: older, label: 'Older' },
              ].map(({ post: p, label }) =>
                p ? (
                  <Link
                    key={label}
                    href={`/blog/${p.slug}`}
                    className="panel p-4 no-underline transition-transform duration-200 hover:-translate-y-0.5"
                  >
                    <span className="font-mono text-[0.7rem] uppercase tracking-[0.14em] text-dim2">
                      {label}
                    </span>
                    <span className="mt-1.5 block text-pretty font-semibold text-text">
                      {p.title}
                    </span>
                  </Link>
                ) : (
                  <span key={label} className="hidden sm:block" />
                ),
              )}
            </nav>
          )}

          <p className="mt-10">
            <Link
              href="/blog"
              className="text-[0.9rem] text-cyan no-underline hover:text-violet"
            >
              ← Back to all posts
            </Link>
          </p>
        </article>

        <aside className="hidden lg:block">
          <TocRail headings={headings} />
        </aside>
      </div>
    </div>
  );
}

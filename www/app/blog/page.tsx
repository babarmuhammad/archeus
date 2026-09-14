import Link from 'next/link';
import { allPosts } from '@/lib/blog';
import { humanDate, readingTime } from '@/components/blog/prose';
import { breadcrumbs, jsonLd, meta } from '@/lib/meta';
import { SITE, url } from '@/lib/site';
import { Spine } from '@/components/site/Spine';

const TITLE = 'Blog';
const DESCRIPTION =
  'Long-form notes on working with Claude Code: session archives, CLAUDE.md and context cost, multi-account setups, and what Claude Code writes to disk.';

export const metadata = meta({ title: TITLE, description: DESCRIPTION, path: '/blog' });

export default function BlogIndex() {
  const posts = allPosts();

  const ld = {
    '@context': 'https://schema.org',
    '@type': 'Blog',
    name: `${SITE.name} blog`,
    description: DESCRIPTION,
    url: url('/blog'),
    author: { '@type': 'Person', name: SITE.author, url: SITE.authorGithub },
    blogPost: posts.map((p) => ({
      '@type': 'BlogPosting',
      headline: p.title,
      description: p.description,
      datePublished: p.date,
      url: url(`/blog/${p.slug}`),
    })),
  };

  return (
    <div className="py-16 sm:py-20">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: jsonLd(ld).text }}
      />
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{
          __html: jsonLd(
            breadcrumbs([
              { name: 'Home', path: '/' },
              { name: TITLE, path: '/blog' },
            ]),
          ).text,
        }}
      />

      <div className="mx-auto max-w-[74rem] px-5">
        <h1 className="text-balance text-3xl font-semibold tracking-tight text-text sm:text-[2.5rem] sm:leading-[1.15]">
          Blog
        </h1>
        <p className="mt-4 max-w-3xl text-pretty text-lg leading-[1.65] text-dim">
          {DESCRIPTION}
        </p>
      </div>

      {posts.length === 0 ? (
        <p className="mx-auto mt-14 max-w-[74rem] px-5 text-dim2">No posts yet.</p>
      ) : (
        // A rail on the LEFT, so the index does not read as the FAQ with
        // different words in it.
        <Spine
          layout="rail-left"
          items={posts.map((post) => ({
            key: post.slug,
            // A longer post is a bigger solid: same derived-weight rule the rest
            // of the site uses, no hand-kept ordering.
            weight: post.text.length,
            node: (
              <Link
                href={`/blog/${post.slug}`}
                className="panel block p-5 no-underline transition-transform duration-200 hover:-translate-y-0.5 sm:p-6"
              >
                <h2 className="text-pretty text-xl font-semibold tracking-tight text-text sm:text-[1.35rem]">
                  {post.title}
                </h2>
                <p className="mt-2 text-[0.95rem] leading-[1.7] text-dim">
                  {post.description}
                </p>

                <p className="mt-4 flex flex-wrap items-center gap-x-2 gap-y-1 font-mono text-[0.72rem] uppercase tracking-[0.1em] text-dim2">
                  <time dateTime={post.date}>{humanDate(post.date)}</time>
                  <span aria-hidden="true">·</span>
                  <span>{readingTime(post.text)} min read</span>
                </p>

                {post.tags.length > 0 && (
                  <p className="mt-3 flex flex-wrap gap-2">
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
              </Link>
            ),
          }))}
        />
      )}
    </div>
  );
}

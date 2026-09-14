import type { ReactNode } from 'react';
import Link from 'next/link';
import type { Doc } from '@/lib/content';
import type { HtmlSection } from '@/lib/build-data';
import { SectionView } from '@/components/doc/Blocks';
import { Spine, type SpineLayout } from '@/components/site/Spine';

/**
 * The chrome every apex route opens with, so the nine of them read as one site.
 *
 * Width is fixed at max-w-4xl here and in DocSections deliberately: DocView in
 * components/doc/Blocks.tsx already uses it, and a page that mixes widths shows
 * a ragged left edge the moment a screenshot sits next to a paragraph.
 */
export function PageHeader({
  eyebrow,
  title,
  lead,
  children,
}: {
  eyebrow?: string;
  title: string;
  lead?: string;
  /** Call-to-action row under the lead. */
  children?: ReactNode;
}) {
  return (
    <header className="reveal mx-auto max-w-4xl px-5 pt-14 sm:pt-20">
      {eyebrow ? (
        <p className="mb-3 font-mono text-[0.7rem] uppercase tracking-[0.16em] text-cyan/80">
          {eyebrow}
        </p>
      ) : null}
      <h1 className="text-balance text-3xl font-semibold tracking-tight text-text sm:text-[2.5rem] sm:leading-[1.15]">
        {title}
      </h1>
      {lead ? (
        <p className="mt-4 max-w-3xl text-pretty text-lg leading-[1.65] text-dim">{lead}</p>
      ) : null}
      {children ? <div className="mt-7 flex flex-wrap items-center gap-3">{children}</div> : null}
    </header>
  );
}

/**
 * A Doc's sections, with an optional node appended after a named one — which is
 * how a screenshot lands inside the section it illustrates without the prose
 * having to know an image exists.
 */
export function DocSections({
  doc,
  after,
  layout,
}: {
  doc: Doc;
  after?: Record<string, ReactNode>;
  /** Which showcase this route wears. Every apex route picks its own — see the
   *  `.spine-*` grids at the end of app/globals.css. */
  layout?: SpineLayout;
}) {
  return (
    <div className="py-16">
      <Spine
        layout={layout}
        items={doc.sections.map((s) => ({
          key: s.id,
          // Weight is how much the section actually contains — a table of six
          // rows outweighs a one-paragraph aside. Derived rather than authored,
          // so nobody has to keep a second list of importances in step.
          weight: s.blocks.reduce(
            (n, b) =>
              n +
              (b.kind === 'ul' ? b.items.length
                : b.kind === 'dl' ? b.items.length * 2
                : b.kind === 'table' ? b.rows.length * 2
                : 1),
            0,
          ),
          node: (
            <div className="space-y-8">
              <SectionView section={s} />
              {after?.[s.id]}
            </div>
          ),
        }))}
      />
    </div>
  );
}

/** Body wrapper for the routes that render markdown rather than a Doc. */
export function PageBody({ children }: { children: ReactNode }) {
  return <div className="reveal mx-auto max-w-4xl px-5 py-16">{children}</div>;
}

/**
 * A rendered markdown page as spine sections, one per `<h2>`.
 *
 * The routes that render a repository file straight to HTML — changelog,
 * contributing, code of conduct — were the only ones with nothing for the rail
 * to show, and an earlier attempt to give them one drew the solids over the
 * text: their prose fills the whole column, so there is no empty half. The
 * `zigzag` layout answers that by moving the COLUMN instead, and a release or a
 * numbered step is already a section, so nothing had to be invented as data.
 */
export function ProseSections({
  sections,
  layout = 'zigzag',
}: {
  sections: HtmlSection[];
  layout?: SpineLayout;
}) {
  return (
    <div className="py-14">
      <Spine
        layout={layout}
        items={sections.map((s) => ({
          key: s.id,
          weight: s.html.length,
          node: (
            // No id here: splitHeadings puts it on the <h2> itself, so the
            // anchor is on the heading a reader is actually looking for and two
            // elements never claim the same one.
            <div
              // The section's own heading is its first child, so the rule that
              // puts a top border above every h2 would draw one above nothing.
              className="prose scroll-mt-24 [&>h2:first-child]:mt-0 [&>h2:first-child]:border-0 [&>h2:first-child]:pt-0 [&_h2]:scroll-mt-24"
              dangerouslySetInnerHTML={{ __html: s.html }}
            />
          ),
        }))}
      />
    </div>
  );
}

/** A link that looks like a button. next/link renders a plain anchor for an
 *  absolute URL, so the external destinations need no second component. */
export function Cta({
  href,
  primary,
  children,
}: {
  href: string;
  primary?: boolean;
  children: ReactNode;
}) {
  return (
    <Link
      href={href}
      className={`rounded-lg border px-4 py-2 text-sm no-underline transition-colors ${
        primary
          ? 'border-cyan/45 bg-cyan/10 text-text hover:border-cyan/75'
          : 'border-line text-dim hover:border-cyan/45 hover:text-text'
      }`}
    >
      {children}
    </Link>
  );
}

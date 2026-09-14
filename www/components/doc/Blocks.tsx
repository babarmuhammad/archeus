import type { Block, Doc, Section } from '@/lib/content';

/**
 * One renderer for the Doc/Section/Block data in lib/content.ts.
 *
 * Every apex route renders through this, so a page cannot invent its own
 * typography and /llms-full.txt (generated from the same Doc) cannot drift from
 * what a human reads.
 */
function BlockView({ block }: { block: Block }) {
  switch (block.kind) {
    case 'p':
      return <p className="text-[0.98rem] leading-[1.75] text-dim">{block.text}</p>;

    case 'ul':
      return (
        <ul className="space-y-2">
          {block.items.map((it) => (
            <li key={it} className="flex gap-3 text-[0.95rem] leading-[1.7] text-dim">
              <span aria-hidden="true" className="mt-[0.6em] h-1 w-1 shrink-0 rounded-full bg-cyan/70" />
              <span>{it}</span>
            </li>
          ))}
        </ul>
      );

    case 'dl':
      return (
        <dl className="grid gap-3 sm:grid-cols-2">
          {block.items.map((it) => (
            <div key={it.t} className="panel p-4">
              <dt className="text-[0.95rem] font-semibold text-text">{it.t}</dt>
              <dd className="mt-1.5 text-[0.9rem] leading-[1.65] text-dim">{it.d}</dd>
            </div>
          ))}
        </dl>
      );

    case 'code':
      return (
        <figure className="panel-solid overflow-hidden">
          {block.label ? (
            <figcaption className="border-b border-line px-4 py-2 font-mono text-[0.7rem] uppercase tracking-[0.14em] text-dim2">
              {block.label}
            </figcaption>
          ) : null}
          <pre className="overflow-x-auto px-4 py-3 font-mono text-[0.85rem] leading-[1.7] text-module">
            <code>{block.text}</code>
          </pre>
        </figure>
      );

    case 'table':
      return (
        <div className="panel-solid overflow-x-auto">
          <table className="w-full border-collapse text-left text-[0.88rem]">
            <thead>
              <tr>
                {block.head.map((h) => (
                  <th
                    key={h}
                    className="border-b border-line px-4 py-2.5 font-semibold text-text"
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {block.rows.map((row, i) => (
                <tr key={i} className="border-b border-line/60 last:border-0">
                  {row.map((cell, j) => (
                    <td
                      key={j}
                      className={`px-4 py-2.5 align-top ${j === 0 ? 'text-text' : 'text-dim'}`}
                    >
                      {cell}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
  }
}

export function SectionView({ section }: { section: Section }) {
  return (
    // `reveal` is the site-wide scroll entrance: a native view timeline, so no
    // observer and no JS. Where animation-timeline is unsupported it plays once
    // on load and fills forwards, which leaves the copy visible either way.
    <section id={section.id} className="reveal scroll-mt-20">
      {section.eyebrow ? (
        <p className="mb-2 font-mono text-[0.7rem] uppercase tracking-[0.16em] text-cyan/80">
          {section.eyebrow}
        </p>
      ) : null}
      <h2 className="text-balance text-2xl font-semibold tracking-tight text-text sm:text-[1.75rem]">
        {section.heading}
      </h2>
      {section.lead ? (
        <p className="mt-3 max-w-3xl text-pretty text-[1.02rem] leading-[1.7] text-dim">
          {section.lead}
        </p>
      ) : null}
      <div className="mt-6 space-y-5">
        {section.blocks.map((b, i) => (
          <BlockView key={i} block={b} />
        ))}
      </div>
    </section>
  );
}

/** A whole Doc as a page body: h1, intro, then every section. */
export function DocView({ doc }: { doc: Doc }) {
  return (
    <div className="mx-auto max-w-4xl px-5 py-16 sm:py-20">
      <h1 className="text-balance text-3xl font-semibold tracking-tight text-text sm:text-[2.5rem] sm:leading-[1.15]">
        {doc.h1 ?? doc.title}
      </h1>
      {doc.intro ? (
        <p className="mt-4 max-w-3xl text-pretty text-lg leading-[1.65] text-dim">{doc.intro}</p>
      ) : null}
      <div className="mt-14 space-y-16">
        {doc.sections.map((s) => (
          <SectionView key={s.id} section={s} />
        ))}
      </div>
    </div>
  );
}

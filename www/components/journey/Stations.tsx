import Image from 'next/image';
import Link from 'next/link';
import type { Block, Section } from '@/lib/content';
import { HOME } from '@/lib/content';
import { SITE } from '@/lib/site';
import { SectionView } from '@/components/doc/Blocks';
import { CopyLine } from './CopyLine';

/**
 * The six stations, as server-rendered DOM.
 *
 * Copy is DOM and not canvas text on purpose: a crawler has to see the words in
 * view-source, and canvas text would also ignore the palette, need font loading
 * and re-rasterise every frame. The scene behind is decoration; this is the page.
 *
 * `data-station` is the contract with Canvas.tsx, which measures these offsets
 * to drive the camera. Every panel needs one, in order.
 */

/** Which side the copy sits on. The scene places the six centres at centre,
 *  left, right, left, right, centre (STATIONS in scene.ts) and the camera looks
 *  AT each one, so a parked solid is always frame-centre — the alternation is
 *  what keeps the copy off it, and it runs against the direction the camera
 *  travels between stations. The finale centres because the camera has pulled
 *  back and the constellation spreads wider than the card. */
const SIDE = [
  'justify-start',
  'justify-end',
  'justify-start',
  'justify-end',
  'justify-start',
  'justify-center',
] as const;

/** The three stations that earn a real screenshot instead of another abstract
 *  panel — and these are the SAME three files scene.ts hangs on framed planes in
 *  3D, at the same stations.
 *
 *  So this markup is the fallback, not a second copy: `html.journey-on
 *  .shot-fallback` hides it the moment GL has actually painted. A visitor with
 *  no WebGL, a dead context or a machine that cannot run the scene still sees
 *  every picture and its alt text; everybody else sees it fly in on its node
 *  face, once, and never twice on one screen. */
const SHOTS: Record<string, { src: string; alt: string }> = {
  memory: {
    src: '/img/gui-memory.png',
    alt: 'The memory tab: entities, relations and lessons extracted from a codebase, with token budgets per surface.',
  },
  workspace: {
    src: '/img/tui-sessions.png',
    alt: 'The session browser: every Claude Code session in a project, searchable, with tokens and cost per session.',
  },
  tokens: {
    src: '/img/gui-usage.png',
    alt: 'The usage screen: tokens in, out and cached with estimated cost per project, per day and per model.',
  },
};

type CodeBlock = Extract<Block, { kind: 'code' }>;
const isCode = (b: Block): b is CodeBlock => b.kind === 'code';
const isUl = (b: Block): b is Extract<Block, { kind: 'ul' }> => b.kind === 'ul';

const BTN =
  'inline-flex items-center justify-center gap-2 rounded-xl px-5 py-3 text-[0.95rem] font-semibold no-underline transition-colors';

function Shot({ id }: { id: string }) {
  const shot = SHOTS[id];
  if (!shot) return null;
  return (
    <figure className="shot-fallback mt-7">
      <Image
        src={shot.src}
        alt={shot.alt}
        width={1600}
        height={1000}
        sizes="(max-width: 640px) 90vw, 40rem"
        className="h-auto w-full rounded-lg border border-line"
      />
    </figure>
  );
}

function Panel({
  index,
  wide = false,
  children,
}: {
  index: number;
  wide?: boolean;
  children: React.ReactNode;
}) {
  return (
    <section
      data-station={index}
      className="flex min-h-[100svh] items-center px-5 py-16 sm:py-28"
    >
      <div className={`mx-auto flex w-full max-w-[92rem] ${SIDE[index] ?? 'justify-start'}`}>
        <div
          className={`panel-solid station-in w-full p-6 sm:p-8 ${wide ? 'max-w-[42rem]' : 'max-w-[38rem]'}`}
        >
          {children}
        </div>
      </div>
    </section>
  );
}

/** Station 01. Hand-composed rather than run through SectionView: it is the
 *  only panel with an h1, a copy button and the two CTAs, and the point of the
 *  page is that you can get archeus from it without scrolling. */
function Hero({ section }: { section: Section }) {
  const install = section.blocks.filter(isCode)[0];
  const bullets = section.blocks.filter(isUl).flatMap((b) => b.items);

  return (
    <section
      id={section.id}
      data-station={0}
      className="flex min-h-[100svh] scroll-mt-20 items-center px-5 py-16 sm:py-28"
    >
      <div className="mx-auto flex w-full max-w-[92rem] justify-start">
        <div className="panel station-in w-full max-w-[40rem] p-6 sm:p-9">
          {section.eyebrow ? (
            <p className="mb-3 font-mono text-[0.7rem] uppercase tracking-[0.16em] text-cyan/80">
              {section.eyebrow}
            </p>
          ) : null}

          <h1 className="text-balance text-[2.15rem] font-semibold leading-[1.08] tracking-tight text-text sm:text-[3.1rem]">
            {HOME.h1 ?? HOME.title}
          </h1>

          {HOME.intro ? (
            <p className="mt-5 max-w-2xl text-pretty text-[1.1rem] leading-[1.6] text-dim">
              {HOME.intro}
            </p>
          ) : null}
          {section.lead ? (
            <p className="mt-3 max-w-2xl text-pretty text-[0.97rem] leading-[1.7] text-dim">
              {section.lead}
            </p>
          ) : null}

          {install ? (
            <CopyLine text={install.text} label={install.label} className="mt-7" />
          ) : null}

          <div className="mt-5 flex flex-wrap gap-3">
            <Link href="/download" className={`${BTN} bg-cyan text-bg hover:bg-violet`}>
              Download archeus
              <span aria-hidden="true">↓</span>
            </Link>
            <a
              href={SITE.docs}
              className={`${BTN} border border-line bg-panel2/60 text-text hover:border-cyan/60`}
            >
              Documentation
            </a>
          </div>

          {bullets.length ? (
            <ul className="mt-8 grid gap-2.5 border-t border-line pt-7 sm:grid-cols-2">
              {bullets.map((it) => (
                <li key={it} className="flex gap-2.5 text-[0.88rem] leading-[1.6] text-dim">
                  <span
                    aria-hidden="true"
                    className="mt-[0.55em] h-1 w-1 shrink-0 rounded-full bg-cyan/70"
                  />
                  <span>{it}</span>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      </div>
    </section>
  );
}

/** The finale. The camera has pulled back to hold all six solids in frame, so
 *  this panel is centred and full-width and ends the page on the install lines
 *  plus one last CTA row. Every non-code block still goes through the shared
 *  renderer, so nothing in the section can be silently dropped here. */
function Finale({ section, index }: { section: Section; index: number }) {
  const codes = section.blocks.filter(isCode);
  const rest = section.blocks.filter((b) => !isCode(b));

  return (
    <Panel index={index} wide>
      <SectionView section={{ ...section, blocks: rest }} />
      <div className="mt-6 space-y-3">
        {codes.map((b) => (
          <CopyLine key={b.text} text={b.text} label={b.label} />
        ))}
      </div>
      <div className="mt-8 flex flex-wrap gap-3 border-t border-line pt-7">
        <Link href="/download" className={`${BTN} bg-cyan text-bg hover:bg-violet`}>
          Download archeus
          <span aria-hidden="true">↓</span>
        </Link>
        <a
          href={SITE.docs}
          className={`${BTN} border border-line bg-panel2/60 text-text hover:border-cyan/60`}
        >
          Documentation
        </a>
        <a
          href={SITE.repo}
          className={`${BTN} border border-line bg-panel2/60 text-dim hover:border-cyan/60 hover:text-text`}
        >
          Source on GitHub
        </a>
      </div>
    </Panel>
  );
}

export function Stations() {
  const [hero, ...rest] = HOME.sections;
  const middle = rest.slice(0, -1);
  const finale = rest[rest.length - 1];

  return (
    <div id="journey-stations">
      <Hero section={hero} />
      {middle.map((s, i) => (
        <Panel key={s.id} index={i + 1}>
          <SectionView section={s} />
          <Shot id={s.id} />
        </Panel>
      ))}
      {finale ? <Finale section={finale} index={HOME.sections.length - 1} /> : null}
    </div>
  );
}

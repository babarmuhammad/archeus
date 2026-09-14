import type { ReactNode } from 'react';
import { FEATURES } from '@/lib/content';
import { breadcrumbs, jsonLd, meta } from '@/lib/meta';
import { SITE } from '@/lib/site';
import { Cta, DocSections, PageHeader } from '@/components/Page';
import { Shot, ShotPair } from '@/components/Shot';

export const metadata = meta({
  title: FEATURES.title,
  description: FEATURES.description,
  path: '/features',
});

const CRUMBS = breadcrumbs([
  { name: 'Home', path: '/' },
  { name: 'Features', path: '/features' },
]);

/** The grid is the Doc's own sections, not a second copy of them: a hand-written
 *  summary card would drift from the section it links to. A section with no lead
 *  gets no card rather than invented copy. */
const CARDS = FEATURES.sections.filter((s) => s.lead);

const HALF = '(min-width: 936px) 420px, (min-width: 640px) 45vw, 100vw';

/** Screenshots, keyed by the section each one illustrates. Keeping them out here
 *  is what lets lib/content.ts stay prose that /llms-full.txt can render. */
const SHOTS: Record<string, ReactNode> = {
  sessions: (
    <ShotPair>
      <Shot
        src="/img/gui-sessions.png"
        width={1600}
        height={1000}
        sizes={HALF}
        alt="The archeus session browser listing past Claude Code sessions with topic, message count and age."
        caption="Every session in a project, searchable and resumable."
      />
      <Shot
        src="/img/tui-sessions.png"
        width={836}
        height={456}
        sizes={HALF}
        alt="The same session list in the keyboard-first terminal UI."
        caption="The same list in the terminal UI."
      />
    </ShotPair>
  ),
  memory: (
    <Shot
      src="/img/gui-memory.png"
      width={1600}
      height={1000}
      alt="The memory screen showing the project's semantic graph, its entities and the learned lessons."
      caption="The project memory graph, its entities and the lessons distilled from past sessions."
    />
  ),
  integration: (
    <Shot
      src="/img/gui-claude-code.png"
      width={1600}
      height={1000}
      alt="The Claude Code screen listing MCP servers, agents, skills and hooks for the project."
      caption="MCP servers, agents, skills and hooks, per project and per account."
    />
  ),
  health: (
    <Shot
      src="/img/gui-usage.png"
      width={1600}
      height={1000}
      alt="The usage screen breaking down tokens and estimated cost per project, session, day and model."
      caption="Tokens and estimated cost, parsed from your own local transcripts."
    />
  ),
  gui: (
    <div className="space-y-4">
      <ShotPair>
        <Shot
          src="/img/gui-skin-graph.png"
          width={1600}
          height={1000}
          sizes={HALF}
          alt="The GUI wearing the graph world: cards drawn as nodes with connector stubs."
          caption="The graph world."
        />
        <Shot
          src="/img/gui-skin-crt.png"
          width={1600}
          height={1000}
          sizes={HALF}
          alt="The GUI wearing the CRT skin: scanlines, a blinking caret and phosphor type."
          caption="The CRT skin."
        />
      </ShotPair>
      <Shot
        src="/img/tui-main.png"
        width={836}
        height={477}
        alt="The archeus terminal UI main screen, listing projects with usage bars."
        caption="And the terminal UI, which has parity with all of it."
      />
    </div>
  ),
};

export default function FeaturesPage() {
  return (
    <>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: jsonLd(CRUMBS).text }}
      />

      <PageHeader
        eyebrow="Features"
        title={FEATURES.h1 ?? FEATURES.title}
        lead={FEATURES.intro}
      >
        <Cta href="/download" primary>
          Install archeus
        </Cta>
        <Cta href={SITE.docs}>Read the documentation</Cta>
      </PageHeader>

      <div className="mx-auto max-w-4xl px-5 pt-12">
        <ul className="grid gap-3 sm:grid-cols-2">
          {CARDS.map((s) => (
            <li key={s.id}>
              <a
                href={`#${s.id}`}
                className="panel group block h-full p-5 no-underline transition-transform hover:-translate-y-0.5"
              >
                <h2 className="text-[0.98rem] font-semibold text-text transition-colors group-hover:text-cyan">
                  {s.heading}
                </h2>
                <p className="mt-1.5 text-[0.88rem] leading-[1.6] text-dim">{s.lead}</p>
              </a>
            </li>
          ))}
        </ul>

        <div className="mt-8">
          <Shot
            src="/img/gui-dashboard.png"
            width={1600}
            height={1000}
            priority
            alt="The archeus desktop dashboard: projects, recent sessions, usage and job status on one screen."
            caption="The dashboard: every project Claude Code has opened, with its sessions, memory and usage."
          />
        </div>
      </div>

      {/* Nine sections, each with something to show: full-height rows, the copy
          and its solid trading sides down the page. */}
      <DocSections doc={FEATURES} after={SHOTS} layout="beside" />
    </>
  );
}

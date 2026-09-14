import type { ReactNode } from 'react';

/**
 * The section rail, and the contract that places the 3D solids.
 *
 * Two things live here and nowhere else:
 *
 *  1. `data-section` / `data-weight` — which section you are reading, and how
 *     much it contains.
 *  2. `.spine-slot` — an EMPTY element sitting in the space this page leaves for
 *     that section's solid. Canvas.tsx measures its rect and the scene draws
 *     inside it.
 *
 * The second one is the whole design. The scene used to derive a position from
 * the frustum (`u_sx`/`u_sy`/`u_fs` plus a `dense` flag), which cannot know where
 * the copy is: solids sat at the viewport centre while the copy was half a screen
 * above, landed in the margin outside a `max-w-4xl` column, and had to be turned
 * off on the pages whose prose filled the width. Now CSS decides the space and
 * the scene obeys it, so a page's showcase is a grid in globals.css rather than
 * new shader code — which is why every route below can have its own.
 *
 * The layouts are defined at the end of app/globals.css, keyed by these class
 * names. They are hand-written CSS, not Tailwind, precisely so `spine-${layout}`
 * can be interpolated — a Tailwind class built by interpolation never gets
 * generated, because the scanner reads source text.
 */

export type SpineLayout =
  /** features — full-height rows, copy and solid trading sides */
  | 'beside'
  /** download — solid in a fixed right column, one rung per step */
  | 'ladder'
  /** architecture — one column, solids nested front to back */
  | 'depth'
  /** about — solids circling a point beside the copy */
  | 'orbit'
  /** community — three solids, chorded to each other rather than chained */
  | 'triad'
  /** blog — a narrow rail of small solids down the left */
  | 'rail-left'
  /** faq — the same rail on the right */
  | 'rail-right'
  /** changelog and the prose routes — solids down the left, alternating out */
  | 'zigzag';

export type SpineItem = {
  key: string;
  node: ReactNode;
  /** How much this section contains. Relative, normalised by the scene: it
   *  decides how much of its slot the solid fills, never where the slot is. */
  weight?: number;
};

/** connections.TYPE_COLORS, cycled — the same palette the scene draws with.
 *  Written out in full because Tailwind scans source text: a class built by
 *  interpolation (`bg-${name}`) is a class that never gets generated. */
const NODE = [
  'bg-module', 'bg-component', 'bg-concept', 'bg-service', 'bg-model', 'bg-agent',
] as const;

export function Spine({
  items,
  layout = 'beside',
}: {
  items: SpineItem[];
  layout?: SpineLayout;
}) {
  return (
    // data-layout is what Canvas.tsx reads to know which showcase to drive; the
    // class is what globals.css reads to lay the slots out. One name, two sides.
    <div className={`spine spine-${layout}`} data-spine data-layout={layout}>
      <ol>
        {items.map((it, i) => (
          <li
            key={it.key}
            data-section={i}
            data-weight={it.weight ?? 1}
            className="spine-row"
          >
            <div className="spine-mark" aria-hidden="true">
              {/* The rail. A scaled div, not an SVG path: `stroke-dashoffset`
                  repaints, and the rule here is transform and opacity only. It
                  spans the whole row, so a tall section gets a long rail for free
                  and nothing has to measure anything. The last row stops halfway
                  — a tree ends, it does not trail off. */}
              <span
                className={`spine-rail${i === items.length - 1 ? ' spine-rail-end' : ''}`}
              />
              <span className={`spine-node ${NODE[i % NODE.length]}`} />
            </div>
            <div className="spine-copy reveal">{it.node}</div>
            {/* Empty on purpose: this is the space, not a thing in it. */}
            <div className="spine-slot" data-slot aria-hidden="true" />
          </li>
        ))}
      </ol>
    </div>
  );
}

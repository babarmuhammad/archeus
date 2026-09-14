/**
 * The mark: the archeus A, pierced by its orbit — the same figure as the app
 * icon (`docs/assets/logo.png`), the OG card's tile and the desktop app's
 * sidebar. Artwork by Federico Coscia (github.com/cosfederico); this is it
 * re-cut as a single monochrome glyph.
 *
 * This is brand-study §5.3, the monochrome tier, and the whole point of the
 * tier is that it carries NO colour of its own: every stroke is
 * `currentColor`, so the glyph inherits whatever contrast the surface it sits
 * on has already been held to. That is why it replaced a version whose strokes
 * were `var(--color-cyan)` / `var(--color-violet)` — those vars exist on this
 * site and nowhere else, so the same component was wrong the moment it was
 * used anywhere but here.
 *
 * Inline SVG rather than a file: one request fewer, and `currentColor` cannot
 * cross an <img>.
 *
 * The letter is FILLED, not stroked — a uniform stroke draws a wire diagram of
 * an A. Two triangles of unequal foot width (thin left, heavy right) plus a
 * crescent crossbar that dips in the middle. The bead sits ON the orbit by
 * construction: it is inside the same rotated <g>, at
 * (16 + rx·cos-42°, 16.5 + ry·sin-42°).
 */
export function Mark({ className = '' }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={className} aria-hidden="true">
      <g fill="currentColor">
        <path d="M16 3.6 L7.6 27.8 L4.8 27.8 Z" />
        <path d="M16 3.6 L27.7 27.8 L23.5 27.8 Z" />
        <path d="M8.6 21 Q16 28.2 23.4 21 Q16 23.6 8.6 21 Z" />
      </g>
      <g transform="rotate(-18 16 16.5)">
        <ellipse
          cx="16"
          cy="16.5"
          rx="13.2"
          ry="5.4"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.35"
          opacity="0.55"
        />
        <circle cx="25.81" cy="12.89" r="1.7" fill="currentColor" />
      </g>
    </svg>
  );
}

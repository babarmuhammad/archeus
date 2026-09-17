/**
 * A coffee cup, for the donation link in the header.
 *
 * Inline SVG in `currentColor`, the way `Mark` is and for the same two reasons:
 * one request fewer, and `currentColor` cannot cross an `<img>` — so the glyph
 * takes the button's ink and there is no second place to keep the two in step.
 *
 * Steam is drawn but the cup reads without it; there is no animation on it. A
 * looping wisp beside a nav label is the ambient motion this project deleted
 * everywhere else, and the button is not asking for attention it has not earned.
 */
export function CoffeeCup({ className = '' }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden="true" fill="none">
      <path
        d="M4 9h12v6a5 5 0 0 1-5 5H9a5 5 0 0 1-5-5V9Z"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinejoin="round"
      />
      <path
        d="M16 10.5h1.8a2.7 2.7 0 0 1 0 5.4H16"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinecap="round"
      />
      <path
        d="M8 2.6c-.9 1.1-.9 2 0 3.1M12 2.6c-.9 1.1-.9 2 0 3.1"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        opacity="0.65"
      />
    </svg>
  );
}

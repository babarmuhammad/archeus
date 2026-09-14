'use client';

import { useState } from 'react';

/**
 * The one client component on the marketing routes. Everything else is rendered
 * at build time; copying to the clipboard is the single thing that cannot be.
 */
export function CopyButton({ text, label = 'Copy' }: { text: string; label?: string }) {
  const [done, setDone] = useState(false);

  return (
    <button
      type="button"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text);
        } catch {
          // No clipboard permission, or an insecure origin. The command is
          // still on screen and selectable, so say nothing and do nothing.
          return;
        }
        setDone(true);
        setTimeout(() => setDone(false), 1600);
      }}
      // The visible label is two words that change; the accessible name says
      // what is actually being copied.
      aria-label={`Copy command: ${text}`}
      className="shrink-0 rounded-md border border-line px-2.5 py-1 text-center font-sans text-[0.7rem] text-dim transition-colors hover:border-cyan/50 hover:text-text"
    >
      {/* Fixed width so the label swap cannot nudge the row it sits in. */}
      <span aria-live="polite" className="inline-block min-w-[3.4rem]">
        {done ? 'Copied' : label}
      </span>
    </button>
  );
}

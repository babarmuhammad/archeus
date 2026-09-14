'use client';

/**
 * A command with a copy button — the one interaction the landing page owes the
 * visitor, since "download archeus" really means "run this line".
 *
 * Styled to match the `code` case in components/doc/Blocks.tsx, so a command
 * looks the same wherever on the site it appears.
 */
import { useState } from 'react';

export function CopyLine({
  text,
  label,
  className = '',
}: {
  text: string;
  label?: string;
  className?: string;
}) {
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      // Clipboard denied or unavailable. The text is selectable; that is the
      // fallback, and it needs no code.
    }
  };

  return (
    <figure className={`panel-solid overflow-hidden ${className}`}>
      <figcaption className="flex items-center justify-between gap-3 border-b border-line px-4 py-2">
        <span className="font-mono text-[0.7rem] uppercase tracking-[0.14em] text-dim2">
          {label ?? 'install'}
        </span>
        <button
          type="button"
          onClick={copy}
          aria-live="polite"
          className="-my-1 rounded-md border border-line px-2.5 py-1 font-mono text-[0.7rem] uppercase tracking-[0.1em] text-dim transition-colors hover:border-cyan/60 hover:text-text"
        >
          {copied ? 'Copied' : 'Copy'}
        </button>
      </figcaption>
      <pre className="overflow-x-auto px-4 py-3.5 font-mono text-[0.9rem] leading-[1.7] text-module">
        <code>{text}</code>
      </pre>
    </figure>
  );
}

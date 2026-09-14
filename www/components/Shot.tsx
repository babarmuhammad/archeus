import type { ReactNode } from 'react';
import Image from 'next/image';

/**
 * A product screenshot in a panel with a caption.
 *
 * Every shot is a real capture of the app, so the intrinsic size is passed
 * through rather than guessed — next/image needs it to reserve the box and stop
 * the page reflowing as each one arrives.
 */
export function Shot({
  src,
  width,
  height,
  alt,
  caption,
  sizes = '(min-width: 936px) 856px, 100vw',
  priority,
  unoptimized,
}: {
  src: string;
  width: number;
  height: number;
  alt: string;
  caption?: string;
  sizes?: string;
  priority?: boolean;
  /** Animated GIF: the optimizer would either strip the animation or spend the
   *  build re-encoding megabytes of it. */
  unoptimized?: boolean;
}) {
  return (
    <figure className="panel-solid overflow-hidden">
      <Image
        src={src}
        width={width}
        height={height}
        alt={alt}
        sizes={sizes}
        priority={priority}
        unoptimized={unoptimized}
        className="h-auto w-full"
      />
      {caption ? (
        <figcaption className="border-t border-line px-4 py-2.5 text-[0.8rem] leading-[1.5] text-dim2">
          {caption}
        </figcaption>
      ) : null}
    </figure>
  );
}

/** Two shots side by side on a wide screen, stacked on a narrow one. */
export function ShotPair({ children }: { children: ReactNode }) {
  return <div className="grid gap-4 sm:grid-cols-2">{children}</div>;
}

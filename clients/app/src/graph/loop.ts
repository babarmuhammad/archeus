// The one animation loop of the client (p18-design-gate A9; p16 §18.1 rule 5):
// the only requestAnimationFrame caller in clients/app/src. It holds finite
// animations (a camera move, a fade, a pulse) and schedules a frame only while
// one is unfinished or a redraw was asked for. It parks — cancels its pending
// frame and schedules nothing — while the page is hidden, the window is
// blurred, motion is reduced (no animation is ever accepted then; a change
// draws once), the canvas context is lost, or nothing is animating.

export interface Anim {
  until: number; // ms timestamp it ends at
}

export interface LoopHost {
  raf: (cb: (t: number) => void) => number;
  caf: (id: number) => void;
  now: () => number;
  hidden: () => boolean;
  focused: () => boolean;
  reduced: () => boolean;
}

export type LoopState = 'running' | 'parked';

// frame-time degrade (A10; Ship Notes R7 ADAPT): this many consecutive frames
// slower than SLOW_FRAME_MS during an animation drop its extras until it ends
export const SLOW_FRAME_MS = 20;
export const SLOW_FRAMES = 3;

export class Loop {
  private anims = new Set<Anim>();
  private frame: number | null = null;
  private dirty = false;
  private lost = false;
  private last: number | null = null; // the previous frame's time in this chain
  private slow = 0;
  /** Frames are running slow during this animation: the view drops pulses
   * and every label but the focus's until it ends. */
  degraded = false;
  frames = 0; // frames run: what the tests (and the view's data attribute) read

  private host: LoopHost;
  private draw: (now: number) => void;
  private onState?: (s: LoopState) => void;

  constructor(host: LoopHost, draw: (now: number) => void, onState?: (s: LoopState) => void) {
    this.host = host;
    this.draw = draw;
    this.onState = onState;
  }

  get state(): LoopState {
    return this.frame === null ? 'parked' : 'running';
  }

  private blocked() {
    return this.lost || this.host.hidden() || !this.host.focused();
  }

  /** Ask for one redraw (a state change, a pan, a zoom). */
  request() {
    this.dirty = true;
    this.kick();
  }

  /** Start a finite animation; refused (returns false) under reduced motion. */
  animate(ms: number): boolean {
    if (this.host.reduced()) {
      this.request(); // the change still shows, at once
      return false;
    }
    this.anims.add({ until: this.host.now() + ms });
    this.kick();
    return true;
  }

  /** The canvas lost (true) or regained (false) its context. */
  setLost(lost: boolean) {
    this.lost = lost;
    if (lost) this.park();
    else this.request();
  }

  /** Visibility or focus changed: park, or resume what is still owed. */
  wake() {
    if (this.blocked()) this.park();
    else if (this.dirty || this.anims.size) this.kick();
  }

  private kick() {
    if (this.frame !== null || this.blocked()) return;
    this.frame = this.host.raf((t) => this.tick(t));
    this.onState?.('running');
  }

  private park() {
    if (this.frame !== null) this.host.caf(this.frame);
    this.frame = null;
    this.last = null; // a parked gap is not a slow frame
    this.onState?.('parked');
  }

  private tick(t: number) {
    this.frame = null;
    if (this.blocked()) return this.park();
    if (this.anims.size && this.last !== null) {
      this.slow = t - this.last > SLOW_FRAME_MS ? this.slow + 1 : 0;
      if (this.slow >= SLOW_FRAMES) this.degraded = true;
    }
    this.last = t;
    this.frames++;
    this.dirty = false;
    this.draw(t);
    const now = this.host.now();
    for (const a of [...this.anims]) if (a.until <= now) this.anims.delete(a);
    if (this.anims.size) this.kick();
    else if (this.degraded) {
      // the animation ended: one more frame puts back what was dropped
      this.degraded = false;
      this.slow = 0;
      this.last = null;
      this.request();
    } else {
      this.last = null;
      this.slow = 0;
      this.onState?.('parked');
    }
  }

  get animating() {
    return this.anims.size;
  }

  dispose() {
    this.park();
    this.anims.clear();
  }
}

let focused = typeof document === 'undefined' ? true : document.hasFocus();

/** The browser host: the document, the window and the motion preference.
 * *wake* runs after every visibility or focus change; the returned function
 * removes the listeners. */
export function browserHost(wake: () => void): [LoopHost, () => void] {
  const blur = () => {
    focused = false;
    wake();
  };
  const focus = () => {
    focused = true;
    wake();
  };
  addEventListener('blur', blur);
  addEventListener('focus', focus);
  document.addEventListener('visibilitychange', wake);
  const off = () => {
    removeEventListener('blur', blur);
    removeEventListener('focus', focus);
    document.removeEventListener('visibilitychange', wake);
  };
  return [{
    raf: (cb) => requestAnimationFrame(cb),
    caf: (id) => cancelAnimationFrame(id),
    now: () => performance.now(),
    hidden: () => document.hidden,
    focused: () => focused,
    reduced: () => document.documentElement.dataset.motion === 'reduced' || matchMedia('(prefers-reduced-motion: reduce)').matches,
  }, off];
}

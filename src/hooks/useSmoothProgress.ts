/**
 * useSmoothProgress – Animates a progress value toward a target using rAF.
 *
 * Instead of jumping between discrete polled values (e.g. 27→72), this hook:
 * 1. Eases toward the target when behind (speed ∝ gap, feels natural)
 * 2. Creeps slowly forward when stalled (visual feedback during long phases)
 * 3. Caps creep at target + 5% so it never overshoots badly
 * 4. Snaps to 100 on completion
 *
 * Returns an integer 0–100 suitable for direct use as a width percentage.
 */
import { useEffect, useRef, useState } from 'react';

export function useSmoothProgress(target: number, isActive: boolean): number {
  const targetRef = useRef(target);
  const displayRef = useRef(0);
  const [display, setDisplay] = useState(0);

  // Keep target ref in sync (avoids tearing down the RAF loop on every poll).
  targetRef.current = target;

  // Reset when upload finishes or is cancelled.
  useEffect(() => {
    if (!isActive) {
      displayRef.current = 0;
      setDisplay(0);
    }
  }, [isActive]);

  // Single RAF loop runs for the lifetime of the upload.
  useEffect(() => {
    if (!isActive) return;

    let raf: number;
    let lastTime = performance.now();

    const tick = (now: number) => {
      // Cap dt to avoid big jumps when tab was backgrounded.
      const dt = Math.min((now - lastTime) / 1000, 0.1);
      lastTime = now;

      const t = targetRef.current;
      const current = displayRef.current;
      const gap = t - current;

      let next: number;
      if (gap > 0.5) {
        // Behind target → ease toward it.  Speed ∝ gap (min 2 %/s).
        // A 10% gap takes ~0.8s, a 30% gap takes ~1.5s (decelerating).
        const speed = Math.max(gap * 1.5, 2);
        next = current + Math.min(speed * dt, gap);
      } else if (t < 100 && current < Math.min(t + 5, 97)) {
        // At target and not complete → creep slowly (+0.1 %/s, max 5% ahead).
        // Gives visual feedback during long stalls (e.g. parsing a huge CSV).
        next = current + 0.1 * dt;
      } else if (t >= 100) {
        // Completion → snap.
        next = 100;
      } else {
        next = current;
      }

      displayRef.current = next;

      // Only trigger a React re-render when the integer % actually changes.
      const rounded = Math.min(Math.round(next), 100);
      setDisplay(prev => (prev !== rounded ? rounded : prev));

      raf = requestAnimationFrame(tick);
    };

    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [isActive]);

  return display;
}

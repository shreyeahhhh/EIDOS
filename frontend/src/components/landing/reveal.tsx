"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";

/**
 * Fades a landing-page section in as it scrolls into view (`globals.css`'s `.reveal`). Renders fully
 * visible by default — a script error or slow hydration never hides content, only a confirmed
 * IntersectionObserver hit adds `is-hidden`'s inverse (removes it) after starting hidden. Fires once;
 * this is a one-time entrance, never a repeating scroll animation.
 */
export function Reveal({ children, className, delayMs = 0 }: { children: ReactNode; className?: string; delayMs?: number }) {
  const ref = useRef<HTMLDivElement>(null);
  const [hidden, setHidden] = useState(true);

  useEffect(() => {
    const node = ref.current;
    if (!node || typeof IntersectionObserver === "undefined") {
      setHidden(false);
      return;
    }
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          const timer = setTimeout(() => setHidden(false), delayMs);
          observer.disconnect();
          return () => clearTimeout(timer);
        }
      },
      { threshold: 0.15 },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [delayMs]);

  return (
    <div ref={ref} className={`reveal${hidden ? " is-hidden" : ""}${className ? ` ${className}` : ""}`}>
      {children}
    </div>
  );
}

"use client";

import { useEffect, useRef, useState } from "react";

import { cn } from "@/lib/cn";

/** Until the browser can measure the title, a goal this long is assumed to need the toggle (it is clamped either way). */
const LONG_GOAL_CHARS = 160;

/**
 * The mission's goal as its page title. A goal can be long, and can hold something with no spaces in it at all (a web address), which cannot wrap on its own and used to push the page sideways: so the text
 * may break anywhere, and a long goal shows its first three lines with "Read more" for the rest. The whole text is always in the page (a screen reader reads all of it, and it can be copied); only the
 * look is clamped. The toggle appears only when the text really is cut off, which the browser tells us by measuring (a short goal never shows it).
 */
export function GoalText({ goal }: { goal: string }) {
  const heading = useRef<HTMLHeadingElement>(null);
  const [open, setOpen] = useState(false);
  const [overflowing, setOverflowing] = useState(goal.length > LONG_GOAL_CHARS);

  useEffect(() => {
    const node = heading.current;
    if (!node || open || typeof ResizeObserver === "undefined") return; // open: the last answer stands, so "Show less" stays
    const observer = new ResizeObserver(() => setOverflowing(node.scrollHeight > node.clientHeight + 1));
    observer.observe(node);
    return () => observer.disconnect();
  }, [goal, open]);

  return (
    <div className="flex min-w-0 flex-col items-start gap-2">
      <h1 ref={heading} className={cn("font-display text-2xl leading-snug text-ink [overflow-wrap:anywhere] sm:text-3xl", !open && "line-clamp-3")}>
        {goal}
      </h1>
      {(overflowing || open) && (
        <button type="button" aria-expanded={open} onClick={() => setOpen((current) => !current)} className="text-sm font-medium text-accent-strong underline underline-offset-4 hover:text-ink">
          {open ? "Show less" : "Read more"}
        </button>
      )}
    </div>
  );
}

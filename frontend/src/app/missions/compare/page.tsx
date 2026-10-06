import type { Metadata } from "next";
import { Suspense } from "react";

import { CompareView } from "@/components/compare/compare-view";
import { Skeleton } from "@/components/ui/skeleton";

export const metadata: Metadata = { title: "Compare models" };

export default function ComparePage() {
  return (
    <div className="mx-auto max-w-7xl px-6 py-12">
      <div className="mb-8">
        <p className="text-xs font-medium tracking-[0.2em] text-accent-strong uppercase">Compare</p>
        <h1 className="mt-3 font-display text-3xl text-ink sm:text-4xl">One goal, several models</h1>
      </div>
      {/* the page reads its runs from its own address, which a statically built page cannot know */}
      <Suspense fallback={<Skeleton className="h-64 w-full" />}>
        <CompareView />
      </Suspense>
    </div>
  );
}

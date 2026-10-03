import Link from "next/link";

import { createClient } from "@/lib/supabase/server";
import { buttonClassName } from "@/components/ui/button";
import { Reveal } from "@/components/landing/reveal";
import { MissionLoopVisual } from "@/components/landing/mission-loop-visual";
import { ProductThesis } from "@/components/landing/product-thesis";
import { HowItWorksVideo } from "@/components/landing/how-it-works-video";
import { TOTAL_MS, formatClock } from "@/components/landing/how-it-works-scenes";
import { ModelIndependent } from "@/components/landing/model-independent";

export default async function HomePage() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  const primaryHref = user ? "/missions" : "/signup";
  const primaryLabel = user ? "Open EIDOS →" : "Get started →";

  return (
    <div className="mx-auto max-w-6xl px-6">
      {/* Hero */}
      <section className="grid gap-12 py-20 sm:py-28 lg:grid-cols-[1.1fr_1fr] lg:items-center lg:gap-16">
        <div className="flex flex-col gap-6">
          <p className="text-xs font-medium tracking-[0.2em] text-accent-strong uppercase">
            Execution Intelligence &amp; Dynamic Orchestration System
          </p>
          <h1 className="max-w-xl font-display text-5xl leading-[1.05] tracking-tight text-ink sm:text-6xl">
            Execution intelligence for AI systems.
          </h1>
          <p className="max-w-md text-lg leading-relaxed text-ink-muted">Plan. Execute. Verify.</p>
          <div className="mt-2 flex flex-wrap items-center gap-5">
            <Link href={primaryHref} className={buttonClassName("primary", "md")}>
              {primaryLabel}
            </Link>
            {!user && (
              <Link href="/login" className="text-sm font-medium text-ink-muted hover:text-ink">
                Sign in
              </Link>
            )}
            <a href="#how-it-works" className="text-sm font-medium text-ink-muted hover:text-ink">
              See how it works ↓
            </a>
          </div>
        </div>
        <MissionLoopVisual />
      </section>

      {/* What is EIDOS */}
      <section id="product" className="scroll-mt-20 border-t border-border py-20">
        <Reveal>
          <ProductThesis />
        </Reveal>
      </section>

      {/* How it works — a short video (a motion piece in the page itself) */}
      <section id="how-it-works" className="scroll-mt-20 border-t border-border py-20">
        <Reveal>
          <div className="mb-8 flex flex-wrap items-end justify-between gap-x-10 gap-y-3">
            <div className="max-w-2xl">
              <p className="font-mono text-xs font-semibold tracking-[0.2em] text-accent-strong uppercase">{formatClock(TOTAL_MS)} · zero jargon</p>
              <h2 className="mt-2 font-display text-4xl leading-[1.05] tracking-tight text-ink sm:text-5xl">
                How EIDOS works, <em>in under a minute</em>.
              </h2>
            </div>
            <p className="max-w-xs text-sm leading-relaxed text-ink-muted">One question, start to finish — and how you can check every step of its work.</p>
          </div>
          <HowItWorksVideo ctaHref={primaryHref} ctaLabel={user ? "Open EIDOS →" : "Try it yourself →"} />
        </Reveal>
      </section>

      {/* Model independent */}
      <section id="architecture" className="scroll-mt-20 border-t border-border py-20">
        <Reveal>
          <ModelIndependent />
        </Reveal>
      </section>

      {/* Final CTA */}
      <section className="border-t border-border py-24 text-center">
        <Reveal>
          <h2 className="font-display text-4xl text-ink sm:text-5xl">Give EIDOS a mission.</h2>
          <div className="mt-8 flex flex-wrap items-center justify-center gap-5">
            <Link href={primaryHref} className={buttonClassName("primary", "md")}>
              {primaryLabel}
            </Link>
            <a href="#architecture" className="text-sm font-medium text-ink-muted hover:text-ink">
              Explore the architecture →
            </a>
          </div>
        </Reveal>
      </section>
    </div>
  );
}

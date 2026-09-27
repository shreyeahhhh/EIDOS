import Link from "next/link";

import { createClient } from "@/lib/supabase/server";
import { buttonClassName } from "@/components/ui/button";
import { Reveal } from "@/components/landing/reveal";
import { MissionLoopVisual } from "@/components/landing/mission-loop-visual";
import { ProductThesis } from "@/components/landing/product-thesis";
import { HowItWorks } from "@/components/landing/how-it-works";
import { WhyEidos } from "@/components/landing/why-eidos";
import { ProductPreview } from "@/components/landing/product-preview";
import { ModelIndependent } from "@/components/landing/model-independent";
import { Principles } from "@/components/landing/principles";
import { BuildWithEidos } from "@/components/landing/build-with-eidos";

export default async function HomePage() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  const primaryHref = user ? "/missions" : "/login";
  const primaryLabel = user ? "Open EIDOS →" : "Open EIDOS →";

  return (
    <div className="mx-auto max-w-6xl px-6">
      {/* Hero */}
      <section className="grid gap-12 py-20 sm:py-28 lg:grid-cols-[1.1fr_1fr] lg:items-center lg:gap-16">
        <div className="flex flex-col gap-6">
          <p className="text-xs font-medium tracking-[0.2em] text-accent uppercase">
            Execution Intelligence &amp; Dynamic Orchestration System
          </p>
          <h1 className="max-w-xl font-display text-5xl leading-[1.05] tracking-tight text-ink sm:text-6xl">
            Execution intelligence for AI systems.
          </h1>
          <p className="max-w-md text-lg leading-relaxed text-ink-muted">Plan. Execute. Verify. Learn.</p>
          <div className="mt-2 flex flex-wrap items-center gap-5">
            <Link href={primaryHref} className={buttonClassName("primary", "md")}>
              {primaryLabel}
            </Link>
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

      {/* How it works */}
      <section id="how-it-works" className="scroll-mt-20 border-t border-border py-20">
        <Reveal>
          <div className="mb-10 max-w-xl">
            <h2 className="font-display text-3xl text-ink">How EIDOS works</h2>
            <p className="mt-3 text-sm leading-relaxed text-ink-muted">
              Every mission moves through the same bounded loop, whether it succeeds on the first plan or takes two.
            </p>
          </div>
          <HowItWorks />
        </Reveal>
      </section>

      {/* Why EIDOS */}
      <section className="border-t border-border py-20">
        <Reveal>
          <h2 className="mb-2 font-display text-3xl text-ink">Why EIDOS</h2>
          <WhyEidos />
        </Reveal>
      </section>

      {/* Product preview */}
      <section id="preview" className="scroll-mt-20 border-t border-border py-20">
        <Reveal>
          <div className="mb-10 max-w-xl">
            <h2 className="font-display text-3xl text-ink">See it work</h2>
            <p className="mt-3 text-sm leading-relaxed text-ink-muted">
              A real EIDOS mission workspace — the same components, rendering an example run.
            </p>
          </div>
          <ProductPreview />
        </Reveal>
      </section>

      {/* Model independent */}
      <section id="architecture" className="scroll-mt-20 border-t border-border py-20">
        <Reveal>
          <ModelIndependent />
        </Reveal>
      </section>

      {/* Engineering principles */}
      <section id="principles" className="scroll-mt-20 border-t border-border py-20">
        <Reveal>
          <h2 className="mb-2 font-display text-3xl text-ink">Engineering principles</h2>
          <p className="mb-6 max-w-xl text-sm leading-relaxed text-ink-muted">The rules the runtime is held to, not just described by.</p>
          <Principles />
        </Reveal>
      </section>

      {/* Build with EIDOS */}
      <section id="build" className="scroll-mt-20 border-t border-border py-20">
        <Reveal>
          <BuildWithEidos />
        </Reveal>
      </section>

      {/* Final CTA */}
      <section className="border-t border-border py-24 text-center">
        <Reveal>
          <h2 className="font-display text-4xl text-ink sm:text-5xl">Give EIDOS a mission.</h2>
          <div className="mt-8 flex flex-wrap items-center justify-center gap-5">
            <Link href={primaryHref} className={buttonClassName("primary", "md")}>
              Open EIDOS →
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

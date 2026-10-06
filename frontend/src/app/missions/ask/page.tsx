import type { Metadata } from "next";

import { AskView } from "@/components/ask/ask-view";

export const metadata: Metadata = { title: "Ask models" };

export default function AskPage() {
  return (
    <div className="mx-auto max-w-7xl px-6 py-12">
      <div className="mb-8 max-w-2xl">
        <p className="text-xs font-medium tracking-[0.2em] text-accent-strong uppercase">Ask models</p>
        <h1 className="mt-3 font-display text-3xl text-ink sm:text-4xl">One question, several models</h1>
        <p className="mt-3 text-sm leading-relaxed text-ink-muted">
          Put the same question to the models you choose, with your own API keys, and read what each says side by side. This is not a mission: nothing is saved, and the answers are the models&apos; own words,
          with no sources and no checks.
        </p>
      </div>
      <AskView />
    </div>
  );
}

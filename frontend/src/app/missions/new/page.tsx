import type { Metadata } from "next";

import Link from "next/link";

import { Card } from "@/components/ui/card";
import { CreateMissionForm } from "@/components/mission/create-mission-form";

export const metadata: Metadata = { title: "New mission" };

export default function NewMissionPage() {
  return (
    <div className="mx-auto max-w-2xl px-6 py-16">
      <div className="mb-10">
        <p className="text-xs font-medium tracking-[0.2em] text-accent-strong uppercase">New mission</p>
        <h1 className="mt-3 font-display text-3xl text-ink sm:text-4xl">Create a mission</h1>
        <p className="mt-3 max-w-lg text-sm leading-relaxed text-ink-muted">
          Describe the objective in plain language. EIDOS validates it and builds a plan once you start it.
        </p>
        <p className="mt-2 max-w-lg text-sm leading-relaxed text-ink-muted">
          Just want to see what different models say about a question, with no sources?{" "}
          <Link href="/missions/ask" className="font-medium text-accent-strong underline underline-offset-4">
            Ask the models directly
          </Link>
          .
        </p>
      </div>
      <Card className="p-6 sm:p-8">
        <CreateMissionForm />
      </Card>
    </div>
  );
}

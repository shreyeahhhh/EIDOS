import type { Metadata } from "next";

import { Card } from "@/components/ui/card";
import { CreateMissionForm } from "@/components/mission/create-mission-form";

export const metadata: Metadata = { title: "New mission" };

export default function NewMissionPage() {
  return (
    <div className="mx-auto max-w-2xl px-6 py-16">
      <div className="mb-8">
        <h1 className="font-display text-3xl text-ink">New mission</h1>
        <p className="mt-2 text-sm text-ink-muted">
          Describe the objective. EIDOS validates it, selects a strategy, and runs it once you start it.
        </p>
      </div>
      <Card>
        <CreateMissionForm />
      </Card>
    </div>
  );
}

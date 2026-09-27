import type { Metadata } from "next";
import Link from "next/link";

import { PageHeader } from "@/components/layout/page-header";
import { buttonClassName } from "@/components/ui/button";
import { MissionDashboard } from "@/components/mission/mission-dashboard";

export const metadata: Metadata = { title: "Missions" };

export default function MissionsPage() {
  return (
    <div className="mx-auto max-w-4xl px-6 py-16">
      <PageHeader
        title="Missions"
        description="Your execution workspace. EIDOS remains the source of truth for each mission's state — this browser only remembers which ones to ask about."
        actions={
          <Link href="/missions/new" className={buttonClassName("primary", "md")}>
            + New mission
          </Link>
        }
      />
      <div className="mt-10">
        <MissionDashboard />
      </div>
    </div>
  );
}

import type { Metadata } from "next";
import Link from "next/link";

import { PageHeader } from "@/components/layout/page-header";
import { buttonClassName } from "@/components/ui/button";
import { MissionDashboard } from "@/components/mission/mission-dashboard";

export const metadata: Metadata = { title: "Missions" };

export default function MissionsPage() {
  return (
    <div className="mx-auto max-w-3xl px-6 py-16">
      <PageHeader
        title="Missions"
        description="Missions you've created in this browser. EIDOS itself remains the source of truth for each one."
        actions={
          <Link href="/missions/new" className={buttonClassName("primary", "md")}>
            New mission
          </Link>
        }
      />
      <div className="mt-10">
        <MissionDashboard />
      </div>
    </div>
  );
}

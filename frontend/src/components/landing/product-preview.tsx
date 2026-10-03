"use client";

import { MissionCockpit } from "@/components/cockpit/mission-cockpit";
import { EXAMPLE_EVENTS, EXAMPLE_EVIDENCE, EXAMPLE_EXECUTION, EXAMPLE_MISSION, EXAMPLE_RESULT } from "@/lib/example-run";

/**
 * The real mission cockpit rendering a static, illustrative example mission — not a live fetch, and said so plainly in the caption. This is
 * deliberately the actual product code, not a mockup drawn to look like it: what a visitor can play, scrub and click here is what a signed-in
 * mission's workspace does.
 */
export function ProductPreview() {
  return (
    <div className="flex flex-col gap-4">
      <MissionCockpit
        mission={EXAMPLE_MISSION}
        events={EXAMPLE_EVENTS}
        execution={EXAMPLE_EXECUTION}
        result={EXAMPLE_RESULT}
        resultLoading={false}
        evidence={EXAMPLE_EVIDENCE}
        starting={false}
        startError={null}
        onStart={() => undefined}
      />
      <p className="text-xs text-ink-faint">Example mission, shown with static data for illustration — not a live run. Press play, drag the strip, or click a step.</p>
    </div>
  );
}

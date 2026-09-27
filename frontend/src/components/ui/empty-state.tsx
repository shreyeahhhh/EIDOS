import type { ReactNode } from "react";

import { Callout } from "./callout";

/** A section that genuinely has nothing yet — never an error, never a fabricated placeholder. */
export function EmptyState({ title, children }: { title: string; children: ReactNode }) {
  return (
    <Callout tone="neutral" title={title}>
      {children}
    </Callout>
  );
}

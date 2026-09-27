import type { ReactNode } from "react";

interface SectionProps {
  id?: string;
  title: string;
  description?: string;
  actions?: ReactNode;
  children: ReactNode;
}

/** One labelled block of the mission workspace ("Execution", "Plan", "Evidence", ...). Sections are the workspace's
 * only structure — never a card-per-section, so the page reads as one continuous document, not a grid of boxes. */
export function Section({ id, title, description, actions, children }: SectionProps) {
  return (
    <section id={id} className="scroll-mt-24 border-t border-border py-10 first:border-t-0 first:pt-0">
      <div className="mb-6 flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h2 className="font-display text-xl text-ink">{title}</h2>
          {description && <p className="mt-1 text-sm text-ink-muted">{description}</p>}
        </div>
        {actions && <div className="shrink-0">{actions}</div>}
      </div>
      {children}
    </section>
  );
}

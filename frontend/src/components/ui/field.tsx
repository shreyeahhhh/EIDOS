import { useId, type ReactNode } from "react";

interface FieldProps {
  label: string;
  hint?: string;
  error?: string;
  children: (id: string, describedBy: string | undefined) => ReactNode;
}

/** A label, one form control, an optional hint and an accessible error message — the one shape every field in the app uses. */
export function Field({ label, hint, error, children }: FieldProps) {
  const id = useId();
  const hintId = hint ? `${id}-hint` : undefined;
  const errorId = error ? `${id}-error` : undefined;
  const describedBy = [hintId, errorId].filter(Boolean).join(" ") || undefined;

  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-sm font-medium text-ink">
        {label}
      </label>
      {children(id, describedBy)}
      {hint && !error && (
        <p id={hintId} className="text-xs text-ink-faint">
          {hint}
        </p>
      )}
      {error && (
        <p id={errorId} role="alert" className="text-xs text-error">
          {error}
        </p>
      )}
    </div>
  );
}

const inputBase =
  "w-full rounded-md border border-border-strong bg-surface-raised px-3 py-2 text-sm text-ink placeholder:text-ink-faint focus-visible:border-accent";

export function fieldInputClassName(hasError: boolean): string {
  return `${inputBase}${hasError ? " border-error" : ""}`;
}

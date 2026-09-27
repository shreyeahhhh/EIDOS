import { Button } from "./button";
import { Callout } from "./callout";

interface ErrorStateProps {
  title?: string;
  message: string;
  onRetry?: () => void;
}

/** A call that failed — the backend's own message, and a retry action when the failure might be transient. */
export function ErrorState({ title = "This could not be loaded", message, onRetry }: ErrorStateProps) {
  return (
    <Callout tone="error" title={title}>
      <p>{message}</p>
      {onRetry && (
        <Button variant="secondary" size="sm" onClick={onRetry} className="mt-3">
          Try again
        </Button>
      )}
    </Callout>
  );
}

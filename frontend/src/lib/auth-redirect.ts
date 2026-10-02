/** Where a visitor lands after signing in or confirming an email when nothing else was asked for. */
export const DEFAULT_NEXT = "/missions/new";

/** Only ever redirect within this app: an absolute or protocol-relative value (`//host`, `/\host`) is never followed. */
export function safeNext(value: string | null | undefined): string {
  if (value && value.startsWith("/") && !value.startsWith("//") && !value.startsWith("/\\")) return value;
  return DEFAULT_NEXT;
}

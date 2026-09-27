/** Joins class names, dropping falsy values. Deliberately not a full merge utility (`clsx`/`tailwind-merge`): nothing here has conflicting utility classes to resolve. */
export function cn(...classes: Array<string | false | null | undefined>): string {
  return classes.filter(Boolean).join(" ");
}

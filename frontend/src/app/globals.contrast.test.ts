import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

/**
 * WCAG AA asks 4.5:1 for normal text. The design tokens are the one place every colour in the app comes from, so this reads the real
 * `globals.css` and measures the pairs the interface actually puts text on. It exists because a pair that read 3.95:1 (warning text on
 * its own soft background) went unnoticed through several releases: a token change that breaks a pair now fails here instead.
 * There is one scheme (oat page, plum writing, tangerine for the rest) and no dark theme.
 */

const css = readFileSync(join(__dirname, "globals.css"), "utf-8");

const rootStart = css.indexOf(":root {");
const theme = Object.fromEntries(
  [...css.slice(rootStart, css.indexOf("@theme inline")).matchAll(/--color-([a-z-]+):\s*(#[0-9a-fA-F]{6})\s*;/g)].map((match) => [match[1], match[2].toLowerCase()]),
);

function luminance(hex: string): number {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255).map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}
function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

// [text token, background token] — each pair is one the interface really uses for small text.
const PAIRS: [string, string][] = [
  ["ink", "surface"], ["ink", "surface-raised"], ["ink", "surface-sunken"],
  ["ink-muted", "surface"], ["ink-muted", "surface-raised"], ["ink-muted", "surface-sunken"], ["ink-muted", "accent-soft"],
  ["ink-faint", "surface"], ["ink-faint", "surface-raised"],
  // the accent (tangerine) is a mid-tone, so what sits on it is a deep plum; `accent-strong` is the accent as text and `accent-hover` the hovered fill
  ["accent-strong", "accent-soft"], ["accent-strong", "surface-raised"], ["accent-strong", "surface"], ["on-accent", "accent"], ["on-accent", "accent-hover"],
  ["success", "surface"], ["success", "surface-raised"], ["success", "success-soft"],
  ["warning", "surface"], ["warning", "surface-raised"], ["warning", "warning-soft"],
  ["error", "surface"], ["error", "surface-raised"], ["error", "error-soft"],
  ["info", "surface"], ["info", "surface-raised"], ["info", "info-soft"],
];

describe("design token contrast (WCAG AA, 4.5:1 for normal text)", () => {
  it("found the tokens", () => {
    expect(theme["ink"]).toMatch(/^#/);
    expect(Object.keys(theme).length).toBeGreaterThan(20);
  });

  it("has one scheme only: no dark theme, and the page declares itself light", () => {
    expect(css).not.toContain("prefers-color-scheme");
    expect(css).toMatch(/color-scheme:\s*light;/);
    expect(css).toMatch(/accent-color:\s*var\(--color-accent\)/); // native controls (ticked boxes) follow the scheme, not the browser's blue
  });

  it.each(PAIRS)("%s on %s", (text, background) => {
    expect(theme[text], `--color-${text}`).toBeDefined();
    expect(theme[background], `--color-${background}`).toBeDefined();
    expect(contrast(theme[text], theme[background])).toBeGreaterThanOrEqual(4.5);
  });

  // WCAG 1.4.11: the outline that shows where keyboard focus is must stand out from what it is drawn on by 3:1.
  it.each(["surface", "surface-raised"])("the focus ring on %s", (background) => {
    expect(css).toMatch(/:focus-visible\s*\{\s*outline:\s*2px solid var\(--color-accent-strong\)/); // the ring uses the token measured here
    expect(contrast(theme["accent-strong"], theme[background])).toBeGreaterThanOrEqual(3);
  });

  it("uses the three given colours as given: oat is the page, plum is the writing, tangerine is the accent", () => {
    expect(theme["surface"]).toBe("#e7d2a9");
    expect(theme["ink"]).toBe("#3f1e46");
    expect(theme["accent"]).toBe("#dd6e2d");
  });
});

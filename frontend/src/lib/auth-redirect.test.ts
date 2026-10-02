import { describe, expect, it } from "vitest";

import { DEFAULT_NEXT, safeNext } from "./auth-redirect";

describe("safeNext", () => {
  it("follows a path inside this app", () => {
    expect(safeNext("/missions")).toBe("/missions");
    expect(safeNext("/missions/abc?x=1")).toBe("/missions/abc?x=1");
  });

  it.each([undefined, null, "", "missions", "https://evil.example", "//evil.example", "/\\evil.example", "javascript:alert(1)"])(
    "never follows %j",
    (value) => {
      expect(safeNext(value)).toBe(DEFAULT_NEXT);
    },
  );
});

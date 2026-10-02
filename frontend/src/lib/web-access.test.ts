import { describe, expect, it } from "vitest";

import { MAX_WEB_ADDRESSES, webAccessNote, webAddressesIn } from "./web-access";

describe("webAddressesIn", () => {
  it("finds the addresses written in a goal, in order, once each, without trailing punctuation", () => {
    const goal = "Review https://a.example.com/x?y=1, then (https://b.example.org). Also https://a.example.com/x?y=1 and http://old.example.net/.";
    expect(webAddressesIn(goal)).toEqual(["https://a.example.com/x?y=1", "https://b.example.org", "http://old.example.net/"]);
  });

  it("finds nothing in a goal that only mentions a site by name", () => {
    expect(webAddressesIn("Look at example.com and www.example.org")).toEqual([]);
  });
});

describe("webAccessNote", () => {
  it("asks for an address when the goal has none", () => {
    expect(webAccessNote("Review my portfolio")).toMatch(/full https:\/\/ address/);
  });

  it("says nothing when one https address is named", () => {
    expect(webAccessNote("Review https://example.com/ for faults")).toBeNull();
  });

  it("warns that more than the limit would read none", () => {
    const goal = Array.from({ length: MAX_WEB_ADDRESSES + 1 }, (_, n) => `https://s${n}.example.com/`).join(" ");
    expect(webAccessNote(goal)).toMatch(/at most 3 are read, so none would be/);
  });

  it("warns that an http address is refused", () => {
    expect(webAccessNote("Read http://example.com/")).toMatch(/Only https/);
  });
});

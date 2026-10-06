import { describe, expect, it } from "vitest";

import { apiKeyProblem, decodeRuns, encodeRuns, modelNameProblem, providerLabel, PROVIDERS } from "./compare";

const ID_A = "0b0d6e4c-5a39-4b0e-8e6e-1d3c6d8f9a01";
const ID_B = "9f1c2d3e-4b5a-4c6d-8e7f-0a1b2c3d4e5f";

describe("the model name and key checks (the same rules as the backend)", () => {
  it("accepts the usual model ids and refuses anything with a space or a symbol a name never has", () => {
    for (const name of ["gpt-4o-mini", "gemini-2.5-flash", "openai/gpt-oss-120b", "llama-3.3-70b-versatile", "models/x.y_z:1"]) expect(modelNameProblem(name), name).toBeNull();
    for (const name of ["", "  ", "has space", "semi;colon", "-leading", "x".repeat(101), "a\nb"]) expect(modelNameProblem(name), name).not.toBeNull();
  });

  it("accepts a key-shaped string and refuses what could not be one, without ever repeating it", () => {
    expect(apiKeyProblem("sk-test-0123456789ABCDEF")).toBeNull();
    for (const key of ["", "short", "has a space 12345678", "line\nbreak-12345678", "é-non-ascii-12345678", "k".repeat(513)]) {
      const problem = apiKeyProblem(key);
      expect(problem, JSON.stringify(key)).not.toBeNull();
      if (key.length >= 5) expect(problem).not.toContain(key);
    }
  });
});

describe("carrying a comparison in the address", () => {
  const runs = [
    { id: ID_A, provider: "openai" as const, model: "gpt-4o-mini" },
    { id: ID_B, provider: "groq" as const, model: "openai/gpt-oss-120b" },
  ];

  it("round-trips ids, providers and model names, and nothing else", () => {
    const query = encodeRuns(runs);
    expect(decodeRuns(new URLSearchParams(query))).toEqual(runs);
    expect(query).not.toMatch(/key/i);
  });

  it("drops an entry that is not a real mission id, a known provider and a plausible model", () => {
    const params = new URLSearchParams();
    for (const entry of [`${ID_A}~openai~gpt-4o`, "not-a-uuid~openai~m", `${ID_B}~unknown~m`, `${ID_B}~gemini~has space`, `${ID_B}~gemini`, `${ID_B}~gemini~m~extra`, "", `${ID_B}~gemini~gemini-x`]) {
      params.append("r", entry);
    }
    expect(decodeRuns(params).map((run) => run.provider)).toEqual(["openai", "gemini"]);
  });

  it("keeps one run per provider and per mission", () => {
    const params = new URLSearchParams();
    params.append("r", `${ID_A}~openai~a`);
    params.append("r", `${ID_B}~openai~b`);
    params.append("r", `${ID_A}~gemini~c`);
    expect(decodeRuns(params)).toEqual([{ id: ID_A, provider: "openai", model: "a" }]);
  });

  it("knows three providers and names them for people", () => {
    expect(PROVIDERS.map((provider) => provider.id)).toEqual(["openai", "gemini", "groq"]);
    expect(providerLabel("gemini")).toBe("Google Gemini");
    expect(providerLabel("other")).toBe("other");
  });
});

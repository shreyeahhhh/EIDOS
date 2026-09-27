import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { EvidenceView } from "@/lib/api/types";
import { EvidencePanel } from "./evidence-panel";

describe("EvidencePanel", () => {
  it("shows an empty state when nothing was cited, never fabricating evidence", () => {
    const view: EvidenceView = { audit: { traces: [], cited: [] }, evidence: [] };
    render(<EvidencePanel evidence={view} />);
    expect(screen.getByText("No citations were recorded")).toBeInTheDocument();
  });

  it("states plainly when no knowledge base was used, rather than hiding the fact", () => {
    const view: EvidenceView = {
      audit: {
        traces: [{ step_id: "s1", ref: "doc:1", kind: "not_evidence", kb_id: null, chunk_id: null, document_id: null, source_id: null, retrieved_by: [] }],
        cited: [],
      },
      evidence: [],
    };
    render(<EvidencePanel evidence={view} />);
    expect(screen.getByText(/didn.t use a knowledge base/)).toBeInTheDocument();
    expect(screen.getByText("doc:1")).toBeInTheDocument();
  });

  it("shows resolved evidence text and does not repeat the 'no knowledge base' notice when evidence exists", () => {
    const view: EvidenceView = {
      audit: {
        traces: [{ step_id: "s1", ref: "evidence:abc", kind: "resolved", kb_id: "kb", chunk_id: "c", document_id: "d", source_id: "src", retrieved_by: [] }],
        cited: [{ source_id: "src", document_id: "d" }],
      },
      evidence: [{ ref: "evidence:abc", content_type: "text/plain", content: "the retrieved chunk's text" }],
    };
    render(<EvidencePanel evidence={view} />);
    expect(screen.getByText("the retrieved chunk's text")).toBeInTheDocument();
    expect(screen.queryByText(/didn.t use a knowledge base/)).toBeNull();
    expect(screen.getByText("1 distinct source behind the resolved citations.")).toBeInTheDocument();
  });
});

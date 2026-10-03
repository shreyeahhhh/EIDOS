import { describe, expect, it } from "vitest";

import type { MissionStatus, NodeStatus, RunStatus, VerificationVerdict } from "./api/types";
import {
  MISSION_STATUS_LABEL,
  MISSION_STATUS_TONE,
  NODE_STATUS_LABEL,
  RUN_STATUS_LABEL,
  RUN_STATUS_TONE,
  VERDICT_LABEL,
  VERDICT_TONE,
  failureCauseLabel,
  formatDateTime,
  stepKindLabel,
} from "./status";

const RUN_STATUSES: RunStatus[] = ["created", "queued", "running", "finished", "rejected", "interrupted", "error"];
const MISSION_STATUSES: MissionStatus[] = ["created", "completed", "failed", "paused"];
const VERDICTS: VerificationVerdict[] = ["pass", "fail", "inconclusive"];
const NODE_STATUSES: NodeStatus[] = [
  "succeeded",
  "failed",
  "no_result",
  "verification_failed",
  "verification_inconclusive",
  "skipped",
  "not_reached",
  "awaiting",
];

describe("status labels and tones", () => {
  it("has a label and a tone for every run_status value the backend can send", () => {
    for (const status of RUN_STATUSES) {
      expect(RUN_STATUS_LABEL[status]).toBeTruthy();
      expect(RUN_STATUS_TONE[status]).toBeTruthy();
    }
  });

  it("has a label and a tone for every mission_status value the backend can send", () => {
    for (const status of MISSION_STATUSES) {
      expect(MISSION_STATUS_LABEL[status]).toBeTruthy();
      expect(MISSION_STATUS_TONE[status]).toBeTruthy();
    }
  });

  it("never calls run_status finished a success — mission_status carries that", () => {
    expect(RUN_STATUS_TONE.finished).toBe("neutral");
    expect(MISSION_STATUS_TONE.completed).toBe("success");
    expect(MISSION_STATUS_TONE.failed).toBe("error");
  });

  it("maps every verdict to a label and a tone, fail and inconclusive never reading as success", () => {
    for (const verdict of VERDICTS) {
      expect(VERDICT_LABEL[verdict]).toBeTruthy();
    }
    expect(VERDICT_TONE.pass).toBe("success");
    expect(VERDICT_TONE.fail).toBe("error");
    expect(VERDICT_TONE.inconclusive).toBe("warning");
  });

  it("labels every failure cause the state machine can record", () => {
    expect(failureCauseLabel("execution_failed")).toMatch(/failed/i);
    expect(failureCauseLabel("verification_inconclusive")).toMatch(/inconclusive/i);
  });

  it("formats an ISO timestamp into a readable local date and time", () => {
    const formatted = formatDateTime("2026-09-27T07:03:57.330675Z");
    expect(formatted).toMatch(/2026/);
  });

  it("has a label for every plan-node status the backend can send, distinct from mission_status", () => {
    for (const status of NODE_STATUSES) {
      expect(NODE_STATUS_LABEL[status]).toBeTruthy();
    }
  });

  it("labels a work step by its capability, and a control step by its role", () => {
    expect(stepKindLabel("agent", "research")).toBe("Research");
    expect(stepKindLabel("agent", null)).toBe("Agent");
    expect(stepKindLabel("VERIFY", null)).toBe("Verify");
    expect(stepKindLabel("REPLAN", null)).toBe("Replan");
  });
});

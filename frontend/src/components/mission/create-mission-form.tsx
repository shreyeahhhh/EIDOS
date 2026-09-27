"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { ApiError } from "@/lib/api/errors";
import { createMission } from "@/lib/api/client";
import type { MissionSpec, RiskLevel } from "@/lib/api/types";
import { KNOWN_CAPABILITIES } from "@/lib/api/types";
import { rememberMission } from "@/lib/mission-index";
import { Button } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { Field, fieldInputClassName } from "@/components/ui/field";
import { NoWorkspaceAccess } from "./no-workspace-access";
import { TenantRequiredForm } from "./tenant-required-form";

const CAPABILITY_LABEL: Record<(typeof KNOWN_CAPABILITIES)[number], string> = {
  research: "Research",
  architecture: "Architecture analysis",
  security: "Security analysis",
  cost: "Cost analysis",
};

const RISK_LEVELS: RiskLevel[] = ["low", "medium", "high"];

type Stage = { name: "form" } | { name: "tenant_required" } | { name: "no_membership" };

interface FieldErrors {
  goal?: string;
  required_capabilities?: string;
  risk_level?: string;
}

/** Creates a mission, then hands off to its workspace (`/missions/[id]`) — the one place its status, its run, and
 * its results ever live. This form never shows a mission's state itself. */
export function CreateMissionForm() {
  const router = useRouter();

  const [goal, setGoal] = useState("");
  const [capabilities, setCapabilities] = useState<string[]>([]);
  const [riskLevel, setRiskLevel] = useState<RiskLevel>("low");
  const [autonomyLevel, setAutonomyLevel] = useState(1);
  const [minQuality, setMinQuality] = useState(0);
  const [maxRiskLevel, setMaxRiskLevel] = useState<RiskLevel>("medium");
  const [minIndependentEvidence, setMinIndependentEvidence] = useState(1);
  const [supportingDocument, setSupportingDocument] = useState("");

  const [stage, setStage] = useState<Stage>({ name: "form" });
  const [submitting, setSubmitting] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [generalErrors, setGeneralErrors] = useState<string[]>([]);

  function toggleCapability(capability: string) {
    setCapabilities((current) =>
      current.includes(capability) ? current.filter((item) => item !== capability) : [...current, capability],
    );
  }

  function buildSpec(): MissionSpec {
    return {
      goal,
      required_capabilities: capabilities,
      risk_level: riskLevel,
      autonomy_level: autonomyLevel as MissionSpec["autonomy_level"],
      allowed_actions: [],
      reliability: {
        min_quality: minQuality,
        max_risk_level: maxRiskLevel,
        min_independent_evidence: minIndependentEvidence,
      },
      supplied_documents: supportingDocument.trim()
        ? [{ ref: "doc:1", content_type: "text/plain", content: supportingDocument }]
        : [],
    };
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFieldErrors({});
    setGeneralErrors([]);

    const errors: FieldErrors = {};
    if (!goal.trim()) errors.goal = "A goal is required.";
    if (capabilities.length === 0) errors.required_capabilities = "Choose at least one capability.";
    if (Object.keys(errors).length > 0) {
      setFieldErrors(errors);
      return;
    }

    setSubmitting(true);
    try {
      const mission = await createMission(buildSpec());
      rememberMission({ id: mission.mission_id, goal, createdAt: mission.created_at });
      router.push(`/missions/${mission.mission_id}`);
    } catch (error) {
      handleError(error);
      setSubmitting(false);
    }
  }

  function handleError(error: unknown) {
    if (!(error instanceof ApiError)) {
      setGeneralErrors(["Something unexpected went wrong. Try again."]);
      return;
    }
    switch (error.code) {
      case "unauthenticated":
        router.push("/login?next=/missions/new");
        return;
      case "no_tenant_membership":
        setStage({ name: "no_membership" });
        return;
      case "tenant_required":
        setStage({ name: "tenant_required" });
        return;
      case "invalid_spec": {
        const next: FieldErrors = {};
        const rest: string[] = [];
        for (const detail of error.details ?? []) {
          if (detail.field === "goal") next.goal = detail.message;
          else if (detail.field === "required_capabilities") next.required_capabilities = detail.message;
          else if (detail.field === "risk_level") next.risk_level = detail.message;
          else rest.push(`${detail.field}: ${detail.message}`);
        }
        setFieldErrors(next);
        setGeneralErrors(rest);
        return;
      }
      default:
        setGeneralErrors([error.message]);
    }
  }

  if (stage.name === "no_membership") return <NoWorkspaceAccess />;

  if (stage.name === "tenant_required") {
    return <TenantRequiredForm onSubmitted={() => setStage({ name: "form" })} />;
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-8" noValidate>
      {generalErrors.length > 0 && (
        <Callout tone="error" title="This request was refused">
          <ul className="list-disc space-y-1 pl-4">
            {generalErrors.map((message) => (
              <li key={message}>{message}</li>
            ))}
          </ul>
        </Callout>
      )}

      <div className="flex flex-col gap-2">
        <label htmlFor="goal" className="font-display text-lg text-ink">
          What do you want EIDOS to accomplish?
        </label>
        <textarea
          id="goal"
          aria-invalid={Boolean(fieldErrors.goal)}
          value={goal}
          onChange={(event) => setGoal(event.target.value)}
          rows={4}
          placeholder="e.g. Research the current landscape of AI agent frameworks and assess build-vs-buy tradeoffs."
          className={`${fieldInputClassName(Boolean(fieldErrors.goal))} text-base leading-relaxed`}
        />
        {fieldErrors.goal && (
          <p role="alert" className="text-xs text-error">
            {fieldErrors.goal}
          </p>
        )}
      </div>

      <fieldset className="flex flex-col gap-2">
        <legend className="text-sm font-medium text-ink">Required capabilities</legend>
        <p className="text-xs text-ink-faint">What kind of work does this mission need done?</p>
        <div className="mt-1 flex flex-wrap gap-4">
          {KNOWN_CAPABILITIES.map((capability) => (
            <label key={capability} className="flex items-center gap-2 text-sm text-ink-muted">
              <input
                type="checkbox"
                checked={capabilities.includes(capability)}
                onChange={() => toggleCapability(capability)}
                className="h-4 w-4 rounded border-border-strong accent-[var(--color-accent)]"
              />
              {CAPABILITY_LABEL[capability]}
            </label>
          ))}
        </div>
        {fieldErrors.required_capabilities && (
          <p role="alert" className="text-xs text-error">
            {fieldErrors.required_capabilities}
          </p>
        )}
      </fieldset>

      {/* A quiet reminder of the shape every mission takes, not a preview of this one's actual plan —
          EIDOS decides the real plan only once this mission is created. */}
      <div className="flex items-center gap-2 rounded-md border border-border bg-surface-sunken px-4 py-3 font-mono text-xs text-ink-faint">
        <span>EIDOS will</span>
        <span className="text-ink-muted">Plan</span>
        <span aria-hidden="true">→</span>
        <span className="text-ink-muted">Execute</span>
        <span aria-hidden="true">→</span>
        <span className="text-ink-muted">Verify</span>
      </div>

      <details className="group rounded-md border border-border">
        <summary className="cursor-pointer list-none px-4 py-3 text-sm font-medium text-ink-muted select-none hover:text-ink">
          <span className="inline-flex items-center gap-2">
            <span aria-hidden="true" className="transition-transform group-open:rotate-90">
              ›
            </span>
            Advanced options
          </span>
        </summary>
        <div className="flex flex-col gap-6 border-t border-border px-4 pt-5 pb-4">
          <div className="grid gap-6 sm:grid-cols-2">
            <Field label="Risk level" error={fieldErrors.risk_level}>
              {(id) => (
                <select id={id} value={riskLevel} onChange={(event) => setRiskLevel(event.target.value as RiskLevel)} className={fieldInputClassName(false)}>
                  {RISK_LEVELS.map((level) => (
                    <option key={level} value={level}>
                      {level[0].toUpperCase() + level.slice(1)}
                    </option>
                  ))}
                </select>
              )}
            </Field>
            <Field label="Autonomy level" hint="Higher levels may be rejected by this server's configuration.">
              {(id) => (
                <select
                  id={id}
                  value={autonomyLevel}
                  onChange={(event) => setAutonomyLevel(Number(event.target.value))}
                  className={fieldInputClassName(false)}
                >
                  <option value={0}>0 — Recommend only</option>
                  <option value={1}>1 — Safe, read-only</option>
                  <option value={2}>2 — Reversible actions</option>
                  <option value={3}>3 — Requires human approval</option>
                  <option value={4}>4 — Fully autonomous</option>
                </select>
              )}
            </Field>
          </div>

          <fieldset className="grid gap-6 border-t border-border pt-6 sm:grid-cols-3">
            <legend className="mb-2 text-sm font-medium text-ink sm:col-span-3">Reliability</legend>
            <Field label="Minimum quality" hint="0 to 1">
              {(id) => (
                <input
                  id={id}
                  type="number"
                  min={0}
                  max={1}
                  step={0.05}
                  value={minQuality}
                  onChange={(event) => setMinQuality(Number(event.target.value))}
                  className={fieldInputClassName(false)}
                />
              )}
            </Field>
            <Field label="Tolerated risk">
              {(id) => (
                <select
                  id={id}
                  value={maxRiskLevel}
                  onChange={(event) => setMaxRiskLevel(event.target.value as RiskLevel)}
                  className={fieldInputClassName(false)}
                >
                  {RISK_LEVELS.map((level) => (
                    <option key={level} value={level}>
                      {level[0].toUpperCase() + level.slice(1)}
                    </option>
                  ))}
                </select>
              )}
            </Field>
            <Field label="Minimum independent evidence">
              {(id) => (
                <input
                  id={id}
                  type="number"
                  min={0}
                  value={minIndependentEvidence}
                  onChange={(event) => setMinIndependentEvidence(Number(event.target.value))}
                  className={fieldInputClassName(false)}
                />
              )}
            </Field>
          </fieldset>

          <Field label="Supporting document (optional)" hint="Plain text EIDOS may cite while researching.">
            {(id) => (
              <textarea
                id={id}
                value={supportingDocument}
                onChange={(event) => setSupportingDocument(event.target.value)}
                rows={4}
                className={fieldInputClassName(false)}
              />
            )}
          </Field>
        </div>
      </details>

      <Button type="submit" disabled={submitting} size="md" className="self-start px-6">
        {submitting ? "Creating…" : "Create mission"}
      </Button>
    </form>
  );
}

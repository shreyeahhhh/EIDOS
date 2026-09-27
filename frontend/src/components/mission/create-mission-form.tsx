"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { ApiError } from "@/lib/api/errors";
import { createMission, startMission } from "@/lib/api/client";
import type { CreatedMission, MissionSpec, RiskLevel, StartedMission } from "@/lib/api/types";
import { KNOWN_CAPABILITIES } from "@/lib/api/types";
import { setStoredTenantId } from "@/lib/tenant";
import { RUN_STATUS_LABEL, formatDateTime } from "@/lib/status";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { Field, fieldInputClassName } from "@/components/ui/field";

const CAPABILITY_LABEL: Record<(typeof KNOWN_CAPABILITIES)[number], string> = {
  research: "Research",
  architecture: "Architecture analysis",
  security: "Security analysis",
  cost: "Cost analysis",
};

const RISK_LEVELS: RiskLevel[] = ["low", "medium", "high"];

type Stage =
  | { name: "form" }
  | { name: "tenant_required" }
  | { name: "no_membership" }
  | { name: "created"; mission: CreatedMission };

interface FieldErrors {
  goal?: string;
  required_capabilities?: string;
  risk_level?: string;
}

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

  const [tenantIdInput, setTenantIdInput] = useState("");
  const [stage, setStage] = useState<Stage>({ name: "form" });
  const [submitting, setSubmitting] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [generalErrors, setGeneralErrors] = useState<string[]>([]);
  const [banner, setBanner] = useState<string | null>(null);

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
    setBanner(null);

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
      setStage({ name: "created", mission });
    } catch (error) {
      handleError(error);
    } finally {
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

  async function handleTenantSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!tenantIdInput.trim()) return;
    setStoredTenantId(tenantIdInput.trim());
    setStage({ name: "form" });
    setBanner("Workspace remembered. Submit the mission again.");
  }

  async function handleStart(missionId: string) {
    setSubmitting(true);
    try {
      const started: StartedMission = await startMission(missionId);
      setBanner(`Mission ${RUN_STATUS_LABEL[started.run_status].toLowerCase()}.`);
    } catch (error) {
      handleError(error);
    } finally {
      setSubmitting(false);
    }
  }

  if (stage.name === "no_membership") {
    return (
      <Callout tone="warning" title="No workspace access yet">
        Your account isn&apos;t linked to an EIDOS workspace yet. Ask whoever administers your workspace to add
        you, then sign in again.
      </Callout>
    );
  }

  if (stage.name === "tenant_required") {
    return (
      <form onSubmit={handleTenantSubmit} className="flex flex-col gap-4">
        <Callout tone="info" title="Which workspace?">
          Your account belongs to more than one EIDOS workspace. Enter the workspace ID you were given.
        </Callout>
        <Field label="Workspace (tenant) ID">
          {(id, describedBy) => (
            <input
              id={id}
              aria-describedby={describedBy}
              value={tenantIdInput}
              onChange={(event) => setTenantIdInput(event.target.value)}
              placeholder="00000000-0000-0000-0000-000000000000"
              className={fieldInputClassName(false)}
            />
          )}
        </Field>
        <Button type="submit">Continue</Button>
      </form>
    );
  }

  if (stage.name === "created") {
    const { mission } = stage;
    return (
      <div className="flex flex-col gap-6">
        <Callout tone="success" title="Mission created">
          Nothing has run yet — start it when you&apos;re ready.
        </Callout>
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
          <dt className="text-ink-faint">Mission ID</dt>
          <dd className="font-mono text-xs text-ink">{mission.mission_id}</dd>
          <dt className="text-ink-faint">Status</dt>
          <dd>
            <Badge>{RUN_STATUS_LABEL[mission.run_status]}</Badge>
          </dd>
          <dt className="text-ink-faint">Created</dt>
          <dd className="text-ink">{formatDateTime(mission.created_at)}</dd>
        </dl>
        {banner && <Callout tone="info">{banner}</Callout>}
        <div className="flex gap-3">
          <Button onClick={() => handleStart(mission.mission_id)} disabled={submitting}>
            {submitting ? "Starting…" : "Start mission"}
          </Button>
          <Button variant="secondary" onClick={() => setStage({ name: "form" })}>
            Create another
          </Button>
        </div>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-6" noValidate>
      {banner && <Callout tone="info">{banner}</Callout>}
      {generalErrors.length > 0 && (
        <Callout tone="error" title="This request was refused">
          <ul className="list-disc space-y-1 pl-4">
            {generalErrors.map((message) => (
              <li key={message}>{message}</li>
            ))}
          </ul>
        </Callout>
      )}

      <Field label="Goal" error={fieldErrors.goal} hint="What should this mission accomplish?">
        {(id, describedBy) => (
          <textarea
            id={id}
            aria-describedby={describedBy}
            aria-invalid={Boolean(fieldErrors.goal)}
            value={goal}
            onChange={(event) => setGoal(event.target.value)}
            rows={3}
            className={fieldInputClassName(Boolean(fieldErrors.goal))}
          />
        )}
      </Field>

      <fieldset className="flex flex-col gap-2">
        <legend className="text-sm font-medium text-ink">Capabilities required</legend>
        <div className="flex flex-wrap gap-4">
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

      <Button type="submit" disabled={submitting} className="self-start">
        {submitting ? "Creating…" : "Create mission"}
      </Button>
    </form>
  );
}

"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type ChangeEvent, type FormEvent } from "react";

import { ApiError } from "@/lib/api/errors";
import { ACCEPTED_EXTENSIONS, addDocument, MAX_DOCUMENTS, toSuppliedDocuments, type PickedDocument } from "@/lib/documents";
import { MAX_WEB_ADDRESSES, WEB_FETCH_ACTION, WEB_FETCH_MAX_TOOL_CALLS, webAccessNote, webAddressesIn } from "@/lib/web-access";
import { createMission, startMission } from "@/lib/api/client";
import { apiKeyProblem, encodeRuns, modelNameProblem, PROVIDERS, providerLabel, type ProviderId, type Run } from "@/lib/compare";
import type { MissionSpec, RiskLevel } from "@/lib/api/types";
import { KNOWN_CAPABILITIES } from "@/lib/api/types";
import { rememberMission } from "@/lib/mission-index";
import { useSignedInUserId } from "@/lib/signed-in-user";
import { Button } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { Field, fieldInputClassName } from "@/components/ui/field";
import { EMPTY_CHOICES, ModelChoices, type ChoiceErrors, type Choices, type ChoiceState } from "./model-choices";
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
  const userId = useSignedInUserId();

  const [goal, setGoal] = useState("");
  const [capabilities, setCapabilities] = useState<string[]>([]);
  const [riskLevel, setRiskLevel] = useState<RiskLevel>("low");
  const [autonomyLevel, setAutonomyLevel] = useState(1);
  const [minQuality, setMinQuality] = useState(0);
  const [maxRiskLevel, setMaxRiskLevel] = useState<RiskLevel>("medium");
  const [minIndependentEvidence, setMinIndependentEvidence] = useState(1);
  const [readWeb, setReadWeb] = useState(false);
  const [documents, setDocuments] = useState<PickedDocument[]>([]);
  const [uploadErrors, setUploadErrors] = useState<string[]>([]);
  // A user's own models and keys (D-246): held in this state only, never in browser storage, and emptied the moment any run holds them.
  const [choices, setChoices] = useState<Choices>(EMPTY_CHOICES);
  const [choiceErrors, setChoiceErrors] = useState<ChoiceErrors>({});

  const [stage, setStage] = useState<Stage>({ name: "form" });
  const [submitting, setSubmitting] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [generalErrors, setGeneralErrors] = useState<string[]>([]);
  // What stopped the button from sending anything, listed beside the button: the field messages sit wherever their field is, which can be a screen or two away from where the person clicked.
  const [summary, setSummary] = useState<string[]>([]);
  const [attempt, setAttempt] = useState(0);

  // After a refused click, take the person to the first field that needs attention.
  useEffect(() => {
    if (attempt === 0) return;
    const first = document.querySelector<HTMLElement>('[aria-invalid="true"], [data-invalid="true"]');
    first?.scrollIntoView?.({ block: "center" });
    if (first && first.tagName !== "FIELDSET") first.focus({ preventScroll: true });
  }, [attempt]);

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
      allowed_actions: readWeb ? [WEB_FETCH_ACTION] : [],
      reliability: {
        min_quality: minQuality,
        max_risk_level: maxRiskLevel,
        min_independent_evidence: minIndependentEvidence,
        ...(readWeb ? { max_tool_calls: WEB_FETCH_MAX_TOOL_CALLS } : {}),
      },
      supplied_documents: toSuppliedDocuments(documents),
    };
  }

  /** Reads every chosen file as text in the browser; each one is checked against the backend's limits before it is kept. */
  async function handleFiles(event: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files ?? []);
    event.target.value = ""; // so choosing the same file again after removing it still fires
    let next = documents;
    const problems: string[] = [];
    for (const file of files) {
      let text: string;
      try {
        text = await file.text();
      } catch {
        problems.push(`${file.name}: could not be read.`);
        continue;
      }
      const result = addDocument(next, file.name, text);
      if ("error" in result) problems.push(result.error);
      else next = result.documents;
    }
    setDocuments(next);
    setUploadErrors(problems);
  }

  function changeChoice(provider: ProviderId, patch: Partial<ChoiceState>) {
    setChoices((current) => ({ ...current, [provider]: { ...current[provider], ...patch } }));
    setChoiceErrors((current) => ({ ...current, [provider]: undefined }));
  }

  function removeDocument(ref: string) {
    setDocuments((current) => current.filter((document) => document.ref !== ref));
    setUploadErrors([]);
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFieldErrors({});
    setChoiceErrors({});
    setGeneralErrors([]);
    setSummary([]);

    // Everything that is wrong is found in one pass and said at once, so nothing is left to be discovered one click at a time.
    const errors: FieldErrors = {};
    const problems: string[] = [];
    if (!goal.trim()) {
      errors.goal = "A goal is required.";
      problems.push("Write what you want EIDOS to accomplish.");
    }
    if (capabilities.length === 0) {
      errors.required_capabilities = "Choose at least one capability.";
      problems.push("Choose at least one capability.");
    }
    const picked = PROVIDERS.filter((provider) => choices[provider.id].on);
    const choiceProblems: ChoiceErrors = {};
    for (const provider of picked) {
      const model = modelNameProblem(choices[provider.id].model);
      const key = apiKeyProblem(choices[provider.id].key);
      if (model || key) choiceProblems[provider.id] = { model: model ?? undefined, key: key ?? undefined };
      if (model) problems.push(`${provider.label} model: ${model}`);
      if (key) problems.push(`${provider.label} API key: ${key}`);
    }
    if (problems.length > 0) {
      setFieldErrors(errors);
      setChoiceErrors(choiceProblems);
      setSummary(problems);
      setAttempt((count) => count + 1);
      return;
    }

    if (picked.length > 0) {
      await submitOnOwnModels(picked.map((provider) => provider.id));
      return;
    }

    setSubmitting(true);
    try {
      const mission = await createMission(buildSpec(), { userId });
      rememberMission(userId, { id: mission.mission_id, goal, createdAt: mission.created_at });
      router.push(`/missions/${mission.mission_id}`);
    } catch (error) {
      handleError(error);
      setSubmitting(false);
    }
  }

  /** One mission per chosen model, each started on its own model and key. One model goes to that mission's page; two or more go to the side-by-side page (D-246). */
  async function submitOnOwnModels(providers: ProviderId[]) {
    setSubmitting(true);
    const started: Run[] = [];
    try {
      for (const provider of providers) {
        const { model, key } = choices[provider];
        const mission = await createMission(buildSpec(), { userId });
        rememberMission(userId, { id: mission.mission_id, goal, createdAt: mission.created_at });
        await startMission(mission.mission_id, { userId, model: { provider, model: model.trim(), api_key: key } });
        started.push({ id: mission.mission_id, provider, model: model.trim() });
      }
    } catch (error) {
      if (started.length > 0) setChoices(EMPTY_CHOICES); // the server holds those keys now; this page need not
      handleError(error);
      if (started.length > 0) {
        const names = started.map((run) => providerLabel(run.provider)).join(", ");
        setGeneralErrors((current) => [...current, `${started.length === 1 ? "A run" : "Some runs"} already started (${names}): find ${started.length === 1 ? "it" : "them"} under Missions.`]);
      }
      setSubmitting(false);
      return;
    }
    setChoices(EMPTY_CHOICES); // the keys leave this page as soon as every run has them
    router.push(started.length === 1 ? `/missions/${started[0].id}` : `/missions/compare?${encodeRuns(started)}`);
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

  const webNote = readWeb ? webAccessNote(goal) : null;
  const ownModels = PROVIDERS.filter((provider) => choices[provider.id].on).length;
  // EIDOS answers only from what it is given. A goal with no document and no web page named for reading would end with "nothing to research", so say so before it is sent rather than after.
  const nothingToRead = goal.trim() !== "" && documents.length === 0 && !(readWeb && webAddressesIn(goal).length > 0);

  if (stage.name === "no_membership") return <NoWorkspaceAccess />;

  if (stage.name === "tenant_required") {
    return <TenantRequiredForm onSubmitted={() => setStage({ name: "form" })} />;
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-8" noValidate>
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

      <fieldset className="flex flex-col gap-2" data-invalid={fieldErrors.required_capabilities ? "true" : undefined}>
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

      <fieldset className="flex flex-col gap-2">
        <legend className="text-sm font-medium text-ink">Documents (optional)</legend>
        <p id="documents-hint" className="text-xs text-ink-faint">
          EIDOS works only from what you give it here — it cannot open links. Add text files ({ACCEPTED_EXTENSIONS.join(", ")}), up to{" "}
          {MAX_DOCUMENTS} files, 32 KB each.
        </p>
        <input
          id="documents"
          type="file"
          aria-label="Choose text files to attach"
          multiple
          accept={ACCEPTED_EXTENSIONS.join(",")}
          aria-describedby="documents-hint"
          onChange={handleFiles}
          className="block w-full cursor-pointer text-sm text-ink-muted file:mr-4 file:cursor-pointer file:rounded-md file:border file:border-border-strong file:bg-surface-raised file:px-3 file:py-1.5 file:text-sm file:font-medium file:text-ink hover:file:bg-surface-sunken"
        />
        {uploadErrors.length > 0 && (
          <ul role="alert" className="list-disc space-y-1 pl-4 text-xs text-error">
            {uploadErrors.map((message) => (
              <li key={message}>{message}</li>
            ))}
          </ul>
        )}
        {documents.length > 0 && (
          <ul className="mt-1 flex flex-col divide-y divide-border rounded-md border border-border">
            {documents.map((document) => (
              <li key={document.ref} className="flex items-center justify-between gap-3 px-3 py-2 text-sm">
                <span className="min-w-0 truncate text-ink">
                  {document.name} <span className="font-mono text-xs text-ink-faint">{Math.max(1, Math.round(document.bytes / 1024))} KB</span>
                </span>
                <button
                  type="button"
                  onClick={() => removeDocument(document.ref)}
                  aria-label={`Remove ${document.name}`}
                  className="shrink-0 text-xs font-medium text-ink-muted hover:text-ink"
                >
                  Remove
                </button>
              </li>
            ))}
          </ul>
        )}
      </fieldset>

      <fieldset className="flex flex-col gap-2">
        <legend className="text-sm font-medium text-ink">Web pages (optional)</legend>
        <label className="flex items-start gap-2 text-sm text-ink-muted">
          <input
            type="checkbox"
            checked={readWeb}
            onChange={(event) => setReadWeb(event.target.checked)}
            aria-describedby="web-hint"
            className="mt-0.5 h-4 w-4 rounded border-border-strong accent-[var(--color-accent)]"
          />
          <span>Let EIDOS read the web pages named in my goal</span>
        </label>
        <p id="web-hint" className="text-xs text-ink-faint">
          Reads the https:// addresses written in your goal (up to {MAX_WEB_ADDRESSES}) as text and cites them. It never logs in, runs scripts, follows links
          inside a page, or opens private or internal addresses, and it cannot see how a page looks.
        </p>
        {readWeb && webNote && (
          <p role="status" className="text-xs text-warning">
            {webNote}
          </p>
        )}
      </fieldset>

      <ModelChoices choices={choices} errors={choiceErrors} onChange={changeChoice} />

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

        </div>
      </details>

      {summary.length > 0 && (
        <Callout tone="error" title="Not sent yet — a few things need fixing">
          <ul className="list-disc space-y-1 pl-4">
            {summary.map((message) => (
              <li key={message}>{message}</li>
            ))}
          </ul>
        </Callout>
      )}

      {generalErrors.length > 0 && (
        <Callout tone="error" title="This request was refused">
          <ul className="list-disc space-y-1 pl-4">
            {generalErrors.map((message) => (
              <li key={message}>{message}</li>
            ))}
          </ul>
        </Callout>
      )}

      {nothingToRead && (
        <Callout tone="warning" title="Nothing for EIDOS to read yet">
          <p>
            EIDOS answers only from sources you give it, and none is attached. Attach a text file above, or tick “Let EIDOS read the web pages named in my goal” and write the page&apos;s full https:// address in your goal.
            Without either, this mission will end with “nothing to research” — EIDOS does not answer from its own memory.
          </p>
          <p className="mt-2">
            Want the models&apos; own answers instead, with no sources?{" "}
            <Link href="/missions/ask" className="font-medium underline underline-offset-4">
              Ask them directly
            </Link>{" "}
            — the answers are labelled unverified.
          </p>
        </Callout>
      )}

      <Button type="submit" disabled={submitting} size="md" className="self-start px-6">
        {submitting ? (ownModels > 1 ? "Starting the runs…" : "Creating…") : ownModels > 1 ? `Compare ${ownModels} models` : "Create mission"}
      </Button>
    </form>
  );
}

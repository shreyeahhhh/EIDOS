"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";

import { AnswerBlocks } from "@/components/cockpit/answer-text";
import { EMPTY_CHOICES, ModelChoices, type ChoiceErrors, type Choices, type ChoiceState } from "@/components/mission/model-choices";
import { Button } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { Skeleton } from "@/components/ui/skeleton";
import { fieldInputClassName } from "@/components/ui/field";
import { askModels } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import type { AskedAnswer, AskResult } from "@/lib/api/types";
import { parseAnswer } from "@/lib/answer-markdown";
import { apiKeyProblem, modelNameProblem, PROVIDERS, providerLabel, type ProviderId } from "@/lib/compare";
import { formatDuration } from "@/lib/run-model";

/** The server refuses a longer question (its ceiling for a goal); saying so here saves a round trip. */
const MAX_QUESTION_CHARS = 2000;

const NO_CITATIONS: ReadonlyMap<string, number> = new Map();

/**
 * One question put straight to the models the person chooses, with their own keys, and the answers side by side (D-248). **This is not a mission and the answers are not verified**: they are each model's own
 * words, with no sources, and the page says so before and beside every answer. Nothing is stored. The keys are held in this page's state only (never in browser storage) and go to the server in the request,
 * which keeps them for the length of the call and no longer.
 */
export function AskView() {
  const router = useRouter();
  const [question, setQuestion] = useState("");
  const [choices, setChoices] = useState<Choices>(EMPTY_CHOICES);
  const [choiceErrors, setChoiceErrors] = useState<ChoiceErrors>({});
  const [questionError, setQuestionError] = useState<string | null>(null);
  const [noneTicked, setNoneTicked] = useState(false);
  const [summary, setSummary] = useState<string[]>([]);
  const [attempt, setAttempt] = useState(0);
  const [asking, setAsking] = useState(false);
  const [result, setResult] = useState<AskResult | null>(null);
  const [asked, setAsked] = useState<{ provider: ProviderId; model: string }[]>([]);
  const [failure, setFailure] = useState<string | null>(null);

  // After a refused click, take the person to the first thing to fix.
  useEffect(() => {
    if (attempt === 0) return;
    const first = document.querySelector<HTMLElement>('[aria-invalid="true"], [data-invalid="true"]');
    first?.scrollIntoView?.({ block: "center" });
    if (first && first.tagName !== "FIELDSET") first.focus({ preventScroll: true });
  }, [attempt]);

  function changeChoice(provider: ProviderId, patch: Partial<ChoiceState>) {
    setChoices((current) => ({ ...current, [provider]: { ...current[provider], ...patch } }));
    setChoiceErrors((current) => ({ ...current, [provider]: undefined }));
    setNoneTicked(false);
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setQuestionError(null);
    setChoiceErrors({});
    setNoneTicked(false);
    setSummary([]);
    setFailure(null);

    const problems: string[] = [];
    const text = question.trim();
    let nextQuestionError: string | null = null;
    if (!text) nextQuestionError = "Write your question.";
    else if (text.length > MAX_QUESTION_CHARS) nextQuestionError = `Keep the question under ${MAX_QUESTION_CHARS.toLocaleString("en-US")} characters.`;
    if (nextQuestionError) problems.push(nextQuestionError);

    const picked = PROVIDERS.filter((provider) => choices[provider.id].on);
    if (picked.length === 0) problems.push("Tick at least one model to ask.");
    const nextChoiceErrors: ChoiceErrors = {};
    for (const provider of picked) {
      const model = modelNameProblem(choices[provider.id].model);
      const key = apiKeyProblem(choices[provider.id].key);
      if (model || key) nextChoiceErrors[provider.id] = { model: model ?? undefined, key: key ?? undefined };
      if (model) problems.push(`${provider.label} model: ${model}`);
      if (key) problems.push(`${provider.label} API key: ${key}`);
    }
    if (problems.length > 0) {
      setQuestionError(nextQuestionError);
      setChoiceErrors(nextChoiceErrors);
      setNoneTicked(picked.length === 0);
      setSummary(problems);
      setAttempt((count) => count + 1);
      return;
    }

    setAsking(true);
    setResult(null);
    setAsked(picked.map((provider) => ({ provider: provider.id, model: choices[provider.id].model.trim() })));
    try {
      setResult(await askModels({ question: text, models: picked.map((provider) => ({ provider: provider.id, model: choices[provider.id].model.trim(), api_key: choices[provider.id].key })) }));
    } catch (error) {
      if (error instanceof ApiError && error.code === "unauthenticated") {
        router.push("/login?next=/missions/ask");
        return;
      }
      setFailure(error instanceof Error ? error.message : "Something unexpected went wrong. Try again.");
    } finally {
      setAsking(false);
    }
  }

  const ticked = PROVIDERS.filter((provider) => choices[provider.id].on).length;

  return (
    <div className="flex flex-col gap-8">
      <form onSubmit={submit} noValidate className="flex max-w-3xl flex-col gap-6">
        <div className="flex flex-col gap-2">
          <label htmlFor="question" className="font-display text-lg text-ink">
            What do you want to ask?
          </label>
          <textarea
            id="question"
            rows={4}
            value={question}
            onChange={(event) => {
              setQuestion(event.target.value);
              setQuestionError(null);
            }}
            aria-invalid={Boolean(questionError)}
            aria-describedby="question-hint"
            placeholder="e.g. Which is the best time for a beginner to buy and sell stocks?"
            className={`${fieldInputClassName(Boolean(questionError))} text-base leading-relaxed`}
          />
          <p id="question-hint" className="text-xs text-ink-faint">
            Sent exactly as written, to each model you tick. No documents, no web pages: each answers from its own knowledge.
          </p>
          {questionError && (
            <p role="alert" className="text-xs text-error">
              {questionError}
            </p>
          )}
        </div>

        <ModelChoices
          choices={choices}
          errors={choiceErrors}
          onChange={changeChoice}
          invalid={noneTicked}
          legend="Which models should answer?"
          intro="Tick the models to ask and enter your own API key for each. Tick two or three to compare what they say. Leave the others unticked."
          comparing={(picked) => `Your question goes to each of the ${picked} models at the same time, and the answers appear side by side.`}
        />

        {summary.length > 0 && (
          <Callout tone="error" title="Not sent yet — a few things need fixing">
            <ul className="list-disc space-y-1 pl-4">
              {summary.map((message) => (
                <li key={message}>{message}</li>
              ))}
            </ul>
          </Callout>
        )}
        {failure && (
          <Callout tone="error" title="This request was refused">
            <p>{failure}</p>
          </Callout>
        )}

        <Button type="submit" disabled={asking} className="self-start px-6">
          {asking ? "Asking…" : ticked > 1 ? `Ask ${ticked} models` : "Ask"}
        </Button>
      </form>

      {asking && (
        <section aria-label="Waiting for the answers" aria-live="polite" className={`grid gap-5 ${asked.length === 3 ? "lg:grid-cols-3" : asked.length === 2 ? "lg:grid-cols-2" : ""}`}>
          {asked.map((entry) => (
            <div key={entry.provider} className="flex flex-col gap-3 rounded-2xl border border-border bg-surface-raised p-5">
              <p className="font-display text-xl text-ink">{providerLabel(entry.provider)}</p>
              <p className="text-xs text-ink-muted">Thinking…</p>
              <Skeleton className="h-32 w-full" />
            </div>
          ))}
        </section>
      )}

      {result && (
        <section aria-label="Answers" className="flex flex-col gap-5">
          <Callout tone="warning" title="Unverified — these answers have no sources">
            <p>{result.note}</p>
          </Callout>
          <div className={`grid gap-5 ${result.answers.length === 3 ? "lg:grid-cols-3" : result.answers.length === 2 ? "lg:grid-cols-2" : ""}`}>
            {result.answers.map((answer, index) => (
              <AnswerColumn key={`${answer.provider}-${index}`} answer={answer} />
            ))}
          </div>
          <p className="max-w-3xl text-sm text-ink-muted">
            Want sources behind an answer? Attach a document, or a page&apos;s address, to a{" "}
            <Link href="/missions/new" className="font-medium underline underline-offset-4">
              mission
            </Link>
            : EIDOS then answers only from what it read, cites it, and checks that every source is real.
          </p>
        </section>
      )}
    </div>
  );
}

function AnswerColumn({ answer }: { answer: AskedAnswer }) {
  const time = answer.elapsed_seconds !== null ? formatDuration(Math.round(answer.elapsed_seconds * 1000)) : null;
  return (
    <article aria-label={`${providerLabel(answer.provider)} ${answer.model}`} className="flex min-w-0 flex-col gap-3 rounded-2xl border border-border bg-surface-raised p-5 shadow-[var(--shadow-card)]">
      <header className="flex flex-col gap-1">
        <h2 className="font-display text-xl text-ink">{providerLabel(answer.provider)}</h2>
        <p className="font-mono text-xs break-all text-ink-muted">{answer.model}</p>
        <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-muted">
          {time && <li>Took {time}</li>}
          {answer.output_tokens !== null && <li>{answer.output_tokens} tokens written</li>}
        </ul>
      </header>
      {answer.ok && answer.text !== null ? (
        <div data-testid="asked-answer">
          <AnswerBlocks blocks={parseAnswer(answer.text)} numbers={NO_CITATIONS} activeRef={null} onCite={() => {}} idPrefix={`ask-${answer.provider}-`} />
        </div>
      ) : (
        <Callout tone="error" title="This model did not answer">
          <p className="break-words">{answer.failure ?? "No reason was given."}</p>
        </Callout>
      )}
    </article>
  );
}

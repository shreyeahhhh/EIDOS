/**
 * Comparing the same goal on several models, with the user's own keys (decisions.md D-246).
 *
 * A comparison is not a new kind of record: it is one ordinary mission per model, each started on its own provider, model and key. The page that shows them side by side knows which missions belong
 * together from its own address (`/compare?r=<mission>~<provider>~<model>&r=…`), which holds ids, provider names and model names and **never a key**. A key lives in the form's state until the runs
 * are started and is then forgotten; the server holds it in memory for the run and nowhere else.
 */

export const PROVIDERS = [
  { id: "openai", label: "OpenAI", note: "ChatGPT models" },
  { id: "gemini", label: "Google Gemini", note: "Gemini models" },
  { id: "groq", label: "Groq", note: "open models run on Groq" },
] as const;

export type ProviderId = (typeof PROVIDERS)[number]["id"];

/** The same rules the backend applies (`eidos.service.user_models`), so a mistake is caught before anything is sent. */
const MODEL_NAME = /^[A-Za-z0-9][A-Za-z0-9._:/-]{0,99}$/;
const API_KEY = /^[\x21-\x7e]{8,512}$/;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function providerLabel(id: string): string {
  return PROVIDERS.find((provider) => provider.id === id)?.label ?? id;
}

export function isProviderId(value: string): value is ProviderId {
  return PROVIDERS.some((provider) => provider.id === value);
}

export function modelNameProblem(name: string): string | null {
  if (!name.trim()) return "Enter the model's id.";
  return MODEL_NAME.test(name.trim()) ? null : "A model id has only letters, digits and . _ : / - (no spaces).";
}

/** Says what is wrong with a key without ever repeating it. */
export function apiKeyProblem(key: string): string | null {
  if (!key) return "Enter your API key.";
  if (/\s/.test(key)) return "A key has no spaces or line breaks. Paste it again without them.";
  return API_KEY.test(key) ? null : "That does not look like an API key (8 to 512 plain characters).";
}

export interface Run {
  id: string;
  provider: ProviderId;
  model: string;
}

/** The query string for a comparison: ids, providers and models only. */
export function encodeRuns(runs: Run[]): string {
  const params = new URLSearchParams();
  for (const run of runs) params.append("r", `${run.id}~${run.provider}~${run.model}`);
  return params.toString();
}

/** The runs a comparison address names. An entry that is not a real mission id, a known provider and a plausible model name is dropped, and no more than one run per provider is kept. */
export function decodeRuns(params: URLSearchParams): Run[] {
  const runs: Run[] = [];
  for (const entry of params.getAll("r")) {
    const [id, provider, model, ...rest] = entry.split("~");
    if (rest.length > 0 || !id || !UUID.test(id) || !provider || !isProviderId(provider) || !model || !MODEL_NAME.test(model)) continue;
    if (runs.some((run) => run.provider === provider || run.id === id)) continue;
    runs.push({ id, provider, model });
  }
  return runs;
}

/**
 * What the landing page's explainer video says, scene by scene. Kept apart from the player so the words can be read and tested on their own,
 * and so the (server-rendered) page can say how long the video is.
 *
 * Every claim here is something a mission really does today, worded so it does not overclaim: the plan is validated before it runs; steps run
 * under hard limits; a failed step leads to a new plan or an honest stop; the final check is that the answer cites sources and that those
 * sources exist — not that the answer is right, which the video says out loud. Learning from past missions is deferred (D-202), so the video
 * does not mention it.
 */

export type SceneId = "ask" | "plan" | "work" | "twist" | "receipts" | "answer";

export interface Scene {
  id: SceneId;
  /** Two or three words, for the chapter list. */
  chapter: string;
  /** The headline, lower-case on purpose; `mark` is the word the highlighter swipes under (it starts exactly one word of the headline). */
  headline: string;
  mark: string;
  /** One plain sentence or two: what is happening, in words anyone can follow. */
  caption: string;
  /** A short, honest aside, where one is owed. */
  aside?: string;
  durationMs: number;
}

export const SCENES: Scene[] = [
  {
    id: "ask",
    chapter: "you ask",
    headline: "you ask a question.",
    mark: "question",
    caption: "Type what you want to know. Add your own files, or a link, if it helps.",
    durationMs: 6000,
  },
  {
    id: "plan",
    chapter: "it plans",
    headline: "EIDOS makes a plan.",
    mark: "plan",
    caption: "Your question becomes a few small steps — and the plan is checked before anything runs.",
    durationMs: 6500,
  },
  {
    id: "work",
    chapter: "it works",
    headline: "then it does the work.",
    mark: "work",
    caption: "Each step reads what you gave it and notes which source it used. Hard limits mean it can never run forever.",
    durationMs: 7000,
  },
  {
    id: "twist",
    chapter: "plot twist",
    headline: "plot twist: a step fails.",
    mark: "fails",
    caption: "EIDOS makes a new plan. If that can't work either, it stops and tells you why — no made-up answer to fill the gap.",
    durationMs: 7000,
  },
  {
    id: "receipts",
    chapter: "receipts",
    headline: "no receipts, no answer.",
    mark: "receipts",
    caption: "A last check: the answer has to name its sources, and every source it names has to be real.",
    aside: "Fine print: it checks the receipts, not whether the answer is right. You still read it.",
    durationMs: 7000,
  },
  {
    id: "answer",
    chapter: "you get it",
    headline: "you get the answer + the receipts.",
    mark: "answer",
    caption: "Read it, open its sources, and replay every step it took.",
    durationMs: 6500,
  },
];

export const TOTAL_MS = SCENES.reduce((total, scene) => total + scene.durationMs, 0);

/** 40000 → "0:40". */
export function formatClock(ms: number): string {
  const seconds = Math.round(ms / 1000);
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

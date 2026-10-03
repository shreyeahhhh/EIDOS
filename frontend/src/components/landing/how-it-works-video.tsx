"use client";

import Link from "next/link";
import { Fragment, useEffect, useReducer, useRef, useSyncExternalStore, type CSSProperties, type KeyboardEvent, type MouseEvent, type ReactNode } from "react";

import { buttonClassName } from "@/components/ui/button";
import { cn } from "@/lib/cn";
import { SCENES, TOTAL_MS, formatClock, type Scene, type SceneId } from "./how-it-works-scenes";

/*
 * "How EIDOS works" as a short video in a Gen Z editorial style — big serif headlines with a highlighter swipe, tilted stickers, cut-out cards with
 * hard shadows, a ticker band, paper grain — in the page's three colours. It is a motion piece made of real text and shapes rather than a video
 * file: it stays sharp at any size, every word is real text, and it needs no media download. It plays like a story: one segment per part, autoplay
 * once it is mostly on screen, a pause when it scrolls away, and the viewer can pause, step, jump to a part, or read the whole thing as text.
 * The animations themselves are in globals.css (`hiw-*`).
 */

// --- the clock -----------------------------------------------------------------------------------------------------------------------

export interface PlayerState {
  index: number;
  /** Bumped whenever a part starts over, so its pieces mount afresh and their animations run from the top. */
  run: number;
  playing: boolean;
  /** Whether the part on screen is animating; false shows every piece at rest (the poster, a part picked while paused). */
  animated: boolean;
  ended: boolean;
  /** The viewer paused it themselves, so scrolling it back into view does not start it again. */
  heldByViewer: boolean;
}

export type PlayerAction = { type: "play"; by: "viewer" | "view" } | { type: "pause"; by: "viewer" | "view" } | { type: "go"; index: number } | { type: "sceneEnded" };

export const INITIAL: PlayerState = { index: 0, run: 0, playing: false, animated: false, ended: false, heldByViewer: false };

const LAST = SCENES.length - 1;

export function player(state: PlayerState, action: PlayerAction): PlayerState {
  switch (action.type) {
    case "play":
      if (action.by === "view" && (state.heldByViewer || state.ended || state.playing)) return state;
      if (state.ended) return { index: 0, run: state.run + 1, playing: true, animated: true, ended: false, heldByViewer: false };
      // a part shown at rest starts from its top; one paused part-way through carries on from where it stopped
      return { ...state, playing: true, animated: true, run: state.animated ? state.run : state.run + 1, heldByViewer: false };
    case "pause":
      if (!state.playing) return state;
      return { ...state, playing: false, heldByViewer: action.by === "viewer" };
    case "go": {
      const index = Math.max(0, Math.min(LAST, action.index));
      return { ...state, index, run: state.run + 1, animated: state.playing, ended: false };
    }
    case "sceneEnded":
      if (!state.playing) return state;
      if (state.index >= LAST) return { ...state, playing: false, ended: true };
      return { ...state, index: state.index + 1, run: state.run + 1, animated: true };
  }
}

const REDUCED_MOTION = "(prefers-reduced-motion: reduce)";

function subscribeToMotion(onChange: () => void): () => void {
  if (typeof window === "undefined" || !window.matchMedia) return () => {};
  const query = window.matchMedia(REDUCED_MOTION);
  query.addEventListener("change", onChange);
  return () => query.removeEventListener("change", onChange);
}

/** Whether the device asks for less motion: then nothing plays by itself, and every part is shown at rest. */
function useReducedMotion(): boolean {
  return useSyncExternalStore(
    subscribeToMotion,
    () => typeof window !== "undefined" && !!window.matchMedia?.(REDUCED_MOTION).matches,
    () => false,
  );
}

// --- the pieces ----------------------------------------------------------------------------------------------------------------------

const at = (delayMs: number, vars: Record<string, string> = {}): CSSProperties => ({ animationDelay: `${delayMs}ms`, ...vars }) as CSSProperties;
const pad = (n: number) => String(n).padStart(2, "0");

const LABEL = "font-mono text-[length:max(0.62rem,0.95cqw)] font-semibold tracking-[0.2em] text-ink-muted uppercase";
const PAPER = "rounded-xl border-2 border-ink bg-surface-raised shadow-[3px_3px_0_var(--color-ink)]";
const CHIP = "inline-flex items-center gap-1 rounded-full border-2 border-ink bg-surface-raised px-2.5 py-0.5 font-mono text-[length:max(0.68rem,1.05cqw)] text-ink";

function Sticker({ children, delay, tilt, className }: { children: ReactNode; delay: number; tilt: string; className?: string }) {
  return (
    <span
      className={cn(
        "hiw-pop z-10 inline-flex items-center gap-1 rounded-full border-2 border-ink bg-accent px-3 py-1 font-mono text-[length:max(0.66rem,1.05cqw)] font-semibold tracking-wider whitespace-nowrap text-on-accent uppercase shadow-[2px_2px_0_var(--color-ink)]",
        className,
      )}
      style={at(delay, { "--hiw-tilt": tilt })}
    >
      {children}
    </span>
  );
}

const STEPS = [
  { n: "01", name: "research", what: "reads your stuff" },
  { n: "02", name: "analyse", what: "thinks it through" },
  { n: "03", name: "check", what: "checks the receipts" },
];

function StepCard({ step, status }: { step: (typeof STEPS)[number]; status?: ReactNode }) {
  return (
    <div className={cn(PAPER, "flex items-center gap-3 px-3.5 py-2.5")}>
      <span className="font-mono text-xs text-ink-muted">{step.n}</span>
      <span className="font-display text-[length:max(1.05rem,1.9cqw)] leading-none text-ink">{step.name}</span>
      <span className="hidden text-[length:max(0.72rem,1.1cqw)] text-ink-muted @md:inline">{step.what}</span>
      <span className="ml-auto">{status}</span>
    </div>
  );
}

function Done({ delay }: { delay: number }) {
  return (
    <span className="hiw-pop inline-flex rounded-full bg-accent px-2 py-0.5 text-xs font-semibold text-on-accent" style={at(delay)}>
      done ✓
    </span>
  );
}

function Cite({ n, delay }: { n: number; delay: number }) {
  return (
    <span className="hiw-pop ml-1 inline-flex h-5 min-w-5 -translate-y-px items-center justify-center rounded-full bg-accent-soft px-1 align-middle text-[11px] font-semibold text-accent-strong" style={at(delay)}>
      {n}
    </span>
  );
}

/** What each part shows beside its words. Example content (a portfolio site, notes.md) is illustrative, the same story from part to part. */
function SceneVisual({ id }: { id: SceneId }) {
  switch (id) {
    case "ask":
      return (
        <div className="relative w-full max-w-[25rem]">
          <div className={cn(PAPER, "hiw-rise p-[max(0.9rem,1.6cqw)]")} style={at(250)}>
            <p className={LABEL}>your question</p>
            <p className="mt-2 font-display text-[length:max(1.05rem,2cqw)] leading-snug text-ink">
              <span className="hiw-type" style={at(700)}>
                is my portfolio site any good?
              </span>
              <span aria-hidden="true" className="hiw-caret ml-0.5 inline-block h-[1em] w-[2px] translate-y-[0.15em] bg-ink" />
            </p>
            <div className="mt-4 flex flex-wrap gap-2">
              <span className={cn("hiw-pop", CHIP)} style={at(2300, { "--hiw-tilt": "-2deg" })}>
                + notes.md
              </span>
              <span className={cn("hiw-pop", CHIP)} style={at(2550, { "--hiw-tilt": "2deg" })}>
                ↗ my-portfolio.com
              </span>
            </div>
          </div>
          <Sticker delay={3100} tilt="7deg" className="absolute -top-4 -right-2">
            that’s it. really.
          </Sticker>
        </div>
      );
    case "plan":
      return (
        <div className="relative flex w-full max-w-[27rem] flex-col gap-2.5 pb-9">
          {STEPS.map((step, index) => (
            <div key={step.n} className="hiw-slide" style={at(300 + index * 350, { "--hiw-tilt": ["-1.5deg", "1deg", "-0.5deg"][index] })}>
              <StepCard step={step} />
            </div>
          ))}
          <Sticker delay={1900} tilt="-5deg" className="absolute right-0 bottom-0">
            ✓ checked before it runs
          </Sticker>
        </div>
      );
    case "work":
      return (
        <div className="relative flex w-full max-w-[27rem] flex-col gap-2.5 pb-9">
          <StepCard step={STEPS[0]} status={<Done delay={900} />} />
          <div className="flex flex-wrap gap-2 pl-8">
            <span className="hiw-rise rounded-sm border border-dashed border-ink bg-surface-raised px-2 py-0.5 font-mono text-[11px] text-ink-muted" style={at(1250)}>
              from notes.md
            </span>
            <span className="hiw-rise rounded-sm border border-dashed border-ink bg-surface-raised px-2 py-0.5 font-mono text-[11px] text-ink-muted" style={at(1500)}>
              from my-portfolio.com
            </span>
          </div>
          <StepCard step={STEPS[1]} status={<Done delay={2300} />} />
          <StepCard step={STEPS[2]} status={<span className="hiw-rise font-mono text-xs text-ink-muted" style={at(2300)}>up next</span>} />
          <div className="mt-1 flex flex-wrap gap-2">
            {["time limit", "step limit", "retry limit"].map((limit, index) => (
              <span key={limit} className={cn("hiw-pop", CHIP)} style={at(3000 + index * 150)}>
                ▮ {limit}
              </span>
            ))}
          </div>
          <Sticker delay={3700} tilt="5deg" className="absolute right-0 bottom-0">
            no endless loops
          </Sticker>
        </div>
      );
    case "twist":
      return (
        <div className="relative flex w-full max-w-[27rem] flex-col gap-2">
          <div className="hiw-shake" style={at(900)}>
            <StepCard
              step={STEPS[0]}
              status={
                <span className="hiw-pop inline-flex rounded-full border-2 border-error bg-error-soft px-2 py-0.5 text-xs font-semibold text-error" style={at(950)}>
                  ✕ didn’t work
                </span>
              }
            />
          </div>
          <svg aria-hidden="true" viewBox="0 0 60 44" className="ml-10 h-11 w-14 text-accent">
            <path pathLength={1} className="hiw-draw" style={at(1600)} d="M8 2 C 2 18, 18 30, 34 30 S 52 34, 50 42" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
            <path pathLength={1} className="hiw-draw" style={at(2150)} d="M42 36 L 50 42 L 55 33" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          <div className="hiw-slide" style={at(2300, { "--hiw-tilt": "-1.5deg" })}>
            <div className={cn(PAPER, "px-3.5 py-3")}>
              <p className={LABEL}>plan 2</p>
              <p className="mt-1 font-display text-[length:max(1.05rem,1.9cqw)] leading-snug text-ink">same question, a new set of steps</p>
            </div>
          </div>
          <Sticker delay={2900} tilt="-6deg" className="absolute top-[42%] right-0">
            ↻ new plan
          </Sticker>
          <p className="hiw-rise mt-1 font-mono text-[length:max(0.7rem,1.05cqw)] text-ink-muted" style={at(3500)}>
            still stuck? it stops + tells you why.
          </p>
        </div>
      );
    case "receipts":
      return (
        <div className="relative w-full max-w-[25rem] pb-8">
          <div className={cn(PAPER, "hiw-rise p-[max(1rem,1.8cqw)]")} style={at(250)}>
            <p className={LABEL}>the answer</p>
            <ul className="mt-3 flex flex-col gap-2.5 text-[length:max(0.9rem,1.5cqw)] leading-snug text-ink">
              <li className="hiw-rise" style={at(600)}>
                your menu shows up twice
                <Cite n={1} delay={1300} />
              </li>
              <li className="hiw-rise" style={at(850)}>
                two images have no alt text
                <Cite n={2} delay={1550} />
              </li>
              <li className="hiw-rise" style={at(1100)}>
                the colours read fine
                <Cite n={1} delay={1800} />
              </li>
            </ul>
          </div>
          <div
            className="hiw-stamp absolute right-[-0.5rem] bottom-0 flex h-[max(5.75rem,10cqw)] w-[max(5.75rem,10cqw)] items-center justify-center rounded-full border-[3px] border-accent-strong bg-surface-raised text-center font-mono text-[length:max(0.6rem,0.95cqw)] leading-tight font-bold tracking-wider text-accent-strong uppercase outline-2 outline-offset-[-8px] outline-accent-strong outline-dashed"
            style={at(2300)}
          >
            every
            <br />
            source
            <br />
            is real ✓
          </div>
        </div>
      );
    case "answer":
      return (
        <div className="relative flex w-full max-w-[26rem] flex-col gap-3">
          <div className={cn(PAPER, "hiw-rise p-[max(1rem,1.8cqw)]")} style={at(250)}>
            <p className={LABEL}>sources</p>
            <ol className="mt-2 flex flex-col gap-2 text-[length:max(0.85rem,1.4cqw)]">
              {[
                ["my-portfolio.com", "web page"],
                ["notes.md", "your file"],
              ].map(([name, kind], index) => (
                <li key={name} className="hiw-rise flex items-center gap-2" style={at(600 + index * 250)}>
                  <span className="inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-accent-soft px-1 text-[11px] font-semibold text-accent-strong">{index + 1}</span>
                  <span className="font-medium text-ink">{name}</span>
                  <span className="text-xs text-ink-muted">{kind}</span>
                </li>
              ))}
            </ol>
          </div>
          <div className={cn(PAPER, "hiw-rise p-3")} style={at(1200)}>
            <div className="flex items-center gap-3">
              <span aria-hidden="true" className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-accent text-on-accent">
                <PlayIcon />
              </span>
              <div className="relative h-1.5 flex-1 rounded-full bg-ink/15">
                {[0, 20, 40, 60, 80, 100].map((tick) => (
                  <span key={tick} className="absolute top-1/2 h-2.5 w-0.5 -translate-y-1/2 bg-ink/40" style={{ left: `${tick}%` }} />
                ))}
                <span className="hiw-glide absolute top-1/2 h-3.5 w-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-ink bg-accent" style={at(1500)} />
              </div>
            </div>
            <p className="mt-2 font-mono text-[11px] text-ink-muted">replay every step</p>
          </div>
          <Sticker delay={3200} tilt="-4deg" className="absolute -top-3 -right-2">
            shows its work ✓
          </Sticker>
        </div>
      );
  }
}

/** The kicker, the headline word by word (the marked word gets the highlighter), the caption, and an aside where one is owed. */
function SceneWords({ scene, index }: { scene: Scene; index: number }) {
  const words = scene.headline.split(" ");
  const markAt = words.findIndex((word) => word.startsWith(scene.mark));
  return (
    <div className="relative z-10 flex flex-col justify-center gap-[max(0.8rem,1.5cqw)]">
      <p className="hiw-rise font-mono text-[length:max(0.68rem,1.05cqw)] font-semibold tracking-[0.22em] text-accent-strong uppercase">
        {pad(index + 1)} — {scene.chapter}
      </p>
      <p className="font-display text-[length:max(2.1rem,5.4cqw)] leading-[0.98] tracking-tight text-ink">
        {words.map((word, position) => (
          <Fragment key={position}>
            {position > 0 && " "}
            <span className="hiw-rise inline-block" style={at(120 + position * 90)}>
              {position === markAt ? (
                <>
                  <span className="relative inline-block">
                    <span aria-hidden="true" className="hiw-swipe absolute inset-x-[-0.06em] bottom-[0.06em] h-[0.42em] rounded-[0.1em] bg-accent/70" style={at(220 + words.length * 90)} />
                    <em className="relative">{scene.mark}</em>
                  </span>
                  {word.slice(scene.mark.length)}
                </>
              ) : (
                word
              )}
            </span>
          </Fragment>
        ))}
      </p>
      <p className="hiw-rise max-w-[36ch] text-[length:max(0.95rem,1.6cqw)] leading-snug text-ink-muted" style={at(700)}>
        {scene.caption}
      </p>
      {scene.aside && (
        <p className="hiw-rise max-w-[42ch] border-l-[3px] border-accent pl-3 font-mono text-[length:max(0.72rem,1.05cqw)] leading-relaxed text-ink-muted" style={at(2600)}>
          {scene.aside}
        </p>
      )}
    </div>
  );
}

const TICKER = ["ask", "plan", "do the work", "check the receipts", "get the answer", "replay it"];

function PlayIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 16 16" className="h-3.5 w-3.5 translate-x-px fill-current">
      <path d="M4 2.5v11l9-5.5z" />
    </svg>
  );
}

function PauseIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 16 16" className="h-3.5 w-3.5 fill-current">
      <path d="M3.5 2.5h3v11h-3zM9.5 2.5h3v11h-3z" />
    </svg>
  );
}

// --- the player ----------------------------------------------------------------------------------------------------------------------

export function HowItWorksVideo({ ctaHref, ctaLabel }: { ctaHref: string; ctaLabel: string }) {
  const reduced = useReducedMotion();
  const [state, dispatch] = useReducer(player, INITIAL);
  const frame = useRef<HTMLDivElement>(null);
  const playing = state.playing && !reduced;
  const animated = state.animated && !reduced;
  const scene = SCENES[state.index];
  const length = formatClock(TOTAL_MS);

  // Plays by itself once it is mostly on screen, and pauses when it scrolls away — unless the viewer paused it, or the device asks for less motion.
  useEffect(() => {
    const node = frame.current;
    if (!node || reduced || typeof IntersectionObserver === "undefined") return;
    const observer = new IntersectionObserver(
      ([entry]) => dispatch(entry.isIntersecting && entry.intersectionRatio >= 0.6 ? { type: "play", by: "view" } : { type: "pause", by: "view" }),
      { threshold: [0, 0.6] },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [reduced]);

  function toggle() {
    if (reduced) return;
    dispatch(playing ? { type: "pause", by: "viewer" } : { type: "play", by: "viewer" });
  }
  const go = (index: number) => dispatch({ type: "go", index });

  function onFrameClick(event: MouseEvent<HTMLDivElement>) {
    if ((event.target as HTMLElement).closest("button, a")) return; // its own controls do their own thing
    toggle();
  }
  function onFrameKey(event: KeyboardEvent<HTMLDivElement>) {
    if (event.target !== event.currentTarget) return;
    if (event.key === " " || event.key === "k") {
      event.preventDefault();
      toggle();
    } else if (event.key === "ArrowRight") {
      event.preventDefault();
      go(state.index + 1);
    } else if (event.key === "ArrowLeft") {
      event.preventDefault();
      go(state.index - 1);
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <div
        ref={frame}
        role="region"
        aria-roledescription="video"
        aria-label={`How EIDOS works: a ${length} explainer in ${SCENES.length} parts`}
        tabIndex={0}
        onClick={onFrameClick}
        onKeyDown={onFrameKey}
        data-paused={playing ? undefined : ""}
        data-static={animated ? undefined : ""}
        data-testid="video-frame"
        className="hiw-frame @container relative isolate flex cursor-pointer flex-col overflow-hidden rounded-[1.75rem] border-2 border-ink bg-surface text-ink shadow-[6px_6px_0_var(--color-ink)] select-none"
      >
        <span aria-hidden="true" className="hiw-grain pointer-events-none absolute inset-0 -z-10 opacity-20" />

        {/* top: one segment per part (the current one fills as it plays — its end moves the video on), and the masthead */}
        <div className="relative z-10 flex flex-col gap-2.5 px-[max(1.25rem,4cqw)] pt-[max(1rem,2.2cqw)]">
          <div aria-hidden="true" className="flex gap-1.5">
            {SCENES.map((item, index) => (
              <span key={item.id} className="h-1 flex-1 overflow-hidden rounded-full bg-ink/15">
                {index === state.index && animated ? (
                  <span
                    key={`${state.index}-${state.run}`}
                    data-testid="scene-clock"
                    className="hiw-fill block h-full w-full bg-accent"
                    style={{ animationDuration: `${item.durationMs}ms` }}
                    onAnimationEnd={(event) => event.target === event.currentTarget && dispatch({ type: "sceneEnded" })}
                  />
                ) : (
                  <span className={cn("block h-full bg-accent", index < state.index || state.ended ? "w-full" : "w-0")} />
                )}
              </span>
            ))}
          </div>
          <div className="flex items-center justify-between font-mono text-[length:max(0.62rem,0.95cqw)] font-semibold tracking-[0.2em] text-ink-muted uppercase">
            <span>EIDOS · how it works</span>
            <span>
              {pad(state.index + 1)} / {pad(SCENES.length)}
            </span>
          </div>
        </div>

        {/* every part is laid out in the same cell, so the frame is as tall as its tallest part and never jumps; only the current one is visible */}
        <div className="relative grid flex-1">
          {SCENES.map((item, index) => {
            const current = index === state.index;
            return (
              <div
                key={current ? `${index}-${state.run}` : index}
                aria-hidden={current ? undefined : true}
                inert={!current}
                data-testid={current ? "scene-current" : undefined}
                className={cn(
                  "relative grid content-center items-center gap-[max(1.5rem,3cqw)] px-[max(1.25rem,4cqw)] py-[max(1.25rem,3cqw)] [grid-area:1/1] @3xl:grid-cols-[1.05fr_1fr]",
                  !current && "hiw-still invisible",
                )}
              >
                <SceneWords scene={item} index={index} />
                <div className="relative z-10 flex items-center justify-center @3xl:justify-end">
                  <SceneVisual id={item.id} />
                </div>
                <span
                  aria-hidden="true"
                  className="hiw-fade pointer-events-none absolute right-[-1cqw] bottom-[-5cqw] font-display text-[length:30cqw] leading-none text-transparent opacity-[0.08] select-none [-webkit-text-stroke:2px_var(--color-ink)]"
                >
                  {pad(index + 1)}
                </span>
              </div>
            );
          })}
        </div>

        {/* the ticker band */}
        <div aria-hidden="true" className="relative z-10 mt-auto overflow-hidden border-t-2 border-ink bg-accent py-[max(0.4rem,0.7cqw)]">
          <div className="hiw-marquee flex w-max">
            {[0, 1].map((copy) => (
              <span key={copy} className="flex shrink-0 items-center font-mono text-[length:max(0.66rem,1cqw)] font-semibold tracking-[0.18em] whitespace-nowrap text-on-accent uppercase">
                {[...TICKER, ...TICKER].map((word, index) => (
                  <span key={index} className="flex items-center gap-4 px-2">
                    {word}
                    <span>✦</span>
                  </span>
                ))}
              </span>
            ))}
          </div>
        </div>

        {!reduced && !playing && !state.ended && (
          <button
            type="button"
            onClick={toggle}
            aria-label={state.animated ? "Resume the video" : `Play the video (${length})`}
            className="absolute right-[max(1rem,3cqw)] bottom-[max(3.25rem,5.5cqw)] z-20 flex items-center gap-2 rounded-full border-2 border-ink bg-accent py-1.5 pr-4 pl-1.5 font-mono text-xs font-semibold tracking-wider text-on-accent uppercase shadow-[3px_3px_0_var(--color-ink)] transition-transform hover:-translate-y-0.5"
          >
            <span className="flex h-9 w-9 items-center justify-center rounded-full bg-ink text-surface">
              <PlayIcon />
            </span>
            {state.animated ? "resume" : `play · ${length}`}
          </button>
        )}

        {state.ended && (
          <div className="absolute inset-0 z-30 flex flex-col items-center justify-center gap-5 bg-surface/95 p-6 text-center">
            <p className="font-display text-[length:max(2.2rem,5.4cqw)] leading-none text-ink">
              that’s <em>EIDOS</em>.
            </p>
            <p className="max-w-[40ch] text-sm leading-relaxed text-ink-muted">Ask a question, get an answer you can check.</p>
            <div className="flex flex-wrap items-center justify-center gap-3">
              <Link href={ctaHref} className={buttonClassName("primary")}>
                {ctaLabel}
              </Link>
              <button type="button" onClick={() => dispatch({ type: "play", by: "viewer" })} className={buttonClassName("secondary")}>
                ↺ Watch again
              </button>
            </div>
          </div>
        )}
      </div>

      {/* controls */}
      <div className="flex flex-wrap items-center gap-2.5">
        {!reduced && (
          <button
            type="button"
            onClick={state.ended ? () => dispatch({ type: "play", by: "viewer" }) : toggle}
            aria-label={playing ? "Pause the video" : state.ended ? "Watch again" : "Play the video"}
            className="flex h-11 w-11 items-center justify-center rounded-full border-2 border-ink bg-accent text-on-accent shadow-[2px_2px_0_var(--color-ink)] transition-transform hover:-translate-y-0.5"
          >
            {playing ? <PauseIcon /> : <PlayIcon />}
          </button>
        )}
        <button
          type="button"
          onClick={() => go(state.index - 1)}
          disabled={state.index === 0}
          aria-label="Previous part"
          className="flex h-11 w-11 items-center justify-center rounded-full border-2 border-ink text-lg text-ink transition-colors hover:bg-surface-raised disabled:cursor-not-allowed disabled:opacity-35"
        >
          ‹
        </button>
        <button
          type="button"
          onClick={() => go(state.index + 1)}
          disabled={state.index === LAST}
          aria-label="Next part"
          className="flex h-11 w-11 items-center justify-center rounded-full border-2 border-ink text-lg text-ink transition-colors hover:bg-surface-raised disabled:cursor-not-allowed disabled:opacity-35"
        >
          ›
        </button>
        <p aria-live={playing ? "off" : "polite"} className="font-mono text-xs text-ink-muted">
          Part {state.index + 1} of {SCENES.length} — {scene.chapter}
        </p>
        <p className="ml-auto hidden text-xs text-ink-muted sm:block">
          {reduced ? "Autoplay is off because your device asks for less motion. Use the arrows." : "Click the video or press space to pause · ← → to move"}
        </p>
      </div>

      <ol aria-label="Parts of the video" className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
        {SCENES.map((item, index) => (
          <li key={item.id}>
            <button
              type="button"
              onClick={() => go(index)}
              aria-current={index === state.index ? "step" : undefined}
              className={cn(
                "flex w-full items-baseline gap-2 rounded-xl border-2 px-3 py-2.5 text-left transition-colors",
                index === state.index ? "border-ink bg-accent text-on-accent shadow-[2px_2px_0_var(--color-ink)]" : "border-border-strong text-ink-muted hover:border-ink hover:text-ink",
              )}
            >
              <span className="font-mono text-xs">{pad(index + 1)}</span>
              <span className="text-sm font-medium">{item.chapter}</span>
            </button>
          </li>
        ))}
      </ol>

      <details className="group rounded-xl border border-border-strong px-4 py-3">
        <summary className="cursor-pointer text-sm font-medium text-ink-muted select-none hover:text-ink">Read it instead</summary>
        <ol className="mt-3 flex flex-col gap-3" data-testid="transcript">
          {SCENES.map((item, index) => (
            <li key={item.id}>
              <p className="font-display text-lg text-ink">
                {pad(index + 1)} — {item.headline}
              </p>
              <p className="text-sm leading-relaxed text-ink-muted">{item.caption}</p>
              {item.aside && <p className="mt-1 font-mono text-xs text-ink-muted">{item.aside}</p>}
            </li>
          ))}
        </ol>
      </details>
    </div>
  );
}

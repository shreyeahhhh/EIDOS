"use client";

import { cn } from "@/lib/cn";
import { formatOffset, type Moment } from "@/lib/run-model";
import type { Tone } from "@/lib/status";

const TICK_TONE: Record<Tone, string> = {
  neutral: "bg-ink-faint/60",
  info: "bg-info",
  success: "bg-success",
  warning: "bg-warning",
  error: "bg-error",
};

interface FilmstripProps {
  moments: Moment[];
  /** The moment being shown (an index into `moments`). */
  cursor: number;
  onScrub: (index: number) => void;
  playing: boolean;
  onTogglePlay: () => void;
  /** The run is still going and the view is following its newest moment. */
  live: boolean;
  /** The run is still going, but the viewer has moved away from its newest moment. */
  canGoLive: boolean;
  onGoLive: () => void;
}

/**
 * The run as a strip you can play or drag through: one tick per recorded event, coloured by what happened, with a taller mark where a new plan
 * began. Moving along it changes the whole cockpit to how things stood at that moment, and the sentence below always says what that moment was.
 * Everything here comes from the recorded events; "playing" only steps through them at a readable pace.
 */
export function Filmstrip({ moments, cursor, onScrub, playing, onTogglePlay, live, canGoLive, onGoLive }: FilmstripProps) {
  if (moments.length === 0) return null;
  const last = moments.length - 1;
  const current = moments[Math.min(Math.max(cursor, 0), last)];
  const position = (index: number) => (last === 0 ? 50 : (index / last) * 100);

  return (
    <div className="flex flex-col gap-3 rounded-lg border border-border bg-surface-raised p-3 sm:p-4">
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={onTogglePlay}
          aria-label={playing ? "Pause the replay" : "Play the replay"}
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-accent text-on-accent transition-colors hover:bg-accent-hover"
        >
          {playing ? (
            <svg aria-hidden="true" viewBox="0 0 24 24" className="h-4 w-4" fill="currentColor"><path d="M7 5h4v14H7zM13 5h4v14h-4z" /></svg>
          ) : (
            <svg aria-hidden="true" viewBox="0 0 24 24" className="h-4 w-4" fill="currentColor"><path d="M8 5v14l11-7z" /></svg>
          )}
        </button>

        <div className="relative min-w-0 flex-1 pt-3 pb-1">
          <div aria-hidden="true" className="pointer-events-none absolute inset-x-0 top-0 h-3">
            {moments.map((moment) => (
              <span
                key={moment.index}
                className={cn("absolute bottom-0 w-0.5 -translate-x-1/2 rounded-full", TICK_TONE[moment.tone], moment.kind === "plan" ? "h-3" : "h-1.5", moment.index === cursor && "w-1")}
                style={{ left: `${position(moment.index)}%` }}
              />
            ))}
          </div>
          <input
            type="range"
            min={0}
            max={last}
            step={1}
            value={Math.min(Math.max(cursor, 0), last)}
            onChange={(event) => onScrub(Number(event.target.value))}
            aria-label="Replay position"
            aria-valuetext={`Moment ${current.index + 1} of ${moments.length}: ${current.text}`}
            className="h-6 w-full cursor-pointer accent-[var(--color-accent)]"
          />
        </div>

        {live ? (
          <span className="flex shrink-0 items-center gap-1.5 text-xs font-medium text-info">
            <span aria-hidden="true" className="h-2 w-2 animate-pulse rounded-full bg-info" />
            Live
          </span>
        ) : canGoLive ? (
          <button type="button" onClick={onGoLive} className="shrink-0 rounded-md border border-border px-2.5 py-1 text-xs font-medium text-ink-muted transition-colors hover:border-border-strong hover:text-ink">
            Jump to live
          </button>
        ) : null}
      </div>

      <p role="status" aria-live="polite" data-testid="replay-caption" className="flex flex-wrap items-baseline gap-x-3 text-sm text-ink">
        <span className="font-mono text-xs text-ink-faint">{formatOffset(current.offsetMs)}</span>
        <span>{current.text}</span>
      </p>
    </div>
  );
}

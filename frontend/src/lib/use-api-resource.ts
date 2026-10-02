"use client";

import { useEffect, useState } from "react";

import { ApiError } from "./api/errors";

export type ApiResourceState<T> =
  | { status: "loading" }
  | { status: "not_ready"; code: string }
  | { status: "error"; error: ApiError | Error }
  | { status: "ready"; data: T };

/**
 * Fetches one backend resource and exposes its state as one of exactly four things: loading, not yet
 * ready (a documented 409 like `no_events`/`not_finished` — not an error, just "ask again later"),
 * an error, or the real data. `notReadyCodes` names which `ApiError.code`s mean "not ready" rather
 * than "failed"; everything else becomes `error`. Re-fetches whenever `enabled` becomes true or `key` changes.
 *
 * A change of `key` refreshes in the background: what was already shown stays on screen until the new answer
 * arrives, so a page that updates as a run progresses does not blank out into placeholders on every event. Only
 * `enabled` flipping or an explicit `reload()` goes back to "loading" — those mean "this is a different request".
 */
export function useApiResource<T>(
  fetcher: () => Promise<T>,
  { enabled = true, key, notReadyCodes = [] }: { enabled?: boolean; key?: unknown; notReadyCodes?: string[] } = {},
): ApiResourceState<T> & { reload: () => void } {
  const [state, setState] = useState<ApiResourceState<T>>({ status: "loading" });
  const [reloadToken, setReloadToken] = useState(0);

  // Resetting to "loading" the instant `enabled` flips or a reload is asked for is a render-time
  // adjustment, not an effect: computing it here (React's own pattern for "state that resets when a prop
  // changes") avoids an extra render pass and a synchronous setState inside the effect below. A change of
  // `key` alone is not a reset: it only re-runs the fetch (`identity` below) and the old answer stays.
  const resetIdentity = JSON.stringify([enabled, reloadToken]);
  const [trackedResetIdentity, setTrackedResetIdentity] = useState(resetIdentity);
  if (resetIdentity !== trackedResetIdentity) {
    setTrackedResetIdentity(resetIdentity);
    setState({ status: "loading" });
  }
  const identity = JSON.stringify([enabled, key, reloadToken]);

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;

    fetcher()
      .then((data) => {
        if (!cancelled) setState({ status: "ready", data });
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        if (error instanceof ApiError && notReadyCodes.includes(error.code)) {
          setState({ status: "not_ready", code: error.code });
        } else if (error instanceof Error) {
          setState({ status: "error", error });
        } else {
          setState({ status: "error", error: new Error("Something unexpected went wrong.") });
        }
      });

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `identity` (enabled/key/reloadToken) is the real dependency; `fetcher` and `notReadyCodes` are expected to be fresh each render
  }, [identity]);

  return { ...state, reload: () => setReloadToken((token) => token + 1) };
}

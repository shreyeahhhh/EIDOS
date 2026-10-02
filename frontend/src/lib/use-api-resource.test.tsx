import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ApiError } from "./api/errors";
import { useApiResource } from "./use-api-resource";

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

describe("useApiResource", () => {
  it("goes loading, then ready with the data", async () => {
    const { result } = renderHook(() => useApiResource(() => Promise.resolve("a")));
    expect(result.current.status).toBe("loading");
    await waitFor(() => expect(result.current.status).toBe("ready"));
    expect(result.current).toMatchObject({ status: "ready", data: "a" });
  });

  it("keeps showing the previous answer while a changed key refreshes it, then shows the new one", async () => {
    const second = deferred<string>();
    const answers: Promise<string>[] = [Promise.resolve("first"), second.promise];
    const { result, rerender } = renderHook(({ key }) => useApiResource(() => answers[key], { key }), { initialProps: { key: 0 } });
    await waitFor(() => expect(result.current).toMatchObject({ status: "ready", data: "first" }));

    rerender({ key: 1 });
    expect(result.current).toMatchObject({ status: "ready", data: "first" }); // not "loading": no blank-out between events

    await act(async () => second.resolve("second"));
    await waitFor(() => expect(result.current).toMatchObject({ status: "ready", data: "second" }));
  });

  it("ignores an older answer that arrives after a newer one was asked for", async () => {
    const slow = deferred<string>();
    const answers: Promise<string>[] = [slow.promise, Promise.resolve("new")];
    const { result, rerender } = renderHook(({ key }) => useApiResource(() => answers[key], { key }), { initialProps: { key: 0 } });
    rerender({ key: 1 });
    await waitFor(() => expect(result.current).toMatchObject({ status: "ready", data: "new" }));
    await act(async () => slow.resolve("old"));
    expect(result.current).toMatchObject({ status: "ready", data: "new" });
  });

  it("goes back to loading when it is enabled afresh, and does not fetch while disabled", async () => {
    let calls = 0;
    const fetcher = () => {
      calls += 1;
      return Promise.resolve("x");
    };
    const { result, rerender } = renderHook(({ enabled }) => useApiResource(fetcher, { enabled }), { initialProps: { enabled: false } });
    expect(result.current.status).toBe("loading");
    expect(calls).toBe(0);
    rerender({ enabled: true });
    await waitFor(() => expect(result.current.status).toBe("ready"));
    expect(calls).toBe(1);
  });

  it("an explicit reload goes back to loading and fetches again", async () => {
    let calls = 0;
    const { result } = renderHook(() => useApiResource(() => Promise.resolve(++calls)));
    await waitFor(() => expect(result.current.status).toBe("ready"));
    act(() => result.current.reload());
    expect(result.current.status).toBe("loading");
    await waitFor(() => expect(result.current).toMatchObject({ status: "ready", data: 2 }));
  });

  it("reads a documented not-ready code as not_ready, and anything else as an error", async () => {
    const notReady = renderHook(() =>
      useApiResource(() => Promise.reject(new ApiError(409, { code: "not_finished", message: "not finished" })), { notReadyCodes: ["not_finished"] }),
    );
    await waitFor(() => expect(notReady.result.current).toMatchObject({ status: "not_ready", code: "not_finished" }));
    const failed = renderHook(() =>
      useApiResource(() => Promise.reject(new ApiError(503, { code: "storage_unavailable", message: "down" })), { notReadyCodes: ["not_finished"] }),
    );
    await waitFor(() => expect(failed.result.current.status).toBe("error"));
  });
});

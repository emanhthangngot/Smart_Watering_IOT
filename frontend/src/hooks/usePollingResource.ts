import { useCallback, useEffect, useState } from "react";
import type { AsyncStatus } from "../api/types";

export interface PollingResource<T> {
  status: AsyncStatus;
  data?: T;
  error?: Error;
  lastUpdated?: Date;
  refresh: () => void;
}

export function usePollingResource<T>(
  loader: (signal: AbortSignal) => Promise<T>,
  intervalMs = 5_000,
): PollingResource<T> {
  const [refreshKey, setRefreshKey] = useState(0);
  const [state, setState] = useState<Omit<PollingResource<T>, "refresh">>({
    status: "idle",
  });
  const refresh = useCallback(() => setRefreshKey((key) => key + 1), []);

  useEffect(() => {
    let mounted = true;
    let running = false;
    let controller: AbortController | undefined;

    const load = async () => {
      if (running) return;
      running = true;
      controller = new AbortController();
      setState((current) => ({
        ...current,
        status: current.data === undefined ? "loading" : current.status,
        error: undefined,
      }));
      try {
        const data = await loader(controller.signal);
        if (mounted) setState({ status: "success", data, lastUpdated: new Date() });
      } catch (error) {
        if (mounted && !(error instanceof DOMException && error.name === "AbortError")) {
          setState((current) => ({
            ...current,
            status: "error",
            error: error instanceof Error ? error : new Error("Lỗi không xác định"),
          }));
        }
      } finally {
        running = false;
      }
    };

    void load();
    const timer = window.setInterval(() => void load(), intervalMs);
    return () => {
      mounted = false;
      controller?.abort();
      window.clearInterval(timer);
    };
  }, [intervalMs, loader, refreshKey]);

  return { ...state, refresh };
}

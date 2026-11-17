"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { api, ApiError } from "./api";

export type Resource<T> = {
  data: T | undefined;
  error: ApiError | Error | undefined;
  loading: boolean;
  reload: () => Promise<void>;
  setData: (d: T) => void;
};

/**
 * Minimal GET hook with explicit loading / error / data states. `path === null` skips the request.
 * `loading` is true until a response for the CURRENT path has arrived, so a path change can never
 * produce a render with loading=false and no data (which callers would treat as loaded).
 */
export function useApi<T>(path: string | null): Resource<T> {
  const [data, setDataState] = useState<T>();
  const [error, setError] = useState<ApiError | Error>();
  const [inFlight, setInFlight] = useState(false);
  const [settledPath, setSettledPath] = useState<string | null>(null);
  const seq = useRef(0);

  const load = useCallback(async () => {
    if (path === null) return;
    const id = ++seq.current;
    setInFlight(true);
    setError(undefined);
    try {
      const d = await api<T>("GET", path);
      if (id === seq.current) setDataState(d);
    } catch (e) {
      if (id === seq.current) setError(e as Error);
    } finally {
      if (id === seq.current) {
        setInFlight(false);
        setSettledPath(path);
      }
    }
  }, [path]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- data fetching on mount/path change
    void load();
  }, [load]);

  const setData = useCallback((d: T) => setDataState(d), []);
  const loading = path !== null && (inFlight || settledPath !== path);
  return { data, error, loading, reload: load, setData };
}

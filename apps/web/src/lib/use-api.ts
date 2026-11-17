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

/** Minimal GET hook with explicit loading / error / data states. `path === null` skips the request. */
export function useApi<T>(path: string | null): Resource<T> {
  const [data, setData] = useState<T>();
  const [error, setError] = useState<ApiError | Error>();
  const [loading, setLoading] = useState<boolean>(path !== null);
  const seq = useRef(0);

  const load = useCallback(async () => {
    if (path === null) return;
    const id = ++seq.current;
    setLoading(true);
    setError(undefined);
    try {
      const d = await api<T>("GET", path);
      if (id === seq.current) setData(d);
    } catch (e) {
      if (id === seq.current) setError(e as Error);
    } finally {
      if (id === seq.current) setLoading(false);
    }
  }, [path]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- data fetching on mount/path change
    void load();
  }, [load]);

  return { data, error, loading, reload: load, setData };
}

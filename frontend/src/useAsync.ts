import { useEffect, useState } from "react";

export interface AsyncState<T> { data: T | null; error: unknown; loading: boolean }

/** Run `fn` whenever `deps` change; stale responses from an earlier dependency set are ignored. */
export function useAsync<T>(fn: () => Promise<T>, deps: unknown[]): AsyncState<T> {
  const [state, setState] = useState<AsyncState<T>>({ data: null, error: null, loading: true });
  useEffect(() => {
    let cancelled = false;
    setState((s) => ({ ...s, loading: true, error: null }));
    fn().then(
      (data) => { if (!cancelled) setState({ data, error: null, loading: false }); },
      (error) => { if (!cancelled) setState({ data: null, error, loading: false }); },
    );
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return state;
}

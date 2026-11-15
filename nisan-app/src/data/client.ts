/**
 * Stale-while-revalidate data layer: TanStack Query core with an IndexedDB persister.
 * `swr` hands back what we already have immediately (memory, then disk) and
 * refreshes in the background, calling back again when fresh data lands.
 */
import { QueryClient, type QueryKey } from "@tanstack/query-core";
import { persistQueryClient, type PersistedClient, type Persister } from "@tanstack/query-persist-client-core";
import { del, get, set } from "idb-keyval";

const KEY = "nisan-query-cache-v1";

export const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 60_000, gcTime: 7 * 24 * 3600_000, retry: 1, refetchOnWindowFocus: false } },
});

const persister: Persister = {
  persistClient: async (c: PersistedClient) => { try { await set(KEY, c); } catch { /* private mode / quota */ } },
  restoreClient: async () => { try { return await get<PersistedClient>(KEY); } catch { return undefined; } },
  removeClient: async () => { try { await del(KEY); } catch { /* ignore */ } },
};

let restored: Promise<void> | null = null;
/** Bring the last session's data back from disk (resolves quickly; never rejects). */
export function restoreCache(): Promise<void> {
  restored ??= new Promise<void>((done) => {
    const [, promise] = persistQueryClient({ queryClient, persister, maxAge: 7 * 24 * 3600_000, buster: "2" });
    promise.then(() => done(), () => done());
  });
  return restored;
}

export interface SwrOptions<T> {
  key: QueryKey;
  fetcher: (signal: AbortSignal) => Promise<T>;
  staleTime?: number;
  /** Called with cached data first (if any, flagged stale) and again with fresh data. */
  onData: (data: T, meta: { fromCache: boolean; updatedAt: number }) => void;
  onError?: (e: unknown) => void;
}

export function swr<T>(o: SwrOptions<T>): Promise<void> {
  const cached = queryClient.getQueryState<T>(o.key);
  if (cached?.data !== undefined) o.onData(cached.data as T, { fromCache: true, updatedAt: cached.dataUpdatedAt });
  return queryClient
    .fetchQuery({ queryKey: o.key, queryFn: ({ signal }) => o.fetcher(signal), staleTime: o.staleTime ?? 60_000 })
    .then((d) => {
      const st = queryClient.getQueryState<T>(o.key);
      o.onData(d, { fromCache: false, updatedAt: st?.dataUpdatedAt ?? Date.now() });
    })
    .catch((e) => o.onError?.(e));
}

/** Run when the browser is idle so background loads never compete with first paint. */
export function whenIdle(fn: () => void, timeout = 1500): void {
  const w = window as unknown as { requestIdleCallback?: (f: () => void, o?: { timeout: number }) => void };
  if (w.requestIdleCallback) w.requestIdleCallback(fn, { timeout });
  else setTimeout(fn, 50);
}

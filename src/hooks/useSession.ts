/**
 * useSession – React hook that bootstraps the session on app mount.
 *
 * Returns { sessionId, loading, error }. While loading is true, child
 * components should show a loading state or skip API calls.
 *
 * Used by BalancePositionsCardConnected to get the current session_id
 * before making any balance/curves API calls.
 */

import { useEffect, useState } from "react";
import { getOrCreateSessionId } from "../lib/session";

export function useSession() {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    let cancelled = false;

    (async () => {
      try {
        const id = await getOrCreateSessionId();
        if (!cancelled) setSessionId(id);
      } catch (e) {
        if (!cancelled) setError(e as Error);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, []);

  return { sessionId, loading, error };
}

"use client";

import { useState, useEffect } from "react";
import { useAuth } from "@clerk/nextjs";
import { getStats, sseUserEventsUrl } from "@/lib/api";
import type { Stats } from "@/lib/types";

/**
 * Subscribe to the user's stats. SSE is the source of truth — a `stats_changed`
 * event triggers a re-fetch. We keep an *optional* visibility-gated fallback
 * interval (`fallbackMs`) for the rare case where SSE drops silently; pass `0`
 * to disable it entirely. The interval pauses while the tab is hidden so we
 * don't burn quota on unfocused tabs.
 */
export function useStats(fallbackMs = 0) {
  const [stats, setStats] = useState<Stats | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { getToken } = useAuth();

  useEffect(() => {
    let active = true;
    let es: EventSource | null = null;
    let fallbackId: ReturnType<typeof setInterval> | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

    const fetchStats = () =>
      getStats()
        .then((s) => { if (active) setStats(s); })
        .catch((e) => { if (active) setError(String(e)); });

    // Initial fetch
    fetchStats();

    // Connect to the per-user SSE event bus
    const connect = () => {
      getToken().then((token) => {
        if (!active || !token) return;
        const url = `${sseUserEventsUrl()}?token=${encodeURIComponent(token)}`;
        es = new EventSource(url);

        es.addEventListener("stats_changed", () => {
          if (active) fetchStats();
        });

        es.onerror = () => {
          es?.close();
          es = null;
          // Back off 5s then reconnect
          if (active) reconnectTimer = setTimeout(connect, 5_000);
        };
      }).catch(() => {
        // Token unavailable — SSE skipped
      });
    };
    connect();

    // Optional fallback — only when fallbackMs > 0, and only while the tab is
    // visible. Pause/resume with `visibilitychange` so background tabs idle.
    const startInterval = () => {
      if (fallbackId != null || fallbackMs <= 0) return;
      fallbackId = setInterval(fetchStats, fallbackMs);
    };
    const stopInterval = () => {
      if (fallbackId != null) {
        clearInterval(fallbackId);
        fallbackId = null;
      }
    };
    const onVisibilityChange = () => {
      if (document.visibilityState === "visible") startInterval();
      else stopInterval();
    };
    if (fallbackMs > 0) {
      if (typeof document !== "undefined" && document.visibilityState === "visible") {
        startInterval();
      }
      document.addEventListener("visibilitychange", onVisibilityChange);
    }

    return () => {
      active = false;
      es?.close();
      stopInterval();
      if (reconnectTimer != null) clearTimeout(reconnectTimer);
      if (fallbackMs > 0) {
        document.removeEventListener("visibilitychange", onVisibilityChange);
      }
    };
  }, [getToken, fallbackMs]);

  return { stats, error };
}

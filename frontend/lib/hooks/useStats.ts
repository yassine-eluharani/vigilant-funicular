"use client";

import { useState, useEffect } from "react";
import { useAuth } from "@clerk/nextjs";
import { getStats, sseUserEventsUrl } from "@/lib/api";
import type { Stats } from "@/lib/types";

export function useStats(fallbackMs = 60_000) {
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
        es = new EventSource(sseUserEventsUrl(token));

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
        // Token unavailable — SSE skipped, fallback polling still runs
      });
    };
    connect();

    // Fallback interval — keeps stats fresh if SSE drops or is slow
    fallbackId = setInterval(fetchStats, fallbackMs);

    return () => {
      active = false;
      es?.close();
      if (fallbackId != null) clearInterval(fallbackId);
      if (reconnectTimer != null) clearTimeout(reconnectTimer);
    };
  }, [getToken, fallbackMs]);

  return { stats, error };
}

"use client";

import { useState, useEffect } from "react";
import { getStats } from "@/lib/api";
import type { Stats } from "@/lib/types";

export function useStats(intervalMs = 10_000) {
  const [stats, setStats] = useState<Stats | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;

    const fetch = () =>
      getStats()
        .then((s) => { if (active) setStats(s); })
        .catch((e) => { if (active) setError(String(e)); });

    fetch();
    const id = setInterval(fetch, intervalMs);
    return () => { active = false; clearInterval(id); };
  }, [intervalMs]);

  return { stats, error };
}

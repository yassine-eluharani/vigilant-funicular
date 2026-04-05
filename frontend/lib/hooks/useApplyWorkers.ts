"use client";

import { useState, useEffect, useRef } from "react";
import { getApplyStatus, sseApplyUrl } from "@/lib/api";
import type { ApplyStatus } from "@/lib/types";

export function useApplyWorkers() {
  const [data, setData] = useState<ApplyStatus | null>(null);
  const esRef = useRef<EventSource | null>(null);

  // Initial fetch
  useEffect(() => {
    getApplyStatus().then(setData).catch(() => {});
  }, []);

  // SSE stream
  useEffect(() => {
    const es = new EventSource(sseApplyUrl());
    esRef.current = es;

    es.onmessage = (e) => {
      try {
        const payload = JSON.parse(e.data) as ApplyStatus;
        setData(payload);
      } catch {}
    };

    es.onerror = () => {
      // Reconnect silently — EventSource handles this automatically
    };

    return () => {
      es.close();
      esRef.current = null;
    };
  }, []);

  return data;
}

"use client";

import { useState, useEffect, useRef } from "react";

export function useSSE(url: string | null) {
  const [lines, setLines] = useState<string[]>([]);
  const [status, setStatus] = useState<"idle" | "connecting" | "streaming" | "done" | "error">("idle");
  const esRef = useRef<EventSource | null>(null);

  useEffect(() => {
    if (!url) {
      setLines([]);
      setStatus("idle");
      return;
    }

    setLines([]);
    setStatus("connecting");

    const es = new EventSource(url);
    esRef.current = es;

    es.onopen = () => setStatus("streaming");

    es.onmessage = (e) => {
      setLines((prev) => [...prev, e.data]);
    };

    es.addEventListener("status", (e) => {
      setStatus((e as MessageEvent).data === "done" ? "done" : "error");
      es.close();
    });

    es.onerror = () => {
      setStatus("error");
      es.close();
    };

    return () => {
      es.close();
      esRef.current = null;
    };
  }, [url]);

  const reset = () => {
    esRef.current?.close();
    setLines([]);
    setStatus("idle");
  };

  return { lines, status, reset };
}

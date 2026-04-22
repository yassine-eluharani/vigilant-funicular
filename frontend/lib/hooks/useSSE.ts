"use client";

import { useState, useEffect, useRef } from "react";

export function useSSE(url: string | null, token?: string | null) {
  const [lines, setLines] = useState<string[]>([]);
  const [status, setStatus] = useState<"idle" | "connecting" | "streaming" | "done" | "error">("idle");
  const esRef = useRef<EventSource | null>(null);

  useEffect(() => {
    if (!url || !token) {
      setLines([]);
      setStatus("idle");
      return;
    }

    setLines([]);
    setStatus("connecting");

    // EventSource can't send Authorization headers — pass token as query param
    const urlWithToken = `${url}${url.includes("?") ? "&" : "?"}token=${encodeURIComponent(token)}`;
    const es = new EventSource(urlWithToken);
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
  }, [url, token]);

  const reset = () => {
    esRef.current?.close();
    setLines([]);
    setStatus("idle");
  };

  return { lines, status, reset };
}

"use client";

import { useCallback } from "react";
import { useAuth } from "@clerk/nextjs";
import { getTask, sseTaskUrl } from "@/lib/api";

async function pollUntilDone(taskId: string): Promise<void> {
  for (let i = 0; i < 120; i++) {
    await new Promise((r) => setTimeout(r, 1500));
    const task = await getTask(taskId);
    if (task.status === "done") return;
    if (task.status === "error") throw new Error(task.error ?? "Task failed");
  }
  throw new Error("Task timed out");
}

/**
 * Returns a `waitForTask(taskId)` function that resolves when a background
 * task completes. Uses SSE for instant delivery; falls back to polling if
 * SSE is unavailable.
 */
export function useTaskProgress() {
  const { getToken } = useAuth();

  const waitForTask = useCallback(async (taskId: string): Promise<void> => {
    const token = await getToken().catch(() => null);
    if (!token) return pollUntilDone(taskId);

    return new Promise((resolve, reject) => {
      const url = `${sseTaskUrl(taskId)}?token=${encodeURIComponent(token)}`;
      const es = new EventSource(url);

      es.addEventListener("status", (e) => {
        const st = (e as MessageEvent).data;
        es.close();
        if (st === "done") resolve();
        else reject(new Error(`Task ended with status: ${st}`));
      });

      es.onerror = () => {
        es.close();
        // Fall back to polling if SSE fails
        pollUntilDone(taskId).then(resolve).catch(reject);
      };
    });
  }, [getToken]);

  return { waitForTask };
}

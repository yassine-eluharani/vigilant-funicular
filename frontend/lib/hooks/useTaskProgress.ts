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

  // `getToken` is a stable reference from Clerk, so we don't include it in
  // the deps array — doing so would force consumers to re-create wrappers
  // on every render of an ancestor.
  const waitForTask = useCallback(async (taskId: string): Promise<void> => {
    const token = await getToken().catch(() => null);
    if (!token) return pollUntilDone(taskId);

    return new Promise((resolve, reject) => {
      const url = `${sseTaskUrl(taskId)}?token=${encodeURIComponent(token)}`;
      const es = new EventSource(url);
      let resolved = false;

      es.addEventListener("status", (e) => {
        const st = (e as MessageEvent).data;
        resolved = true;
        es.close();
        if (st === "done") resolve();
        else reject(new Error(`Task ended with status: ${st}`));
      });

      es.onerror = () => {
        // If we already received a terminal `status` event the connection
        // close that follows triggers `onerror`; ignore it — the work is
        // already done.
        if (resolved) return;
        es.close();
        // Fall back to polling if SSE genuinely failed before completion
        pollUntilDone(taskId).then(resolve).catch(reject);
      };
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return { waitForTask };
}

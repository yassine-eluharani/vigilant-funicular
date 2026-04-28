"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { getJobs } from "@/lib/api";
import type { Job, JobsResponse } from "@/lib/types";
import type { Filters } from "@/components/jobs/JobFilters";

const PAGE_SIZE = 30;

export function useJobs(filters: Filters) {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const offsetRef = useRef(0);
  // Track the in-flight request so rapid filter changes don't deliver stale
  // responses out-of-order. Each new fetch aborts the previous controller.
  const abortRef = useRef<AbortController | null>(null);
  const hasMore = jobs.length < total;

  const fetchJobs = useCallback(
    async (reset: boolean) => {
      const offset = reset ? 0 : offsetRef.current;
      if (reset) setLoading(true);
      else setLoadingMore(true);

      // Cancel any previous in-flight request
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;

      try {
        const data: JobsResponse = await getJobs(
          {
            min_score: filters.minScore,
            max_score: filters.maxScore,
            site: filters.site || undefined,
            search: filters.search || undefined,
            status: filters.status,
            offset,
            limit: PAGE_SIZE,
          },
          controller.signal,
        );
        if (controller.signal.aborted) return;
        setJobs((prev) => (reset ? data.jobs : [...prev, ...data.jobs]));
        setTotal(data.total);
        offsetRef.current = offset + data.jobs.length;
        setError(null);
      } catch (e) {
        // Swallow aborts — they're expected when filters change rapidly
        if (controller.signal.aborted) return;
        if (e instanceof DOMException && e.name === "AbortError") return;
        setError(String(e));
      } finally {
        if (!controller.signal.aborted) {
          setLoading(false);
          setLoadingMore(false);
        }
      }
    },
    [filters.minScore, filters.maxScore, filters.site, filters.search, filters.status]
  );

  // Reset on filter change
  useEffect(() => {
    offsetRef.current = 0;
    fetchJobs(true);
    // Clean up any in-flight request when the hook unmounts or filters change
    return () => abortRef.current?.abort();
  }, [fetchJobs]);

  const loadMore = useCallback(() => {
    if (!loadingMore && hasMore) fetchJobs(false);
  }, [loadingMore, hasMore, fetchJobs]);

  const refresh = useCallback(() => {
    offsetRef.current = 0;
    fetchJobs(true);
  }, [fetchJobs]);

  return { jobs, total, loading, loadingMore, error, hasMore, loadMore, refresh };
}

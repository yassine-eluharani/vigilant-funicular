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
  const hasMore = jobs.length < total;

  const fetchJobs = useCallback(
    async (reset: boolean) => {
      const offset = reset ? 0 : offsetRef.current;
      if (reset) setLoading(true);
      else setLoadingMore(true);

      try {
        const data: JobsResponse = await getJobs({
          min_score: filters.minScore,
          max_score: filters.maxScore,
          site: filters.site || undefined,
          search: filters.search || undefined,
          status: filters.status,
          offset,
          limit: PAGE_SIZE,
        });
        setJobs((prev) => (reset ? data.jobs : [...prev, ...data.jobs]));
        setTotal(data.total);
        offsetRef.current = offset + data.jobs.length;
        setError(null);
      } catch (e) {
        setError(String(e));
      } finally {
        setLoading(false);
        setLoadingMore(false);
      }
    },
    [filters.minScore, filters.maxScore, filters.site, filters.search, filters.status]
  );

  // Reset on filter change
  useEffect(() => {
    offsetRef.current = 0;
    fetchJobs(true);
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

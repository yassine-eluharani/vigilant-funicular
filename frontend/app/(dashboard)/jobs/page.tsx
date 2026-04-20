"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { JobCard } from "@/components/jobs/JobCard";
import { JobFilters, type Filters } from "@/components/jobs/JobFilters";
import { JobDetailDrawer } from "@/components/jobs/JobDetailDrawer";
import { useJobs } from "@/lib/hooks/useJobs";
import { useStats } from "@/lib/hooks/useStats";
import { dismissJob, markApplied, getMe, upgradeAccount, getSchedulerStatus, triggerScheduler } from "@/lib/api";
import { useToast } from "@/components/ui/Toast";
import type { Job, UserInfo } from "@/lib/types";

const DEFAULT_FILTERS: Filters = {
  minScore: 7,
  maxScore: 10,
  site: "",
  search: "",
  status: "pending",
};

// ── Upgrade Modal ─────────────────────────────────────────────────────────────

function UpgradeModal({
  lockedCount,
  userInfo,
  onClose,
  onUpgraded,
}: {
  lockedCount: number;
  userInfo: UserInfo | null;
  onClose: () => void;
  onUpgraded: () => void;
}) {
  const [loading, setLoading] = useState(false);

  const handleUpgrade = async () => {
    setLoading(true);
    try {
      await upgradeAccount();
      onUpgraded();
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
      <div className="w-full max-w-sm bg-void-surface border border-void-border rounded-2xl p-6 shadow-2xl animate-fade-in">
        {/* Icon */}
        <div className="w-12 h-12 rounded-xl bg-amber-500/15 border border-amber-500/30 flex items-center justify-center mb-4">
          <svg viewBox="0 0 24 24" fill="currentColor" className="w-6 h-6 text-amber-400">
            <path fillRule="evenodd" d="M12 1.5a5.25 5.25 0 0 0-5.25 5.25v3a3 3 0 0 0-3 3v6.75a3 3 0 0 0 3 3h10.5a3 3 0 0 0 3-3v-6.75a3 3 0 0 0-3-3v-3c0-2.9-2.35-5.25-5.25-5.25Zm3.75 8.25v-3a3.75 3.75 0 1 0-7.5 0v3h7.5Z" clipRule="evenodd" />
          </svg>
        </div>

        <h2 className="text-base font-semibold text-void-text mb-1">Unlock your best matches</h2>
        <p className="text-sm text-void-muted mb-5">
          {lockedCount > 0
            ? `${lockedCount} high-scoring job${lockedCount > 1 ? "s are" : " is"} hidden behind your free plan.`
            : "Upgrade to Pro for unlimited access."}
        </p>

        {/* Feature list */}
        <ul className="space-y-2 mb-6">
          {[
            "All high-match jobs fully visible",
            "Unlimited tailored resumes",
            "Unlimited cover letters",
            "PDF export",
          ].map((f) => (
            <li key={f} className="flex items-center gap-2 text-sm text-void-text">
              <svg viewBox="0 0 16 16" fill="currentColor" className="w-4 h-4 text-void-success shrink-0">
                <path d="M12.416 3.376a.75.75 0 0 1 .208 1.04l-5 7.5a.75.75 0 0 1-1.154.114l-3-3a.75.75 0 0 1 1.06-1.06l2.353 2.353 4.493-6.74a.75.75 0 0 1 1.04-.207Z" />
              </svg>
              {f}
            </li>
          ))}
        </ul>

        {/* Usage context */}
        {userInfo && userInfo.tier === "free" && userInfo.tailor_limit && (
          <div className="mb-5 p-3 rounded-lg bg-void-raised border border-void-border text-xs text-void-muted">
            <span className="text-void-text">{userInfo.tailors_used}/{userInfo.tailor_limit}</span> tailors used this month
            {" · "}
            <span className="text-void-text">{userInfo.covers_used}/{userInfo.cover_limit}</span> cover letters used
          </div>
        )}

        <button
          onClick={handleUpgrade}
          disabled={loading}
          className="w-full py-2.5 rounded-lg bg-amber-500 text-black text-sm font-semibold hover:bg-amber-400 disabled:opacity-40 transition-colors mb-2"
        >
          {loading ? "Upgrading…" : "Upgrade to Pro — $19/mo"}
        </button>
        <button
          onClick={onClose}
          className="w-full py-2 text-xs text-void-subtle hover:text-void-muted transition-colors"
        >
          Maybe later
        </button>
      </div>
    </div>
  );
}

function SkeletonCard() {
  return (
    <div className="bg-void-surface border border-void-border rounded-lg p-4 flex flex-col gap-3">
      <div className="flex gap-3">
        <div className="skeleton w-9 h-9 rounded-lg" />
        <div className="flex-1 space-y-2">
          <div className="skeleton h-4 w-3/4" />
          <div className="skeleton h-3 w-1/2" />
        </div>
        <div className="skeleton w-8 h-8 rounded-full" />
      </div>
      <div className="skeleton h-3 w-full" />
      <div className="skeleton h-3 w-2/3" />
      <div className="skeleton h-8 w-full rounded mt-1" />
    </div>
  );
}

export default function JobsPage() {
  const toast = useToast();
  const [filters, setFilters] = useState<Filters>(DEFAULT_FILTERS);
  const [selectedUrl, setSelectedUrl] = useState<string | null>(null);
  const [showUpgrade, setShowUpgrade] = useState(false);
  const [userInfo, setUserInfo] = useState<UserInfo | null>(null);
  const [syncInfo, setSyncInfo] = useState<{ last_sync: string | null; jobs_found: number } | null>(null);
  const [syncing, setSyncing] = useState(false);
  const { jobs, total, loading, loadingMore, hasMore, loadMore, refresh } = useJobs(filters);
  const { stats } = useStats();

  const lockedCount = jobs.filter((j) => j.locked).length;

  useEffect(() => {
    getMe().then(setUserInfo).catch(() => null);
    getSchedulerStatus().then(setSyncInfo).catch(() => null);
  }, []);

  const handleManualSync = useCallback(async () => {
    setSyncing(true);
    try {
      await triggerScheduler();
      toast("Background sync started — jobs will appear shortly");
      // Refresh sync info after a short delay
      setTimeout(() => getSchedulerStatus().then(setSyncInfo).catch(() => null), 3000);
    } catch {
      toast("Sync failed", false);
    } finally {
      setSyncing(false);
    }
  }, [toast]);

  const handleUpgraded = useCallback(() => {
    getMe().then(setUserInfo).catch(() => null);
    setShowUpgrade(false);
    refresh();
    toast("Upgraded to Pro! All jobs are now unlocked.");
  }, [refresh, toast]);

  // Infinite scroll sentinel
  const sentinelRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!sentinelRef.current) return;
    const observer = new IntersectionObserver(
      ([entry]) => { if (entry.isIntersecting) loadMore(); },
      { threshold: 0.1 }
    );
    observer.observe(sentinelRef.current);
    return () => observer.disconnect();
  }, [loadMore]);

  const handleDismiss = useCallback(async (job: Job) => {
    try {
      await dismissJob(job.url_encoded);
      toast("Job dismissed");
      refresh();
    } catch {
      toast("Failed to dismiss", false);
    }
  }, [toast, refresh]);

  const handleMarkApplied = useCallback(async (job: Job) => {
    try {
      await markApplied(job.url_encoded);
      toast("Marked as applied");
      refresh();
    } catch {
      toast("Failed to update status", false);
    }
  }, [toast, refresh]);

  return (
    <>
    {showUpgrade && (
      <UpgradeModal
        lockedCount={lockedCount}
        userInfo={userInfo}
        onClose={() => setShowUpgrade(false)}
        onUpgraded={handleUpgraded}
      />
    )}
    <div className="flex h-full">
      {/* Sidebar filters */}
      <aside className="w-56 shrink-0 border-r border-void-border bg-void-surface overflow-y-auto">
        {stats && (
          <div className="px-4 pt-4 pb-2 border-b border-void-border">
            <div className="grid grid-cols-2 gap-2">
              {[
                { label: "Tailored",  value: stats.tailored  },
                { label: "Applied",   value: stats.applied   },
                { label: "Ready",     value: stats.ready_to_apply },
                { label: "Dismissed", value: stats.dismissed },
              ].map(({ label, value }) => (
                <div key={label} className="bg-void-raised rounded-lg px-2 py-2 text-center border border-void-border">
                  <p className="text-lg font-semibold font-mono text-void-text">{value}</p>
                  <p className="text-xs text-void-muted">{label}</p>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Last synced indicator */}
        <div className="px-4 py-2.5 border-b border-void-border">
          <div className="flex items-center justify-between mb-1">
            <span className="text-xs text-void-subtle">Job pool</span>
            <button
              onClick={handleManualSync}
              disabled={syncing}
              title="Sync now"
              className="text-void-muted hover:text-void-accent disabled:opacity-40 transition-colors"
            >
              <svg viewBox="0 0 16 16" fill="currentColor" className={`w-3.5 h-3.5 ${syncing ? "animate-spin" : ""}`}>
                <path fillRule="evenodd" d="M8 3a5 5 0 1 0 4.546 2.914.5.5 0 0 1 .908-.417A6 6 0 1 1 8 2v1z"/>
                <path d="M8 4.466V.534a.25.25 0 0 1 .41-.192l2.36 1.966c.12.1.12.284 0 .384L8.41 4.658A.25.25 0 0 1 8 4.466z"/>
              </svg>
            </button>
          </div>
          {syncInfo?.last_sync ? (
            <p className="text-xs text-void-subtle">
              Synced <RelativeTime iso={syncInfo.last_sync} />
            </p>
          ) : (
            <p className="text-xs text-void-subtle">Never synced</p>
          )}
        </div>

        {/* Usage meters for free users */}
        {userInfo?.tier === "free" && userInfo.tailor_limit != null && (
          <div className="px-4 py-3 border-b border-void-border space-y-2.5">
            <UsageMeter label="Tailors" used={userInfo.tailors_used} limit={userInfo.tailor_limit} />
            <UsageMeter label="Cover letters" used={userInfo.covers_used} limit={userInfo.cover_limit ?? 1} />
            <button
              onClick={() => setShowUpgrade(true)}
              className="w-full mt-1 py-1.5 rounded-lg bg-amber-500/10 border border-amber-500/30 text-xs text-amber-300 hover:bg-amber-500/20 transition-colors"
            >
              Upgrade to Pro
            </button>
          </div>
        )}

        <JobFilters
          filters={filters}
          sites={stats?.sites ?? []}
          onChange={setFilters}
        />
      </aside>

      {/* Main content */}
      <div className="flex-1 min-w-0 flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-void-border shrink-0">
          <div>
            <h1 className="text-base font-semibold text-void-text">Jobs</h1>
            {!loading && (
              <p className="text-xs text-void-muted mt-0.5">
                {total} job{total !== 1 ? "s" : ""} · showing {jobs.length}
              </p>
            )}
          </div>
          {lockedCount > 0 && (
            <button
              onClick={() => setShowUpgrade(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-amber-500/10 border border-amber-500/30 text-xs text-amber-300 hover:bg-amber-500/20 transition-colors"
            >
              <svg viewBox="0 0 16 16" fill="currentColor" className="w-3.5 h-3.5">
                <path d="M8 1a3.5 3.5 0 0 0-3.5 3.5V6A1.5 1.5 0 0 0 3 7.5v5A1.5 1.5 0 0 0 4.5 14h7a1.5 1.5 0 0 0 1.5-1.5v-5A1.5 1.5 0 0 0 11.5 6V4.5A3.5 3.5 0 0 0 8 1Zm2.5 5V4.5a2.5 2.5 0 0 0-5 0V6h5Z" />
              </svg>
              {lockedCount} high-match job{lockedCount > 1 ? "s" : ""} locked · Upgrade
            </button>
          )}
          <button
            onClick={refresh}
            className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-void-border text-xs text-void-muted hover:text-void-text transition-colors"
          >
            <svg viewBox="0 0 16 16" fill="currentColor" className="w-3.5 h-3.5">
              <path fillRule="evenodd" d="M13.887 5.923a.5.5 0 0 1 .123.52l-1.5 4.5a.5.5 0 0 1-.88.143l-1.54-2.31-1.677 1.676a.5.5 0 0 1-.707 0L6.146 8.896 4.177 11.5a.5.5 0 0 1-.854-.354V8.5H2a.5.5 0 0 1-.5-.5V4a.5.5 0 0 1 .5-.5h3a.5.5 0 0 1 .5.5v1.793L7.146 4.146a.5.5 0 0 1 .708 0l1.56 1.56 1.677-1.676a.5.5 0 0 1 .52-.123l2.276.016Z" clipRule="evenodd"/>
            </svg>
            Refresh
          </button>
        </div>

        {/* Job grid */}
        <div className="flex-1 overflow-y-auto p-6">
          {loading ? (
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
              {Array.from({ length: 9 }).map((_, i) => <SkeletonCard key={i} />)}
            </div>
          ) : jobs.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-64 text-void-muted">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} className="w-12 h-12 mb-3 opacity-40">
                <path strokeLinecap="round" strokeLinejoin="round" d="m21 21-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5 7.5 0 0 0 10.607 10.607Z" />
              </svg>
              <p className="text-sm">No jobs match your filters</p>
              <button onClick={() => setFilters(DEFAULT_FILTERS)} className="text-xs text-void-accent mt-2 hover:underline">
                Reset filters
              </button>
            </div>
          ) : (
            <>
              <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
                {jobs.map((job) => (
                  <JobCard
                    key={job.url}
                    job={job}
                    onSelect={(j) => setSelectedUrl(j.url_encoded)}
                    onDismiss={handleDismiss}
                    onMarkApplied={handleMarkApplied}
                    onUpgrade={() => setShowUpgrade(true)}
                  />
                ))}
              </div>
              {hasMore && (
                <div ref={sentinelRef} className="py-6 flex justify-center">
                  {loadingMore && (
                    <div className="w-5 h-5 border-2 border-void-border border-t-void-accent rounded-full animate-spin-slow" />
                  )}
                </div>
              )}
            </>
          )}
        </div>
      </div>

      {/* Detail Drawer */}
      <JobDetailDrawer
        encodedUrl={selectedUrl}
        onClose={() => setSelectedUrl(null)}
        onJobUpdated={refresh}
      />
    </div>
    </>
  );
}

function RelativeTime({ iso }: { iso: string }) {
  const [label, setLabel] = useState("");
  useEffect(() => {
    const update = () => {
      const diff = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
      if (diff < 60) setLabel("just now");
      else if (diff < 3600) setLabel(`${Math.floor(diff / 60)}m ago`);
      else if (diff < 86400) setLabel(`${Math.floor(diff / 3600)}h ago`);
      else setLabel(`${Math.floor(diff / 86400)}d ago`);
    };
    update();
    const id = setInterval(update, 30_000);
    return () => clearInterval(id);
  }, [iso]);
  return <>{label}</>;
}

function UsageMeter({ label, used, limit }: { label: string; used: number; limit: number }) {
  const pct = Math.min(100, Math.round((used / limit) * 100));
  const isExhausted = used >= limit;
  return (
    <div>
      <div className="flex justify-between items-center mb-1">
        <span className="text-xs text-void-muted">{label}</span>
        <span className={`text-xs font-medium ${isExhausted ? "text-void-danger" : "text-void-text"}`}>
          {used}/{limit}
        </span>
      </div>
      <div className="h-1 rounded-full bg-void-raised overflow-hidden">
        <div
          className={`h-full rounded-full transition-all ${isExhausted ? "bg-void-danger" : "bg-void-accent"}`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

"use client";

import { Suspense, useState, useEffect, useRef, useCallback, useMemo } from "react";
import { useRouter, useSearchParams, usePathname } from "next/navigation";
import { JobCard } from "@/components/jobs/JobCard";
import { JobFilters, type Filters } from "@/components/jobs/JobFilters";
import { JobDetailDrawer } from "@/components/jobs/JobDetailDrawer";
import { ProWelcomeModal } from "@/components/jobs/ProWelcomeModal";
import { useJobs } from "@/lib/hooks/useJobs";
import { useStats } from "@/lib/hooks/useStats";
import { dismissJob, markApplied, getMe, createCheckoutSession, getSchedulerStatus, maybeScore } from "@/lib/api";
import { useToast } from "@/components/ui/Toast";
import type { Job, UserInfo } from "@/lib/types";

const DEFAULT_FILTERS: Filters = {
  minScore: 7,
  maxScore: 10,
  site: "",
  search: "",
  status: "pending",
};

const BROAD_FILTERS: Filters = {
  minScore: 1,
  maxScore: 10,
  site: "",
  search: "",
  status: "scored",
};

// Stable, deterministic-ish sparkbar heights so they don't reshuffle on
// every render. Seeded by the KPI label so each tile gets its own pattern.
function makeSparkbars(seed: string, len = 14): number[] {
  let h = 0;
  for (let i = 0; i < seed.length; i++) h = (h * 31 + seed.charCodeAt(i)) >>> 0;
  const out: number[] = [];
  for (let i = 0; i < len; i++) {
    h = (h * 1103515245 + 12345) >>> 0;
    // Bars range from 25% → 100% of the strip's height.
    out.push(25 + ((h >>> 16) % 75));
  }
  return out;
}

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
  const toast = useToast();
  const [loading, setLoading] = useState(false);

  const handleUpgrade = async () => {
    setLoading(true);
    try {
      const { checkout_url } = await createCheckoutSession();
      window.location.href = checkout_url;
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      toast(msg.includes("503") ? "Payments not configured — contact support." : "Upgrade failed. Please try again.", false);
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
  // Matches JobCard's shape: avatar + title block + score ring on top,
  // a 3-pill meta row, two reasoning lines, and a 2-button action row.
  return (
    <div className="bg-void-surface border border-void-border rounded-lg p-4 flex flex-col gap-3 animate-pulse">
      {/* Header: avatar / title / score ring */}
      <div className="flex items-start gap-3">
        <div className="w-9 h-9 rounded-lg bg-void-raised" />
        <div className="flex-1 space-y-2 pt-0.5">
          <div className="h-4 w-3/4 rounded bg-void-raised" />
          <div className="h-3 w-1/2 rounded bg-void-raised" />
        </div>
        {/* Circular score-ring placeholder, same footprint as <ScoreBadge size="sm" /> */}
        <div className="w-8 h-8 rounded-full bg-void-raised border-2 border-void-border" />
      </div>

      {/* Meta row: 3 small pills */}
      <div className="flex items-center gap-2">
        <div className="h-4 w-16 rounded bg-void-raised" />
        <div className="h-4 w-12 rounded bg-void-raised" />
        <div className="h-4 w-20 rounded bg-void-raised" />
      </div>

      {/* Reasoning preview: 2 lines */}
      <div className="space-y-1.5">
        <div className="h-3 w-full rounded bg-void-raised" />
        <div className="h-3 w-2/3 rounded bg-void-raised" />
      </div>

      {/* Action row: 2 button-shaped placeholders */}
      <div className="flex items-center gap-2 pt-2 border-t border-void-border">
        <div className="h-7 w-20 rounded bg-void-raised" />
        <div className="h-7 w-20 rounded bg-void-raised" />
      </div>
    </div>
  );
}

function JobsPanel() {
  const toast = useToast();
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const upgradedFlag = searchParams.get("upgraded") === "true";
  const [showProWelcome, setShowProWelcome] = useState(false);
  const [filters, setFilters] = useState<Filters>(DEFAULT_FILTERS);

  // Generic filter mutation handler. When the status switches *into* or
  // *out of* "scored" we tweak `minScore` so the user sees a useful slice by
  // default (1..10 for "scored", restored back to the default floor otherwise).
  const handleFiltersChange = useCallback((next: Filters) => {
    setFilters((prev) => {
      if (next.status !== prev.status) {
        if (next.status === "scored" && prev.status !== "scored") {
          return { ...next, minScore: 1 };
        }
        if (next.status !== "scored" && prev.status === "scored" && prev.minScore === 1) {
          return { ...next, minScore: DEFAULT_FILTERS.minScore };
        }
      }
      return next;
    });
  }, []);
  const [selectedUrl, setSelectedUrl] = useState<string | null>(null);
  const [showUpgrade, setShowUpgrade] = useState(false);
  const [userInfo, setUserInfo] = useState<UserInfo | null>(null);
  const [syncInfo, setSyncInfo] = useState<{ last_sync: string | null; jobs_found: number } | null>(null);
  const { jobs, total, loading, loadingMore, hasMore, loadMore, refresh } = useJobs(filters);
  const { stats } = useStats();

  const visibleJobs = jobs.filter((j) => !j.locked);
  // Use server-side locked count from stats — accurate regardless of pagination
  const lockedCount = stats?.locked_count ?? jobs.filter((j) => j.locked).length;

  useEffect(() => {
    let cancelled = false;
    getMe()
      .then((me) => { if (!cancelled) setUserInfo(me); })
      .catch(() => null);
    getSchedulerStatus()
      .then((info) => { if (!cancelled) setSyncInfo(info); })
      .catch(() => null);
    // Kick off scoring for any unscored jobs in the background
    maybeScore().catch(() => null);
    return () => { cancelled = true; };
  }, []);

  // Detect ?upgraded=true → poll /api/auth/me until tier flips to pro
  // (webhook may take a moment to land), then show the celebration modal.
  useEffect(() => {
    if (!upgradedFlag) return;
    let attempts = 0;
    let cancelled = false;
    let timeoutId: ReturnType<typeof setTimeout> | null = null;

    const tick = async () => {
      attempts += 1;
      try {
        const me = await getMe();
        if (cancelled) return;
        setUserInfo(me);
        if (me.tier === "pro") {
          setShowProWelcome(true);
          refresh();
          return;
        }
      } catch { /* keep polling */ }
      if (attempts < 10 && !cancelled) {
        timeoutId = setTimeout(tick, 1000);
      } else if (!cancelled) {
        // Webhook never landed — surface a fallback toast
        toast("Payment received but upgrade is still processing. Refresh in a moment.", false);
      }
    };
    tick();

    return () => {
      cancelled = true;
      if (timeoutId != null) clearTimeout(timeoutId);
    };
  }, [upgradedFlag, refresh, toast]);

  const handleCloseProWelcome = useCallback(() => {
    setShowProWelcome(false);
    // Clean the ?upgraded=true off the URL so a refresh doesn't re-trigger
    router.replace(pathname);
  }, [router, pathname]);

  const handleSeeMatches = useCallback(() => {
    setShowProWelcome(false);
    router.replace(pathname);
    setFilters({ ...DEFAULT_FILTERS, minScore: 8 });
  }, [router, pathname]);

  const handleRefreshSyncInfo = useCallback(() => {
    getSchedulerStatus().then(setSyncInfo).catch(() => null);
  }, []);

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
    {showProWelcome && (
      <ProWelcomeModal
        stats={stats}
        userInfo={userInfo}
        onClose={handleCloseProWelcome}
        onSeeMatches={handleSeeMatches}
      />
    )}
    {showUpgrade && (
      <UpgradeModal
        lockedCount={lockedCount}
        userInfo={userInfo}
        onClose={() => setShowUpgrade(false)}
        onUpgraded={handleUpgraded}
      />
    )}
    <main className="page-accent-jobs flex h-full">
      {/* Sidebar filters — sections grouped by whitespace, not borders. */}
      <aside className="w-56 shrink-0 border-r border-void-border bg-void-surface overflow-y-auto">
        <div className="px-4 py-5 space-y-6">
          {stats && (
            <section>
              <h2 className="font-display text-base text-void-muted mb-3">Pipeline</h2>
              <div className="grid grid-cols-2 gap-2">
                {[
                  { label: "Scored",    value: stats.funnel.scored },
                  { label: "Tailored",  value: stats.tailored  },
                  { label: "Applied",   value: stats.applied   },
                  { label: "Ready",     value: stats.ready_to_apply },
                ].map(({ label, value }) => (
                  <KpiTile key={label} label={label} value={value} />
                ))}
              </div>
            </section>
          )}

          {/* Last synced indicator */}
          <section>
            <h2 className="font-display text-base text-void-muted mb-2">Job pool</h2>
            <div className="flex items-center justify-between">
              {syncInfo?.last_sync ? (
                <p className="text-xs text-void-subtle">
                  Synced <RelativeTime iso={syncInfo.last_sync} />
                </p>
              ) : (
                <p className="text-xs text-void-subtle">Never synced</p>
              )}
              <button
                onClick={handleRefreshSyncInfo}
                title="Check sync status"
                className="text-void-muted hover:text-void-accent transition-colors"
              >
                <svg viewBox="0 0 16 16" fill="currentColor" className="w-3.5 h-3.5">
                  <path fillRule="evenodd" d="M8 3a5 5 0 1 0 4.546 2.914.5.5 0 0 1 .908-.417A6 6 0 1 1 8 2v1z"/>
                  <path d="M8 4.466V.534a.25.25 0 0 1 .41-.192l2.36 1.966c.12.1.12.284 0 .384L8.41 4.658A.25.25 0 0 1 8 4.466z"/>
                </svg>
              </button>
            </div>
          </section>

          {/* Usage meters for free users */}
          {userInfo?.tier === "free" && userInfo.tailor_limit != null && (
            <section className="space-y-2.5">
              <h2 className="font-display text-base text-void-muted">Usage</h2>
              <UsageMeter label="Tailors" used={userInfo.tailors_used} limit={userInfo.tailor_limit} />
              <UsageMeter label="Cover letters" used={userInfo.covers_used} limit={userInfo.cover_limit ?? 1} />
              <button
                onClick={() => setShowUpgrade(true)}
                className="w-full mt-1 py-1.5 rounded-lg bg-amber-500/10 border border-amber-500/30 text-xs text-amber-300 hover:bg-amber-500/20 transition-colors"
              >
                Upgrade to Pro
              </button>
            </section>
          )}
        </div>

        <JobFilters
          filters={filters}
          sites={stats?.sites ?? []}
          onChange={handleFiltersChange}
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

        {/* New-user setup prompt */}
        {userInfo && !userInfo.has_profile && (
          <div className="mx-6 mt-4 flex items-center gap-3 p-3 rounded-lg border border-void-accent/30 bg-void-accent/5">
            <svg viewBox="0 0 20 20" fill="currentColor" className="w-5 h-5 text-void-accent shrink-0">
              <path fillRule="evenodd" d="M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0Zm-7-4a1 1 0 1 1-2 0 1 1 0 0 1 2 0ZM9 9a.75.75 0 0 0 0 1.5h.253a.25.25 0 0 1 .244.304l-.459 2.066A1.75 1.75 0 0 0 10.747 15H11a.75.75 0 0 0 0-1.5h-.253a.25.25 0 0 1-.244-.304l.459-2.066A1.75 1.75 0 0 0 9.253 9H9Z" clipRule="evenodd" />
            </svg>
            <p className="text-sm text-void-muted flex-1">
              Complete your profile so jobs can be scored against your CV.
            </p>
            <a
              href="/setup"
              className="text-xs font-medium text-void-accent hover:underline shrink-0"
            >
              Set up now →
            </a>
          </div>
        )}

        {/* Job grid */}
        <div className="flex-1 overflow-y-auto p-6">
          {loading ? (
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
              {Array.from({ length: 9 }).map((_, i) => <SkeletonCard key={i} />)}
            </div>
          ) : jobs.length === 0 ? (
            <EmptyState
              onLoosen={() => setFilters(DEFAULT_FILTERS)}
              onBroaden={() => setFilters(BROAD_FILTERS)}
            />
          ) : (
            <>
              <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
                {visibleJobs.map((job) => (
                  <JobCard
                    key={job.url}
                    job={job}
                    onSelect={(j) => setSelectedUrl(j.url_encoded)}
                    onDismiss={handleDismiss}
                    onMarkApplied={handleMarkApplied}
                    onRefresh={refresh}
                    onUpgrade={() => setShowUpgrade(true)}
                  />
                ))}
                {lockedCount > 0 && (
                  <button
                    onClick={() => setShowUpgrade(true)}
                    className="col-span-full flex items-center gap-4 p-4 rounded-lg border border-amber-500/25 bg-amber-500/5 hover:bg-amber-500/10 transition-colors text-left group"
                  >
                    <div className="w-10 h-10 rounded-lg bg-amber-500/15 border border-amber-500/30 flex items-center justify-center shrink-0">
                      <svg viewBox="0 0 20 20" fill="currentColor" className="w-5 h-5 text-amber-400">
                        <path fillRule="evenodd" d="M10 1a4.5 4.5 0 0 0-4.5 4.5V9H5a2 2 0 0 0-2 2v6a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-6a2 2 0 0 0-2-2h-.5V5.5A4.5 4.5 0 0 0 10 1Zm3 8V5.5a3 3 0 1 0-6 0V9h6Z" clipRule="evenodd" />
                      </svg>
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-amber-300">
                        {lockedCount} high-match job{lockedCount > 1 ? "s" : ""} locked
                      </p>
                      <p className="text-xs text-void-muted mt-0.5">
                        These jobs score 8+ and are reserved for Pro users. Upgrade to see them.
                      </p>
                    </div>
                    <span className="text-xs font-medium text-amber-300 border border-amber-500/30 rounded-lg px-3 py-1.5 group-hover:bg-amber-500/20 transition-colors shrink-0">
                      Unlock →
                    </span>
                  </button>
                )}
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
    </main>
    </>
  );
}

// `useSearchParams()` requires a Suspense boundary in Next.js — without it the
// whole page is forced into client rendering and `next build` warns.
export default function JobsPage() {
  return (
    <Suspense>
      <JobsPanel />
    </Suspense>
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

function KpiTile({ label, value }: { label: string; value: number }) {
  // Memoise the sparkbar pattern by label so it stays stable across renders.
  const bars = useMemo(() => makeSparkbars(label), [label]);
  return (
    <div className="bg-void-raised rounded-lg px-2.5 py-2 border border-void-border">
      <p className="text-lg font-semibold font-mono text-void-text leading-none mb-1.5">
        {value}
      </p>
      <p className="text-[11px] text-void-muted mb-1.5 leading-none">{label}</p>
      <div className="flex gap-px h-6 items-end" aria-hidden>
        {bars.map((h, i) => (
          <div
            key={i}
            className={`flex-1 rounded-[1px] ${
              i === bars.length - 1 ? "bg-void-accent" : "bg-void-accent/30"
            }`}
            style={{ height: `${h}%` }}
          />
        ))}
      </div>
    </div>
  );
}

function EmptyState({
  onLoosen,
  onBroaden,
}: {
  onLoosen: () => void;
  onBroaden: () => void;
}) {
  return (
    <div className="flex flex-col items-center justify-center text-center py-16 px-6 max-w-md mx-auto">
      <DeskWithTeacup className="w-40 h-40 mb-6 text-void-muted" />
      <p className="font-display text-2xl text-void-text leading-snug mb-2">
        Inbox zero.
      </p>
      <p className="font-display text-lg text-void-muted leading-snug mb-8">
        Nothing matches your filters — that&apos;s either great news or too tight a query.
      </p>
      <div className="flex gap-3">
        <button
          onClick={onLoosen}
          className="px-4 py-2 rounded-lg bg-void-raised border border-void-border text-sm text-void-text hover:border-void-accent/40 transition-colors"
        >
          Loosen filters
        </button>
        <button
          onClick={onBroaden}
          className="px-4 py-2 rounded-lg bg-void-accent text-white text-sm font-medium hover:bg-void-accent-hover transition-colors"
        >
          Change scope
        </button>
      </div>
    </div>
  );
}

// Stylised desk-with-teacup illustration. Monochrome, low-detail — uses
// `currentColor` so it picks up parent text colour.
function DeskWithTeacup({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 200 160"
      fill="none"
      stroke="currentColor"
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={1.5}
      className={className}
      aria-hidden
    >
      {/* Desk surface */}
      <path d="M20 110 L180 110" />
      {/* Desk legs */}
      <path d="M30 110 L30 145" />
      <path d="M170 110 L170 145" />
      {/* Desk shadow line */}
      <path d="M28 116 L172 116" opacity="0.4" />
      {/* Teacup body */}
      <path d="M82 88 Q82 108 100 108 Q118 108 118 88 Z" />
      {/* Saucer */}
      <ellipse cx="100" cy="110" rx="24" ry="3" />
      {/* Cup handle */}
      <path d="M118 92 Q128 92 128 99 Q128 106 118 104" />
      {/* Steam */}
      <path d="M92 78 Q90 72 94 68 Q98 64 96 58" opacity="0.7" />
      <path d="M104 80 Q106 74 102 70 Q98 66 100 60" opacity="0.5" />
      {/* Notebook */}
      <rect x="35" y="98" width="30" height="12" rx="1.5" />
      <path d="M40 102 L60 102" opacity="0.5" />
      <path d="M40 106 L55 106" opacity="0.5" />
      {/* Pen */}
      <path d="M138 105 L156 95" />
      <path d="M155 94 L158 92 L160 94 L157 96 Z" />
      {/* Plant pot */}
      <path d="M145 86 L145 100 Q145 104 149 104 L161 104 Q165 104 165 100 L165 86 Z" />
      {/* Plant leaves */}
      <path d="M152 86 Q150 78 154 72 Q156 78 154 86" opacity="0.8" />
      <path d="M158 86 Q160 76 156 70 Q152 76 156 86" opacity="0.8" />
    </svg>
  );
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

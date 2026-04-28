"use client";

import { Suspense, useEffect, useState, type ReactNode } from "react";
import { useSearchParams } from "next/navigation";
import { getProfile, updateProfile, getSearches, updateSearches, getResumeText, updateResumeText, uploadResumePdf, getMe, createCheckoutSession, createBillingPortalSession } from "@/lib/api";
import { useToast } from "@/components/ui/Toast";
import type { Profile, SearchConfig, SearchLocation, SearchQuery, UserInfo } from "@/lib/types";

type Tab = "profile" | "searches" | "resume" | "billing";

// ── Profile tab ───────────────────────────────────────────────────────────────

function ProfileTab() {
  const toast = useToast();
  const [profile, setProfile] = useState<Profile>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    getProfile()
      .then(setProfile)
      .catch(() => setProfile({}))
      .finally(() => setLoading(false));
  }, []);

  const save = async () => {
    setSaving(true);
    try {
      await updateProfile(profile);
      toast("Profile saved");
    } catch {
      toast("Failed to save", false);
    } finally {
      setSaving(false);
    }
  };

  const setPersonal = (k: string, v: string) =>
    setProfile((p) => ({ ...p, personal: { ...p.personal, [k]: v } }));

  const setAuth = (k: string, v: unknown) =>
    setProfile((p) => ({ ...p, work_authorization: { ...p.work_authorization, [k]: v } }));

  if (loading) return <div className="p-6 space-y-3">{Array.from({length:8}).map((_,i)=><div key={i} className="skeleton h-8" />)}</div>;

  const p = profile.personal ?? {};
  const a = profile.work_authorization ?? {};

  return (
    <div className="p-6 max-w-2xl">
      <Section title="Personal">
        <div className="grid grid-cols-2 gap-4">
          {(["name","email","phone","city","country","linkedin","github","portfolio"] as const).map((field) => (
            <Field key={field} label={field} value={String(p[field as keyof typeof p] ?? "")} onChange={(v) => setPersonal(field, v)} />
          ))}
        </div>
      </Section>

      <Section title="Work Authorization" className="mt-6">
        <div className="flex flex-col gap-3">
          <label className="flex items-center gap-2 cursor-pointer">
            <input type="checkbox" checked={!!a.legally_authorized_to_work} onChange={e => setAuth("legally_authorized_to_work", e.target.checked)} className="accent-void-accent" />
            <span className="text-sm text-void-text">Legally authorized to work</span>
          </label>
          <label className="flex items-center gap-2 cursor-pointer">
            <input type="checkbox" checked={!!a.require_sponsorship} onChange={e => setAuth("require_sponsorship", e.target.checked)} className="accent-void-accent" />
            <span className="text-sm text-void-text">Requires visa sponsorship</span>
          </label>
          <Field label="Permit type" value={a.work_permit_type ?? ""} onChange={v => setAuth("work_permit_type", v)} />
        </div>
      </Section>

      <div className="mt-6">
        <button onClick={save} disabled={saving}
          className="px-6 py-2 rounded-lg bg-void-accent text-white text-sm font-medium hover:bg-indigo-500 disabled:opacity-50 transition-colors">
          {saving ? "Saving…" : "Save Profile"}
        </button>
      </div>
    </div>
  );
}

// ── Searches tab ──────────────────────────────────────────────────────────────

const ALL_BOARDS = ["indeed", "linkedin", "glassdoor", "zip_recruiter", "google"];

function TagInput({ tags, onAdd, onRemove, placeholder }: {
  tags: string[];
  onAdd: (v: string) => void;
  onRemove: (v: string) => void;
  placeholder?: string;
}) {
  const [val, setVal] = useState("");
  const add = () => { const t = val.trim(); if (t && !tags.includes(t)) { onAdd(t); setVal(""); } };
  return (
    <div className="flex flex-col gap-2">
      {tags.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {tags.map(t => (
            <span key={t} className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-void-raised border border-void-border text-xs text-void-text">
              {t}
              <button onClick={() => onRemove(t)} className="text-void-muted hover:text-void-danger leading-none ml-0.5">×</button>
            </span>
          ))}
        </div>
      )}
      <div className="flex gap-2">
        <input
          className="flex-1 px-3 py-1.5 rounded-lg bg-void-raised border border-void-border text-sm text-void-text placeholder:text-void-subtle focus:outline-none focus:border-void-accent/60 transition-colors"
          value={val}
          onChange={e => setVal(e.target.value)}
          onKeyDown={e => { if (e.key === "Enter") { e.preventDefault(); add(); } }}
          placeholder={placeholder}
        />
        <button onClick={add} disabled={!val.trim()} className="px-3 py-1.5 rounded-lg bg-void-raised border border-void-border text-sm text-void-muted hover:text-void-text disabled:opacity-30 transition-colors">Add</button>
      </div>
    </div>
  );
}

function SearchesTab() {
  const toast = useToast();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  // Parsed state — every field maps to an explicit `SearchConfig` key.
  const [queries, setQueries] = useState<SearchQuery[]>([]);
  const [locations, setLocations] = useState<SearchLocation[]>([]);
  const [boards, setBoards] = useState<string[]>([]);
  const [country, setCountry] = useState("USA");
  const [hoursOld, setHoursOld] = useState(72);
  const [resultsPerSite, setResultsPerSite] = useState(100);
  const [excludeTitles, setExcludeTitles] = useState<string[]>([]);
  const [acceptPatterns, setAcceptPatterns] = useState<string[]>([]);
  const [rejectPatterns, setRejectPatterns] = useState<string[]>([]);
  // Local state for the "add a new query" input — replaces the previous
  // `document.getElementById("new-query")` lookup.
  const [newQuery, setNewQuery] = useState("");

  useEffect(() => {
    getSearches()
      .then((cfg: SearchConfig) => {
        setQueries(cfg.queries ?? []);
        setLocations(cfg.locations ?? []);
        setBoards(cfg.boards ?? []);
        setCountry(cfg.country ?? "USA");
        setHoursOld(cfg.defaults?.hours_old ?? 72);
        setResultsPerSite(cfg.defaults?.results_per_site ?? 100);
        setExcludeTitles(cfg.exclude_titles ?? []);
        setAcceptPatterns(cfg.location?.accept_patterns ?? []);
        setRejectPatterns(cfg.location?.reject_patterns ?? []);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const save = async () => {
    setSaving(true);
    try {
      const payload: SearchConfig = {
        queries,
        locations,
        boards,
        country,
        defaults: { results_per_site: resultsPerSite, hours_old: hoursOld },
        exclude_titles: excludeTitles,
        location: { accept_patterns: acceptPatterns, reject_patterns: rejectPatterns },
      };
      await updateSearches(payload);
      toast("Search config saved");
    } catch {
      toast("Failed to save", false);
    } finally {
      setSaving(false);
    }
  };

  const toggleBoard = (b: string) =>
    setBoards(prev => prev.includes(b) ? prev.filter(x => x !== b) : [...prev, b]);

  const addQuery = (query: string, tier: 1 | 2 | 3 = 2) => {
    if (!queries.some(q => q.query.toLowerCase() === query.toLowerCase()))
      setQueries(prev => [...prev, { query, tier }]);
  };

  const submitNewQuery = () => {
    const trimmed = newQuery.trim();
    if (!trimmed) return;
    addQuery(trimmed);
    setNewQuery("");
  };

  const removeQuery = (query: string) =>
    setQueries(prev => prev.filter(q => q.query !== query));

  const cycleQueryTier = (query: string) =>
    setQueries(prev => prev.map(q =>
      q.query === query ? { ...q, tier: q.tier === 3 ? 1 : (q.tier + 1) as 1 | 2 | 3 } : q
    ));

  const addLocation = () =>
    setLocations(prev => [...prev, { location: "", remote: false }]);

  const updateLocation = (i: number, patch: Partial<SearchLocation>) =>
    setLocations(prev => prev.map((l, idx) => idx === i ? { ...l, ...patch } : l));

  const removeLocation = (i: number) =>
    setLocations(prev => prev.filter((_, idx) => idx !== i));

  const tierColors: Record<number, string> = {
    1: "bg-void-success/15 text-void-success border-void-success/30",
    2: "bg-void-accent/15 text-void-accent border-void-accent/30",
    3: "bg-void-muted/15 text-void-muted border-void-muted/30",
  };

  if (loading) return <div className="p-6 space-y-4">{Array.from({length: 5}).map((_,i) => <div key={i} className="skeleton h-16" />)}</div>;

  return (
    <div className="p-6 max-w-2xl space-y-8">

      {/* Queries */}
      <section>
        <SectionHeader title="Search Queries" hint="What to search for on job boards. Click the tier badge to cycle priority (1 = most targeted, 3 = broad net)." />
        <div className="flex flex-wrap gap-1.5 mb-3">
          {queries.map(({ query, tier }) => (
            <span key={query} className="inline-flex items-center gap-1 pl-2 pr-1 py-0.5 rounded-full bg-void-raised border border-void-border text-xs text-void-text">
              {query}
              <button
                title="Click to cycle tier"
                onClick={() => cycleQueryTier(query)}
                className={`px-1.5 py-0.5 rounded-full border text-xs font-semibold transition-colors ${tierColors[tier]}`}
              >
                {tier}
              </button>
              <button onClick={() => removeQuery(query)} className="text-void-muted hover:text-void-danger px-0.5 leading-none">×</button>
            </span>
          ))}
        </div>
        <div className="flex gap-2">
          <input
            value={newQuery}
            onChange={e => setNewQuery(e.target.value)}
            onKeyDown={e => {
              if (e.key === "Enter") { e.preventDefault(); submitNewQuery(); }
            }}
            className="flex-1 px-3 py-1.5 rounded-lg bg-void-raised border border-void-border text-sm text-void-text placeholder:text-void-subtle focus:outline-none focus:border-void-accent/60 transition-colors"
            placeholder="Add a search query…"
          />
          <button
            onClick={submitNewQuery}
            disabled={!newQuery.trim()}
            className="px-3 py-1.5 rounded-lg bg-void-raised border border-void-border text-sm text-void-muted hover:text-void-text disabled:opacity-30 transition-colors"
          >Add</button>
        </div>
      </section>

      {/* Locations */}
      <section>
        <SectionHeader title="Locations" hint="Where to search. Toggle Remote for location-agnostic searches." />
        <div className="flex flex-col gap-2 mb-2">
          {locations.map((loc, i) => (
            <div key={i} className="flex items-center gap-2">
              <input
                className="flex-1 px-3 py-1.5 rounded-lg bg-void-raised border border-void-border text-sm text-void-text placeholder:text-void-subtle focus:outline-none focus:border-void-accent/60 transition-colors"
                value={loc.location}
                onChange={e => updateLocation(i, { location: e.target.value })}
                placeholder="San Francisco CA"
              />
              <label className="flex items-center gap-1.5 text-xs text-void-muted cursor-pointer shrink-0">
                <input type="checkbox" checked={loc.remote} onChange={e => updateLocation(i, { remote: e.target.checked })} className="accent-void-accent" />
                Remote
              </label>
              <button onClick={() => removeLocation(i)} className="text-void-muted hover:text-void-danger text-lg leading-none px-1">×</button>
            </div>
          ))}
        </div>
        <button onClick={addLocation} className="text-xs text-void-accent hover:underline">+ Add location</button>
      </section>

      {/* Job Boards */}
      <section>
        <SectionHeader title="Job Boards" hint="Which boards to search on." />
        <div className="flex flex-wrap gap-2">
          {ALL_BOARDS.map(b => (
            <button
              key={b}
              onClick={() => toggleBoard(b)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                boards.includes(b)
                  ? "bg-void-accent/15 border border-void-accent/40 text-void-accent"
                  : "bg-void-raised border border-void-border text-void-muted hover:text-void-text"
              }`}
            >
              {b.replace("_", " ")}
            </button>
          ))}
        </div>
      </section>

      {/* Defaults */}
      <section>
        <SectionHeader title="Defaults" hint="Search volume and recency controls." />
        <div className="flex gap-4">
          <div>
            <label className="block text-xs text-void-muted mb-1">Max results per board</label>
            <input type="number" min={10} max={500} value={resultsPerSite}
              onChange={e => setResultsPerSite(Number(e.target.value))}
              className="w-32 px-3 py-1.5 rounded-lg bg-void-raised border border-void-border text-sm text-void-text focus:outline-none focus:border-void-accent/60 transition-colors" />
          </div>
          <div>
            <label className="block text-xs text-void-muted mb-1">Max job age (hours)</label>
            <input type="number" min={1} max={720} value={hoursOld}
              onChange={e => setHoursOld(Number(e.target.value))}
              className="w-32 px-3 py-1.5 rounded-lg bg-void-raised border border-void-border text-sm text-void-text focus:outline-none focus:border-void-accent/60 transition-colors" />
          </div>
          <div>
            <label className="block text-xs text-void-muted mb-1">Country</label>
            <input value={country} onChange={e => setCountry(e.target.value)}
              className="w-28 px-3 py-1.5 rounded-lg bg-void-raised border border-void-border text-sm text-void-text focus:outline-none focus:border-void-accent/60 transition-colors" />
          </div>
        </div>
      </section>

      {/* Exclude titles */}
      <section>
        <SectionHeader title="Exclude Job Titles" hint="Jobs whose title contains any of these keywords will be skipped." />
        <TagInput tags={excludeTitles} onAdd={v => setExcludeTitles(p => [...p, v])} onRemove={v => setExcludeTitles(p => p.filter(x => x !== v))} placeholder="e.g. intern, VP, clearance required" />
      </section>

      {/* Location filters */}
      <section>
        <SectionHeader title="Location Filters" hint="Accept/reject jobs based on their listed location text." />
        <div className="grid grid-cols-2 gap-6">
          <div>
            <p className="text-xs text-void-success mb-2 font-medium">Accept patterns</p>
            <TagInput tags={acceptPatterns} onAdd={v => setAcceptPatterns(p => [...p, v])} onRemove={v => setAcceptPatterns(p => p.filter(x => x !== v))} placeholder="e.g. Remote, California" />
          </div>
          <div>
            <p className="text-xs text-void-danger mb-2 font-medium">Reject patterns</p>
            <TagInput tags={rejectPatterns} onAdd={v => setRejectPatterns(p => [...p, v])} onRemove={v => setRejectPatterns(p => p.filter(x => x !== v))} placeholder="e.g. onsite only, London" />
          </div>
        </div>
      </section>

      <button onClick={save} disabled={saving}
        className="px-6 py-2 rounded-lg bg-void-accent text-white text-sm font-medium hover:bg-indigo-500 disabled:opacity-50 transition-colors">
        {saving ? "Saving…" : "Save Search Config"}
      </button>
    </div>
  );
}

function SectionHeader({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="mb-3">
      <h3 className="text-xs font-medium text-void-muted uppercase tracking-wider">{title}</h3>
      {hint && <p className="text-xs text-void-subtle mt-0.5">{hint}</p>}
    </div>
  );
}

// ── Resume tab ────────────────────────────────────────────────────────────────

function ResumeTab() {
  const toast = useToast();
  const [text, setText] = useState("");
  const [exists, setExists] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);

  useEffect(() => {
    getResumeText()
      .then(({ text, exists }) => { setText(text); setExists(exists); })
      .finally(() => setLoading(false));
  }, []);

  const save = async () => {
    setSaving(true);
    try {
      await updateResumeText(text);
      toast("Resume saved");
      setExists(true);
    } catch {
      toast("Failed to save", false);
    } finally {
      setSaving(false);
    }
  };

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      await uploadResumePdf(file);
      toast("PDF uploaded — text extraction started");
      setTimeout(() => getResumeText().then(({ text }) => setText(text)), 3000);
    } catch {
      toast("Upload failed", false);
    } finally {
      setUploading(false);
      e.target.value = "";
    }
  };

  if (loading) return <div className="p-6"><div className="skeleton h-96" /></div>;

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-3">
        <div>
          <p className="text-sm text-void-text font-medium">Master Resume</p>
          <p className="text-xs text-void-muted mt-0.5">{text.length} chars · {text.split("\n").length} lines</p>
        </div>
        <label className={`
          cursor-pointer px-3 py-1.5 rounded-lg border border-void-border text-xs text-void-muted
          hover:text-void-text hover:border-void-accent/40 transition-colors
          ${uploading ? "opacity-50 pointer-events-none" : ""}
        `}>
          {uploading ? "Uploading…" : "Upload PDF"}
          <input type="file" accept=".pdf" onChange={handleUpload} className="hidden" />
        </label>
      </div>
      <textarea
        value={text}
        onChange={e => setText(e.target.value)}
        placeholder="Paste your resume text here…"
        className="w-full h-[62vh] font-mono text-xs bg-void-raised border border-void-border rounded-lg p-3 text-void-text placeholder:text-void-muted focus:outline-none focus:border-void-accent/60 resize-none leading-relaxed"
      />
      <button onClick={save} disabled={saving}
        className="mt-3 px-6 py-2 rounded-lg bg-void-accent text-white text-sm font-medium hover:bg-indigo-500 disabled:opacity-50 transition-colors">
        {saving ? "Saving…" : "Save Resume"}
      </button>
    </div>
  );
}

// ── Shared primitives ─────────────────────────────────────────────────────────

function Section({ title, children, className = "" }: { title: string; children: React.ReactNode; className?: string }) {
  return (
    <div className={className}>
      <h3 className="text-xs font-medium text-void-muted uppercase tracking-wider mb-3">{title}</h3>
      {children}
    </div>
  );
}

function Field({ label, value, onChange, type = "text" }: { label: string; value: string; onChange: (v: string) => void; type?: string }) {
  return (
    <div>
      <label className="block text-xs text-void-muted mb-1 capitalize">{label.replace(/_/g, " ")}</label>
      <input
        type={type}
        value={value}
        onChange={e => onChange(e.target.value)}
        className="w-full px-3 py-1.5 rounded-lg bg-void-raised border border-void-border text-sm text-void-text focus:outline-none focus:border-void-accent/60 transition-colors"
      />
    </div>
  );
}

// ── Billing tab ───────────────────────────────────────────────────────────────

function BillingTab() {
  const toast = useToast();
  const [me, setMe] = useState<UserInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    getMe().then(setMe).catch(() => null).finally(() => setLoading(false));
  }, []);

  const handleManage = async () => {
    setBusy(true);
    try {
      const { portal_url } = await createBillingPortalSession();
      window.location.href = portal_url;
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      toast(msg || "Couldn't open billing portal", false);
      setBusy(false);
    }
  };

  const handleUpgrade = async () => {
    setBusy(true);
    try {
      const { checkout_url } = await createCheckoutSession();
      window.location.href = checkout_url;
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      toast(msg || "Upgrade failed", false);
      setBusy(false);
    }
  };

  if (loading) {
    return <div className="p-6 text-sm text-void-muted">Loading…</div>;
  }
  if (!me) {
    return <div className="p-6 text-sm text-void-muted">Couldn't load account info.</div>;
  }

  const isPro = me.tier === "pro";

  return (
    <div className="p-6 max-w-2xl space-y-6">
      {/* Plan card */}
      <div className={`rounded-xl border p-5 ${
        isPro
          ? "bg-gradient-to-br from-amber-500/10 to-transparent border-amber-500/30"
          : "bg-void-surface border-void-border"
      }`}>
        <div className="flex items-start justify-between gap-4 mb-4">
          <div>
            <p className="text-xs uppercase tracking-wider text-void-subtle mb-1">Current plan</p>
            <p className={`text-2xl font-semibold ${isPro ? "text-amber-300" : "text-void-text"}`}>
              {isPro ? "Pro" : "Free"}
            </p>
          </div>
          {isPro && (
            <span className="px-2 py-1 rounded-full bg-amber-500/15 border border-amber-500/30 text-xs text-amber-300 font-medium">
              Active
            </span>
          )}
        </div>

        {isPro ? (
          <ul className="space-y-1.5 text-sm text-void-text">
            <li>· Unlimited tailored resumes</li>
            <li>· Unlimited cover letters</li>
            <li>· All high-match jobs visible</li>
            <li>· PDF export</li>
          </ul>
        ) : (
          <div className="space-y-3">
            <p className="text-sm text-void-muted">
              You're on the free plan: <span className="text-void-text">3 tailored resumes</span> and{" "}
              <span className="text-void-text">1 cover letter</span> per month.
            </p>
            <p className="text-sm text-void-muted">
              Upgrade to remove limits and unlock all high-match jobs.
            </p>
          </div>
        )}
      </div>

      {/* Usage */}
      {me.tailor_limit != null && (
        <div className="rounded-xl border border-void-border bg-void-surface p-5">
          <p className="text-sm font-medium text-void-text mb-3">This month's usage</p>
          <div className="grid grid-cols-2 gap-4">
            <UsageStat
              label="Tailored resumes"
              used={me.tailors_used}
              limit={me.tailor_limit}
              isPro={isPro}
            />
            <UsageStat
              label="Cover letters"
              used={me.covers_used}
              limit={me.cover_limit ?? 1}
              isPro={isPro}
            />
          </div>
        </div>
      )}

      {/* Actions */}
      <div className="flex flex-col gap-2">
        {isPro ? (
          <>
            <button
              onClick={handleManage}
              disabled={busy}
              className="w-full py-3 rounded-lg bg-void-raised border border-void-border text-sm font-medium text-void-text hover:border-void-accent/40 disabled:opacity-50 transition-colors"
            >
              {busy ? "Opening…" : "Manage subscription"}
            </button>
            <p className="text-xs text-void-subtle text-center">
              Cancel, update your card, or download invoices in Stripe's secure portal.
            </p>
          </>
        ) : (
          <button
            onClick={handleUpgrade}
            disabled={busy}
            className="w-full py-3 rounded-lg bg-amber-500 text-black text-sm font-semibold hover:bg-amber-400 disabled:opacity-50 transition-colors"
          >
            {busy ? "Redirecting…" : "Upgrade to Pro — $19/mo"}
          </button>
        )}
      </div>
    </div>
  );
}

function UsageStat({ label, used, limit, isPro }: { label: string; used: number; limit: number; isPro: boolean }) {
  const pct = isPro ? 0 : Math.min(100, Math.round((used / Math.max(limit, 1)) * 100));
  return (
    <div>
      <div className="flex justify-between items-baseline mb-1.5">
        <span className="text-xs text-void-muted">{label}</span>
        <span className="text-sm font-mono text-void-text">
          {used}
          <span className="text-void-subtle"> / {isPro ? "∞" : limit}</span>
        </span>
      </div>
      <div className="h-1.5 rounded-full bg-void-raised overflow-hidden">
        <div
          className={`h-full rounded-full transition-all ${
            isPro ? "bg-amber-400" : used >= limit ? "bg-void-danger" : "bg-void-accent"
          }`}
          style={{ width: isPro ? "100%" : `${pct}%` }}
        />
      </div>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

interface TabDef {
  id: Tab;
  label: string;
  icon: ReactNode;
}

const PROFILE_ICON = (
  <svg viewBox="0 0 20 20" fill="currentColor" className="w-3.5 h-3.5" aria-hidden>
    <path fillRule="evenodd" d="M10 9a3 3 0 1 0 0-6 3 3 0 0 0 0 6Zm-7 9a7 7 0 1 1 14 0H3Z" clipRule="evenodd" />
  </svg>
);
const SEARCH_ICON = (
  <svg viewBox="0 0 20 20" fill="currentColor" className="w-3.5 h-3.5" aria-hidden>
    <path fillRule="evenodd" d="M9 3.5a5.5 5.5 0 1 0 3.6 9.7l3.1 3.1a1 1 0 0 0 1.4-1.4l-3.1-3.1A5.5 5.5 0 0 0 9 3.5ZM5.5 9a3.5 3.5 0 1 1 7 0 3.5 3.5 0 0 1-7 0Z" clipRule="evenodd" />
  </svg>
);
const RESUME_ICON = (
  <svg viewBox="0 0 20 20" fill="currentColor" className="w-3.5 h-3.5" aria-hidden>
    <path fillRule="evenodd" d="M5 2a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V6.41a2 2 0 0 0-.59-1.41L13.41 2.59A2 2 0 0 0 12 2H5Zm1 6a1 1 0 0 1 1-1h6a1 1 0 1 1 0 2H7a1 1 0 0 1-1-1Zm0 4a1 1 0 0 1 1-1h6a1 1 0 1 1 0 2H7a1 1 0 0 1-1-1Zm0 4a1 1 0 0 1 1-1h3a1 1 0 1 1 0 2H7a1 1 0 0 1-1-1Z" clipRule="evenodd" />
  </svg>
);
const BILLING_ICON = (
  <svg viewBox="0 0 20 20" fill="currentColor" className="w-3.5 h-3.5" aria-hidden>
    <path d="M2 6a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v1H2V6Zm0 3h16v5a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V9Zm3 4a1 1 0 1 0 0 2h3a1 1 0 1 0 0-2H5Z" />
  </svg>
);

const TABS: TabDef[] = [
  { id: "profile",   label: "Profile",  icon: PROFILE_ICON },
  { id: "searches",  label: "Searches", icon: SEARCH_ICON },
  { id: "resume",    label: "Resume",   icon: RESUME_ICON },
  { id: "billing",   label: "Billing",  icon: BILLING_ICON },
];

function ProfilePanel() {
  const params = useSearchParams();
  const [tab, setTab] = useState<Tab>(() => {
    const t = params.get("tab");
    if (t === "billing" || t === "profile" || t === "searches" || t === "resume") {
      return t;
    }
    return "profile";
  });

  // Pending-state indicators — the page header doesn't fetch profile/resume
  // itself (each tab does), so we re-issue the cheap GETs here once on mount
  // to know which tabs need attention. Idempotent, low cost.
  const [pendingProfile, setPendingProfile] = useState(false);
  const [pendingSearches, setPendingSearches] = useState(false);
  const [pendingResume, setPendingResume] = useState(false);

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      getProfile().catch(() => ({} as Profile)),
      getSearches().catch(() => ({} as SearchConfig)),
      getResumeText().catch(() => ({ text: "", exists: false })),
    ]).then(([prof, sr, rt]) => {
      if (cancelled) return;
      const noName = !prof.personal?.full_name?.trim();
      setPendingProfile(noName);
      setPendingSearches((sr.queries ?? []).length === 0);
      setPendingResume(!rt.text || !rt.text.trim());
    });
    return () => { cancelled = true; };
  }, []);

  const pendingByTab: Record<Tab, boolean> = {
    profile: pendingProfile,
    searches: pendingSearches,
    resume: pendingResume,
    billing: false,
  };

  return (
    <main className="page-accent-profile flex flex-col h-full">
      {/* Header */}
      <div className="px-6 pt-6 pb-0 border-b border-void-border shrink-0">
        <h1 className="font-display text-3xl text-void-text leading-tight">
          Profile &amp; Config
        </h1>
        <p className="text-sm text-void-muted mt-1 mb-5">
          Tune the inputs that drive scoring, tailoring, and matching.
        </p>

        {/* Segmented tab strip */}
        <div className="flex gap-1 -mb-px">
          {TABS.map(({ id, label, icon }) => {
            const isActive = tab === id;
            const needsAttention = pendingByTab[id];
            return (
              <button
                key={id}
                onClick={() => setTab(id)}
                className={`
                  group flex items-center gap-2 px-4 h-10 rounded-t-lg text-sm border-b-2 transition-colors
                  ${isActive
                    ? "border-void-accent text-void-accent font-display"
                    : "border-transparent text-void-muted hover:text-void-text"
                  }
                `}
              >
                <span className={isActive ? "text-void-accent" : "text-void-subtle group-hover:text-void-muted"}>
                  {icon}
                </span>
                <span>{label}</span>
                {needsAttention && (
                  <span
                    title="Needs attention"
                    className="inline-flex items-center justify-center min-w-[1.25rem] h-5 px-1.5 rounded-full bg-amber-500/20 border border-amber-500/40 text-[10px] font-semibold text-amber-300"
                  >
                    !
                  </span>
                )}
              </button>
            );
          })}
        </div>
      </div>

      {/* Tab content */}
      <div className="flex-1 overflow-y-auto">
        {tab === "profile"   && <ProfileTab />}
        {tab === "searches"  && <SearchesTab />}
        {tab === "resume"    && <ResumeTab />}
        {tab === "billing"   && <BillingTab />}
      </div>
    </main>
  );
}

// `useSearchParams()` must be wrapped in a Suspense boundary so the rest of
// the page isn't forced into runtime rendering during build.
export default function ProfilePage() {
  return (
    <Suspense>
      <ProfilePanel />
    </Suspense>
  );
}

"use client";

import { useState, useEffect } from "react";
import { getProfile, updateProfile, getSearches, updateSearches, getEmployers, updateEmployers, getResumeText, updateResumeText, uploadResumePdf } from "@/lib/api";
import { useToast } from "@/components/ui/Toast";
import type { Profile } from "@/lib/types";

type Tab = "profile" | "searches" | "employers" | "resume";

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

interface SearchQuery { query: string; tier: 1 | 2 | 3 }
interface SearchLocation { location: string; remote: boolean }

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

  // Parsed state
  const [queries, setQueries] = useState<SearchQuery[]>([]);
  const [locations, setLocations] = useState<SearchLocation[]>([]);
  const [boards, setBoards] = useState<string[]>([]);
  const [country, setCountry] = useState("USA");
  const [hoursOld, setHoursOld] = useState(72);
  const [resultsPerSite, setResultsPerSite] = useState(100);
  const [excludeTitles, setExcludeTitles] = useState<string[]>([]);
  const [acceptPatterns, setAcceptPatterns] = useState<string[]>([]);
  const [rejectPatterns, setRejectPatterns] = useState<string[]>([]);
  // Preserve unknown keys so we don't lose them on save
  const [extra, setExtra] = useState<Record<string, unknown>>({});

  useEffect(() => {
    getSearches()
      .then(d => {
        const raw = d as Record<string, unknown>;
        setQueries((raw.queries as SearchQuery[] | undefined) ?? []);
        setLocations((raw.locations as SearchLocation[] | undefined) ?? []);
        setBoards((raw.boards as string[] | undefined) ?? []);
        setCountry((raw.country as string | undefined) ?? "USA");
        const defaults = (raw.defaults as Record<string, number> | undefined) ?? {};
        setHoursOld(defaults.hours_old ?? 72);
        setResultsPerSite(defaults.results_per_site ?? 100);
        setExcludeTitles((raw.exclude_titles as string[] | undefined) ?? []);
        const loc = (raw.location as Record<string, string[]> | undefined) ?? {};
        setAcceptPatterns(loc.accept_patterns ?? []);
        setRejectPatterns(loc.reject_patterns ?? []);
        // Preserve unrecognised keys
        const { queries: _q, locations: _l, boards: _b, country: _c, defaults: _d,
                exclude_titles: _e, location: _loc, ...rest } = raw;
        setExtra(rest);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const save = async () => {
    setSaving(true);
    try {
      await updateSearches({
        ...extra,
        queries,
        locations,
        boards,
        country,
        defaults: { results_per_site: resultsPerSite, hours_old: hoursOld },
        exclude_titles: excludeTitles,
        location: { accept_patterns: acceptPatterns, reject_patterns: rejectPatterns },
      });
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
            id="new-query"
            className="flex-1 px-3 py-1.5 rounded-lg bg-void-raised border border-void-border text-sm text-void-text placeholder:text-void-subtle focus:outline-none focus:border-void-accent/60 transition-colors"
            placeholder="Add a search query…"
            onKeyDown={e => {
              if (e.key === "Enter") {
                const v = (e.target as HTMLInputElement).value.trim();
                if (v) { addQuery(v); (e.target as HTMLInputElement).value = ""; }
              }
            }}
          />
          <button
            onClick={() => {
              const el = document.getElementById("new-query") as HTMLInputElement;
              if (el.value.trim()) { addQuery(el.value.trim()); el.value = ""; }
            }}
            className="px-3 py-1.5 rounded-lg bg-void-raised border border-void-border text-sm text-void-muted hover:text-void-text transition-colors"
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

// ── Employers tab ─────────────────────────────────────────────────────────────

function EmployersTab() {
  const toast = useToast();
  const [employers, setEmployers] = useState<Record<string, Record<string, unknown>>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [filter, setFilter] = useState("");

  useEffect(() => {
    getEmployers()
      .then(d => setEmployers(d as Record<string, Record<string, unknown>>))
      .catch(() => setEmployers({}))
      .finally(() => setLoading(false));
  }, []);

  const toggleEnabled = (key: string) => {
    setEmployers(e => ({
      ...e,
      [key]: { ...e[key], enabled: !e[key].enabled }
    }));
  };

  const save = async () => {
    setSaving(true);
    try {
      await updateEmployers(employers);
      toast("Employers saved");
    } catch {
      toast("Failed to save", false);
    } finally {
      setSaving(false);
    }
  };

  const filtered = Object.entries(employers).filter(([key]) =>
    key.toLowerCase().includes(filter.toLowerCase()) ||
    String((employers[key] as Record<string, unknown>).name ?? "").toLowerCase().includes(filter.toLowerCase())
  );

  if (loading) return <div className="p-6"><div className="skeleton h-96" /></div>;

  return (
    <div className="p-6">
      <div className="mb-4 p-3 rounded-lg bg-void-raised border border-void-border text-xs text-void-muted leading-relaxed">
        <span className="text-void-text font-medium">Workday direct scraping</span>
        {" — "}Enable companies below to have their jobs scraped directly from their Workday career portals, bypassing generic job boards. Disabled by default; enable only the ones you're interested in.
      </div>
      <div className="flex items-center gap-3 mb-4">
        <input
          type="text"
          placeholder="Filter employers…"
          value={filter}
          onChange={e => setFilter(e.target.value)}
          className="flex-1 px-3 py-1.5 rounded-lg bg-void-raised border border-void-border text-sm text-void-text placeholder:text-void-muted focus:outline-none focus:border-void-accent/60 transition-colors"
        />
        <span className="text-xs text-void-muted">{filtered.length} of {Object.keys(employers).length}</span>
      </div>

      <div className="border border-void-border rounded-lg overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-void-border bg-void-raised">
              <th className="text-left px-4 py-2.5 text-xs font-medium text-void-muted">Key</th>
              <th className="text-left px-4 py-2.5 text-xs font-medium text-void-muted">Name</th>
              <th className="text-left px-4 py-2.5 text-xs font-medium text-void-muted">Tenant</th>
              <th className="text-center px-4 py-2.5 text-xs font-medium text-void-muted">Enabled</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map(([key, emp]) => (
              <tr key={key} className="border-b border-void-border/50 hover:bg-void-raised/40 transition-colors">
                <td className="px-4 py-2.5 text-void-muted font-mono text-xs">{key}</td>
                <td className="px-4 py-2.5 text-void-text">{String(emp.name ?? "")}</td>
                <td className="px-4 py-2.5 text-void-muted font-mono text-xs">{String(emp.tenant ?? "")}</td>
                <td className="px-4 py-2.5 text-center">
                  <input
                    type="checkbox"
                    checked={!!emp.enabled}
                    onChange={() => toggleEnabled(key)}
                    className="accent-void-accent"
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <button onClick={save} disabled={saving}
        className="mt-4 px-6 py-2 rounded-lg bg-void-accent text-white text-sm font-medium hover:bg-indigo-500 disabled:opacity-50 transition-colors">
        {saving ? "Saving…" : "Save Employers"}
      </button>
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

// ── Page ──────────────────────────────────────────────────────────────────────

const TABS: { id: Tab; label: string }[] = [
  { id: "profile",   label: "Profile" },
  { id: "searches",  label: "Searches" },
  { id: "employers", label: "Employers" },
  { id: "resume",    label: "Resume" },
];

export default function ProfilePage() {
  const [tab, setTab] = useState<Tab>("profile");

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="px-6 pt-5 border-b border-void-border shrink-0">
        <h1 className="text-base font-semibold text-void-text mb-4">Profile & Config</h1>
        <div className="flex gap-1">
          {TABS.map(({ id, label }) => (
            <button
              key={id}
              onClick={() => setTab(id)}
              className={`
                px-4 py-2 rounded-t-lg text-sm font-medium border-b-2 transition-colors
                ${tab === id
                  ? "border-void-accent text-void-accent"
                  : "border-transparent text-void-muted hover:text-void-text"
                }
              `}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* Tab content */}
      <div className="flex-1 overflow-y-auto">
        {tab === "profile"   && <ProfileTab />}
        {tab === "searches"  && <SearchesTab />}
        {tab === "employers" && <EmployersTab />}
        {tab === "resume"    && <ResumeTab />}
      </div>
    </div>
  );
}

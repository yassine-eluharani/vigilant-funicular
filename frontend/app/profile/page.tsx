"use client";

import { useState, useEffect, useCallback } from "react";
import { getProfile, updateProfile, getSearches, updateSearches, getEmployers, updateEmployers, getEnvConfig, updateEnvConfig, getResumeText, updateResumeText, uploadResumePdf, getSystemStatus } from "@/lib/api";
import { useToast } from "@/components/ui/Toast";
import type { Profile, SystemStatus } from "@/lib/types";

type Tab = "profile" | "searches" | "employers" | "keys" | "resume";

// ── Tier badge ────────────────────────────────────────────────────────────────

function TierBadge({ tier }: { tier: 1 | 2 | 3 }) {
  const styles = [
    "",
    "bg-void-muted/10 text-void-muted border-void-muted/30",
    "bg-void-accent/10 text-void-accent border-void-accent/30",
    "bg-void-success/10 text-void-success border-void-success/30",
  ];
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-medium border ${styles[tier]}`}>
      Tier {tier}
    </span>
  );
}

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

function SearchesTab() {
  const toast = useToast();
  const [data, setData] = useState<Record<string, unknown>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [raw, setRaw] = useState("");
  const [rawError, setRawError] = useState("");

  useEffect(() => {
    getSearches()
      .then(d => { setData(d); setRaw(JSON.stringify(d, null, 2)); })
      .catch(() => setData({}))
      .finally(() => setLoading(false));
  }, []);

  const save = async () => {
    let parsed: unknown;
    try { parsed = JSON.parse(raw); setRawError(""); } catch {
      setRawError("Invalid JSON"); return;
    }
    setSaving(true);
    try {
      await updateSearches(parsed as Record<string, unknown>);
      toast("Searches config saved");
    } catch {
      toast("Failed to save", false);
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <div className="p-6"><div className="skeleton h-96" /></div>;

  return (
    <div className="p-6">
      <p className="text-xs text-void-muted mb-3">Edit searches.yaml configuration as JSON. Changes take effect on next pipeline run.</p>
      <textarea
        value={raw}
        onChange={e => setRaw(e.target.value)}
        className="w-full h-[60vh] font-mono text-xs bg-void-raised border border-void-border rounded-lg p-3 text-void-text focus:outline-none focus:border-void-accent/60 resize-none leading-relaxed"
      />
      {rawError && <p className="text-xs text-void-danger mt-1">{rawError}</p>}
      <button onClick={save} disabled={saving}
        className="mt-3 px-6 py-2 rounded-lg bg-void-accent text-white text-sm font-medium hover:bg-indigo-500 disabled:opacity-50 transition-colors">
        {saving ? "Saving…" : "Save Searches"}
      </button>
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

// ── API Keys tab ──────────────────────────────────────────────────────────────

function ApiKeysTab() {
  const toast = useToast();
  const [keys, setKeys] = useState<Record<string, string>>({});
  const [edits, setEdits] = useState<Record<string, string>>({});
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    Promise.all([getEnvConfig(), getSystemStatus()])
      .then(([k, s]) => {
        setKeys(k as Record<string, string>);
        setEdits({});
        setStatus(s);
      })
      .finally(() => setLoading(false));
  }, []);

  const save = async () => {
    setSaving(true);
    try {
      await updateEnvConfig(edits);
      toast("API keys saved");
      const fresh = await getEnvConfig();
      setKeys(fresh as Record<string, string>);
      setEdits({});
    } catch {
      toast("Failed to save", false);
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <div className="p-6 space-y-3">{Array.from({length:5}).map((_,i)=><div key={i} className="skeleton h-12" />)}</div>;

  const KEY_LABELS: Record<string, string> = {
    GEMINI_API_KEY: "Gemini API Key",
    OPENAI_API_KEY: "OpenAI API Key",
    LLM_URL: "Local LLM URL",
    LLM_MODEL: "LLM Model Override",
    CAPSOLVER_API_KEY: "CapSolver API Key",
  };

  return (
    <div className="p-6 max-w-xl">
      {status && (
        <div className="mb-6 p-4 rounded-lg bg-void-surface border border-void-border">
          <h3 className="text-xs font-medium text-void-muted uppercase tracking-wider mb-3">System Status</h3>
          <div className="flex flex-wrap gap-3">
            <TierBadge tier={status.tier} />
            <span className="text-xs text-void-muted border border-void-border rounded px-2 py-0.5">{status.tier_label}</span>
            {status.llm_provider && <span className="text-xs text-void-accent border border-void-accent/30 rounded px-2 py-0.5">{status.llm_provider}</span>}
            {status.llm_model && <span className="text-xs text-void-muted font-mono">{status.llm_model}</span>}
          </div>
          <div className="flex gap-4 mt-3">
            <span className={`text-xs ${status.has_chrome ? "text-void-success" : "text-void-muted"}`}>
              {status.has_chrome ? "✓" : "✗"} Chrome
            </span>
            <span className={`text-xs ${status.has_claude_cli ? "text-void-success" : "text-void-muted"}`}>
              {status.has_claude_cli ? "✓" : "✗"} Claude CLI
            </span>
          </div>
        </div>
      )}

      <div className="flex flex-col gap-4">
        {Object.keys(KEY_LABELS).map((key) => {
          const current = keys[key];
          const editVal = edits[key] ?? "";
          const isSet = current === "***" || (current && current !== "***");
          return (
            <div key={key}>
              <label className="block text-xs text-void-muted mb-1.5">{KEY_LABELS[key]}</label>
              <div className="relative">
                <input
                  type={key.endsWith("API_KEY") ? "password" : "text"}
                  value={editVal}
                  onChange={e => setEdits(d => ({ ...d, [key]: e.target.value }))}
                  placeholder={isSet ? "••••••••••• (set — enter new value to change)" : "Not configured"}
                  className="w-full px-3 py-2 rounded-lg bg-void-raised border border-void-border text-sm text-void-text placeholder:text-void-muted/60 focus:outline-none focus:border-void-accent/60 transition-colors pr-16"
                />
                {isSet && !editVal && (
                  <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-void-success">set</span>
                )}
              </div>
            </div>
          );
        })}
      </div>

      <button onClick={save} disabled={saving || Object.keys(edits).every(k => !edits[k])}
        className="mt-6 px-6 py-2 rounded-lg bg-void-accent text-white text-sm font-medium hover:bg-indigo-500 disabled:opacity-50 transition-colors">
        {saving ? "Saving…" : "Save Keys"}
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
  { id: "keys",      label: "API Keys" },
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
        {tab === "keys"      && <ApiKeysTab />}
        {tab === "resume"    && <ResumeTab />}
      </div>
    </div>
  );
}

"use client";

import { useState, useCallback, useRef } from "react";
import { useRouter } from "next/navigation";
import { updateProfile, updateSearches, updateResumeText, uploadResumePdf, parseResumeCv, getTask } from "@/lib/api";
import type { Profile } from "@/lib/types";

// ── Progress bar ──────────────────────────────────────────────────────────────

const STEPS = [
  { id: 1, label: "Resume" },
  { id: 2, label: "Personal" },
  { id: 3, label: "Preferences" },
  { id: 4, label: "Search" },
];

function StepIndicator({ current }: { current: number }) {
  return (
    <div className="flex items-center gap-0 mb-10">
      {STEPS.map((step, i) => (
        <div key={step.id} className="flex items-center flex-1 last:flex-none">
          <div className="flex flex-col items-center gap-1.5">
            <div
              className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-semibold transition-colors ${
                step.id < current
                  ? "bg-void-success text-white"
                  : step.id === current
                  ? "bg-void-accent text-white"
                  : "bg-void-raised border border-void-border text-void-muted"
              }`}
            >
              {step.id < current ? (
                <svg viewBox="0 0 16 16" fill="currentColor" className="w-3.5 h-3.5">
                  <path d="M12.416 3.376a.75.75 0 0 1 .208 1.04l-5 7.5a.75.75 0 0 1-1.154.114l-3-3a.75.75 0 0 1 1.06-1.06l2.353 2.353 4.493-6.74a.75.75 0 0 1 1.04-.207Z" />
                </svg>
              ) : step.id}
            </div>
            <span className={`text-xs ${step.id === current ? "text-void-text" : "text-void-subtle"}`}>
              {step.label}
            </span>
          </div>
          {i < STEPS.length - 1 && (
            <div className={`flex-1 h-px mx-2 mb-5 ${step.id < current ? "bg-void-success/40" : "bg-void-border"}`} />
          )}
        </div>
      ))}
    </div>
  );
}

// ── Shared input styles ───────────────────────────────────────────────────────

const inputCls = "w-full px-3 py-2 rounded-lg bg-void-raised border border-void-border text-sm text-void-text placeholder:text-void-subtle focus:outline-none focus:border-void-accent/60 transition-colors";
const labelCls = "text-xs text-void-muted block mb-1";

// ── Step 1: Resume Import ─────────────────────────────────────────────────────

function Step1({
  onExtracted,
  onResumeText,
  onNext,
}: {
  onExtracted: (data: Partial<Profile>) => void;
  onResumeText: (text: string) => void;
  onNext: () => void;
}) {
  const [mode, setMode] = useState<"upload" | "paste">("upload");
  const [text, setText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [parsing, setParsing] = useState(false);
  const [status, setStatus] = useState<"idle" | "extracted" | "error">("idle");
  const [errorMsg, setErrorMsg] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  const handleUpload = async () => {
    if (!file) return;
    setParsing(true);
    setErrorMsg("");
    try {
      // Upload PDF and extract text via backend task
      const { task_id } = await uploadResumePdf(file);
      // Poll until text is extracted
      for (let i = 0; i < 20; i++) {
        await new Promise((r) => setTimeout(r, 1500));
        const task = await getTask(task_id);
        if (task.status === "done") break;
        if (task.status === "error") throw new Error("Text extraction failed");
      }
      // Now fetch the extracted text from the backend and parse it
      const { getResumeText } = await import("@/lib/api");
      const { text: extracted } = await getResumeText();
      if (!extracted) throw new Error("No text extracted from PDF");
      setText(extracted);
      onResumeText(extracted);
      await doParse(extracted);
    } catch (e) {
      setErrorMsg(String(e));
      setStatus("error");
    } finally {
      setParsing(false);
    }
  };

  const doParse = async (resumeText: string) => {
    try {
      const result = await parseResumeCv(resumeText);
      const ex = result.extracted as Record<string, unknown>;

      // Map flat extracted fields into Profile shape
      const profile: Partial<Profile> = {
        personal: {
          full_name: ex.full_name as string,
          email: ex.email as string,
          phone: ex.phone as string,
          city: ex.city as string,
          country: ex.country as string,
          linkedin_url: ex.linkedin_url as string,
          github_url: ex.github_url as string,
          portfolio_url: ex.portfolio_url as string,
        },
        experience: {
          target_role: ex.target_role as string,
          years_of_experience_total: ex.years_of_experience_total as number,
          education_level: ex.education_level as string,
        },
        skills_boundary: ex.skills as Profile["skills_boundary"],
        resume_facts: {
          preserved_companies: ex.companies as string[],
          preserved_projects: ex.projects as string[],
          preserved_school: ex.school as string,
          real_metrics: ex.metrics as string[],
        },
      };
      onExtracted(profile);
      setStatus("extracted");
    } catch (e) {
      setErrorMsg(String(e));
      setStatus("error");
    }
  };

  const handlePaste = async () => {
    if (!text.trim()) return;
    setParsing(true);
    setErrorMsg("");
    try {
      onResumeText(text);
      await doParse(text);
    } finally {
      setParsing(false);
    }
  };

  return (
    <div>
      <h2 className="text-base font-semibold text-void-text mb-1">Import your resume</h2>
      <p className="text-sm text-void-muted mb-6">
        We'll extract your details automatically. You can review everything in the next steps.
      </p>

      {/* Mode toggle */}
      <div className="flex gap-2 mb-5">
        {(["upload", "paste"] as const).map((m) => (
          <button
            key={m}
            onClick={() => setMode(m)}
            className={`px-4 py-1.5 rounded-lg text-sm transition-colors ${
              mode === m
                ? "bg-void-accent/15 border border-void-accent/40 text-void-accent"
                : "bg-void-raised border border-void-border text-void-muted hover:text-void-text"
            }`}
          >
            {m === "upload" ? "Upload PDF" : "Paste text"}
          </button>
        ))}
      </div>

      {mode === "upload" ? (
        <div>
          <div
            onClick={() => fileRef.current?.click()}
            className={`border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-colors ${
              file ? "border-void-accent/40 bg-void-accent/5" : "border-void-border hover:border-void-accent/30"
            }`}
          >
            <input
              ref={fileRef}
              type="file"
              accept=".pdf"
              className="hidden"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
            <div className="flex flex-col items-center gap-2">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} className="w-8 h-8 text-void-muted">
                <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 0 0-3.375-3.375h-1.5A1.125 1.125 0 0 1 13.5 7.125v-1.5a3.375 3.375 0 0 0-3.375-3.375H8.25m6.75 12-3-3m0 0-3 3m3-3v6m-1.5-15H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 0 0-9-9Z" />
              </svg>
              {file ? (
                <p className="text-sm text-void-accent">{file.name}</p>
              ) : (
                <>
                  <p className="text-sm text-void-text">Drop your resume PDF here</p>
                  <p className="text-xs text-void-muted">or click to browse</p>
                </>
              )}
            </div>
          </div>
          {file && (
            <button
              onClick={handleUpload}
              disabled={parsing}
              className="mt-4 w-full py-2.5 rounded-lg bg-void-accent text-white text-sm font-medium hover:bg-indigo-500 disabled:opacity-40 transition-colors flex items-center justify-center gap-2"
            >
              {parsing ? (
                <><div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin-slow" /> Extracting…</>
              ) : "Extract from PDF"}
            </button>
          )}
        </div>
      ) : (
        <div>
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Paste your resume text here…"
            rows={10}
            className="w-full px-3 py-2.5 rounded-lg bg-void-raised border border-void-border text-sm text-void-text placeholder:text-void-subtle focus:outline-none focus:border-void-accent/60 transition-colors font-mono resize-none"
          />
          <button
            onClick={handlePaste}
            disabled={parsing || !text.trim()}
            className="mt-3 w-full py-2.5 rounded-lg bg-void-accent text-white text-sm font-medium hover:bg-indigo-500 disabled:opacity-40 transition-colors flex items-center justify-center gap-2"
          >
            {parsing ? (
              <><div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin-slow" /> Parsing…</>
            ) : "Parse resume"}
          </button>
        </div>
      )}

      {status === "extracted" && (
        <div className="mt-4 flex items-center gap-2 text-void-success text-sm bg-void-success/10 border border-void-success/20 rounded-lg px-3 py-2">
          <svg viewBox="0 0 16 16" fill="currentColor" className="w-4 h-4 shrink-0">
            <path d="M12.416 3.376a.75.75 0 0 1 .208 1.04l-5 7.5a.75.75 0 0 1-1.154.114l-3-3a.75.75 0 0 1 1.06-1.06l2.353 2.353 4.493-6.74a.75.75 0 0 1 1.04-.207Z" />
          </svg>
          Resume parsed! Your details are pre-filled in the next steps.
        </div>
      )}

      {status === "error" && (
        <p className="mt-4 text-xs text-void-danger bg-void-danger/10 border border-void-danger/20 rounded-lg px-3 py-2">
          {errorMsg || "Failed to parse resume."}
        </p>
      )}
    </div>
  );
}

// ── Step 2: Personal Info ─────────────────────────────────────────────────────

function Step2({
  personal,
  onChange,
}: {
  personal: NonNullable<Profile["personal"]>;
  onChange: (p: NonNullable<Profile["personal"]>) => void;
}) {
  const set = (k: keyof typeof personal) => (e: React.ChangeEvent<HTMLInputElement>) =>
    onChange({ ...personal, [k]: e.target.value });

  return (
    <div>
      <h2 className="text-base font-semibold text-void-text mb-1">Personal information</h2>
      <p className="text-sm text-void-muted mb-6">Used on your applications and tailored resumes.</p>
      <div className="grid grid-cols-2 gap-4">
        <div className="col-span-2 sm:col-span-1">
          <label className={labelCls}>Full name *</label>
          <input className={inputCls} value={personal.full_name ?? ""} onChange={set("full_name")} placeholder="Jane Smith" />
        </div>
        <div className="col-span-2 sm:col-span-1">
          <label className={labelCls}>Preferred name</label>
          <input className={inputCls} value={personal.preferred_name ?? ""} onChange={set("preferred_name")} placeholder="Jane" />
        </div>
        <div className="col-span-2 sm:col-span-1">
          <label className={labelCls}>Email *</label>
          <input className={inputCls} type="email" value={personal.email ?? ""} onChange={set("email")} placeholder="jane@example.com" />
        </div>
        <div className="col-span-2 sm:col-span-1">
          <label className={labelCls}>Phone</label>
          <input className={inputCls} value={personal.phone ?? ""} onChange={set("phone")} placeholder="+1 555 000 0000" />
        </div>
        <div>
          <label className={labelCls}>City</label>
          <input className={inputCls} value={personal.city ?? ""} onChange={set("city")} placeholder="San Francisco" />
        </div>
        <div>
          <label className={labelCls}>Country</label>
          <input className={inputCls} value={personal.country ?? ""} onChange={set("country")} placeholder="USA" />
        </div>
        <div className="col-span-2">
          <label className={labelCls}>LinkedIn URL</label>
          <input className={inputCls} value={personal.linkedin_url ?? ""} onChange={set("linkedin_url")} placeholder="https://linkedin.com/in/..." />
        </div>
        <div className="col-span-2">
          <label className={labelCls}>GitHub URL</label>
          <input className={inputCls} value={personal.github_url ?? ""} onChange={set("github_url")} placeholder="https://github.com/..." />
        </div>
      </div>
    </div>
  );
}

// ── Step 3: Preferences ───────────────────────────────────────────────────────

function Step3({
  experience,
  workAuth,
  onExpChange,
  onAuthChange,
}: {
  experience: NonNullable<Profile["experience"]>;
  workAuth: NonNullable<Profile["work_authorization"]>;
  onExpChange: (e: NonNullable<Profile["experience"]>) => void;
  onAuthChange: (a: NonNullable<Profile["work_authorization"]>) => void;
}) {
  return (
    <div>
      <h2 className="text-base font-semibold text-void-text mb-1">Job preferences</h2>
      <p className="text-sm text-void-muted mb-6">Help the AI score and tailor jobs to your goals.</p>
      <div className="flex flex-col gap-4">
        <div>
          <label className={labelCls}>Target role / job title</label>
          <input
            className={inputCls}
            value={experience.target_role ?? ""}
            onChange={(e) => onExpChange({ ...experience, target_role: e.target.value })}
            placeholder="Software Engineer"
          />
        </div>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className={labelCls}>Years of experience</label>
            <input
              className={inputCls}
              type="number"
              min={0}
              max={50}
              value={experience.years_of_experience_total ?? ""}
              onChange={(e) => onExpChange({ ...experience, years_of_experience_total: Number(e.target.value) })}
            />
          </div>
          <div>
            <label className={labelCls}>Education level</label>
            <select
              className={inputCls}
              value={experience.education_level ?? ""}
              onChange={(e) => onExpChange({ ...experience, education_level: e.target.value })}
            >
              <option value="">— Select —</option>
              <option>High School</option>
              <option>Associate&apos;s Degree</option>
              <option>Bachelor&apos;s Degree</option>
              <option>Master&apos;s Degree</option>
              <option>PhD</option>
              <option>Bootcamp / Self-taught</option>
            </select>
          </div>
        </div>
        <div className="flex flex-col gap-3 pt-2">
          <label className="flex items-center gap-3 cursor-pointer">
            <input
              type="checkbox"
              className="accent-void-accent w-4 h-4"
              checked={workAuth.legally_authorized_to_work ?? false}
              onChange={(e) => onAuthChange({ ...workAuth, legally_authorized_to_work: e.target.checked })}
            />
            <span className="text-sm text-void-text">Legally authorized to work</span>
          </label>
          <label className="flex items-center gap-3 cursor-pointer">
            <input
              type="checkbox"
              className="accent-void-accent w-4 h-4"
              checked={workAuth.require_sponsorship ?? false}
              onChange={(e) => onAuthChange({ ...workAuth, require_sponsorship: e.target.checked })}
            />
            <span className="text-sm text-void-text">Require visa sponsorship</span>
          </label>
        </div>
      </div>
    </div>
  );
}

// ── Step 4: Search Config ─────────────────────────────────────────────────────

const ALL_BOARDS = ["indeed", "linkedin", "glassdoor", "zip_recruiter", "google"];

const SUGGESTED_QUERIES = [
  "Software Engineer",
  "Frontend Engineer",
  "Backend Engineer",
  "Full Stack Engineer",
  "Data Engineer",
  "Data Scientist",
  "Machine Learning Engineer",
  "DevOps Engineer",
  "Platform Engineer",
  "Site Reliability Engineer",
  "Product Manager",
  "Engineering Manager",
  "Mobile Engineer",
  "iOS Engineer",
  "Android Engineer",
  "Python Developer",
  "TypeScript Developer",
  "Go Engineer",
  "Security Engineer",
  "QA Engineer",
];

function QueryPicker({
  queries,
  setQueries,
}: {
  queries: string[];
  setQueries: (v: string[]) => void;
}) {
  const [customInput, setCustomInput] = useState("");

  const toggle = (q: string) => {
    const normalized = q.toLowerCase();
    const exists = queries.some((x) => x.toLowerCase() === normalized);
    setQueries(exists ? queries.filter((x) => x.toLowerCase() !== normalized) : [...queries, q]);
  };

  const addCustom = () => {
    const trimmed = customInput.trim();
    if (!trimmed) return;
    if (!queries.some((x) => x.toLowerCase() === trimmed.toLowerCase())) {
      setQueries([...queries, trimmed]);
    }
    setCustomInput("");
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") { e.preventDefault(); addCustom(); }
  };

  const isSelected = (q: string) => queries.some((x) => x.toLowerCase() === q.toLowerCase());

  return (
    <div className="flex flex-col gap-3">
      {/* Selected tags */}
      {queries.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {queries.map((q) => (
            <span
              key={q}
              className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-void-accent/15 border border-void-accent/40 text-void-accent text-xs font-medium"
            >
              {q}
              <button
                type="button"
                onClick={() => toggle(q)}
                className="text-void-accent/60 hover:text-void-accent leading-none"
                aria-label={`Remove ${q}`}
              >
                ×
              </button>
            </span>
          ))}
        </div>
      )}

      {/* Suggestions */}
      <div>
        <p className="text-xs text-void-subtle mb-1.5">Suggestions — click to add</p>
        <div className="flex flex-wrap gap-1.5">
          {SUGGESTED_QUERIES.filter((q) => !isSelected(q)).map((q) => (
            <button
              key={q}
              type="button"
              onClick={() => toggle(q)}
              className="px-2.5 py-1 rounded-lg text-xs bg-void-raised border border-void-border text-void-muted hover:text-void-text hover:border-void-accent/30 transition-colors"
            >
              + {q}
            </button>
          ))}
        </div>
      </div>

      {/* Custom input */}
      <div className="flex gap-2">
        <input
          className={inputCls + " flex-1"}
          value={customInput}
          onChange={(e) => setCustomInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Add a custom query…"
        />
        <button
          type="button"
          onClick={addCustom}
          disabled={!customInput.trim()}
          className="px-3 py-2 rounded-lg bg-void-raised border border-void-border text-sm text-void-muted hover:text-void-text disabled:opacity-30 transition-colors"
        >
          Add
        </button>
      </div>
    </div>
  );
}

function Step4({
  queries,
  setQueries,
  locations,
  setLocations,
  boards,
  setBoards,
  hoursOld,
  setHoursOld,
}: {
  queries: string[];
  setQueries: (v: string[]) => void;
  locations: string;
  setLocations: (v: string) => void;
  boards: string[];
  setBoards: (v: string[]) => void;
  hoursOld: number;
  setHoursOld: (v: number) => void;
}) {
  const toggle = (b: string) =>
    setBoards(boards.includes(b) ? boards.filter((x) => x !== b) : [...boards, b]);

  return (
    <div>
      <h2 className="text-base font-semibold text-void-text mb-1">Job search config</h2>
      <p className="text-sm text-void-muted mb-6">Configure where and what to search for.</p>
      <div className="flex flex-col gap-5">
        <div>
          <label className={labelCls}>Job search queries</label>
          <QueryPicker queries={queries} setQueries={setQueries} />
        </div>
        <div>
          <label className={labelCls}>Locations (comma-separated)</label>
          <input
            className={inputCls}
            value={locations}
            onChange={(e) => setLocations(e.target.value)}
            placeholder="San Francisco CA, Remote"
          />
        </div>
        <div>
          <label className={labelCls}>Job boards</label>
          <div className="flex flex-wrap gap-2 mt-1.5">
            {ALL_BOARDS.map((b) => (
              <button
                key={b}
                type="button"
                onClick={() => toggle(b)}
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
        </div>
        <div className="w-40">
          <label className={labelCls}>Max job age (hours)</label>
          <input
            className={inputCls}
            type="number"
            min={1}
            max={720}
            value={hoursOld}
            onChange={(e) => setHoursOld(Number(e.target.value))}
          />
        </div>
      </div>
    </div>
  );
}


// ── Main wizard ───────────────────────────────────────────────────────────────

export default function SetupPage() {
  const router = useRouter();
  const [step, setStep] = useState(1);
  const [saving, setSaving] = useState(false);

  // Profile state
  const [personal, setPersonal] = useState<NonNullable<Profile["personal"]>>({});
  const [experience, setExperience] = useState<NonNullable<Profile["experience"]>>({});
  const [workAuth, setWorkAuth] = useState<NonNullable<Profile["work_authorization"]>>({});
  const [skills, setSkills] = useState<NonNullable<Profile["skills_boundary"]>>({});
  const [resumeFacts, setResumeFacts] = useState<NonNullable<Profile["resume_facts"]>>({});
  const [rawResumeText, setRawResumeText] = useState("");

  // Search config state
  const [queries, setQueries] = useState<string[]>(["Software Engineer", "Backend Engineer"]);
  const [locations, setLocations] = useState("Remote");
  const [boards, setBoards] = useState(["indeed", "linkedin"]);
  const [hoursOld, setHoursOld] = useState(72);


  const handleExtracted = useCallback((extracted: Partial<Profile>) => {
    if (extracted.personal) setPersonal((p) => ({ ...extracted.personal, ...p }));
    if (extracted.experience) setExperience((e) => ({ ...extracted.experience, ...e }));
    if (extracted.work_authorization) setWorkAuth((a) => ({ ...extracted.work_authorization, ...a }));
    if (extracted.skills_boundary) setSkills(extracted.skills_boundary!);
    if (extracted.resume_facts) setResumeFacts(extracted.resume_facts!);
  }, []);

  const canAdvance = () => {
    if (step === 2) return !!personal.full_name?.trim();
    return true;
  };

  const handleComplete = async () => {
    setSaving(true);
    try {
      const profile: Profile = {
        personal,
        experience,
        work_authorization: workAuth,
        skills_boundary: skills,
        resume_facts: resumeFacts,
      };
      await updateProfile(profile);

      // Save raw resume text so the scorer can use it
      if (rawResumeText.trim()) {
        await updateResumeText(rawResumeText);
      }

      // Save searches config
      const locationList = locations.split(",").map((l) => l.trim()).filter(Boolean);
      await updateSearches({
        queries: queries.map((q, i) => ({ query: q, tier: i < 3 ? 1 : 2 })),
        locations: locationList.map((l) => ({ location: l, remote: l.toLowerCase().includes("remote") })),
        boards,
        defaults: { results_per_site: 100, hours_old: hoursOld },
      });

      // Kick off scoring immediately — profile + resume are now saved
      import("@/lib/api").then(({ maybeScore }) => maybeScore().catch(() => null));

      router.replace("/jobs");
    } catch (e) {
      console.error(e);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="min-h-screen bg-void-bg flex items-start justify-center pt-12 px-4 pb-12">
      <div className="w-full max-w-xl">
        {/* Header */}
        <div className="mb-8">
          <p className="text-xs text-void-muted font-medium uppercase tracking-wider mb-1">Setup</p>
          <h1 className="text-2xl font-semibold text-void-text">Welcome to ApplyPilot</h1>
          <p className="text-sm text-void-muted mt-1">Let&apos;s get you set up in a few steps.</p>
        </div>

        <StepIndicator current={step} />

        {/* Step content */}
        <div className="bg-void-surface border border-void-border rounded-2xl p-6 min-h-[320px]">
          {step === 1 && <Step1 onExtracted={handleExtracted} onResumeText={setRawResumeText} onNext={() => setStep(2)} />}
          {step === 2 && <Step2 personal={personal} onChange={setPersonal} />}
          {step === 3 && (
            <Step3
              experience={experience}
              workAuth={workAuth}
              onExpChange={setExperience}
              onAuthChange={setWorkAuth}
            />
          )}
          {step === 4 && (
            <Step4
              queries={queries} setQueries={setQueries}
              locations={locations} setLocations={setLocations}
              boards={boards} setBoards={setBoards}
              hoursOld={hoursOld} setHoursOld={setHoursOld}
            />
          )}
        </div>

        {/* Navigation */}
        <div className="flex items-center justify-between mt-5">
          {step > 1 ? (
            <button
              onClick={() => setStep((s) => s - 1)}
              className="px-4 py-2 rounded-lg text-sm text-void-muted hover:text-void-text border border-void-border hover:border-void-accent/30 transition-colors"
            >
              ← Back
            </button>
          ) : (
            <button
              onClick={() => router.replace("/jobs")}
              className="px-4 py-2 rounded-lg text-sm text-void-subtle hover:text-void-muted transition-colors"
            >
              Skip setup
            </button>
          )}

          {step < STEPS.length ? (
            <button
              onClick={() => setStep((s) => s + 1)}
              disabled={!canAdvance()}
              className="px-5 py-2.5 rounded-lg bg-void-accent text-white text-sm font-medium hover:bg-indigo-500 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              Continue →
            </button>
          ) : (
            <button
              onClick={handleComplete}
              disabled={saving}
              className="px-5 py-2.5 rounded-lg bg-void-success text-white text-sm font-medium hover:bg-emerald-500 disabled:opacity-40 transition-colors flex items-center gap-2"
            >
              {saving ? (
                <><div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin-slow" /> Saving…</>
              ) : "Get started →"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

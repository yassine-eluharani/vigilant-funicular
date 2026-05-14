"use client";

import { useState, useCallback, useRef, useMemo, useEffect, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import {
  getResumeText,
  getTask,
  maybeScore,
  parseResumeCv,
  updateProfile,
  updateResumeText,
  updateSearches,
  uploadResumePdf,
} from "@/lib/api";
import type { ExtractedResume, Profile } from "@/lib/types";

// ── Step metadata ────────────────────────────────────────────────────────────

const STEPS = [
  { id: 1, label: "Resume",      blurb: "Upload or paste — we'll do the rest." },
  { id: 2, label: "Personal",    blurb: "Your contact details for applications." },
  { id: 3, label: "Preferences", blurb: "Goals and work-authorization context." },
  { id: 4, label: "Search",      blurb: "Where and what to look for." },
] as const;

// ── Vertical narrative rail ──────────────────────────────────────────────────

function StepRail({
  current,
  totalSteps,
}: {
  current: number;
  totalSteps: number;
}) {
  // Fill ratio for the connecting line — ranges from 0 (step 1 active, no
  // progress) to 1 (final step active or completed). We bias the fill so it
  // visually communicates "you've made progress" once the user passes step 1.
  const filledRatio = Math.max(0, (current - 1) / (totalSteps - 1));
  return (
    <div className="relative flex flex-col items-center pt-2 pb-2 w-12 shrink-0">
      {/* Vertical track */}
      <div className="absolute top-4 bottom-4 left-1/2 -translate-x-1/2 w-px bg-void-border" aria-hidden />
      {/* Filled portion */}
      <div
        className="absolute left-1/2 -translate-x-1/2 w-px bg-void-accent transition-all duration-500"
        style={{
          top: "1rem",
          height: `calc((100% - 2rem) * ${filledRatio})`,
        }}
        aria-hidden
      />
      {/* Numbered dots */}
      <div className="relative flex flex-col justify-between flex-1 w-full items-center">
        {STEPS.map((step) => {
          const state =
            step.id < current ? "done" : step.id === current ? "active" : "future";
          return (
            <div
              key={step.id}
              className={`
                relative z-10 w-8 h-8 rounded-full flex items-center justify-center text-xs font-semibold
                transition-all duration-300
                ${state === "done" ? "bg-void-accent text-white" :
                  state === "active" ? "bg-void-accent text-white ring-4 ring-void-accent/20" :
                  "bg-void-raised border border-void-border text-void-muted"
                }
              `}
            >
              {state === "done" ? (
                <svg viewBox="0 0 16 16" fill="currentColor" className="w-3.5 h-3.5">
                  <path d="M12.416 3.376a.75.75 0 0 1 .208 1.04l-5 7.5a.75.75 0 0 1-1.154.114l-3-3a.75.75 0 0 1 1.06-1.06l2.353 2.353 4.493-6.74a.75.75 0 0 1 1.04-.207Z" />
                </svg>
              ) : step.id}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── Accordion shell ──────────────────────────────────────────────────────────

function StepAccordion({
  index,
  current,
  label,
  blurb,
  summary,
  onClick,
  children,
}: {
  index: number;
  current: number;
  label: string;
  blurb: string;
  summary?: ReactNode;
  onClick: () => void;
  children?: ReactNode;
}) {
  const state: "done" | "active" | "future" =
    index < current ? "done" : index === current ? "active" : "future";

  const interactive = state !== "active";

  return (
    <section
      className={`
        rounded-xl border transition-colors
        ${state === "active" ? "bg-void-surface border-void-accent/40" : "bg-void-surface/60 border-void-border"}
      `}
    >
      <button
        type="button"
        onClick={interactive ? onClick : undefined}
        disabled={!interactive}
        className={`w-full text-left px-5 py-4 flex items-start gap-4 ${interactive ? "cursor-pointer" : "cursor-default"}`}
      >
        <div className="flex-1 min-w-0">
          <p className={`text-xs uppercase tracking-wider mb-0.5 ${state === "active" ? "text-void-accent" : "text-void-subtle"}`}>
            Step {index}
          </p>
          <h3 className={`font-display text-2xl leading-tight ${state === "future" ? "text-void-muted" : "text-void-text"}`}>
            {label}
          </h3>
          {state === "active" && (
            <p className="text-sm text-void-muted mt-1">{blurb}</p>
          )}
          {state !== "active" && summary && (
            <div className="mt-1.5 text-sm text-void-muted">{summary}</div>
          )}
          {state === "future" && !summary && (
            <p className="text-sm text-void-subtle mt-1">{blurb}</p>
          )}
        </div>
      </button>
      {state === "active" && (
        <div className="px-5 pb-5 pt-1">
          {children}
        </div>
      )}
    </section>
  );
}

// ── Shared input styles ───────────────────────────────────────────────────────

const inputCls = "w-full px-3 py-2 rounded-lg bg-void-raised border border-void-border text-sm text-void-text placeholder:text-void-subtle focus:outline-none focus:border-void-accent/60 transition-colors";
const labelCls = "text-xs text-void-muted block mb-1";

// ── Step 1: Resume Import (with wow moment) ──────────────────────────────────

interface ExtractedChip {
  label: string;
  value: string;
}

function chipsFromExtracted(extracted: Partial<Profile>): ExtractedChip[] {
  const chips: ExtractedChip[] = [];
  const p = extracted.personal ?? {};
  if (p.full_name) chips.push({ label: "Name", value: p.full_name });
  if (p.email) chips.push({ label: "Email", value: p.email });
  if (p.linkedin_url) chips.push({ label: "LinkedIn", value: "linked" });
  if (p.github_url) chips.push({ label: "GitHub", value: "linked" });
  const exp = extracted.experience ?? {};
  if (exp.target_role) chips.push({ label: "Role", value: exp.target_role });
  if (typeof exp.years_of_experience_total === "number") {
    chips.push({ label: "Years", value: `${exp.years_of_experience_total}` });
  }
  const facts = extracted.resume_facts ?? {};
  const projects = facts.preserved_projects;
  if (Array.isArray(projects) && projects.length > 0) {
    chips.push({ label: "Projects", value: `${projects.length}` });
  }
  const companies = facts.preserved_companies;
  if (Array.isArray(companies) && companies.length > 0) {
    chips.push({ label: "Companies", value: `${companies.length}` });
  }
  const skills = extracted.skills_boundary;
  // skills_boundary is a record; pick 3 leaf values for the chip.
  if (skills && typeof skills === "object") {
    const flat: string[] = [];
    for (const v of Object.values(skills)) {
      if (Array.isArray(v)) {
        for (const item of v) if (typeof item === "string") flat.push(item);
      }
    }
    if (flat.length > 0) {
      chips.push({ label: "Skills", value: flat.slice(0, 3).join(", ") });
    }
  }
  return chips;
}

function Step1({
  onExtracted,
  onResumeText,
  onAdvance,
}: {
  onExtracted: (data: Partial<Profile>) => void;
  onResumeText: (text: string) => void;
  onAdvance: () => void;
}) {
  const [mode, setMode] = useState<"upload" | "paste">("upload");
  const [text, setText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [parsing, setParsing] = useState(false);
  const [phase, setPhase] = useState<"idle" | "scanning" | "chips" | "done" | "error">("idle");
  const [chips, setChips] = useState<ExtractedChip[]>([]);
  const [errorMsg, setErrorMsg] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  const runWowMoment = useCallback(
    (extracted: Partial<Profile>) => {
      // Phase 1: scanning sweep (1.2s)
      setPhase("scanning");
      const built = chipsFromExtracted(extracted);
      // Fallback chips if extraction returned nothing recognisable.
      const finalChips = built.length > 0
        ? built
        : [{ label: "Resume", value: "parsed" }];
      setTimeout(() => {
        // Phase 2: chips fly out
        setChips(finalChips);
        setPhase("chips");
        // Phase 3: settle — reveal "advance" CTA
        const totalChipDelay = finalChips.length * 80 + 400;
        setTimeout(() => setPhase("done"), totalChipDelay);
      }, 1200);
    },
    []
  );

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
      const { text: extracted } = await getResumeText();
      if (!extracted) throw new Error("No text extracted from PDF");
      setText(extracted);
      onResumeText(extracted);
      await doParse(extracted);
    } catch (e) {
      setErrorMsg(String(e));
      setPhase("error");
    } finally {
      setParsing(false);
    }
  };

  const doParse = async (resumeText: string) => {
    try {
      const result = await parseResumeCv(resumeText);
      const ex: ExtractedResume = result.extracted ?? {};

      // Map flat extracted fields into Profile shape
      const profile: Partial<Profile> = {
        personal: {
          full_name: ex.full_name ?? undefined,
          email: ex.email ?? undefined,
          phone: ex.phone ?? undefined,
          city: ex.city ?? undefined,
          country: ex.country ?? undefined,
          linkedin_url: ex.linkedin_url ?? undefined,
          github_url: ex.github_url ?? undefined,
          portfolio_url: ex.portfolio_url ?? undefined,
        },
        experience: {
          target_role: ex.target_role ?? undefined,
          years_of_experience_total: ex.years_of_experience_total ?? undefined,
          education_level: ex.education_level ?? undefined,
        },
        skills_boundary: ex.skills ?? undefined,
        resume_facts: {
          preserved_companies: ex.companies ?? undefined,
          preserved_projects: ex.projects ?? undefined,
          preserved_school: ex.school ?? undefined,
          real_metrics: ex.metrics ?? undefined,
        },
      };
      onExtracted(profile);
      runWowMoment(profile);
    } catch (e) {
      setErrorMsg(String(e));
      setPhase("error");
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

  const showWow = phase === "scanning" || phase === "chips" || phase === "done";

  return (
    <div>
      {/* Mode toggle */}
      {!showWow && (
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
      )}

      {/* Wow-moment view — preempts the inputs once parsing kicks off. */}
      {showWow ? (
        <WowMoment
          fileName={file?.name ?? "resume.txt"}
          phase={phase}
          chips={chips}
          onAdvance={onAdvance}
        />
      ) : mode === "upload" ? (
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
              className="mt-4 w-full py-2.5 rounded-lg bg-void-accent text-white text-sm font-medium hover:bg-void-accent-hover disabled:opacity-40 transition-colors flex items-center justify-center gap-2"
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
            className="mt-3 w-full py-2.5 rounded-lg bg-void-accent text-white text-sm font-medium hover:bg-void-accent-hover disabled:opacity-40 transition-colors flex items-center justify-center gap-2"
          >
            {parsing ? (
              <><div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin-slow" /> Parsing…</>
            ) : "Parse resume"}
          </button>
        </div>
      )}

      {phase === "error" && (
        <p className="mt-4 text-xs text-void-danger bg-void-danger/10 border border-void-danger/20 rounded-lg px-3 py-2">
          {errorMsg || "Failed to parse resume."}
        </p>
      )}
    </div>
  );
}

// ── Wow moment ───────────────────────────────────────────────────────────────

function WowMoment({
  fileName,
  phase,
  chips,
  onAdvance,
}: {
  fileName: string;
  phase: "idle" | "scanning" | "chips" | "done" | "error";
  chips: ExtractedChip[];
  onAdvance: () => void;
}) {
  return (
    <div className="flex flex-col items-center text-center py-4">
      {/* Scoped keyframes for the scan sweep — one-shot keyframes for this
          page only. Foundation utilities own everything else. */}
      <style
        dangerouslySetInnerHTML={{
          __html: `
@keyframes ap-scan {
  from { top: 0%; opacity: 0; }
  10%  { opacity: 1; }
  90%  { opacity: 1; }
  to   { top: 100%; opacity: 0; }
}
.ap-scanning .ap-scan-line {
  animation: ap-scan 1.2s var(--ease-out-quart) forwards;
}
`,
        }}
      />
      <div className={`relative w-40 h-52 ${phase === "scanning" ? "ap-scanning" : ""}`}>
        {/* Document frame */}
        <div className="absolute inset-0 rounded-lg border border-void-accent/40 bg-void-raised flex flex-col items-center justify-center gap-2 overflow-hidden">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} className="w-10 h-10 text-void-accent">
            <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 0 0-3.375-3.375h-1.5A1.125 1.125 0 0 1 13.5 7.125v-1.5a3.375 3.375 0 0 0-3.375-3.375H8.25m6.75 12-3-3m0 0-3 3m3-3v6m-1.5-15H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 0 0-9-9Z" />
          </svg>
          <p className="text-xs text-void-muted px-3 truncate max-w-full">{fileName}</p>
          {/* Decorative redacted lines */}
          <div className="w-full px-5 mt-2 flex flex-col gap-1.5 opacity-50">
            {Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="h-1 rounded bg-void-muted/40" style={{ width: `${60 + ((i * 13) % 35)}%` }} />
            ))}
          </div>
          {/* The scanning line */}
          {phase === "scanning" && (
            <div
              className="ap-scan-line absolute left-0 right-0 h-0.5 bg-void-accent shadow-[0_0_12px_var(--void-accent)]"
              style={{ top: "0%" }}
            />
          )}
        </div>
      </div>

      {/* Status copy */}
      <p className="font-display text-xl text-void-text mt-6">
        {phase === "scanning" && "Reading your resume…"}
        {(phase === "chips" || phase === "done") && "Got it."}
      </p>

      {/* Chips — fly out one at a time */}
      {(phase === "chips" || phase === "done") && (
        <div className="flex flex-wrap justify-center gap-2 mt-5 max-w-md">
          {chips.map((c, i) => (
            <span
              key={`${c.label}-${i}`}
              className="animate-fade-up inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-void-accent/10 border border-void-accent/30 text-xs text-void-text"
              style={{ animationDelay: `${i * 80}ms`, animationFillMode: "both" }}
            >
              <span className="text-void-accent font-medium">{c.label}:</span>
              <span className="text-void-text">{c.value}</span>
            </span>
          ))}
        </div>
      )}

      {/* Advance CTA */}
      {phase === "done" && (
        <button
          onClick={onAdvance}
          className="animate-fade-up mt-6 px-5 py-2.5 rounded-lg bg-void-accent text-white text-sm font-medium hover:bg-void-accent-hover transition-colors"
          style={{ animationDelay: `${chips.length * 80 + 100}ms`, animationFillMode: "both" }}
        >
          Review pre-filled details →
        </button>
      )}
    </div>
  );
}

// ── Step 2: Personal Info ─────────────────────────────────────────────────────

// Track which fields were just pre-filled — used to pulse them briefly.
function PrefillField({
  label,
  highlight,
  children,
}: {
  label: ReactNode;
  highlight: boolean;
  children: ReactNode;
}) {
  // 600ms pulse window when `highlight` flips to true. We don't unset it —
  // the parent controls the lifetime by passing `highlight={false}` later.
  return (
    <div>
      <label className={labelCls}>{label}</label>
      <div
        className={`rounded-lg transition-colors duration-500 ${
          highlight ? "bg-void-accent/10 ring-1 ring-void-accent/40" : ""
        }`}
      >
        {children}
      </div>
    </div>
  );
}

function Step2({
  personal,
  onChange,
  highlightedFields,
}: {
  personal: NonNullable<Profile["personal"]>;
  onChange: (p: NonNullable<Profile["personal"]>) => void;
  highlightedFields: Set<string>;
}) {
  const set = (k: keyof typeof personal) => (e: React.ChangeEvent<HTMLInputElement>) =>
    onChange({ ...personal, [k]: e.target.value });

  return (
    <div>
      <div className="grid grid-cols-2 gap-4">
        <div className="col-span-2 sm:col-span-1">
          <PrefillField label="Full name *" highlight={highlightedFields.has("full_name")}>
            <input className={inputCls} value={personal.full_name ?? ""} onChange={set("full_name")} placeholder="Jane Smith" />
          </PrefillField>
        </div>
        <div className="col-span-2 sm:col-span-1">
          <PrefillField label="Preferred name" highlight={highlightedFields.has("preferred_name")}>
            <input className={inputCls} value={personal.preferred_name ?? ""} onChange={set("preferred_name")} placeholder="Jane" />
          </PrefillField>
        </div>
        <div className="col-span-2 sm:col-span-1">
          <PrefillField label="Email *" highlight={highlightedFields.has("email")}>
            <input className={inputCls} type="email" value={personal.email ?? ""} onChange={set("email")} placeholder="jane@example.com" />
          </PrefillField>
        </div>
        <div className="col-span-2 sm:col-span-1">
          <PrefillField label="Phone" highlight={highlightedFields.has("phone")}>
            <input className={inputCls} value={personal.phone ?? ""} onChange={set("phone")} placeholder="+1 555 000 0000" />
          </PrefillField>
        </div>
        <PrefillField label="City" highlight={highlightedFields.has("city")}>
          <input className={inputCls} value={personal.city ?? ""} onChange={set("city")} placeholder="San Francisco" />
        </PrefillField>
        <PrefillField label="Country" highlight={highlightedFields.has("country")}>
          <input className={inputCls} value={personal.country ?? ""} onChange={set("country")} placeholder="USA" />
        </PrefillField>
        <div className="col-span-2">
          <PrefillField label="LinkedIn URL" highlight={highlightedFields.has("linkedin_url")}>
            <input className={inputCls} value={personal.linkedin_url ?? ""} onChange={set("linkedin_url")} placeholder="https://linkedin.com/in/..." />
          </PrefillField>
        </div>
        <div className="col-span-2">
          <PrefillField label="GitHub URL" highlight={highlightedFields.has("github_url")}>
            <input className={inputCls} value={personal.github_url ?? ""} onChange={set("github_url")} placeholder="https://github.com/..." />
          </PrefillField>
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

  // Pre-fill highlight set — populated when extraction completes, cleared
  // after the pulse settles (~600ms). The set tracks personal-field keys.
  const [highlightedFields, setHighlightedFields] = useState<Set<string>>(new Set());

  const handleExtracted = useCallback((extracted: Partial<Profile>) => {
    const filled = new Set<string>();
    if (extracted.personal) {
      for (const [k, v] of Object.entries(extracted.personal)) {
        if (v !== undefined && v !== null && v !== "") filled.add(k);
      }
      setPersonal((p) => ({ ...extracted.personal, ...p }));
    }
    if (extracted.experience) setExperience((e) => ({ ...extracted.experience, ...e }));
    if (extracted.work_authorization) setWorkAuth((a) => ({ ...extracted.work_authorization, ...a }));
    if (extracted.skills_boundary) setSkills(extracted.skills_boundary!);
    if (extracted.resume_facts) setResumeFacts(extracted.resume_facts!);
    setHighlightedFields(filled);
  }, []);

  // Clear highlights ~600ms after entering step 2 so the pulse fades out.
  useEffect(() => {
    if (step !== 2 || highlightedFields.size === 0) return;
    const id = setTimeout(() => setHighlightedFields(new Set()), 600);
    return () => clearTimeout(id);
  }, [step, highlightedFields]);

  const canAdvance = () => {
    if (step === 2) return !!personal.full_name?.trim();
    return true;
  };

  // Summary copy for collapsed (already-filled-in) accordion sections.
  const summaryFor = (id: number): ReactNode => {
    if (id === 1) {
      const len = rawResumeText.length;
      if (len === 0) return null;
      return <span>Resume parsed · {len.toLocaleString()} chars</span>;
    }
    if (id === 2) {
      if (!personal.full_name && !personal.email) return null;
      return (
        <span>
          {personal.full_name ?? "—"}
          {personal.email ? ` · ${personal.email}` : ""}
        </span>
      );
    }
    if (id === 3) {
      if (!experience.target_role && !experience.years_of_experience_total) return null;
      return (
        <span>
          {experience.target_role ?? "Role not set"}
          {experience.years_of_experience_total != null ? ` · ${experience.years_of_experience_total}y` : ""}
        </span>
      );
    }
    if (id === 4) {
      if (queries.length === 0) return null;
      return <span>{queries.length} {queries.length === 1 ? "query" : "queries"} · {boards.length} boards</span>;
    }
    return null;
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
      maybeScore().catch(() => null);

      router.replace("/apply");
    } catch (e) {
      console.error(e);
    } finally {
      setSaving(false);
    }
  };

  const totalSteps = STEPS.length;

  // For each step, decide which body to render in the active accordion slot.
  const stepBody = useMemo(() => ({
    1: (
      <Step1
        onExtracted={handleExtracted}
        onResumeText={setRawResumeText}
        onAdvance={() => setStep(2)}
      />
    ),
    2: <Step2 personal={personal} onChange={setPersonal} highlightedFields={highlightedFields} />,
    3: (
      <Step3
        experience={experience}
        workAuth={workAuth}
        onExpChange={setExperience}
        onAuthChange={setWorkAuth}
      />
    ),
    4: (
      <Step4
        queries={queries} setQueries={setQueries}
        locations={locations} setLocations={setLocations}
        boards={boards} setBoards={setBoards}
        hoursOld={hoursOld} setHoursOld={setHoursOld}
      />
    ),
  } as Record<number, ReactNode>), [handleExtracted, personal, highlightedFields, experience, workAuth, queries, locations, boards, hoursOld]);

  return (
    <main className="page-accent-setup min-h-screen bg-void-bg flex items-start justify-center pt-12 px-4 pb-12">
      <div className="w-full max-w-3xl">
        {/* Header */}
        <div className="mb-10">
          <p className="text-xs text-void-muted font-medium uppercase tracking-wider mb-1">Setup</p>
          <h1 className="font-display text-4xl text-void-text mb-2 leading-tight">
            Welcome to ApplyPilot
          </h1>
          <p className="text-[18px] text-void-muted leading-relaxed">
            Four steps. We&apos;ll have you scoring jobs against your CV in about a minute.
          </p>
        </div>

        {/* Vertical narrative — rail on the left, accordions on the right */}
        <div className="flex gap-6 items-stretch">
          <StepRail current={step} totalSteps={totalSteps} />

          <div className="flex-1 flex flex-col gap-3">
            {STEPS.map((s) => (
              <StepAccordion
                key={s.id}
                index={s.id}
                current={step}
                label={s.label}
                blurb={s.blurb}
                summary={summaryFor(s.id)}
                onClick={() => setStep(s.id)}
              >
                {stepBody[s.id]}
              </StepAccordion>
            ))}

            {/* Navigation */}
            <div className="flex items-center justify-between mt-3">
              {step > 1 ? (
                <button
                  onClick={() => setStep((s) => s - 1)}
                  className="px-4 py-2 rounded-lg text-sm text-void-muted hover:text-void-text border border-void-border hover:border-void-accent/30 transition-colors"
                >
                  ← Back
                </button>
              ) : (
                <button
                  onClick={() => router.replace("/apply")}
                  className="px-4 py-2 rounded-lg text-sm text-void-subtle hover:text-void-muted transition-colors"
                >
                  Skip setup
                </button>
              )}

              {step < totalSteps ? (
                <button
                  onClick={() => setStep((s) => s + 1)}
                  disabled={!canAdvance()}
                  className="px-5 py-2.5 rounded-lg bg-void-accent text-white text-sm font-medium hover:bg-void-accent-hover disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
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
      </div>
    </main>
  );
}

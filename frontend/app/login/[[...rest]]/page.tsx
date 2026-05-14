"use client";

import { Suspense } from "react";
import { SignIn } from "@clerk/nextjs";
import { dark } from "@clerk/themes";
import { useSearchParams } from "next/navigation";
import Link from "next/link";

function LoginPanel() {
  const params = useSearchParams();
  const next = params.get("next") ?? "/apply";

  return (
    <div className="min-h-screen flex">
      {/* Left panel — literary moment */}
      <div className="hidden lg:flex flex-col justify-between w-[45%] bg-void-surface border-r border-void-border p-12 relative overflow-hidden">
        <div className="absolute inset-0 pointer-events-none">
          <div className="absolute bottom-1/4 left-1/2 -translate-x-1/2 w-[500px] h-[500px] bg-[var(--void-accent)]/8 rounded-full blur-[120px]" />
        </div>

        <Link href="/" className="relative flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-[var(--void-accent)] flex items-center justify-center">
            <svg viewBox="0 0 20 20" fill="white" className="w-4 h-4">
              <path
                fillRule="evenodd"
                d="M4 4a2 2 0 0 1 2-2h4.586A2 2 0 0 1 12 2.586L15.414 6A2 2 0 0 1 16 7.414V16a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V4Zm2 6a1 1 0 0 1 1-1h6a1 1 0 1 1 0 2H7a1 1 0 0 1-1-1Zm1 3a1 1 0 1 0 0 2h4a1 1 0 1 0 0-2H7Z"
                clipRule="evenodd"
              />
            </svg>
          </div>
          <span className="font-semibold text-void-text">ApplyPilot</span>
        </Link>

        <div className="relative max-w-md">
          <blockquote className="font-display text-3xl text-void-text leading-[1.2] tracking-tight">
            &ldquo;The job worth your time has already been written.
            <br />
            <span className="text-[var(--void-accent)]">We just find it.</span>
            &rdquo;
          </blockquote>
        </div>

        <p className="relative text-xs text-void-subtle font-mono">
          © 2026 ApplyPilot
        </p>
      </div>

      {/* Right panel — Clerk SignIn */}
      <div className="flex-1 flex items-center justify-center px-6 py-12">
        {/* Mobile logo */}
        <div className="w-full max-w-sm flex flex-col items-center gap-8">
          <Link href="/" className="flex lg:hidden items-center gap-2 self-start">
            <div className="w-7 h-7 rounded-lg bg-[var(--void-accent)] flex items-center justify-center">
              <svg viewBox="0 0 20 20" fill="white" className="w-4 h-4">
                <path
                  fillRule="evenodd"
                  d="M4 4a2 2 0 0 1 2-2h4.586A2 2 0 0 1 12 2.586L15.414 6A2 2 0 0 1 16 7.414V16a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V4Zm2 6a1 1 0 0 1 1-1h6a1 1 0 1 1 0 2H7a1 1 0 0 1-1-1Zm1 3a1 1 0 1 0 0 2h4a1 1 0 1 0 0-2H7Z"
                  clipRule="evenodd"
                />
              </svg>
            </div>
            <span className="font-semibold text-void-text text-sm">ApplyPilot</span>
          </Link>

          <SignIn
            forceRedirectUrl={next}
            signUpUrl="/register"
            appearance={{
              // baseTheme: dark — Clerk ships a maintained dark token set
              // (text, borders, secondary surfaces, OAuth button labels…).
              // Without it the variables.colorText override only repaints
              // the obvious headings and leaves Clerk's internal labels
              // (e.g. social-button text, error states) on default light.
              baseTheme: dark,
              variables: {
                colorPrimary: "#7C7CF5",
                colorBackground: "#0A0A0F",
                colorInputBackground: "#14141C",
                colorText: "#E2E8F0",
                colorTextSecondary: "#9CA3AF",
                colorInputText: "#E2E8F0",
                colorNeutral: "#1E1E2A",
                colorDanger: "#EF4444",
                borderRadius: "0.5rem",
                fontFamily: "var(--font-sans), sans-serif",
              },
              elements: {
                card: "shadow-none border border-white/[0.06] bg-[#0A0A0F]",
                headerTitle: "text-void-text",
                headerSubtitle: "text-void-muted",
                formButtonPrimary: "bg-[var(--void-accent)] hover:bg-indigo-500 text-white text-sm",
                formFieldInput: "bg-[#14141C] border-white/10 text-void-text",
                formFieldLabel: "text-void-text",
                footerActionLink: "text-[var(--void-accent)] hover:text-indigo-400",
                footerActionText: "text-void-muted",
                dividerLine: "bg-white/10",
                dividerText: "text-void-subtle",
                socialButtonsBlockButton:
                  "border-white/10 text-void-text bg-[#14141C] hover:bg-white/5",
                socialButtonsBlockButtonText: "text-void-text",
                socialButtonsProviderIcon: "brightness-110",
                identityPreviewText: "text-void-text",
                identityPreviewEditButton: "text-[var(--void-accent)]",
              },
            }}
          />
        </div>
      </div>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense>
      <LoginPanel />
    </Suspense>
  );
}

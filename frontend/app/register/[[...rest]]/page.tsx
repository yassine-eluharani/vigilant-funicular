"use client";

import { SignUp } from "@clerk/nextjs";
import { dark } from "@clerk/themes";
import Link from "next/link";

export default function RegisterPage() {
  return (
    <div className="min-h-screen flex">
      {/* Left branding panel */}
      <div className="hidden lg:flex flex-col justify-between w-[45%] bg-void-surface border-r border-void-border p-12 relative overflow-hidden">
        <div className="absolute inset-0 pointer-events-none">
          <div className="absolute top-1/3 left-1/2 -translate-x-1/2 w-[400px] h-[400px] bg-void-success/6 rounded-full blur-[100px]" />
        </div>
        <Link href="/" className="relative flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-void-accent flex items-center justify-center">
            <svg viewBox="0 0 20 20" fill="white" className="w-4 h-4">
              <path fillRule="evenodd" d="M4 4a2 2 0 0 1 2-2h4.586A2 2 0 0 1 12 2.586L15.414 6A2 2 0 0 1 16 7.414V16a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V4Zm2 6a1 1 0 0 1 1-1h6a1 1 0 1 1 0 2H7a1 1 0 0 1-1-1Zm1 3a1 1 0 1 0 0 2h4a1 1 0 1 0 0-2H7Z" clipRule="evenodd" />
            </svg>
          </div>
          <span className="font-semibold text-void-text">ApplyPilot</span>
        </Link>

        <div className="relative space-y-6">
          {[
            { icon: "🔍", title: "Discover 200+ jobs", desc: "Across all major boards and Workday portals" },
            { icon: "🤖", title: "AI scores every role", desc: "1–10 fit score against your profile, instantly" },
            { icon: "📄", title: "Tailored resume + cover", desc: "Generated per job, validated, exported to PDF" },
            { icon: "🚀", title: "Auto-submit overnight", desc: "Browser workers apply while you sleep" },
          ].map(({ icon, title, desc }) => (
            <div key={title} className="flex items-start gap-3">
              <span className="text-xl">{icon}</span>
              <div>
                <p className="text-sm font-medium text-void-text">{title}</p>
                <p className="text-xs text-void-muted">{desc}</p>
              </div>
            </div>
          ))}
        </div>

        <p className="relative text-xs text-void-subtle">© 2026 ApplyPilot. All rights reserved.</p>
      </div>

      {/* Right panel — Clerk SignUp */}
      <div className="flex-1 flex items-center justify-center px-6 py-12">
        <div className="w-full max-w-sm flex flex-col items-center gap-8">
          {/* Mobile logo */}
          <Link href="/" className="flex lg:hidden items-center gap-2 self-start">
            <div className="w-7 h-7 rounded-lg bg-void-accent flex items-center justify-center">
              <svg viewBox="0 0 20 20" fill="white" className="w-4 h-4">
                <path fillRule="evenodd" d="M4 4a2 2 0 0 1 2-2h4.586A2 2 0 0 1 12 2.586L15.414 6A2 2 0 0 1 16 7.414V16a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V4Zm2 6a1 1 0 0 1 1-1h6a1 1 0 1 1 0 2H7a1 1 0 0 1-1-1Zm1 3a1 1 0 1 0 0 2h4a1 1 0 1 0 0-2H7Z" clipRule="evenodd" />
              </svg>
            </div>
            <span className="font-semibold text-void-text text-sm">ApplyPilot</span>
          </Link>

          <SignUp
            forceRedirectUrl="/setup"
            signInUrl="/login"
            appearance={{
              // Object-style elements — see /login for the why. Tailwind
              // class strings lost the specificity war against Clerk's
              // internal styles, leaving OAuth labels invisible.
              baseTheme: dark,
              variables: {
                colorPrimary: "#7C7CF5",
                colorBackground: "#0A0A0F",
                colorInputBackground: "#14141C",
                colorText: "#F1F5F9",
                colorTextSecondary: "#94A3B8",
                colorInputText: "#F1F5F9",
                colorNeutral: "#1E1E2A",
                colorDanger: "#EF4444",
                colorTextOnPrimaryBackground: "#FFFFFF",
                borderRadius: "0.5rem",
                fontFamily: "var(--font-sans), sans-serif",
                fontSize: "0.95rem",
              },
              elements: {
                rootBox: { width: "100%" },
                card: {
                  backgroundColor: "#0A0A0F",
                  border: "1px solid rgba(255,255,255,0.06)",
                  boxShadow: "none",
                },
                headerTitle: { color: "#F1F5F9", fontWeight: 600 },
                headerSubtitle: { color: "#94A3B8" },
                formButtonPrimary: {
                  backgroundColor: "#7C7CF5",
                  color: "#FFFFFF",
                  fontWeight: 600,
                  textShadow: "none",
                  boxShadow: "none",
                  "&:hover": { backgroundColor: "#9494FF" },
                  "&:focus": { boxShadow: "0 0 0 3px rgba(124,124,245,0.35)" },
                },
                formFieldLabel: { color: "#F1F5F9", fontWeight: 500 },
                formFieldInput: {
                  backgroundColor: "#14141C",
                  borderColor: "rgba(255,255,255,0.10)",
                  color: "#F1F5F9",
                  "&::placeholder": { color: "#6B7280" },
                  "&:focus": {
                    borderColor: "#7C7CF5",
                    boxShadow: "0 0 0 3px rgba(124,124,245,0.18)",
                  },
                },
                socialButtonsBlockButton: {
                  backgroundColor: "#14141C",
                  border: "1px solid rgba(255,255,255,0.10)",
                  color: "#F1F5F9",
                  "&:hover": { backgroundColor: "#1A1A24" },
                },
                socialButtonsBlockButtonText: {
                  color: "#F1F5F9",
                  fontWeight: 500,
                },
                socialButtonsBlockButtonArrow: { color: "#94A3B8" },
                socialButtonsProviderIcon: { filter: "brightness(1.15)" },
                dividerLine: { backgroundColor: "rgba(255,255,255,0.10)" },
                dividerText: { color: "#6B7280" },
                footerActionText: { color: "#94A3B8" },
                footerActionLink: {
                  color: "#9494FF",
                  fontWeight: 500,
                  "&:hover": { color: "#B5B5FF" },
                },
                identityPreview: {
                  backgroundColor: "#14141C",
                  border: "1px solid rgba(255,255,255,0.10)",
                },
                identityPreviewText: { color: "#F1F5F9" },
                footer: { backgroundColor: "transparent" },
                badge: { color: "#94A3B8" },
              },
            }}
          />
        </div>
      </div>
    </div>
  );
}

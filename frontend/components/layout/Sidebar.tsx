"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "@/contexts/AuthContext";

const NAV = [
  {
    href: "/jobs",
    label: "Jobs",
    icon: (
      <svg viewBox="0 0 20 20" fill="currentColor" className="w-5 h-5">
        <path d="M6 3a1 1 0 0 0-1 1v1H4a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-1V4a1 1 0 0 0-1-1H6Zm5 10a1 1 0 1 1-2 0 1 1 0 0 1 2 0ZM7 4h6v1H7V4Z" />
      </svg>
    ),
  },
  {
    href: "/pipeline",
    label: "Pipeline",
    icon: (
      <svg viewBox="0 0 20 20" fill="currentColor" className="w-5 h-5">
        <path d="M3 4a1 1 0 0 1 1-1h12a1 1 0 0 1 0 2H4a1 1 0 0 1-1-1Zm0 5a1 1 0 0 1 1-1h12a1 1 0 0 1 0 2H4a1 1 0 0 1-1-1Zm1 4a1 1 0 0 0 0 2h12a1 1 0 0 0 0-2H4Z" />
      </svg>
    ),
  },
  {
    href: "/profile",
    label: "Profile",
    icon: (
      <svg viewBox="0 0 20 20" fill="currentColor" className="w-5 h-5">
        <path
          fillRule="evenodd"
          d="M10 9a3 3 0 1 0 0-6 3 3 0 0 0 0 6Zm-7 9a7 7 0 1 1 14 0H3Z"
          clipRule="evenodd"
        />
      </svg>
    ),
  },
];

export function Sidebar() {
  const pathname = usePathname();
  const { logout, user } = useAuth();

  return (
    <aside className="flex flex-col w-52 shrink-0 border-r border-void-border bg-void-surface h-full">
      {/* Logo */}
      <div className="flex items-center gap-2.5 px-4 py-4 border-b border-void-border">
        <div className="w-7 h-7 rounded-lg bg-void-accent flex items-center justify-center shrink-0">
          <svg viewBox="0 0 20 20" fill="white" className="w-4 h-4">
            <path
              fillRule="evenodd"
              d="M4 4a2 2 0 0 1 2-2h4.586A2 2 0 0 1 12 2.586L15.414 6A2 2 0 0 1 16 7.414V16a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V4Zm2 6a1 1 0 0 1 1-1h6a1 1 0 1 1 0 2H7a1 1 0 0 1-1-1Zm1 3a1 1 0 1 0 0 2h4a1 1 0 1 0 0-2H7Z"
              clipRule="evenodd"
            />
          </svg>
        </div>
        <span className="text-sm font-semibold text-void-text tracking-tight">
          ApplyPilot
        </span>
      </div>

      {/* Nav */}
      <nav className="flex-1 py-3 px-2 flex flex-col gap-0.5">
        {NAV.map(({ href, label, icon }) => {
          const active = pathname.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              className={`
                flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors
                ${active
                  ? "bg-void-raised text-void-text border border-void-border"
                  : "text-void-muted hover:text-void-text hover:bg-void-raised/60"
                }
              `}
            >
              <span className={active ? "text-void-accent" : ""}>{icon}</span>
              {label}
              {active && (
                <span className="ml-auto w-1.5 h-1.5 rounded-full bg-void-accent" />
              )}
            </Link>
          );
        })}
      </nav>

      {/* Footer */}
      <div className="px-3 py-3 border-t border-void-border flex items-center justify-between gap-2">
        <div className="min-w-0">
          {user ? (
            <p className="text-xs text-void-text truncate font-medium">{user.full_name}</p>
          ) : null}
          <p className="text-xs text-void-subtle font-mono">v1.0.0</p>
        </div>
        <button
          onClick={logout}
          title="Sign out"
          className="p-1.5 rounded-lg text-void-subtle hover:text-void-danger hover:bg-void-danger/10 transition-colors"
        >
          <svg viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4">
            <path fillRule="evenodd" d="M3 4.25A2.25 2.25 0 0 1 5.25 2h5.5A2.25 2.25 0 0 1 13 4.25v2a.75.75 0 0 1-1.5 0v-2a.75.75 0 0 0-.75-.75h-5.5a.75.75 0 0 0-.75.75v11.5c0 .414.336.75.75.75h5.5a.75.75 0 0 0 .75-.75v-2a.75.75 0 0 1 1.5 0v2A2.25 2.25 0 0 1 10.75 18h-5.5A2.25 2.25 0 0 1 3 15.75V4.25Z" clipRule="evenodd" />
            <path fillRule="evenodd" d="M19 10a.75.75 0 0 0-.75-.75H8.704l1.048-1.04a.75.75 0 1 0-1.056-1.064l-2.25 2.25a.75.75 0 0 0 0 1.064l2.25 2.25a.75.75 0 1 0 1.056-1.064L8.704 10.75H18.25A.75.75 0 0 0 19 10Z" clipRule="evenodd" />
          </svg>
        </button>
      </div>
    </aside>
  );
}

"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "@/contexts/AuthContext";

/**
 * DES-006 — icon-only left rail at 56px.
 *
 * NOTE: Per audit, the contextual sub-rail (e.g. a filter panel for /jobs)
 * is deferred. This pass is intentionally just icons + tooltips. The
 * sub-rail expansion can layer onto this later as a separate panel
 * docked next to the rail.
 */

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

interface SidebarProps {
  isOpen?: boolean;
  onClose?: () => void;
}

export function Sidebar({ isOpen, onClose }: SidebarProps) {
  const pathname = usePathname();
  const { logout, user } = useAuth();

  return (
    <>
      {/* Mobile backdrop */}
      {isOpen && (
        <div
          className="fixed inset-0 z-30 bg-black/50 md:hidden"
          onClick={onClose}
        />
      )}

      {/* Sidebar panel — 56px on desktop, full slide-over on mobile */}
      <aside
        className={`
          fixed inset-y-0 left-0 z-40 flex flex-col
          w-14 border-r border-void-border bg-void-surface h-full
          transition-transform duration-200
          md:static md:translate-x-0 md:z-auto
          ${isOpen ? "translate-x-0" : "-translate-x-full"}
        `}
      >
        {/* Logo */}
        <div className="flex items-center justify-center h-14 border-b border-void-border shrink-0">
          <Link
            href="/jobs"
            aria-label="ApplyPilot home"
            title="ApplyPilot"
            className="w-8 h-8 rounded-lg bg-void-accent flex items-center justify-center hover:bg-void-accent-hover transition-colors"
          >
            <svg viewBox="0 0 20 20" fill="white" className="w-4 h-4">
              <path
                fillRule="evenodd"
                d="M4 4a2 2 0 0 1 2-2h4.586A2 2 0 0 1 12 2.586L15.414 6A2 2 0 0 1 16 7.414V16a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V4Zm2 6a1 1 0 0 1 1-1h6a1 1 0 1 1 0 2H7a1 1 0 0 1-1-1Zm1 3a1 1 0 1 0 0 2h4a1 1 0 1 0 0-2H7Z"
                clipRule="evenodd"
              />
            </svg>
          </Link>
        </div>

        {/* Nav — icon-only, with active indicator on the LEFT edge */}
        <nav className="flex-1 py-3 flex flex-col items-center gap-1">
          {NAV.map(({ href, label, icon }) => {
            const active = pathname.startsWith(href);
            return (
              <Link
                key={href}
                href={href}
                onClick={onClose}
                title={label}
                aria-label={label}
                aria-current={active ? "page" : undefined}
                className={`
                  relative flex items-center justify-center w-10 h-10 rounded-lg transition-colors
                  ${active
                    ? "bg-void-raised text-void-accent"
                    : "text-void-muted hover:text-void-text hover:bg-void-raised/60"
                  }
                `}
              >
                {/* Active indicator — 2px periwinkle bar on the left edge */}
                {active && (
                  <span
                    aria-hidden
                    className="absolute -left-2 top-1.5 bottom-1.5 w-[2px] rounded-r bg-void-accent"
                  />
                )}
                {icon}
              </Link>
            );
          })}
        </nav>

        {/* Footer — user avatar + logout. v1.0.0 mono stamp dropped (DES-006). */}
        <div className="py-3 border-t border-void-border flex flex-col items-center gap-2 shrink-0">
          {user && (
            <div
              title={user.full_name || user.email}
              aria-label={user.full_name || user.email}
              className="
                w-8 h-8 rounded-full bg-void-raised border border-void-border
                flex items-center justify-center text-xs font-display text-void-text
              "
            >
              {(user.full_name || user.email || "?").trim().charAt(0).toUpperCase()}
            </div>
          )}
          <button
            onClick={logout}
            aria-label="Sign out"
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
    </>
  );
}

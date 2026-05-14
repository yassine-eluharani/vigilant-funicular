"use client";

import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { Sidebar } from "@/components/layout/Sidebar";

const NO_SIDEBAR = ["/setup"];

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [sidebarOpen, setSidebarOpen] = useState(false);

  // Close sidebar on route change. The setState inside the effect is
  // intentional: pathname changes are an external event we react to.
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { setSidebarOpen(false); }, [pathname]);

  const showSidebar = !NO_SIDEBAR.some((p) => pathname.startsWith(p));

  return (
    <div className="flex h-full">
      {showSidebar && (
        <Sidebar isOpen={sidebarOpen} onClose={() => setSidebarOpen(false)} />
      )}
      <div className="flex-1 min-w-0 flex flex-col">
        {/* Mobile header */}
        {showSidebar && (
          <header className="md:hidden flex items-center gap-3 px-4 py-3 border-b border-void-border bg-void-surface shrink-0">
            <button
              onClick={() => setSidebarOpen(true)}
              aria-label="Open menu"
              className="p-1.5 rounded-lg text-void-muted hover:text-void-text hover:bg-void-raised transition-colors"
            >
              <svg viewBox="0 0 20 20" fill="currentColor" className="w-5 h-5">
                <path fillRule="evenodd" d="M2 4.75A.75.75 0 0 1 2.75 4h14.5a.75.75 0 0 1 0 1.5H2.75A.75.75 0 0 1 2 4.75ZM2 10a.75.75 0 0 1 .75-.75h14.5a.75.75 0 0 1 0 1.5H2.75A.75.75 0 0 1 2 10Zm0 5.25a.75.75 0 0 1 .75-.75h14.5a.75.75 0 0 1 0 1.5H2.75a.75.75 0 0 1-.75-.75Z" clipRule="evenodd" />
              </svg>
            </button>
            <span className="text-sm font-semibold text-void-text">ApplyPilot</span>
          </header>
        )}
        <main className="flex-1 min-w-0 overflow-y-auto">
          {children}
        </main>
      </div>
    </div>
  );
}

"use client";

import { usePathname } from "next/navigation";
import { Sidebar } from "./Sidebar";

const NO_SIDEBAR_PATHS = ["/login", "/setup"];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const showSidebar = !NO_SIDEBAR_PATHS.some((p) => pathname.startsWith(p));

  return (
    <>
      {showSidebar && <Sidebar />}
      <main className="flex-1 min-w-0 overflow-y-auto">
        {children}
      </main>
    </>
  );
}

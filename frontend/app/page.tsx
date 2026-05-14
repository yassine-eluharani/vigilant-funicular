import { redirect } from "next/navigation";

// Marketing landing was removed in the personal-tool revamp. The root URL
// now bounces straight to the primary view; Clerk middleware (proxy.ts)
// will redirect unauthenticated visitors to /login from there.
export default function RootPage() {
  redirect("/apply");
}

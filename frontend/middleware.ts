import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

// Paths accessible without a token
const PUBLIC_PREFIXES = ["/", "/pricing", "/login", "/register"];

function isPublic(pathname: string): boolean {
  return PUBLIC_PREFIXES.some((p) =>
    p === "/" ? pathname === "/" : pathname.startsWith(p)
  );
}

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const token = request.cookies.get("ap_token")?.value;

  // Public routes — but redirect authenticated users away from login/register
  if (isPublic(pathname)) {
    if (token && (pathname.startsWith("/login") || pathname.startsWith("/register"))) {
      return NextResponse.redirect(new URL("/jobs", request.url));
    }
    return NextResponse.next();
  }

  // Protected routes — require auth cookie
  if (!token) {
    const loginUrl = new URL("/login", request.url);
    loginUrl.searchParams.set("next", pathname);
    return NextResponse.redirect(loginUrl);
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|.*\\..*$).*)"],
};

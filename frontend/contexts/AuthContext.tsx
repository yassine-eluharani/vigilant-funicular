"use client";

import { createContext, useContext, useEffect } from "react";
import {
  useUser,
  useClerk,
  useAuth as useClerkAuth,
} from "@clerk/nextjs";
import { setTokenFn } from "@/lib/auth";

interface User {
  id: string;
  email: string;
  full_name: string;
}

interface AuthContextValue {
  isAuthenticated: boolean;
  isLoading: boolean;
  user: User | null;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue>({
  isAuthenticated: false,
  isLoading: true,
  user: null,
  logout: () => {},
});

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const { isLoaded, isSignedIn, user } = useUser();
  const { signOut } = useClerk();
  const { getToken } = useClerkAuth();

  // Wire Clerk's token getter into lib/api.ts so all API calls get Authorization headers
  useEffect(() => {
    setTokenFn(() => getToken());
  }, [getToken]);

  const logout = () => signOut({ redirectUrl: "/" });

  const userObj: User | null =
    isSignedIn && user
      ? {
          id: user.id,
          email: user.primaryEmailAddress?.emailAddress ?? "",
          full_name: user.fullName ?? "",
        }
      : null;

  return (
    <AuthContext.Provider
      value={{
        isAuthenticated: !!isSignedIn,
        isLoading: !isLoaded,
        user: userObj,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}

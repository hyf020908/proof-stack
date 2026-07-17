import { create } from "zustand";
import { persist } from "zustand/middleware";

import type { AuthTokens, User } from "../api/types";

interface AuthState {
  accessToken: string | null;
  refreshToken: string | null;
  user: User | null;
  hydrated: boolean;
  setSession: (tokens: AuthTokens, user?: User | null) => void;
  setUser: (user: User | null) => void;
  setHydrated: (hydrated: boolean) => void;
  clearSession: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      accessToken: null,
      refreshToken: null,
      user: null,
      hydrated: false,
      setSession: (tokens, user) =>
        set({
          accessToken: tokens.access_token,
          refreshToken: tokens.refresh_token,
          user: user ?? tokens.user ?? null,
        }),
      setUser: (user) => set({ user }),
      setHydrated: (hydrated) => set({ hydrated }),
      clearSession: () => set({ accessToken: null, refreshToken: null, user: null }),
    }),
    {
      name: "proofstack-session",
      partialize: ({ accessToken, refreshToken, user }) => ({ accessToken, refreshToken, user }),
      onRehydrateStorage: () => (state) => state?.setHydrated(true),
    },
  ),
);

export const canManageProjects = (role?: string): boolean =>
  role === "owner" || role === "maintainer";

export const canReviewFindings = (role?: string): boolean =>
  role === "owner" || role === "maintainer" || role === "reviewer";

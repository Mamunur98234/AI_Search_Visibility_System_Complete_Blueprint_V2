"use client";

import { useRouter } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useState } from "react";

import { api, ApiError, type Schemas } from "./api";

type Me = Schemas["MeOut"];

type SessionValue = {
  me: Me;
  can: (perm: string) => boolean;
  refresh: () => Promise<void>;
  logout: () => Promise<void>;
  switchTenant: (id: string) => Promise<void>;
};

const SessionContext = createContext<SessionValue | null>(null);

export function useSession(): SessionValue {
  const v = useContext(SessionContext);
  if (!v) throw new Error("useSession must be used inside <SessionProvider>");
  return v;
}

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);
  const [failed, setFailed] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setMe(await api<Me>("GET", "/auth/me"));
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) {
        router.replace(`/login?next=${encodeURIComponent(window.location.pathname)}`);
      } else {
        setFailed(e instanceof Error ? e.message : "Unable to load your session");
      }
    }
  }, [router]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- load session once on mount
    void refresh();
    const onUnauth = () => router.replace("/login");
    window.addEventListener("aisv:unauthenticated", onUnauth);
    return () => window.removeEventListener("aisv:unauthenticated", onUnauth);
  }, [refresh, router]);

  const logout = useCallback(async () => {
    try {
      await api("POST", "/auth/logout");
    } finally {
      router.replace("/login");
    }
  }, [router]);

  const switchTenant = useCallback(
    async (id: string) => {
      await api("POST", "/auth/switch-tenant", { tenant_id: id });
      await refresh();
      router.push("/");
    },
    [refresh, router],
  );

  if (failed) {
    return (
      <main className="centered">
        <div className="card" role="alert">
          <h1>Unable to load</h1>
          <p>{failed}</p>
          <button className="btn" onClick={() => window.location.reload()}>
            Retry
          </button>
        </div>
      </main>
    );
  }
  if (!me) {
    return (
      <main className="centered" aria-busy="true">
        <p className="muted">Loading your workspace…</p>
      </main>
    );
  }
  const can = (perm: string) => me.permissions.includes(perm);
  return (
    <SessionContext.Provider value={{ me, can, refresh, logout, switchTenant }}>{children}</SessionContext.Provider>
  );
}

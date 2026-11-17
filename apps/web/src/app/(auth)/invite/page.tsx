"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Button, Field, FormError, Loading } from "@/components/ui";
import { api, ApiError, type Schemas } from "@/lib/api";

const STORE_KEY = "aisv_invite_token";

function readToken(): string | null {
  const fromHash = new URLSearchParams(window.location.hash.slice(1)).get("token");
  if (fromHash) {
    try {
      sessionStorage.setItem(STORE_KEY, fromHash); // survives a sign-in round trip in this tab only
    } catch {
      /* storage unavailable: token still works for this page view */
    }
    window.history.replaceState(null, "", window.location.pathname);
    return fromHash;
  }
  try {
    return sessionStorage.getItem(STORE_KEY);
  } catch {
    return null;
  }
}

export default function InvitePage() {
  const router = useRouter();
  const [token, setToken] = useState<string | null | undefined>(undefined);
  const [info, setInfo] = useState<Schemas["InvitationPublicOut"]>();
  const [loadError, setLoadError] = useState<unknown>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();

  useEffect(() => {
    const t = readToken();
    // eslint-disable-next-line react-hooks/set-state-in-effect -- read fragment once on mount
    setToken(t);
    if (!t) return;
    api<Schemas["InvitationPublicOut"]>("GET", "/invitations/lookup", undefined, { "X-Invitation-Token": t })
      .then(setInfo)
      .catch(setLoadError);
  }, []);

  async function accept(e?: React.FormEvent<HTMLFormElement>) {
    e?.preventDefault();
    const f = e ? new FormData(e.currentTarget) : null;
    setBusy(true);
    setError(undefined);
    try {
      await api(
        "POST",
        "/invitations/accept",
        f ? { name: f.get("name"), password: f.get("password") } : {},
        { "X-Invitation-Token": token ?? "" },
      );
      try {
        sessionStorage.removeItem(STORE_KEY);
      } catch {
        /* ignore */
      }
      router.replace("/");
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  if (token === undefined) return <Loading />;
  if (!token)
    return (
      <div className="card auth-card">
        <h1>Invitation</h1>
        <p className="muted">Open this page from the link in your invitation email.</p>
      </div>
    );
  if (loadError)
    return (
      <div className="card auth-card" role="alert">
        <h1>Invitation unavailable</h1>
        <p>{loadError instanceof Error ? loadError.message : "This invitation cannot be used."}</p>
        <Link href="/login">Go to sign in</Link>
      </div>
    );
  if (!info) return <Loading label="Checking invitation…" />;

  const fe = error instanceof ApiError ? error.fieldErrors : {};
  const needsLogin = error instanceof ApiError && error.status === 401;
  return (
    <div className="card auth-card">
      <h1>Join {info.tenant_name}</h1>
      <p>
        You were invited as <strong>{info.role}</strong> using <strong>{info.email}</strong>.
      </p>
      <FormError error={error} />
      {info.account_exists ? (
        <>
          <p className="muted">An account already exists for this email. Accept while signed in as that account.</p>
          <div className="row">
            <Button variant="primary" busy={busy} onClick={() => void accept()}>
              Accept invitation
            </Button>
            {needsLogin ? (
              <Link className="btn" href="/login?next=/invite">
                Sign in first
              </Link>
            ) : null}
          </div>
        </>
      ) : (
        <form onSubmit={accept}>
          <Field label="Your name" name="name" required maxLength={200} autoComplete="name" error={fe.name} autoFocus />
          <Field label="Password" name="password" type="password" required minLength={12} autoComplete="new-password"
            hint="At least 12 characters." error={fe.password} />
          <Button variant="primary" type="submit" busy={busy}>
            Create account and join
          </Button>
        </form>
      )}
    </div>
  );
}

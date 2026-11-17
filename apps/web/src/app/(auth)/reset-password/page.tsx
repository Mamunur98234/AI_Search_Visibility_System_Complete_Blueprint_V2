"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { Button, Field, FormError } from "@/components/ui";
import { api, ApiError } from "@/lib/api";

export default function ResetPasswordPage() {
  const [token, setToken] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  const [done, setDone] = useState(false);

  useEffect(() => {
    // The token is in the URL fragment, which browsers never send to servers. Remove it from the address bar.
    const t = new URLSearchParams(window.location.hash.slice(1)).get("token");
    // eslint-disable-next-line react-hooks/set-state-in-effect -- read fragment once on mount
    setToken(t);
    if (t) window.history.replaceState(null, "", window.location.pathname);
  }, []);

  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    if (f.get("password") !== f.get("confirm")) {
      setError(new Error("Passwords do not match."));
      return;
    }
    setBusy(true);
    setError(undefined);
    try {
      await api("POST", "/auth/password/reset", { token, password: f.get("password") });
      setDone(true);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  const fe = error instanceof ApiError ? error.fieldErrors : {};
  return (
    <div className="card auth-card">
      <h1>Choose a new password</h1>
      {done ? (
        <p role="status">
          Your password has been changed and all sessions were signed out. <Link href="/login">Sign in</Link>
        </p>
      ) : token === null ? (
        <p className="muted">This page needs the link from your reset email.</p>
      ) : (
        <>
          <FormError error={error} />
          <form onSubmit={submit}>
            <Field label="New password" name="password" type="password" minLength={12} required
              autoComplete="new-password" error={fe.password} autoFocus />
            <Field label="Confirm new password" name="confirm" type="password" minLength={12} required
              autoComplete="new-password" />
            <Button variant="primary" type="submit" busy={busy}>
              Set password
            </Button>
          </form>
        </>
      )}
    </div>
  );
}

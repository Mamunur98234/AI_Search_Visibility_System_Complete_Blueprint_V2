"use client";

import Link from "next/link";
import { useState } from "react";

import { Button, Field, FormError } from "@/components/ui";
import { api } from "@/lib/api";

export default function ForgotPasswordPage() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  const [sent, setSent] = useState(false);

  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    setBusy(true);
    setError(undefined);
    try {
      await api("POST", "/auth/password/forgot", { email: f.get("email") });
      setSent(true);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card auth-card">
      <h1>Reset your password</h1>
      {sent ? (
        <p role="status">If an account exists for that email, a reset link has been sent. The link expires in 60 minutes.</p>
      ) : (
        <>
          <FormError error={error} />
          <form onSubmit={submit}>
            <Field label="Email" name="email" type="email" required autoComplete="email" autoFocus />
            <Button variant="primary" type="submit" busy={busy}>
              Send reset link
            </Button>
          </form>
        </>
      )}
      <p className="small">
        <Link href="/login">Back to sign in</Link>
      </p>
    </div>
  );
}

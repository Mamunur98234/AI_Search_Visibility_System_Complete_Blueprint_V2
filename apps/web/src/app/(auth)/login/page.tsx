"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { Button, Field, FormError } from "@/components/ui";
import { api } from "@/lib/api";

function safeNext(raw: string | null): string {
  // Only same-site relative paths; blocks open redirects such as //evil.example or /\evil.
  return raw && raw.startsWith("/") && !raw.startsWith("//") && !raw.startsWith("/\\") ? raw : "/";
}

function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const next = safeNext(params.get("next"));
  const [step, setStep] = useState<"password" | "mfa">("password");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();

  async function submitPassword(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    setBusy(true);
    setError(undefined);
    try {
      const r = await api<{ mfa_required: boolean }>("POST", "/auth/login", {
        email: f.get("email"),
        password: f.get("password"),
      });
      if (r.mfa_required) setStep("mfa");
      else router.replace(next);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  async function submitCode(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    setBusy(true);
    setError(undefined);
    try {
      await api("POST", "/auth/mfa/verify-login", { code: f.get("code") });
      router.replace(next);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card auth-card">
      <h1>Sign in</h1>
      <p className="muted">AI Search Visibility workspace</p>
      <FormError error={error} />
      {step === "password" ? (
        <form onSubmit={submitPassword} noValidate={false}>
          <Field label="Email" name="email" type="email" autoComplete="username" required autoFocus />
          <Field label="Password" name="password" type="password" autoComplete="current-password" required />
          <Button variant="primary" type="submit" busy={busy}>
            Sign in
          </Button>
          <p className="small">
            <Link href="/forgot-password">Forgot password?</Link> · <Link href="/signup">Create an agency workspace</Link>
          </p>
        </form>
      ) : (
        <form onSubmit={submitCode}>
          <p>Enter the 6-digit code from your authenticator app, or one of your recovery codes.</p>
          <Field label="Verification code" name="code" autoComplete="one-time-code" inputMode="text" required autoFocus />
          <Button variant="primary" type="submit" busy={busy}>
            Verify
          </Button>
        </form>
      )}
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense>
      <LoginForm />
    </Suspense>
  );
}

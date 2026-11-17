"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button, Field, FormError } from "@/components/ui";
import { api, ApiError } from "@/lib/api";

export default function SignupPage() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  const fe = error instanceof ApiError ? error.fieldErrors : {};

  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    setBusy(true);
    setError(undefined);
    try {
      await api("POST", "/auth/signup", {
        agency_name: f.get("agency_name"),
        name: f.get("name"),
        email: f.get("email"),
        password: f.get("password"),
      });
      router.replace("/");
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card auth-card">
      <h1>Create an agency workspace</h1>
      <p className="muted">You will be the Agency Owner. You can invite your team afterwards.</p>
      <FormError error={error} />
      <form onSubmit={submit}>
        <Field label="Agency name" name="agency_name" required maxLength={200} error={fe.agency_name} autoFocus />
        <Field label="Your name" name="name" required maxLength={200} autoComplete="name" error={fe.name} />
        <Field label="Work email" name="email" type="email" required autoComplete="email" error={fe.email} />
        <Field
          label="Password"
          name="password"
          type="password"
          required
          minLength={12}
          autoComplete="new-password"
          hint="At least 12 characters. A passphrase works well."
          error={fe.password}
        />
        <Button variant="primary" type="submit" busy={busy}>
          Create workspace
        </Button>
      </form>
      <p className="small">
        Already have an account? <Link href="/login">Sign in</Link>
      </p>
    </div>
  );
}

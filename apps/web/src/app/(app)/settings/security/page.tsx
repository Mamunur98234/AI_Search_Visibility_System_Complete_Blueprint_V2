"use client";

import { useState } from "react";

import { Button, Field, FormError, toast } from "@/components/ui";
import { api, ApiError, type Schemas } from "@/lib/api";
import { useSession } from "@/lib/session";

export default function SecurityPage() {
  return (
    <>
      <div className="page-head">
        <div>
          <h1>Security</h1>
          <p className="muted">Your password and two-factor authentication.</p>
        </div>
      </div>
      <div className="stack">
        <PasswordCard />
        <MfaCard />
      </div>
    </>
  );
}

function PasswordCard() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  const fe = error instanceof ApiError ? error.fieldErrors : {};

  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const f = new FormData(form);
    if (f.get("new_password") !== f.get("confirm")) {
      setError(new Error("New passwords do not match."));
      return;
    }
    setBusy(true);
    setError(undefined);
    try {
      await api("POST", "/auth/password/change", {
        current_password: f.get("current_password"),
        new_password: f.get("new_password"),
      });
      form.reset();
      toast("Password changed. Other sessions were signed out.");
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card" aria-labelledby="pw-h">
      <h2 id="pw-h">Change password</h2>
      <form onSubmit={submit}>
        <FormError error={error} />
        <Field label="Current password" name="current_password" type="password" required autoComplete="current-password" />
        <Field label="New password" name="new_password" type="password" required minLength={12}
          autoComplete="new-password" error={fe.new_password} hint="At least 12 characters." />
        <Field label="Confirm new password" name="confirm" type="password" required minLength={12} autoComplete="new-password" />
        <Button type="submit" busy={busy}>
          Change password
        </Button>
      </form>
    </section>
  );
}

function MfaCard() {
  const { me, refresh } = useSession();
  const [setup, setSetup] = useState<Schemas["MfaSetupOut"] | null>(null);
  const [codes, setCodes] = useState<string[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();

  async function start() {
    setBusy(true);
    setError(undefined);
    try {
      setSetup(await api<Schemas["MfaSetupOut"]>("POST", "/auth/mfa/setup"));
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  async function enable(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    setError(undefined);
    try {
      const r = await api<Schemas["RecoveryCodesOut"]>("POST", "/auth/mfa/enable", {
        code: new FormData(e.currentTarget).get("code"),
      });
      setCodes(r.recovery_codes);
      setSetup(null);
      await refresh();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  async function disable(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    setError(undefined);
    try {
      await api("POST", "/auth/mfa/disable", { code: new FormData(e.currentTarget).get("code") });
      setCodes(null);
      await refresh();
      toast("Two-factor authentication turned off");
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card" aria-labelledby="mfa-h">
      <h2 id="mfa-h">Two-factor authentication</h2>
      <FormError error={error} />
      {codes ? (
        <div className="alert alert-warn" role="alert">
          <p>
            <strong>Save these recovery codes now.</strong> Each works once if you lose your authenticator. They will not be
            shown again.
          </p>
          <ul>
            {codes.map((c) => (
              <li key={c}>
                <code className="secret">{c}</code>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {me.mfa_enabled ? (
        <form onSubmit={disable}>
          <p>Two-factor authentication is <strong>on</strong>.</p>
          <Field label="Code or recovery code to turn off" name="code" required autoComplete="one-time-code" />
          <Button variant="danger" type="submit" busy={busy}>
            Turn off
          </Button>
        </form>
      ) : setup ? (
        <form onSubmit={enable}>
          <p>Add this account to your authenticator app using the setup key, then enter the 6-digit code it shows.</p>
          <dl className="kv">
            <dt>Setup key</dt>
            <dd>
              <code className="secret">{setup.secret}</code>
            </dd>
            <dt>Setup URI</dt>
            <dd>
              <code className="small">{setup.otpauth_uri}</code>
            </dd>
          </dl>
          <Field label="6-digit code" name="code" required inputMode="numeric" pattern="[0-9]{6}" autoComplete="one-time-code" />
          <Button variant="primary" type="submit" busy={busy}>
            Verify and turn on
          </Button>
        </form>
      ) : (
        <>
          <p>Protect your account with a time-based code from an authenticator app.</p>
          <Button variant="primary" onClick={() => void start()} busy={busy}>
            Set up two-factor authentication
          </Button>
        </>
      )}
    </section>
  );
}

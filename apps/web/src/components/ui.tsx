"use client";

import { useEffect, useId, useRef, useState, type ReactNode } from "react";

import { ApiError } from "@/lib/api";

export function Button({
  variant = "default",
  busy,
  children,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "default" | "primary" | "danger"; busy?: boolean }) {
  return (
    <button
      {...props}
      className={`btn ${variant !== "default" ? `btn-${variant}` : ""} ${props.className ?? ""}`}
      disabled={props.disabled || busy}
      aria-busy={busy || undefined}
    >
      {busy ? "Working…" : children}
    </button>
  );
}

/** A control that is visible but not usable, with the reason exposed to assistive tech and on hover. */
export function DisabledHint({ label, reason }: { label: string; reason: string }) {
  const id = useId();
  return (
    <span className="disabled-hint">
      <button className="btn" disabled aria-describedby={id}>
        {label}
      </button>
      <span id={id} className="hint">
        {reason}
      </span>
    </span>
  );
}

type FieldProps = {
  label: string;
  name: string;
  error?: string;
  hint?: string;
  children?: ReactNode;
} & React.InputHTMLAttributes<HTMLInputElement>;

export function Field({ label, name, error, hint, children, ...input }: FieldProps) {
  const id = useId();
  const describedBy = [error ? `${id}-err` : null, hint ? `${id}-hint` : null].filter(Boolean).join(" ") || undefined;
  return (
    <div className="field">
      <label htmlFor={id}>
        {label}
        {input.required ? <span aria-hidden="true"> *</span> : null}
      </label>
      {children ?? <input id={id} name={name} aria-invalid={!!error} aria-describedby={describedBy} {...input} />}
      {hint ? (
        <p id={`${id}-hint`} className="hint">
          {hint}
        </p>
      ) : null}
      {error ? (
        <p id={`${id}-err`} className="field-error">
          {error}
        </p>
      ) : null}
    </div>
  );
}

export function SelectField({
  label,
  error,
  children,
  ...props
}: { label: string; error?: string } & React.SelectHTMLAttributes<HTMLSelectElement>) {
  const id = useId();
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <select id={id} aria-invalid={!!error} aria-describedby={error ? `${id}-err` : undefined} {...props}>
        {children}
      </select>
      {error ? (
        <p id={`${id}-err`} className="field-error">
          {error}
        </p>
      ) : null}
    </div>
  );
}

export function TextAreaField({
  label,
  error,
  ...props
}: { label: string; error?: string } & React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  const id = useId();
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <textarea id={id} aria-invalid={!!error} aria-describedby={error ? `${id}-err` : undefined} {...props} />
      {error ? (
        <p id={`${id}-err`} className="field-error">
          {error}
        </p>
      ) : null}
    </div>
  );
}

export function FormError({ error }: { error?: unknown }) {
  if (!error) return null;
  const msg = error instanceof Error ? error.message : String(error);
  const rid = error instanceof ApiError ? error.requestId : undefined;
  return (
    <div className="alert alert-error" role="alert">
      {msg}
      {rid ? <span className="muted small"> (request {rid})</span> : null}
    </div>
  );
}

export function Loading({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="state" aria-busy="true" aria-live="polite">
      <span className="spinner" aria-hidden="true" />
      <span>{label}</span>
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const rid = error instanceof ApiError ? error.requestId : undefined;
  const status = error instanceof ApiError ? error.status : undefined;
  return (
    <div className="state state-error" role="alert">
      <strong>{status === 404 ? "Not found" : status === 403 ? "No access" : "Could not load this data"}</strong>
      <span>{error instanceof Error ? error.message : "Unexpected error"}</span>
      {rid ? <span className="muted small">Request ID: {rid}</span> : null}
      {onRetry && status !== 404 && status !== 403 ? (
        <Button onClick={onRetry}>Retry</Button>
      ) : null}
    </div>
  );
}

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="state">
      <strong>{title}</strong>
      {children}
    </div>
  );
}

export function Badge({ children, tone = "neutral" }: { children: ReactNode; tone?: "neutral" | "ok" | "warn" | "bad" | "info" }) {
  return <span className={`badge badge-${tone}`}>{children}</span>;
}

/** Native <dialog>: focus is trapped and restored by the browser; Escape closes. */
export function Dialog({
  open,
  title,
  onClose,
  children,
}: {
  open: boolean;
  title: string;
  onClose: () => void;
  children: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) d.showModal();
    if (!open && d.open) d.close();
  }, [open]);
  return (
    <dialog ref={ref} aria-labelledby={titleId} onClose={onClose} className="dialog">
      <div className="dialog-head">
        <h2 id={titleId}>{title}</h2>
        <button className="btn btn-ghost" onClick={onClose} aria-label="Close dialog">
          ×
        </button>
      </div>
      {open ? children : null}
    </dialog>
  );
}

let toastListener: ((m: string) => void) | null = null;
export function toast(message: string) {
  toastListener?.(message);
}

export function ToastRegion() {
  const [msg, setMsg] = useState<string | null>(null);
  useEffect(() => {
    let t: ReturnType<typeof setTimeout> | undefined;
    toastListener = (m) => {
      setMsg(m);
      clearTimeout(t);
      t = setTimeout(() => setMsg(null), 4000);
    };
    return () => {
      toastListener = null;
      clearTimeout(t);
    };
  }, []);
  return (
    <div className="toast-region" role="status" aria-live="polite">
      {msg ? <div className="toast">{msg}</div> : null}
    </div>
  );
}

export function formatDate(value?: string | null): string {
  if (!value) return "—";
  const d = new Date(value.length === 10 ? `${value}T00:00:00Z` : value);
  return d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric", timeZone: "UTC" });
}

export function formatDateTime(value?: string | null): string {
  if (!value) return "—";
  return new Date(value).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short", timeZone: "UTC" }) + " UTC";
}

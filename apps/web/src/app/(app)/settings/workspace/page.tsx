"use client";

import { useState } from "react";

import { Button, DisabledHint, ErrorState, Field, FormError, Loading, formatDate, toast } from "@/components/ui";
import { api, ApiError, type Schemas } from "@/lib/api";
import { useSession } from "@/lib/session";
import { useApi } from "@/lib/use-api";

export default function WorkspacePage() {
  const { can, refresh } = useSession();
  const tenant = useApi<Schemas["TenantOut"]>("/tenant");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  const fe = error instanceof ApiError ? error.fieldErrors : {};

  async function save(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    setError(undefined);
    try {
      tenant.setData(await api<Schemas["TenantOut"]>("PATCH", "/tenant", { name: new FormData(e.currentTarget).get("name") }));
      await refresh();
      toast("Workspace renamed");
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  if (tenant.loading && !tenant.data) return <Loading />;
  if (tenant.error) return <ErrorState error={tenant.error} onRetry={tenant.reload} />;
  const t = tenant.data!;
  return (
    <>
      <div className="page-head">
        <div>
          <h1>Workspace</h1>
          <p className="muted">Created {formatDate(t.created_at)}</p>
        </div>
      </div>
      <section className="card">
        <form onSubmit={save}>
          <FormError error={error} />
          <Field label="Workspace name" name="name" defaultValue={t.name} required maxLength={200} error={fe.name}
            disabled={!can("tenant.update")} />
          {can("tenant.update") ? (
            <Button type="submit" busy={busy}>
              Save
            </Button>
          ) : (
            <DisabledHint label="Save" reason="Only agency owners and admins can rename the workspace." />
          )}
        </form>
        <p className="muted small">Branding, data retention and billing settings arrive in later phases.</p>
      </section>
    </>
  );
}

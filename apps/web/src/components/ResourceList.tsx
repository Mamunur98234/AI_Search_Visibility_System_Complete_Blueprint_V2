"use client";

import { useState, type ReactNode } from "react";

import { api, ApiError } from "@/lib/api";
import { useApi } from "@/lib/use-api";

import { Button, DisabledHint, EmptyState, ErrorState, Field, FormError, Loading, toast } from "./ui";

export type FieldSpec = {
  name: string;
  label: string;
  type?: "text" | "email" | "date" | "checkbox" | "list";
  required?: boolean;
  hint?: string;
  maxLength?: number;
};

type Props<T extends { id: string }> = {
  title: string;
  listPath: string;
  itemPath: (item: T) => string;
  fields: FieldSpec[];
  canManage: boolean;
  manageReason?: string;
  render: (item: T) => ReactNode;
  itemLabel: (item: T) => string;
  emptyText: string;
};

function toPayload(fields: FieldSpec[], f: FormData): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const spec of fields) {
    const raw = f.get(spec.name);
    if (spec.type === "checkbox") out[spec.name] = raw === "on";
    else if (spec.type === "list")
      out[spec.name] = String(raw ?? "")
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean);
    else out[spec.name] = raw === "" || raw === null ? null : raw;
  }
  return out;
}

/** A sub-resource list with inline create and delete. Edit-in-place lands with later workflows. */
export function ResourceList<T extends { id: string }>(props: Props<T>) {
  const { data, error, loading, reload } = useApi<T[]>(props.listPath);
  const [adding, setAdding] = useState(false);
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState<unknown>();
  const fe = formError instanceof ApiError ? formError.fieldErrors : {};

  async function create(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    setBusy(true);
    setFormError(undefined);
    try {
      await api("POST", props.listPath, toPayload(props.fields, new FormData(form)));
      form.reset();
      setAdding(false);
      toast(`${props.title.replace(/s$/, "")} added`);
      await reload();
    } catch (err) {
      setFormError(err);
    } finally {
      setBusy(false);
    }
  }

  async function remove(item: T) {
    if (!window.confirm(`Delete ${props.itemLabel(item)}? This is recorded in the audit log.`)) return;
    try {
      await api("DELETE", props.itemPath(item));
      toast("Deleted");
      await reload();
    } catch (err) {
      toast(err instanceof Error ? err.message : "Delete failed");
    }
  }

  return (
    <section className="card" aria-label={props.title}>
      <div className="page-head">
        <h3>{props.title}</h3>
        {props.canManage ? (
          <Button onClick={() => setAdding((a) => !a)} aria-expanded={adding}>
            {adding ? "Cancel" : "Add"}
          </Button>
        ) : (
          <DisabledHint label="Add" reason={props.manageReason ?? "Your role cannot change these records."} />
        )}
      </div>
      {adding ? (
        <form onSubmit={create} className="card" aria-label={`Add ${props.title}`}>
          <FormError error={formError} />
          {props.fields.map((spec) =>
            spec.type === "checkbox" ? (
              <label key={spec.name} className="checkbox">
                <input type="checkbox" name={spec.name} /> {spec.label}
              </label>
            ) : (
              <Field
                key={spec.name}
                label={spec.label}
                name={spec.name}
                type={spec.type === "list" || !spec.type ? "text" : spec.type}
                required={spec.required}
                maxLength={spec.maxLength ?? 200}
                hint={spec.hint}
                error={fe[spec.name] ?? fe[`${spec.name}.0`]}
              />
            ),
          )}
          <Button variant="primary" type="submit" busy={busy}>
            Save
          </Button>
        </form>
      ) : null}
      {loading && !data ? (
        <Loading />
      ) : error ? (
        <ErrorState error={error} onRetry={reload} />
      ) : !data || data.length === 0 ? (
        <EmptyState title={props.emptyText} />
      ) : (
        <ul className="list-plain">
          {data.map((item) => (
            <li key={item.id} className="row between">
              <div className="grow">{props.render(item)}</div>
              {props.canManage ? (
                <Button variant="danger" onClick={() => void remove(item)} aria-label={`Delete ${props.itemLabel(item)}`}>
                  Delete
                </Button>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

"use client";

import { useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { Field, fieldInputClassName } from "@/components/ui/field";
import { setStoredTenantId } from "@/lib/tenant";

/**
 * Shown wherever the backend says `tenant_required`: the account belongs to more than one workspace
 * and none is remembered yet. There is no endpoint that lists a user's workspaces, so this is a raw
 * id entry, never a picker — the backend still validates it; entering the wrong one simply fails again.
 */
export function TenantRequiredForm({ onSubmitted }: { onSubmitted: () => void }) {
  const [tenantId, setTenantId] = useState("");

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!tenantId.trim()) return;
    setStoredTenantId(tenantId.trim());
    onSubmitted();
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4">
      <Callout tone="info" title="Which workspace?">
        Your account belongs to more than one EIDOS workspace. Enter the workspace ID you were given.
      </Callout>
      <Field label="Workspace (tenant) ID">
        {(id, describedBy) => (
          <input
            id={id}
            aria-describedby={describedBy}
            value={tenantId}
            onChange={(event) => setTenantId(event.target.value)}
            placeholder="00000000-0000-0000-0000-000000000000"
            className={fieldInputClassName(false)}
          />
        )}
      </Field>
      <Button type="submit" className="self-start">
        Continue
      </Button>
    </form>
  );
}

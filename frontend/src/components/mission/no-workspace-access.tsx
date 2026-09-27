import { Callout } from "@/components/ui/callout";

/** Shown wherever the backend says `no_tenant_membership`: the account is real, but not yet linked to a workspace. There is nothing this app can do about it — provisioning is out of band. */
export function NoWorkspaceAccess() {
  return (
    <Callout tone="warning" title="No workspace access yet">
      Your account isn&apos;t linked to an EIDOS workspace yet. Ask whoever administers your workspace to add you,
      then sign in again.
    </Callout>
  );
}

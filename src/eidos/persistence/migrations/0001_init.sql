-- V1.4-B (decisions.md D-230, D-233; docs/13_product_backend.md section 2.2): the durable store of the product backend.
--
-- The event log is the authority. No table holds MissionState, ExecutionRecord or any status the reducer folds; missions.last_sequence is an append guard and nothing more.
-- Nothing here uses session state, so any Supabase connection mode works. Row level security is enabled on every table with no policies, and the API roles hold no privilege on
-- the schema: tenant isolation is enforced by the application, and the deny-all RLS is a safety net so that a leaked public key reaches nothing.

create schema if not exists eidos;

create table if not exists eidos.schema_migrations (
  version text primary key,
  applied_at timestamptz not null default now()
);

create table eidos.tenants (
  tenant_id uuid primary key,
  name text not null check (length(name) between 1 and 200),
  created_at timestamptz not null default now(),
  constraint tenant_is_not_the_reserved_sentinel check (tenant_id <> '00000000-0000-0000-0000-000000000000')
);

create table eidos.tenant_members (
  tenant_id uuid not null references eidos.tenants (tenant_id),
  user_id uuid not null,
  role text not null check (role in ('owner', 'member')),
  created_at timestamptz not null default now(),
  primary key (tenant_id, user_id)
);
create index tenant_members_by_user on eidos.tenant_members (user_id);

create table eidos.missions (
  mission_id uuid primary key,
  tenant_id uuid not null references eidos.tenants (tenant_id),
  execution_id uuid not null unique,
  contract_id uuid not null,
  created_by uuid not null,
  created_at timestamptz not null,
  spec jsonb not null,
  spec_sha256 text not null,
  idempotency_key text,
  run_status text not null default 'created'
    check (run_status in ('created', 'queued', 'running', 'finished', 'rejected', 'interrupted', 'error')),
  run_status_reason text,
  run_updated_at timestamptz not null,
  last_sequence integer not null default 0 check (last_sequence >= 0),
  constraint missions_scope unique (mission_id, tenant_id),
  constraint missions_execution_scope unique (execution_id, tenant_id),
  constraint missions_idempotency unique (tenant_id, idempotency_key)
);

create table eidos.mission_events (
  mission_id uuid not null,
  tenant_id uuid not null,
  sequence integer not null check (sequence >= 1),
  event_id uuid not null,
  event_type text not null,
  occurred_at timestamptz not null,
  record jsonb not null,
  primary key (mission_id, sequence),
  constraint mission_events_event_id unique (mission_id, event_id),
  foreign key (mission_id, tenant_id) references eidos.missions (mission_id, tenant_id)
);

create table eidos.artifacts (
  execution_id uuid not null,
  tenant_id uuid not null,
  ref text not null check (length(ref) >= 1),
  kind text not null check (kind in ('supplied', 'step')),
  step_id text,
  content_type text not null,
  content text not null,
  source_refs jsonb not null default '[]',
  created_at timestamptz not null default now(),
  primary key (execution_id, ref),
  foreign key (execution_id, tenant_id) references eidos.missions (execution_id, tenant_id),
  check ((kind = 'step') = (step_id is not null))
);
create unique index artifacts_one_primary_per_step on eidos.artifacts (execution_id, step_id) where kind = 'step';

alter table eidos.tenants enable row level security;
alter table eidos.tenant_members enable row level security;
alter table eidos.missions enable row level security;
alter table eidos.mission_events enable row level security;
alter table eidos.artifacts enable row level security;
alter table eidos.schema_migrations enable row level security;

do $$
declare role_name text;
begin
  foreach role_name in array array['anon', 'authenticated', 'service_role'] loop
    if exists (select 1 from pg_roles where rolname = role_name) then
      execute format('revoke all on schema eidos from %I', role_name);
      execute format('revoke all on all tables in schema eidos from %I', role_name);
      execute format('alter default privileges in schema eidos revoke all on tables from %I', role_name);
    end if;
  end loop;
end
$$;

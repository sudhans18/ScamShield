-- Syndicate detection persistence tables
create table if not exists public.syndicates (
    id uuid primary key default gen_random_uuid(),
    fingerprint text not null unique,
    cluster_size integer not null,
    phones jsonb not null default '[]'::jsonb,
    entities jsonb not null default '[]'::jsonb,
    risk_score double precision not null default 0,
    status text not null default 'potential',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists public.syndicate_members (
    id uuid primary key default gen_random_uuid(),
    syndicate_id uuid not null references public.syndicates(id) on delete cascade,
    entity_type text not null,
    entity_value text not null,
    entity_key text not null,
    created_at timestamptz not null default now(),
    unique (syndicate_id, entity_key)
);

create index if not exists idx_syndicate_members_type_value
    on public.syndicate_members(entity_type, entity_value);

-- ScamShield intelligence layer schema (4-layer architecture)
-- Run this file in Supabase SQL editor before deploying new backend pipeline.

create extension if not exists pgcrypto;
create extension if not exists vector;

-- Layer 1: embedding datasets and centroids
create table if not exists public.job_postings_legitimate (
    id          uuid primary key default gen_random_uuid(),
    text        text not null,
    embedding   vector(768),
    source      text default 'mock',
    created_at  timestamptz default now()
);

create table if not exists public.job_postings_scam (
    id          uuid primary key default gen_random_uuid(),
    text        text not null,
    embedding   vector(768),
    source      text default 'mock',
    created_at  timestamptz default now()
);

create table if not exists public.cluster_centroids (
    id           uuid primary key default gen_random_uuid(),
    cluster_name text not null unique, -- legitimate | scam
    centroid     vector(768) not null,
    sample_count integer default 0,
    updated_at   timestamptz default now()
);

-- Layer 2: mock company registry + prefix geo map
create table if not exists public.company_registry (
    id                     uuid primary key default gen_random_uuid(),
    name                   text not null,
    name_normalized        text not null unique,
    registered_city        text,
    registered_state       text,
    country                text default 'India',
    emigrate_registered    boolean default false,
    emigrate_raps_id       text,
    placement_countries    text[] default '{}',
    allowed_job_categories text[] default '{}',
    primary_phone          text,
    website                text,
    is_blacklisted         boolean default false,
    created_at             timestamptz default now()
);

create index if not exists idx_company_registry_name
    on public.company_registry(name_normalized);

create table if not exists public.phone_prefix_location (
    prefix    text primary key,
    country   text not null,
    region    text,
    is_mobile boolean default true
);

-- Layer 3: propagation fingerprints
create table if not exists public.message_fingerprints (
    id              uuid primary key default gen_random_uuid(),
    message_hash    text not null unique,
    first_seen_at   timestamptz default now(),
    last_seen_at    timestamptz default now(),
    seen_count      integer default 1,
    forwarded_flag  boolean default false,
    source_channels text[] default '{}'
);

create index if not exists idx_fingerprints_hash
    on public.message_fingerprints(message_hash);


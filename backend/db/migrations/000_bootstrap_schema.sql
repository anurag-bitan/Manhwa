-- Run once on a new Supabase project before 001 and 002.
-- Supabase Dashboard → SQL Editor → New query → paste this file → Run.

begin;

create table if not exists public.processing_jobs (
    id uuid primary key,
    status text not null,
    pdf_storage_path text not null,
    cognito_sub text,
    state_json jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    started_at timestamptz
);

create index if not exists processing_jobs_status_idx
    on public.processing_jobs (status);

insert into storage.buckets (id, name, public)
values
    ('pdfs', 'pdfs', false),
    ('pages', 'pages', false),
    ('audio', 'audio', false)
on conflict (id) do update
set public = excluded.public;

commit;

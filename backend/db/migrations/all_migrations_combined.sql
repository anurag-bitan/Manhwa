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
begin;

-- The API stores the immutable Cognito `sub` claim on every new job and
-- includes it in all user-facing reads. Existing rows remain nullable and are
-- intentionally inaccessible through the new authenticated API.
alter table public.processing_jobs
    add column if not exists cognito_sub text;

create index if not exists processing_jobs_cognito_sub_idx
    on public.processing_jobs (cognito_sub);

-- Only the backend service-role client should read this table directly.
alter table public.processing_jobs enable row level security;

-- Assets are returned as short-lived signed URLs after API ownership checks.
update storage.buckets
set public = false
where id in ('pdfs', 'pages', 'audio');

commit;
begin;

alter table public.processing_jobs
    add column if not exists created_at timestamptz not null default now(),
    add column if not exists started_at timestamptz;

create index if not exists processing_jobs_started_at_idx
    on public.processing_jobs (started_at)
    where started_at is not null;

create index if not exists processing_jobs_owner_started_at_idx
    on public.processing_jobs (cognito_sub, started_at)
    where started_at is not null;

create or replace function public.create_processing_upload(
    p_job_id uuid,
    p_cognito_sub text,
    p_pdf_storage_path text,
    p_state_json jsonb,
    p_max_pending_uploads integer,
    p_max_pending_uploads_global integer
)
returns text
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_count bigint;
begin
    perform pg_advisory_xact_lock(731020260817);

    select count(*)
      into v_count
      from public.processing_jobs
     where cognito_sub = p_cognito_sub
       and status = 'UPLOAD_PENDING'
       and created_at >= now() - interval '2 hours';

    if v_count >= greatest(p_max_pending_uploads, 1) then
        return 'PENDING_LIMIT';
    end if;

    select count(*)
      into v_count
      from public.processing_jobs
     where status = 'UPLOAD_PENDING'
       and created_at >= now() - interval '2 hours';

    if v_count >= greatest(p_max_pending_uploads_global, 1) then
        return 'GLOBAL_PENDING_LIMIT';
    end if;

    insert into public.processing_jobs (
        id, status, pdf_storage_path, cognito_sub, state_json
    ) values (
        p_job_id, 'UPLOAD_PENDING', p_pdf_storage_path, p_cognito_sub, p_state_json
    );

    return 'CREATED';
end;
$$;

create or replace function public.queue_processing_job(
    p_job_id uuid,
    p_cognito_sub text,
    p_max_user_starts_30d integer,
    p_max_global_starts_30d integer
)
returns text
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_status text;
    v_count bigint;
begin
    -- Serialize launch reservations so simultaneous requests cannot bypass the
    -- global concurrency or rolling quota checks.
    perform pg_advisory_xact_lock(731020260816);

    select status
      into v_status
      from public.processing_jobs
     where id = p_job_id
       and cognito_sub = p_cognito_sub
     for update;

    if not found then
        return 'NOT_FOUND';
    end if;

    if v_status in ('QUEUED', 'PROCESSING', 'TTS_COMPLETED') then
        return 'ALREADY_' || v_status;
    end if;

    if v_status <> 'UPLOAD_PENDING' then
        return 'INVALID_STATUS';
    end if;

    if exists (
        select 1
          from public.processing_jobs
         where status in ('QUEUED', 'PROCESSING')
           and id <> p_job_id
    ) then
        return 'BUSY';
    end if;

    select count(*)
      into v_count
      from public.processing_jobs
     where cognito_sub = p_cognito_sub
       and started_at >= now() - interval '30 days';
    if v_count >= greatest(p_max_user_starts_30d, 1) then
        return 'USER_LIMIT';
    end if;

    select count(*)
      into v_count
      from public.processing_jobs
     where started_at >= now() - interval '30 days';
    if v_count >= greatest(p_max_global_starts_30d, 1) then
        return 'GLOBAL_LIMIT';
    end if;

    update public.processing_jobs
       set status = 'QUEUED', started_at = now()
     where id = p_job_id;

    return 'QUEUED';
end;
$$;

revoke all on function public.queue_processing_job(uuid, text, integer, integer)
    from public, anon, authenticated;
grant execute on function public.queue_processing_job(uuid, text, integer, integer)
    to service_role;

revoke all on function public.create_processing_upload(uuid, text, text, jsonb, integer, integer)
    from public, anon, authenticated;
grant execute on function public.create_processing_upload(uuid, text, text, jsonb, integer, integer)
    to service_role;

commit;

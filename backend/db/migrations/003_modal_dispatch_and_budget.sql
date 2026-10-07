begin;

alter table public.processing_jobs
    add column if not exists modal_call_id text,
    add column if not exists lease_owner text,
    add column if not exists lease_expires_at timestamptz,
    add column if not exists heartbeat_at timestamptz,
    add column if not exists attempt_count integer not null default 0,
    add column if not exists completed_at timestamptz,
    add column if not exists runtime_seconds numeric(12,3),
    add column if not exists worker_cpu numeric(6,2),
    add column if not exists worker_memory_mib integer,
    add column if not exists estimated_compute_cost_usd numeric(12,6);

create index if not exists processing_jobs_active_lease_idx
    on public.processing_jobs (lease_expires_at)
    where status = 'PROCESSING';

drop function if exists public.queue_processing_job(uuid, text, integer, integer);

create or replace function public.queue_processing_job(
    p_job_id uuid,
    p_cognito_sub text,
    p_max_user_starts_per_day integer,
    p_max_global_starts_month integer,
    p_monthly_budget_usd numeric,
    p_admission_cost_usd numeric
)
returns text
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_status text;
    v_count bigint;
    v_monthly_cost numeric;
begin
    perform pg_advisory_xact_lock(731020260816);
    perform * from public.recover_stale_processing_jobs();

    select status into v_status
      from public.processing_jobs
     where id = p_job_id and cognito_sub = p_cognito_sub
     for update;

    if not found then return 'NOT_FOUND'; end if;
    if v_status in ('QUEUED', 'PROCESSING', 'TTS_COMPLETED') then
        return 'ALREADY_' || v_status;
    end if;
    if v_status <> 'UPLOAD_PENDING' then return 'INVALID_STATUS'; end if;

    if exists (
        select 1 from public.processing_jobs
         where status not in ('UPLOAD_PENDING', 'TTS_COMPLETED', 'FAILED')
           and id <> p_job_id
    ) then return 'BUSY'; end if;

    select count(*) into v_count
      from public.processing_jobs
     where cognito_sub = p_cognito_sub
       and started_at >= date_trunc('day', now());
    if v_count >= greatest(p_max_user_starts_per_day, 1) then
        return 'DAILY_LIMIT';
    end if;

    select count(*) into v_count
      from public.processing_jobs
     where started_at >= date_trunc('month', now());
    if v_count >= greatest(p_max_global_starts_month, 1) then
        return 'MONTHLY_LIMIT';
    end if;

    select coalesce(sum(estimated_compute_cost_usd), 0) into v_monthly_cost
      from public.processing_jobs
     where started_at >= date_trunc('month', now());
    if v_monthly_cost + greatest(p_admission_cost_usd, 0)
       > greatest(p_monthly_budget_usd, 0) then
        return 'BUDGET_LIMIT';
    end if;

    update public.processing_jobs
       set status = 'QUEUED',
           started_at = now(),
           completed_at = null,
           modal_call_id = null,
           estimated_compute_cost_usd = greatest(p_admission_cost_usd, 0)
     where id = p_job_id;
    return 'QUEUED';
end;
$$;

create or replace function public.claim_processing_job(
    p_job_id uuid,
    p_lease_owner text,
    p_lease_seconds integer
)
returns text
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_status text;
begin
    select status into v_status
      from public.processing_jobs
     where id = p_job_id
     for update;
    if not found then return 'NOT_FOUND'; end if;
    if v_status = 'TTS_COMPLETED' then return 'ALREADY_COMPLETED'; end if;
    if v_status <> 'QUEUED' then return 'NOT_QUEUED'; end if;

    update public.processing_jobs
       set status = 'PROCESSING',
           lease_owner = p_lease_owner,
           heartbeat_at = now(),
           lease_expires_at = now() + make_interval(secs => greatest(p_lease_seconds, 30)),
           attempt_count = attempt_count + 1,
           worker_cpu = 2,
           worker_memory_mib = 10240
     where id = p_job_id;
    return 'CLAIMED';
end;
$$;

create or replace function public.heartbeat_processing_job(
    p_job_id uuid,
    p_lease_owner text,
    p_lease_seconds integer
)
returns text
language plpgsql
security definer
set search_path = ''
as $$
begin
    update public.processing_jobs
       set heartbeat_at = now(),
           lease_expires_at = now() + make_interval(secs => greatest(p_lease_seconds, 30))
     where id = p_job_id
       and lease_owner = p_lease_owner
       and status not in ('TTS_COMPLETED', 'FAILED');
    if not found then return 'LEASE_LOST'; end if;
    return 'HEARTBEAT';
end;
$$;

create or replace function public.finish_processing_job(
    p_job_id uuid,
    p_lease_owner text,
    p_status text,
    p_state_json jsonb,
    p_runtime_seconds numeric,
    p_estimated_compute_cost_usd numeric
)
returns text
language plpgsql
security definer
set search_path = ''
as $$
begin
    if p_status not in ('TTS_COMPLETED', 'FAILED') then
        return 'INVALID_STATUS';
    end if;
    update public.processing_jobs
       set status = p_status,
           state_json = p_state_json,
           completed_at = now(),
           runtime_seconds = greatest(p_runtime_seconds, 0),
           estimated_compute_cost_usd = greatest(p_estimated_compute_cost_usd, 0),
           heartbeat_at = now(),
           lease_owner = null,
           lease_expires_at = null
     where id = p_job_id
       and lease_owner = p_lease_owner
       and status not in ('TTS_COMPLETED', 'FAILED');
    if not found then return 'LEASE_LOST'; end if;
    return 'FINISHED';
end;
$$;

create or replace function public.recover_stale_processing_jobs()
returns table(job_id uuid)
language plpgsql
security definer
set search_path = ''
as $$
begin
    return query
    update public.processing_jobs
       set status = 'FAILED',
           state_json = jsonb_set(
               jsonb_set(coalesce(state_json, '{}'::jsonb), '{status}', '"FAILED"'::jsonb, true),
               '{error}',
               '"Processing stopped unexpectedly. Please start a new upload."'::jsonb,
               true
           ),
           completed_at = now(),
           lease_owner = null,
           lease_expires_at = null,
           heartbeat_at = now()
     where (
           status not in ('UPLOAD_PENDING', 'QUEUED', 'TTS_COMPLETED', 'FAILED')
           and (lease_expires_at is null or lease_expires_at < now())
       )
        or (
           status = 'QUEUED'
           and started_at < now() - interval '5 minutes'
       )
    returning id;
end;
$$;

revoke all on function public.queue_processing_job(uuid, text, integer, integer, numeric, numeric)
    from public, anon, authenticated;
revoke all on function public.claim_processing_job(uuid, text, integer)
    from public, anon, authenticated;
revoke all on function public.heartbeat_processing_job(uuid, text, integer)
    from public, anon, authenticated;
revoke all on function public.finish_processing_job(uuid, text, text, jsonb, numeric, numeric)
    from public, anon, authenticated;
revoke all on function public.recover_stale_processing_jobs()
    from public, anon, authenticated;

grant execute on function public.queue_processing_job(uuid, text, integer, integer, numeric, numeric)
    to service_role;
grant execute on function public.claim_processing_job(uuid, text, integer)
    to service_role;
grant execute on function public.heartbeat_processing_job(uuid, text, integer)
    to service_role;
grant execute on function public.finish_processing_job(uuid, text, text, jsonb, numeric, numeric)
    to service_role;
grant execute on function public.recover_stale_processing_jobs()
    to service_role;

commit;

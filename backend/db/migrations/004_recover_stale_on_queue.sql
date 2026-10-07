-- Re-run after 003. Fails zombie EXTRACTED/PROCESSING rows, then new /start
-- can queue instead of returning BUSY.

begin;

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

grant execute on function public.queue_processing_job(uuid, text, integer, integer, numeric, numeric)
    to service_role;
grant execute on function public.recover_stale_processing_jobs()
    to service_role;

commit;

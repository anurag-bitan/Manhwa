begin;

-- Firebase uid is stored in cognito_sub (legacy column name). Do not rename.
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

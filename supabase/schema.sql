-- SnackScout team cloud. Paste this into Supabase → SQL Editor → New query → Run. Safe to run again.
create table if not exists public.records (
  kind       text not null,                 -- which local table (match_notes, users, ...)
  id         text not null,                 -- that row's key, e.g. "16750:USWATUM1:18"
  data       jsonb not null default '{}',   -- the row itself
  updated    double precision not null,     -- when it was changed (seconds since 1970)
  updated_by text,
  deleted    boolean not null default false,
  synced_at  timestamptz not null default now(),
  primary key (kind, id)
);
create index if not exists records_synced_at on public.records (synced_at);

-- Keep the newest version of each row, and stamp every change so laptops only download what's new.
create or replace function public.snackscout_touch() returns trigger language plpgsql as $$
begin
  if tg_op = 'UPDATE' and new.updated < old.updated then
    return old;                              -- an older edit arrived late: keep the newer one
  end if;
  new.synced_at := clock_timestamp();
  return new;
end $$;

drop trigger if exists records_touch on public.records;
create trigger records_touch before insert or update on public.records
  for each row execute function public.snackscout_touch();

-- Lock the table: only SnackScout's secret service_role key can read or write it.
-- (Newer Supabase projects don't grant table access to service_role automatically, so grant it here.)
alter table public.records enable row level security;
revoke all on public.records from anon, authenticated;
grant usage on schema public to service_role;
grant select, insert, update, delete on public.records to service_role;

-- Sentry RAG — Supabase Auth migration (idempotent).
-- Applied automatically by database.init_db on startup, and also safe to run
-- manually via the Supabase SQL Editor / `supabase db push`.
-- Requires a Supabase database so the `auth` schema exists for the trigger.

create table if not exists public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  email text not null,
  role text check (role in ('employee','manager','hr','admin')),
  status text not null default 'pending' check (status in ('pending','approved')),
  must_change_password boolean not null default false,
  created_at timestamptz not null default now()
);

create or replace function public.handle_new_user()
returns trigger as $$
begin
  insert into public.profiles (id, email, status)
  values (new.id, new.email, 'pending');
  return new;
end;
$$ language plpgsql security definer;

-- Attach the trigger only when Supabase's auth.users exists (guarded so a plain
-- Postgres dev DB — e.g. the Phase-1 POC — skips just this step).
do $$
begin
  if exists (
    select 1 from information_schema.tables
    where table_schema = 'auth' and table_name = 'users'
  ) then
    execute 'drop trigger if exists on_auth_user_created on auth.users';
    execute 'create trigger on_auth_user_created
      after insert on auth.users
      for each row execute function public.handle_new_user()';
  end if;
end
$$;

-- Repoint identity references away from the legacy users table: documents and
-- conversations now store the Supabase auth.users uuid (mirrored in profiles),
-- which the backend resolves against public.profiles. Dropping these FKs makes
-- the columns plain uuids so new Supabase user ids are storable and legacy
-- ids don't violate a constraint. (Ownership is enforced in app queries.)
alter table public.documents drop constraint if exists documents_uploaded_by_fkey;
alter table public.conversations drop constraint if exists conversations_user_id_fkey;

-- RLS: enable with ZERO policies = default-deny for the frontend's anon key.
-- The backend connects with the service-role/owner string, which bypasses RLS,
-- so these don't affect backend behavior — they only block direct client reads.
alter table public.profiles enable row level security;
alter table public.documents enable row level security;
alter table public.chunks enable row level security;
alter table public.conversations enable row level security;
alter table public.messages enable row level security;

-- Sentry RAG — Security hardening migration (idempotent, additive + reversible).
-- Applied automatically by database.init_db (this project applies every sorted
-- `.sql` under migrations/), and safe to run manually via the Supabase SQL Editor.
--
-- Addresses Security Advisor warnings without changing app behavior:
--   * Function Search Path Mutable            (public.handle_new_user)
--   * Public Can Execute SECURITY DEFINER Function (public.handle_new_user)
--   * Signed-In Users Can Execute SECURITY DEFINER Function (public.handle_new_user)
--
-- NOT covered here (do NOT try to automate these in SQL):
--   * public.vector                       -> keep in public (app uses it unqualified)
--   * Leaked Password Protection          -> Supabase project Auth config, must be
--                                             toggled in the Dashboard, not via SQL.

-- 1) Fix "Function Search Path Mutable": pin an EMPTY search_path on the
--    SECURITY DEFINER function. The body already fully-qualifies public.profiles,
--    and only references trigger record fields new.id / new.email, so an empty
--    search_path changes no behavior while preventing resolution of any
--    attacker-created object in an earlier schema.
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = ''
as $function$
begin
  insert into public.profiles (id, email, status)
  values (new.id, new.email, 'pending');
  return new;
end;
$function$;

-- 2) Fix EXECUTE-scope warnings. handle_new_user is a pure signup/trigger helper:
--    it is invoked ONLY by the AFTER INSERT trigger on_auth_user_created on
--    auth.users. Routine users (anon / authenticated) never need to call it by
--    NAME, and allowing them to run a SECURITY DEFINER function that inserts
--    into protected tables is a needless privilege widening.
--
--    PostgreSQL fires trigger functions regardless of whether the INSERT's
--    invoker holds direct EXECUTE on the function, so authentication/signup is
--    NOT affected by these revokes (verified with a transactional live test).
--
--    service_role + owner (postgres) retain EXECUTE for any legitimate
--    server-side / admin need.
revoke execute on function public.handle_new_user() from public;
revoke execute on function public.handle_new_user() from anon;
revoke execute on function public.handle_new_user() from authenticated;

-- Keep direct calls possible for the service role / owner if a future flow ever
-- needs to invoke it outside a trigger.
grant execute on function public.handle_new_user() to service_role;

-- (Optional reversal) To revert entirely, re-create without the security options:
--   create or replace function public.handle_new_user() returns trigger as $$
--     begin
--       insert into public.profiles (id, email, status) values (new.id, new.email, 'pending');
--       return new;
--     end;
--   $$ language plpgsql security definer;
--   grant execute on function public.handle_new_user() to public, anon, authenticated;
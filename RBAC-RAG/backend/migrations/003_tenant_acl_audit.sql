-- Sentry RAG — Tenant isolation, principal-based ACLs, and audit log (idempotent).
-- Applied automatically by database.init_db (this project applies every sorted
-- `.sql` under migrations/), and safe to run manually / repeatedly.
--
-- Design notes:
--   * Every existing row lands in the single default tenant
--     '00000000-0000-0000-0000-000000000001' so current data and tests keep
--     working unchanged.
--   * `acl_principals` generalizes the flat role check: entries are typed
--     strings ("role:manager" today; "group:finance" later — same shape, no
--     second migration). `allowed_roles` / `role` stay as legacy write-through
--     columns during the transition; they are NOT dropped here.
--   * `tenant_id` is denormalized onto chunks so the hot retrieval path
--     filters tenants without joining back to documents.
--   * `acl_version` increments whenever a row's principals change, so caches /
--     persisted indexes (BM25, embeddings) can detect staleness later.
--   * `audit_log` records security-relevant actions (uploads, publishes,
--     deletes, ACL changes) with actor + tenant + detail.

-- 1) Tenant columns -----------------------------------------------------------

ALTER TABLE public.profiles
  ADD COLUMN IF NOT EXISTS tenant_id uuid
  NOT NULL DEFAULT '00000000-0000-0000-0000-000000000001';

ALTER TABLE public.documents
  ADD COLUMN IF NOT EXISTS tenant_id uuid
  NOT NULL DEFAULT '00000000-0000-0000-0000-000000000001';

ALTER TABLE public.chunks
  ADD COLUMN IF NOT EXISTS tenant_id uuid
  NOT NULL DEFAULT '00000000-0000-0000-0000-000000000001';

-- 2) Principal-based ACL columns (legacy allowed_roles stays in place) --------

ALTER TABLE public.documents
  ADD COLUMN IF NOT EXISTS acl_principals text[] NOT NULL DEFAULT ARRAY[]::text[];
ALTER TABLE public.documents
  ADD COLUMN IF NOT EXISTS acl_version int NOT NULL DEFAULT 1;

ALTER TABLE public.chunks
  ADD COLUMN IF NOT EXISTS acl_principals text[] NOT NULL DEFAULT ARRAY[]::text[];
ALTER TABLE public.chunks
  ADD COLUMN IF NOT EXISTS acl_version int NOT NULL DEFAULT 1;

-- 3) Backfill: derive acl_principals from the legacy role arrays --------------
-- Guarded so it only touches rows that have not been backfilled yet (empty
-- acl_principals), making repeated runs a no-op.

UPDATE public.documents
SET acl_principals = ARRAY(SELECT 'role:' || r FROM unnest(allowed_roles) AS r)
WHERE acl_principals = ARRAY[]::text[]
  AND array_length(allowed_roles, 1) > 0;

UPDATE public.chunks
SET acl_principals = ARRAY(SELECT 'role:' || r FROM unnest(allowed_roles) AS r)
WHERE acl_principals = ARRAY[]::text[]
  AND array_length(allowed_roles, 1) > 0;

-- 4) Indexes ------------------------------------------------------------------
-- The hot-path predicate is `WHERE tenant_id = :t AND acl_principals && :p`:
-- a btree on tenant_id narrows the scan and bitmap-ANDs with the GIN index on
-- acl_principals. The legacy allowed_roles GIN index is kept for old readers.

CREATE INDEX IF NOT EXISTS chunks_tenant_idx ON public.chunks (tenant_id);
CREATE INDEX IF NOT EXISTS chunks_acl_principals_gin ON public.chunks USING GIN (acl_principals);

CREATE INDEX IF NOT EXISTS documents_tenant_idx ON public.documents (tenant_id);
CREATE INDEX IF NOT EXISTS documents_acl_principals_gin ON public.documents USING GIN (acl_principals);

-- 5) Audit log ----------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.audit_log (
    id bigserial PRIMARY KEY,
    tenant_id uuid NOT NULL,
    actor_id uuid,
    action text NOT NULL,          -- 'document.upload', 'document.publish',
                                   -- 'document.delete', 'acl.update', 'chunk.acl.update'
    target_type text NOT NULL,     -- 'document' | 'chunk' | 'user'
    target_id text NOT NULL,
    detail jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS audit_log_tenant_created_idx
  ON public.audit_log (tenant_id, created_at DESC);

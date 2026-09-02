-- Sentry RAG — Persisted Postgres full-text lexical index (idempotent).
-- Applied automatically by database.init_db (this project applies every sorted
-- `.sql` under migrations/), and safe to run manually / repeatedly.
--
-- Replaces the per-query in-process BM25 scan: the lexical leg now matches and
-- ranks INSIDE Postgres (search_vector @@ tsquery, ts_rank_cd ordering, LIMIT)
-- instead of pulling every authorized chunk into Python.
--
-- 'simple' text search config ON PURPOSE: unlike 'english' it does not stem
-- and does not drop stopwords, so exact terms — policy numbers, codes, names,
-- amounts — stay matchable, mirroring the raw-token behavior of the previous
-- BM25Okapi leg.
--
-- Note on the migration loader: database._split_sql() is dollar-quote-aware,
-- so the $$ ... $$ plpgsql body below (with its internal semicolons) is kept
-- intact as a single statement. Verified before this migration was written.

-- 1) Column (nullable: backfill below fills it; the trigger keeps it current)

ALTER TABLE public.chunks ADD COLUMN IF NOT EXISTS search_vector tsvector;

-- 2) Backfill existing rows. Updates search_vector only — the trigger below
--    fires on UPDATE OF content, so this pass does not re-trigger itself.

UPDATE public.chunks
SET search_vector = to_tsvector('simple', content)
WHERE search_vector IS NULL;

-- 3) Trigger: keep search_vector current on every content write, so ingest
--    code needs no changes. DROP IF EXISTS + CREATE = idempotent on rerun.

CREATE OR REPLACE FUNCTION public.chunks_search_vector_update() RETURNS trigger AS $$
BEGIN
  NEW.search_vector := to_tsvector('simple', NEW.content);
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS chunks_search_vector_trigger ON public.chunks;

CREATE TRIGGER chunks_search_vector_trigger
  BEFORE INSERT OR UPDATE OF content ON public.chunks
  FOR EACH ROW EXECUTE FUNCTION public.chunks_search_vector_update();

-- 4) GIN index so the @@ match stays indexed at scale

CREATE INDEX IF NOT EXISTS chunks_search_vector_gin
  ON public.chunks USING GIN (search_vector);

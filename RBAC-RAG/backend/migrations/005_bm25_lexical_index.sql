-- Sentry RAG — True BM25 lexical index in plain Postgres (idempotent).
-- Applied automatically by database.init_db (this project applies every sorted
-- `.sql` under migrations/), and safe to run manually / repeatedly.
--
-- Context: the previous lexical leg used ts_rank_cd on a persisted tsvector,
-- which is NOT BM25 (no corpus-aware inverse-document-frequency weighting).
-- ParadeDB pg_search (a real BM25 implementation for Postgres) is NOT usable
-- in our environment: it is absent from Supabase's approved-extension list
-- and ParadeDB only ship it via their own Docker image / VPC deployment
-- ('ParadeDB Cloud: coming soon' — no managed-Postgres/Supabase path).
--
-- This migration therefore implements GENUINE BM25 with only stock Postgres:
--   * chunks.doclen      — document length in tokens (the same [a-z0-9]+
--                          tokenization the app applies to queries).
--   * chunk_terms        — per-(chunk, term) term frequency. The per-term
--                          row count across the corpus IS the document
--                          frequency n_t used by BM25's IDF.
--   * triggers on chunks — keep doclen + chunk_terms current on INSERT,
--                          UPDATE OF content, and DELETE (cascade-safe), so
--                          the ingest/delete code needs no changes.
-- Scoring happens at QUERY time in retrieval.py using the standard BM25
-- formula: sum over query terms t of
--   ln((N - n_t + 0.5)/(n_t + 0.5))                          -- IDF (corpus-aware)
--     * tf * (k1 + 1) / (tf + k1 * (1 - b + b * doclen / avgdl))   -- k1=1.5,b=0.75
-- with N and avgdl computed over the SAME authorized subset the RBAC WHERE
-- clause filters to (matching the semantics of the former BM25Okapi leg).

-- 1) Document length (in app tokens)

ALTER TABLE public.chunks ADD COLUMN IF NOT EXISTS doclen int NOT NULL DEFAULT 0;

-- 2) Per-chunk term frequencies

CREATE TABLE IF NOT EXISTS public.chunk_terms (
    chunk_id bigint NOT NULL REFERENCES public.chunks(id) ON DELETE CASCADE,
    term text NOT NULL,
    tf int NOT NULL,
    PRIMARY KEY (chunk_id, term)
);

CREATE INDEX IF NOT EXISTS chunk_terms_term_idx ON public.chunk_terms (term);

-- 3) Triggers (dollar-quoted; loader database._split_sql is dollar-quote-aware,
--    keeping each body intact as one statement despite internal semicolons).

CREATE OR REPLACE FUNCTION public.chunks_bm25_set_doclen() RETURNS trigger AS $$
DECLARE
  n int;
BEGIN
  SELECT count(*) INTO n FROM regexp_matches(lower(NEW.content), '[a-z0-9]+', 'g');
  NEW.doclen := n;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION public.chunks_bm25_sync_terms() RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    DELETE FROM public.chunk_terms WHERE chunk_id = OLD.id;
    RETURN OLD;
  END IF;
  IF TG_OP = 'UPDATE' AND NEW.content IS NOT DISTINCT FROM OLD.content THEN
    RETURN NEW; -- content unchanged: nothing to rebuild
  END IF;
  DELETE FROM public.chunk_terms WHERE chunk_id = NEW.id;
  INSERT INTO public.chunk_terms (chunk_id, term, tf)
    SELECT NEW.id, lower(m[1]), count(*)
    FROM regexp_matches(lower(NEW.content), '[a-z0-9]+', 'g') AS m
    GROUP BY 1, 2;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS chunks_bm25_doclen_trigger ON public.chunks;
CREATE TRIGGER chunks_bm25_doclen_trigger
  BEFORE INSERT OR UPDATE OF content ON public.chunks
  FOR EACH ROW EXECUTE FUNCTION public.chunks_bm25_set_doclen();

DROP TRIGGER IF EXISTS chunks_bm25_terms_trigger ON public.chunks;
CREATE TRIGGER chunks_bm25_terms_trigger
  AFTER INSERT OR UPDATE OF content OR DELETE ON public.chunks
  FOR EACH ROW EXECUTE FUNCTION public.chunks_bm25_sync_terms();

-- 4) Backfill existing rows (guarded on doclen=0 so reruns are no-ops; the
--    UPDATE ... FROM form avoids a self-referencing subquery on chunks)

UPDATE public.chunks c
SET doclen = sub.n
FROM (
  SELECT c2.id, count(*) AS n
  FROM public.chunks c2
  CROSS JOIN LATERAL regexp_matches(lower(c2.content), '[a-z0-9]+', 'g')
  GROUP BY c2.id
) sub
WHERE c.id = sub.id AND c.doclen = 0;

INSERT INTO public.chunk_terms (chunk_id, term, tf)
SELECT c.id, lower(m[1]), count(*)
FROM public.chunks c
CROSS JOIN LATERAL regexp_matches(lower(c.content), '[a-z0-9]+', 'g') AS m
WHERE c.doclen > 0
  AND NOT EXISTS (SELECT 1 FROM public.chunk_terms ct WHERE ct.chunk_id = c.id)
GROUP BY c.id, 2;
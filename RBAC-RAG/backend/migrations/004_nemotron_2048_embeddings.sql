-- Move the application from nv-embedqa-e5-v5's 1024-dimensional vectors to
-- Nemotron-3 Embed's 2048-dimensional vectors.
--
-- This project reapplies its idempotent migrations on every startup. The
-- dimension check makes this a one-time change: deployments already using
-- vector(2048) are left untouched. Existing 1024-dimension data cannot be
-- converted faithfully, so fail with a clear error instead of mixing models.
-- A halfvec expression index is used because standard vector HNSW indexes are
-- limited to 2000 dimensions while Nemotron-3 Embed returns 2048.

DO $$
DECLARE
  embedding_dimensions integer;
  has_existing_chunks boolean;
BEGIN
  SELECT a.atttypmod
  INTO embedding_dimensions
  FROM pg_attribute AS a
  WHERE a.attrelid = 'public.chunks'::regclass
    AND a.attname = 'embedding'
    AND NOT a.attisdropped;

  IF embedding_dimensions = 1024 THEN
    SELECT EXISTS (SELECT 1 FROM public.chunks) INTO has_existing_chunks;
    IF has_existing_chunks THEN
      RAISE EXCEPTION
        'Cannot migrate non-empty chunks.embedding from vector(1024) to vector(2048). Re-embed existing documents first.';
    END IF;

    DROP INDEX IF EXISTS public.chunks_embedding_hnsw_idx;
    ALTER TABLE public.chunks
      ALTER COLUMN embedding TYPE vector(2048)
      USING embedding::vector(2048);
    CREATE INDEX chunks_embedding_hnsw_idx
      ON public.chunks USING hnsw ((embedding::halfvec(2048)) halfvec_cosine_ops);
  ELSIF embedding_dimensions <> 2048 THEN
    RAISE EXCEPTION
      'Unsupported chunks.embedding dimension: % (expected 1024 or 2048)', embedding_dimensions;
  END IF;
END
$$;

-- 003_hnsw_vector_index.sql – create HNSW index for vector similarity
-- Idempotent migration: creates a HNSW index on the `embedding` column of `chunks`.
-- No DROP statement is included; to roll back, execute the corresponding DROP manually.
--
-- Verify pgvector extension is installed and its version before relying on the index:
--   SELECT extname, extversion FROM pg_extension WHERE extname = 'vector';
--   (should return a version string, e.g., 0.5.1).
--
-- Manual EXPLAIN verification (run against your dev DB):
--   SET LOCAL hnsw.ef_search = 64;  -- or whatever you configure via HNSW_EF_SEARCH
--   EXPLAIN (ANALYZE, BUFFERS)
--   SELECT c.id FROM chunks c
--   JOIN documents d ON d.id = c.document_id
--   WHERE d.status = 'published'
--     AND c.allowed_roles && ARRAY['manager']
--   ORDER BY c.embedding <=> '[0,0,0,...]'::vector
--   LIMIT 10;
--   Look for "Index Scan" on chunks_embedding_hnsw_idx.

CREATE INDEX IF NOT EXISTS chunks_embedding_hnsw_idx
    ON chunks USING hnsw (embedding vector_cosine_ops);

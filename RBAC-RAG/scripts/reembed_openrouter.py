"""Re-embed all chunks whose embedding is NULL after the 2048->1024 migration.

Run this AFTER the backend has started once (which applies
005_openrouter_embed_1024.sql and NULLs the old 2048-dim embeddings). It then
re-embeds every chunk's text through the OpenRouter embed model and writes the
new 1024-dim vectors back. Idempotent/resumable: only rows where embedding IS
NULL are processed, so re-running after a partial failure continues where it
left off.

Usage:
    cd backend && python ../scripts/reembed_openrouter.py
"""
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("reembed")

import openrouter  # noqa: E402  (backend is on the path)
from sqlalchemy import text  # noqa: E402

BATCH = 32


async def main() -> None:
    from database import engine  # reads DATABASE_URL from backend/.env

    async with engine.connect() as conn:
        ids = [
            r[0]
            for r in (await conn.execute(
                text("SELECT id FROM chunks WHERE embedding IS NULL ORDER BY id")
            )).fetchall()
        ]
    logger.info("Chunks to re-embed: %d", len(ids))
    if not ids:
        return

    done = 0
    for i in range(0, len(ids), BATCH):
        batch_ids = ids[i : i + BATCH]
        async with engine.connect() as conn, conn.begin():
            rows = (await conn.execute(
                text("SELECT id, content FROM chunks WHERE id = ANY(:ids)"),
                {"ids": batch_ids},
            )).fetchall()
            texts = [r[1] for r in rows]
            vectors = await openrouter.embed(texts)
            for (chunk_id, _content), vec in zip(rows, vectors):
                await conn.execute(
                    text("UPDATE chunks SET embedding = :v WHERE id = :id"),
                    {"v": "[" + ",".join(f"{x:.7f}" for x in vec) + "]", "id": chunk_id},
                )
        done += len(batch_ids)
        logger.info("Re-embedded %d/%d", done, len(ids))
    logger.info("Done. All chunks re-embedded with OpenRouter bold vectors.")


if __name__ == "__main__":
    asyncio.run(main())

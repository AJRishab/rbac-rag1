"""
Sentry RAG - Phase 1 POC
Proves that:
  1. NVIDIA NIM embeddings API works
  2. NVIDIA NIM chat completions API works
  3. PostgreSQL + pgvector store/retrieve vectors
  4. RBAC filter runs INSIDE the SQL query (WHERE allowed_roles && ARRAY[user_role])
  5. Same query as different roles returns different chunks
  6. Admin bypasses the filter (sees all chunks)
  7. End-to-end RAG generates answer with citations
"""
import os
import asyncio
import json
from pathlib import Path
from dotenv import load_dotenv
import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

load_dotenv(Path(__file__).parent / ".env")

OPENROUTER_API_KEY = os.environ["OPENROUTER_API_KEY"]
OPENROUTER_BASE_URL = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
OPENROUTER_EMBED_MODEL = os.environ.get("OPENROUTER_EMBED_MODEL", "liquid/lfm-2.5-embedding-350m:free")
OPENROUTER_CHAT_MODEL = os.environ.get("OPENROUTER_CHAT_MODEL", "google/gemma-4-31b-it:free")
DATABASE_URL = os.environ["DATABASE_URL"]

# ------------------------------ NIM helpers ------------------------------

async def nim_embed(client: httpx.AsyncClient, texts: list[str], input_type: str = "passage") -> list[list[float]]:
    """Call NIM OpenAI-compatible embeddings endpoint.
    NIM's E5-based models require an 'input_type' extension: 'passage' or 'query'.
    """
    payload = {
        "input": texts,
        "model": OPENROUTER_EMBED_MODEL,
        "input_type": input_type,
        "encoding_format": "float",
        "truncate": "NONE",
    }
    r = await client.post(
        f"{OPENROUTER_BASE_URL}/embeddings",
        headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Accept": "application/json"},
        json=payload,
        timeout=60.0,
    )
    if r.status_code != 200:
        raise RuntimeError(f"NIM embed failed {r.status_code}: {r.text[:400]}")
    data = r.json()
    return [d["embedding"] for d in data["data"]]


async def nim_chat(client: httpx.AsyncClient, system: str, user: str) -> str:
    payload = {
        "model": OPENROUTER_CHAT_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.2,
        "top_p": 0.9,
        "max_tokens": 512,
    }
    r = await client.post(
        f"{OPENROUTER_BASE_URL}/chat/completions",
        headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Accept": "application/json"},
        json=payload,
        timeout=90.0,
    )
    if r.status_code != 200:
        raise RuntimeError(f"NIM chat failed {r.status_code}: {r.text[:400]}")
    data = r.json()
    return data["choices"][0]["message"]["content"]

# ------------------------------ pgvector helpers ------------------------------

SCHEMA_SQL = """
CREATE EXTENSION IF NOT EXISTS vector;
DROP TABLE IF EXISTS poc_chunks;
CREATE TABLE poc_chunks (
    id serial PRIMARY KEY,
    doc_title text NOT NULL,
    content text NOT NULL,
    embedding vector(1024) NOT NULL,
    allowed_roles text[] NOT NULL
);
CREATE INDEX poc_chunks_roles_gin ON poc_chunks USING GIN (allowed_roles);
"""

async def setup_db(engine):
    async with engine.begin() as conn:
        for stmt in [s for s in SCHEMA_SQL.split(";") if s.strip()]:
            await conn.execute(text(stmt))


def fmt_vec(v: list[float]) -> str:
    # pgvector text literal format
    return "[" + ",".join(f"{x:.7f}" for x in v) + "]"


async def insert_chunk(session: AsyncSession, doc_title: str, content: str, embedding: list[float], roles: list[str]):
    await session.execute(
        text(
            "INSERT INTO poc_chunks (doc_title, content, embedding, allowed_roles) "
            "VALUES (:t, :c, CAST(:e AS vector), :r)"
        ),
        {"t": doc_title, "c": content, "e": fmt_vec(embedding), "r": roles},
    )


async def retrieve(session: AsyncSession, query_emb: list[float], user_role: str, top_k: int = 4, admin_bypass: bool = False):
    """Retrieve top_k chunks with RBAC filter applied INSIDE the SQL query.
    Returns tuple (rows, retrieved_count, blocked_count).
    blocked_count = how many of the top_k-by-similarity would have been retrieved without the RBAC filter but were excluded.
    """
    if admin_bypass:
        rows_result = await session.execute(
            text(
                "SELECT id, doc_title, content, allowed_roles, (embedding <=> CAST(:q AS vector)) AS distance "
                "FROM poc_chunks ORDER BY embedding <=> CAST(:q AS vector) LIMIT :k"
            ),
            {"q": fmt_vec(query_emb), "k": top_k},
        )
        rows = rows_result.fetchall()
        return rows, len(rows), 0

    # RBAC-filtered retrieval — filter happens INSIDE SQL, not after
    filtered = await session.execute(
        text(
            "SELECT id, doc_title, content, allowed_roles, (embedding <=> CAST(:q AS vector)) AS distance "
            "FROM poc_chunks WHERE allowed_roles && :r "
            "ORDER BY embedding <=> CAST(:q AS vector) LIMIT :k"
        ),
        {"q": fmt_vec(query_emb), "r": [user_role], "k": top_k},
    )
    rows = filtered.fetchall()

    # Compute blocked_count: top_k-by-similarity ignoring RBAC minus the ones that survived RBAC
    unfiltered = await session.execute(
        text(
            "SELECT id FROM poc_chunks ORDER BY embedding <=> CAST(:q AS vector) LIMIT :k"
        ),
        {"q": fmt_vec(query_emb), "k": top_k},
    )
    unfiltered_ids = {r[0] for r in unfiltered.fetchall()}
    kept_ids = {r[0] for r in rows}
    blocked = len(unfiltered_ids - kept_ids)
    return rows, len(rows), blocked

# ------------------------------ Test corpus ------------------------------

CORPUS = [
    # Employee-visible
    {
        "title": "Employee-Handbook-2026",
        "content": "All employees are eligible for 20 paid vacation days per year. Vacation must be approved by your direct manager at least two weeks in advance. Unused vacation days do not roll over.",
        "roles": ["employee", "manager", "hr"],
    },
    {
        "title": "Company-Values-Doc",
        "content": "Our company values transparency, ownership, and customer obsession. Every employee is expected to embody these values in their daily work.",
        "roles": ["employee", "manager", "hr"],
    },
    # HR-only sensitive content
    {
        "title": "HR-Compensation-Bands-Q3",
        "content": "Software Engineer L3 base compensation ranges from $145,000 to $185,000 with a target bonus of 12 percent. L4 ranges from $180,000 to $230,000 with a target bonus of 15 percent. These bands are confidential and must not be shared outside HR.",
        "roles": ["hr"],
    },
    {
        "title": "HR-Performance-Review-Guidelines",
        "content": "HR performance review guidelines: managers should calibrate ratings across teams. PIP recommendations must be reviewed by HR before delivery. Termination decisions require HR sign-off. This document is HR-only.",
        "roles": ["hr"],
    },
    # Manager+HR only
    {
        "title": "Manager-Playbook-Hiring",
        "content": "Managers running interview loops should schedule five 45-minute panels covering coding, systems design, behavioral, product, and leadership. Interview rubrics are provided in the shared managers folder.",
        "roles": ["manager", "hr"],
    },
]

QUESTIONS = [
    "What is our compensation policy for engineers?",
    "How many vacation days do employees get?",
]

# ------------------------------ Main ------------------------------

async def run_rag(session: AsyncSession, client: httpx.AsyncClient, question: str, role: str, admin_bypass: bool = False):
    q_emb = (await nim_embed(client, [question], input_type="query"))[0]
    rows, retrieved, blocked = await retrieve(session, q_emb, role, top_k=4, admin_bypass=admin_bypass)
    citations = [r.doc_title for r in rows]
    if not rows:
        return {
            "answer": "I don't have any documents that your role is allowed to see for this question.",
            "citations": [],
            "retrieved": 0,
            "blocked": blocked,
            "chunk_ids": [],
        }
    context = "\n\n".join(f"[Source: {r.doc_title}]\n{r.content}" for r in rows)
    system = (
        "You are Sentry RAG. Answer the user's question using ONLY the provided sources. "
        "Cite the source titles you used in the format (Source: Title). If the answer isn't in the sources, say so."
    )
    user = f"Question: {question}\n\nSources:\n{context}"
    answer = await nim_chat(client, system, user)
    return {
        "answer": answer,
        "citations": citations,
        "retrieved": retrieved,
        "blocked": blocked,
        "chunk_ids": [r.id for r in rows],
    }


async def main():
    print("=" * 80)
    print("SENTRY RAG - PHASE 1 POC")
    print("=" * 80)

    engine = create_async_engine(DATABASE_URL, echo=False)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    print("\n[1] Setting up schema (pgvector + poc_chunks)...")
    await setup_db(engine)
    print("    OK")

    async with httpx.AsyncClient() as client:
        print("\n[2] Testing NIM embeddings API on 1 sample...")
        try:
            sample = await nim_embed(client, ["hello world"], input_type="passage")
            print(f"    OK - got embedding, dim={len(sample[0])}")
            embed_dim = len(sample[0])
        except Exception as e:
            print(f"    FAIL: {e}")
            raise

        assert embed_dim == 1024, f"Expected 1024-dim embeddings, got {embed_dim}"

        print("\n[3] Testing NIM chat completions API...")
        try:
            hello = await nim_chat(client, "You are a friendly assistant.", "Say hi in 5 words.")
            print(f"    OK - got response: {hello[:80]}")
        except Exception as e:
            print(f"    FAIL: {e}")
            raise

        print(f"\n[4] Embedding + inserting {len(CORPUS)} test chunks...")
        contents = [c["content"] for c in CORPUS]
        embeddings = await nim_embed(client, contents, input_type="passage")
        async with Session() as session:
            for c, emb in zip(CORPUS, embeddings):
                await insert_chunk(session, c["title"], c["content"], emb, c["roles"])
            await session.commit()
        print("    OK - all chunks inserted")

        print("\n[5] Running RBAC retrieval + RAG for each role...")
        results = {}
        for question in QUESTIONS:
            print(f"\n  QUESTION: {question}")
            results[question] = {}
            for role in ["employee", "manager", "hr"]:
                async with Session() as session:
                    res = await run_rag(session, client, question, role)
                results[question][role] = res
                print(f"    [{role:8s}] retrieved={res['retrieved']:2d} blocked={res['blocked']:2d}  chunks={res['chunk_ids']}  citations={res['citations']}")
            # admin bypass
            async with Session() as session:
                res_admin = await run_rag(session, client, question, "admin", admin_bypass=True)
            results[question]["admin"] = res_admin
            print(f"    [admin   ] retrieved={res_admin['retrieved']:2d} blocked={res_admin['blocked']:2d}  chunks={res_admin['chunk_ids']}  citations={res_admin['citations']}")
            print(f"    ---")
            print(f"    EMPLOYEE ANSWER: {results[question]['employee']['answer'][:200]}")
            print(f"    HR ANSWER      : {results[question]['hr']['answer'][:200]}")
            print(f"    ADMIN ANSWER   : {results[question]['admin']['answer'][:200]}")

        # -------- Assertions --------
        print("\n[6] Verifying RBAC-differentiated retrieval...")

        # For the compensation question: HR-only chunks must appear for HR but NOT for employee
        comp_q = QUESTIONS[0]
        emp_chunks = set(results[comp_q]["employee"]["chunk_ids"])
        hr_chunks = set(results[comp_q]["hr"]["chunk_ids"])
        admin_chunks = set(results[comp_q]["admin"]["chunk_ids"])

        assert hr_chunks != emp_chunks, f"HR and employee retrieved the same chunks — RBAC filter not working! hr={hr_chunks} emp={emp_chunks}"
        assert len(admin_chunks) >= len(hr_chunks), "Admin should see at least as many chunks as HR"

        # Verify HR sees the HR-only compensation chunk (title contains 'HR-Compensation')
        hr_titles = set(results[comp_q]["hr"]["citations"])
        emp_titles = set(results[comp_q]["employee"]["citations"])
        assert any("HR-Compensation" in t for t in hr_titles), f"HR must see HR-Compensation-Bands doc, got: {hr_titles}"
        assert not any("HR-Compensation" in t for t in emp_titles), f"Employee must NOT see HR-Compensation-Bands doc, got: {emp_titles}"

        # Verify blocked count > 0 for employee on compensation question
        assert results[comp_q]["employee"]["blocked"] > 0, "Expected employee blocked_count > 0 on comp question"
        assert results[comp_q]["hr"]["blocked"] == 0, "Expected hr blocked_count == 0 on comp question (HR sees everything relevant)"

        print("    OK - RBAC differentiation verified")
        print(f"    Employee retrieved chunks: {emp_chunks}")
        print(f"    HR retrieved chunks      : {hr_chunks}")
        print(f"    Admin retrieved chunks   : {admin_chunks}")
        print(f"    Employee blocked count on comp question: {results[comp_q]['employee']['blocked']}")

        print("\n[7] All POC assertions passed! Core is proven working.")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())

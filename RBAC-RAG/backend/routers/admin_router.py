"""Admin router: user approvals, document upload/list/edit.

The upload endpoint delegates to focused helpers to keep its cyclomatic complexity low.
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from deps import get_db, require_admin
from schemas import (
    UserOut, ApproveUserRequest, DocumentOut, UpdateDocRolesRequest,
    ChunkOut, UpdateChunkRolesRequest,
)
from ingest import chunk_file
import nim_client

router = APIRouter(prefix="/admin", tags=["admin"])
logger = logging.getLogger(__name__)

VALID_ROLES = {"employee", "manager", "hr", "admin"}
MAX_UPLOAD_MB = 20
SUPPORTED_EXTS = (".txt", ".md", ".markdown", ".pdf", ".docx")


# ---------- Users ----------

@router.get("/users", response_model=list[UserOut])
async def list_users(admin: dict = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        text("SELECT id, email, role, status, must_change_password, created_at FROM users ORDER BY created_at DESC")
    )
    return [
        UserOut(
            id=str(r.id), email=r.email, role=r.role, status=r.status,
            must_change_password=r.must_change_password, created_at=r.created_at,
        )
        for r in result.fetchall()
    ]


async def _update_user_role(db: AsyncSession, user_id: str, role: str, approve: bool = False) -> UserOut:
    if role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail=f"Invalid role. Must be one of {sorted(VALID_ROLES)}")
    if approve:
        sql = (
            "UPDATE users SET status = 'approved', role = :r WHERE id = CAST(:i AS uuid) "
            "RETURNING id, email, role, status, must_change_password, created_at"
        )
    else:
        sql = (
            "UPDATE users SET role = :r WHERE id = CAST(:i AS uuid) "
            "RETURNING id, email, role, status, must_change_password, created_at"
        )
    row = (await db.execute(text(sql), {"r": role, "i": user_id})).first()
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    await db.commit()
    return UserOut(
        id=str(row.id), email=row.email, role=row.role, status=row.status,
        must_change_password=row.must_change_password, created_at=row.created_at,
    )


@router.post("/users/{user_id}/approve", response_model=UserOut)
async def approve_user(user_id: str, req: ApproveUserRequest, admin: dict = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    return await _update_user_role(db, user_id, req.role, approve=True)


@router.post("/users/{user_id}/role", response_model=UserOut)
async def change_user_role(user_id: str, req: ApproveUserRequest, admin: dict = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    return await _update_user_role(db, user_id, req.role, approve=False)


# ---------- Documents ----------

def _fmt_vec(v: list[float]) -> str:
    return "[" + ",".join(f"{x:.7f}" for x in v) + "]"


@router.get("/documents", response_model=list[DocumentOut])
async def list_documents(admin: dict = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    result = await db.execute(text(
        "SELECT d.id, d.title, d.filename, d.allowed_roles, d.status, d.chunk_count, d.uploaded_at, u.email AS uploader_email "
        "FROM documents d LEFT JOIN users u ON u.id = d.uploaded_by "
        "ORDER BY d.uploaded_at DESC"
    ))
    return [
        DocumentOut(
            id=str(r.id), title=r.title, filename=r.filename,
            allowed_roles=list(r.allowed_roles or []), status=r.status, chunk_count=r.chunk_count,
            uploaded_at=r.uploaded_at, uploaded_by_email=r.uploader_email,
        )
        for r in result.fetchall()
    ]


# ---- Upload helpers ----


def _validate_size(data: bytes) -> None:
    if len(data) > MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"File too large (max {MAX_UPLOAD_MB} MB)")


def _validate_filename(filename: str) -> None:
    lower = filename.lower()
    if not lower.endswith(SUPPORTED_EXTS):
        raise HTTPException(status_code=400, detail="Supported formats: .txt, .md, .pdf, .docx")


def _parse_roles(allowed_roles_csv: str) -> list[str]:
    roles = [r.strip().lower() for r in allowed_roles_csv.split(",") if r.strip()]
    invalid = [r for r in roles if r not in VALID_ROLES]
    if invalid:
        raise HTTPException(status_code=400, detail=f"Invalid roles: {invalid}. Must be from {sorted(VALID_ROLES)}")
    if not roles:
        raise HTTPException(status_code=400, detail="Select at least one role")
    return sorted(set(roles))


def _parse_and_chunk(filename: str, data: bytes) -> list[tuple[str, int | None]]:
    try:
        chunks = chunk_file(filename, data, chunk_tokens=500, overlap_tokens=50)
    except Exception as e:
        logger.exception("parse failed for %s", filename)
        raise HTTPException(status_code=400, detail=f"Failed to parse file: {e}") from e
    if not chunks:
        raise HTTPException(status_code=400, detail="File contains no readable text after parsing")
    return chunks


async def _embed_chunks(chunks: list[str]) -> list[list[float]]:
    try:
        return await nim_client.embed(chunks, input_type="passage")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("embedding failed")
        raise HTTPException(status_code=502, detail=f"Embedding failed: {e}") from e


async def _persist_document(
    db: AsyncSession,
    title: str,
    filename: str,
    uploaded_by: str,
    roles: list[str],
    chunks: list[tuple[str, int | None]],
    embeddings: list[list[float]],
    chunk_roles: list[list[str]],
):
    doc = (await db.execute(
        text(
            "INSERT INTO documents (title, filename, uploaded_by, allowed_roles, status, chunk_count) "
            "VALUES (:t, :f, CAST(:u AS uuid), :r, 'pending_review', :c) "
            "RETURNING id, title, filename, allowed_roles, status, chunk_count, uploaded_at"
        ),
        {"t": title, "f": filename, "u": uploaded_by, "r": roles, "c": len(chunks)},
    )).first()

    for idx, ((content, source_page), emb, roles) in enumerate(zip(chunks, embeddings, chunk_roles)):
        await db.execute(
            text(
                "INSERT INTO chunks (document_id, chunk_index, content, embedding, allowed_roles, roles_ai_suggested, source_page) "
                "VALUES (CAST(:d AS uuid), :i, :c, CAST(:e AS vector), :r, true, :p)"
            ),
            {"d": str(doc.id), "i": idx, "c": content, "e": _fmt_vec(emb), "r": roles, "p": source_page},
        )
    await db.commit()
    return doc


@router.post("/documents", response_model=DocumentOut)
async def upload_document(
    title: str = Form(...),
    allowed_roles: str = Form(...),
    file: UploadFile = File(...),
    admin: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    data = await file.read()
    _validate_size(data)
    filename = file.filename or "upload.bin"
    _validate_filename(filename)
    roles = _parse_roles(allowed_roles)

    chunks = _parse_and_chunk(filename, data)
    chunk_texts = [content for content, _page in chunks]
    embeddings = await _embed_chunks(chunk_texts)
    chunk_roles = await nim_client.suggest_chunk_roles(chunk_texts, roles)

    doc_title = title.strip() or filename
    doc = await _persist_document(db, doc_title, filename, admin["id"], roles, chunks, embeddings, chunk_roles)

    return DocumentOut(
        id=str(doc.id), title=doc.title, filename=doc.filename,
        allowed_roles=list(doc.allowed_roles or []), status=doc.status, chunk_count=doc.chunk_count,
        uploaded_at=doc.uploaded_at, uploaded_by_email=admin["email"],
    )


@router.patch("/documents/{doc_id}", response_model=DocumentOut)
async def update_document_roles(doc_id: str, req: UpdateDocRolesRequest, admin: dict = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    roles = sorted(set(r.lower() for r in req.allowed_roles))
    invalid = [r for r in roles if r not in VALID_ROLES]
    if invalid:
        raise HTTPException(status_code=400, detail=f"Invalid roles: {invalid}")

    row = (await db.execute(
        text(
            "UPDATE documents SET allowed_roles = :r, status = 'pending_review' WHERE id = CAST(:i AS uuid) "
            "RETURNING id, title, filename, allowed_roles, status, chunk_count, uploaded_at, uploaded_by"
        ),
        {"r": roles, "i": doc_id},
    )).first()
    if not row:
        raise HTTPException(status_code=404, detail="Document not found")

    await db.execute(
        text("UPDATE chunks SET allowed_roles = :r, roles_ai_suggested = false WHERE document_id = CAST(:i AS uuid)"),
        {"r": roles, "i": doc_id},
    )
    await db.commit()

    return DocumentOut(
        id=str(row.id), title=row.title, filename=row.filename,
        allowed_roles=list(row.allowed_roles or []), status=row.status, chunk_count=row.chunk_count,
        uploaded_at=row.uploaded_at, uploaded_by_email=None,
    )


@router.get("/documents/{doc_id}/chunks", response_model=list[ChunkOut])
async def list_document_chunks(doc_id: str, admin: dict = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    """Return the admin-only review payload in document order."""
    rows = (await db.execute(
        text(
            "SELECT c.id, c.chunk_index, c.content, c.allowed_roles, c.roles_ai_suggested, c.source_page, d.filename "
            "FROM chunks c JOIN documents d ON d.id = c.document_id "
            "WHERE c.document_id = CAST(:i AS uuid) ORDER BY c.chunk_index"
        ),
        {"i": doc_id},
    )).fetchall()
    exists = await db.execute(text("SELECT 1 FROM documents WHERE id = CAST(:i AS uuid)"), {"i": doc_id})
    if not exists.first():
        raise HTTPException(status_code=404, detail="Document not found")
    return [
        ChunkOut(
            id=str(row.id), chunk_index=row.chunk_index, content=row.content,
            allowed_roles=list(row.allowed_roles or []), roles_ai_suggested=row.roles_ai_suggested,
            source=row.filename, page=row.source_page,
        )
        for row in rows
    ]


@router.patch("/documents/{doc_id}/chunks/{chunk_id}", response_model=ChunkOut)
async def update_chunk_roles(
    doc_id: str,
    chunk_id: int,
    req: UpdateChunkRolesRequest,
    admin: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Apply a reviewed tag set, enforcing the document-level access ceiling."""
    candidate = (await db.execute(
        text("SELECT allowed_roles, filename FROM documents WHERE id = CAST(:i AS uuid)"), {"i": doc_id}
    )).first()
    if not candidate:
        raise HTTPException(status_code=404, detail="Document not found")
    roles = sorted(set(req.allowed_roles))
    outside_ceiling = sorted(set(roles) - set(candidate.allowed_roles or []))
    if outside_ceiling:
        raise HTTPException(status_code=400, detail=f"Chunk roles exceed document roles: {outside_ceiling}")

    row = (await db.execute(
        text(
            "UPDATE chunks SET allowed_roles = :r, roles_ai_suggested = false "
            "WHERE id = :chunk_id AND document_id = CAST(:doc_id AS uuid) "
            "RETURNING id, chunk_index, content, allowed_roles, roles_ai_suggested, source_page"
        ),
        {"r": roles, "chunk_id": chunk_id, "doc_id": doc_id},
    )).first()
    if not row:
        raise HTTPException(status_code=404, detail="Chunk not found")
    await db.commit()
    return ChunkOut(
        id=str(row.id), chunk_index=row.chunk_index, content=row.content,
        allowed_roles=list(row.allowed_roles or []), roles_ai_suggested=row.roles_ai_suggested,
        source=candidate.filename, page=row.source_page,
    )


@router.post("/documents/{doc_id}/publish", response_model=DocumentOut)
async def publish_document(doc_id: str, admin: dict = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    row = (await db.execute(
        text(
            "UPDATE documents SET status = 'published' WHERE id = CAST(:i AS uuid) "
            "RETURNING id, title, filename, allowed_roles, status, chunk_count, uploaded_at"
        ),
        {"i": doc_id},
    )).first()
    if not row:
        raise HTTPException(status_code=404, detail="Document not found")
    await db.commit()
    return DocumentOut(
        id=str(row.id), title=row.title, filename=row.filename,
        allowed_roles=list(row.allowed_roles or []), status=row.status, chunk_count=row.chunk_count,
        uploaded_at=row.uploaded_at, uploaded_by_email=None,
    )


@router.post("/documents/{doc_id}/reset-chunk-roles", response_model=list[ChunkOut])
async def reset_chunk_roles(doc_id: str, admin: dict = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    candidate = (await db.execute(
        text("SELECT allowed_roles, filename FROM documents WHERE id = CAST(:i AS uuid)"), {"i": doc_id}
    )).first()
    if not candidate:
        raise HTTPException(status_code=404, detail="Document not found")
    rows = (await db.execute(
        text(
            "UPDATE chunks SET allowed_roles = :r, roles_ai_suggested = false "
            "WHERE document_id = CAST(:i AS uuid) "
            "RETURNING id, chunk_index, content, allowed_roles, roles_ai_suggested, source_page"
        ),
        {"r": list(candidate.allowed_roles or []), "i": doc_id},
    )).fetchall()
    await db.commit()
    return [
        ChunkOut(
            id=str(row.id), chunk_index=row.chunk_index, content=row.content,
            allowed_roles=list(row.allowed_roles or []), roles_ai_suggested=row.roles_ai_suggested,
            source=candidate.filename, page=row.source_page,
        )
        for row in sorted(rows, key=lambda chunk: chunk.chunk_index)
    ]


@router.delete("/documents/{doc_id}")
async def delete_document(doc_id: str, admin: dict = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    row = (await db.execute(
        text("DELETE FROM documents WHERE id = CAST(:i AS uuid) RETURNING id"),
        {"i": doc_id},
    )).first()
    if not row:
        raise HTTPException(status_code=404, detail="Document not found")
    await db.commit()
    return {"deleted": True, "id": str(row.id)}

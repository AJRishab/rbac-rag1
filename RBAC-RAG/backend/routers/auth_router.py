"""Auth endpoints: me, change-password (flag clear).

Signup and login now happen client-side via supabase-js, so there is no
/register or /login endpoint. The backend only serves identity lookups for
the caller identified by their (already verified) Supabase JWT.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from deps import get_db, get_current_user
from schemas import UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me", response_model=UserOut)
async def me(user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        text("SELECT id, email, role, status, must_change_password, created_at FROM profiles WHERE id = CAST(:i AS uuid)"),
        {"i": user["id"]},
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    return UserOut(
        id=str(row.id), email=row.email, role=row.role, status=row.status,
        must_change_password=row.must_change_password, created_at=row.created_at,
    )


@router.post("/change-password", response_model=UserOut)
async def change_password(user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Clear the forced-password-change flag after a client-side password change.

    The actual password update is done client-side via supabase-js
    `auth.updateUser({ password })` (the backend no longer stores password
    hashes). This route just flips must_change_password to false on the profile.
    """
    result = await db.execute(
        text(
            "UPDATE profiles SET must_change_password = false WHERE id = CAST(:i AS uuid) "
            "RETURNING id, email, role, status, must_change_password, created_at"
        ),
        {"i": user["id"]},
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    await db.commit()
    return UserOut(
        id=str(row.id), email=row.email, role=row.role, status=row.status,
        must_change_password=row.must_change_password, created_at=row.created_at,
    )

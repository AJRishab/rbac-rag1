"""FastAPI dependencies: current_user (JWT), require_admin, require_approved."""
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
import jwt

from database import SessionLocal
from auth import decode_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


async def get_db() -> AsyncSession:
    async with SessionLocal() as session:
        yield session


async def get_current_user(token: str | None = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)):
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        payload = decode_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    user_id = payload.get("sub")
    result = await db.execute(
        text("SELECT id, email, role, status, must_change_password FROM users WHERE id = CAST(:i AS uuid)"),
        {"i": user_id},
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    return {
        "id": str(row.id),
        "email": row.email,
        "role": row.role,
        "status": row.status,
        "must_change_password": row.must_change_password,
    }


async def require_approved(user: dict = Depends(get_current_user)):
    if user["status"] != "approved":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account pending admin approval")
    if not user["role"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No role assigned")
    return user


async def require_admin(user: dict = Depends(require_approved)):
    if user["role"] != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")
    return user

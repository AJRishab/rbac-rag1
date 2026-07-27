"""Auth endpoints: register, login, me, change-password."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from database import SessionLocal
from deps import get_db, get_current_user
from auth import hash_password, verify_password, create_access_token
from schemas import RegisterRequest, LoginRequest, ChangePasswordRequest, AuthResponse, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserOut)
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_db)):
    email = req.email.lower().strip()
    existing = await db.execute(text("SELECT id FROM users WHERE email = :e"), {"e": email})
    if existing.first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An account with this email already exists")
    pwd_hash = hash_password(req.password)
    result = await db.execute(
        text(
            "INSERT INTO users (email, password_hash, status) VALUES (:e, :p, 'pending') "
            "RETURNING id, email, role, status, must_change_password, created_at"
        ),
        {"e": email, "p": pwd_hash},
    )
    row = result.first()
    await db.commit()
    return UserOut(
        id=str(row.id), email=row.email, role=row.role, status=row.status,
        must_change_password=row.must_change_password, created_at=row.created_at,
    )


@router.post("/login", response_model=AuthResponse)
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    email = req.email.lower().strip()
    result = await db.execute(
        text("SELECT id, email, password_hash, role, status, must_change_password, created_at FROM users WHERE email = :e"),
        {"e": email},
    )
    row = result.first()
    if not row or not verify_password(req.password, row.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    # Allow login even when pending or must_change_password so the frontend can route the user;
    # backend chat/admin endpoints still enforce approved+role.
    token = create_access_token(
        user_id=str(row.id), email=row.email, role=row.role,
        status=row.status, must_change_password=row.must_change_password,
    )
    return AuthResponse(
        token=token,
        user=UserOut(
            id=str(row.id), email=row.email, role=row.role, status=row.status,
            must_change_password=row.must_change_password, created_at=row.created_at,
        ),
    )


@router.get("/me", response_model=UserOut)
async def me(user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        text("SELECT id, email, role, status, must_change_password, created_at FROM users WHERE id = CAST(:i AS uuid)"),
        {"i": user["id"]},
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    return UserOut(
        id=str(row.id), email=row.email, role=row.role, status=row.status,
        must_change_password=row.must_change_password, created_at=row.created_at,
    )


@router.post("/change-password", response_model=AuthResponse)
async def change_password(req: ChangePasswordRequest, user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        text("SELECT id, email, password_hash, role, status, must_change_password, created_at FROM users WHERE id = CAST(:i AS uuid)"),
        {"i": user["id"]},
    )
    row = result.first()
    if not row or not verify_password(req.current_password, row.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    if req.current_password == req.new_password:
        raise HTTPException(status_code=400, detail="New password must differ from current password")
    new_hash = hash_password(req.new_password)
    await db.execute(
        text("UPDATE users SET password_hash = :p, must_change_password = false WHERE id = CAST(:i AS uuid)"),
        {"p": new_hash, "i": user["id"]},
    )
    await db.commit()

    token = create_access_token(
        user_id=str(row.id), email=row.email, role=row.role, status=row.status, must_change_password=False,
    )
    return AuthResponse(
        token=token,
        user=UserOut(
            id=str(row.id), email=row.email, role=row.role, status=row.status,
            must_change_password=False, created_at=row.created_at,
        ),
    )

"""Pydantic schemas for API requests/responses."""
import re
from typing import Literal
from pydantic import BaseModel, Field, field_validator
from datetime import datetime

RoleType = Literal["employee", "manager", "hr", "admin"]
StatusType = Literal["pending", "approved"]

# Permissive email regex — accepts .local etc. for dev/internal use
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def _validate_email(v: str) -> str:
    v = v.strip().lower()
    if not EMAIL_RE.match(v):
        raise ValueError("Invalid email address")
    return v


class RegisterRequest(BaseModel):
    email: str
    password: str = Field(min_length=8, max_length=200)

    @field_validator("email")
    @classmethod
    def _v_email(cls, v: str) -> str:
        return _validate_email(v)


class LoginRequest(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def _v_email(cls, v: str) -> str:
        return _validate_email(v)


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=200)


class UserOut(BaseModel):
    id: str
    email: str
    role: str | None
    status: str
    must_change_password: bool
    created_at: datetime | None = None


class AuthResponse(BaseModel):
    token: str
    user: UserOut


class ApproveUserRequest(BaseModel):
    role: RoleType


class DocumentOut(BaseModel):
    id: str
    title: str
    filename: str
    allowed_roles: list[str]
    chunk_count: int
    uploaded_at: datetime
    uploaded_by_email: str | None = None


class UpdateDocRolesRequest(BaseModel):
    allowed_roles: list[RoleType]

    @field_validator("allowed_roles")
    @classmethod
    def at_least_one_role(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("At least one role required")
        return list(set(v))


class ConversationOut(BaseModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime


class CitationItem(BaseModel):
    document_id: str
    title: str
    chunk_index: int | None = None


class MessageOut(BaseModel):
    id: str
    role: Literal["user", "assistant"]
    content: str
    citations: list[dict] | None = None
    retrieved_count: int | None = None
    blocked_count: int | None = None
    retrieval_detail: dict | None = None
    created_at: datetime


class AskRequest(BaseModel):
    conversation_id: str | None = None
    question: str = Field(min_length=1, max_length=4000)


class AskResponse(BaseModel):
    conversation_id: str
    user_message: MessageOut
    assistant_message: MessageOut

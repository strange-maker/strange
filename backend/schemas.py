from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, EmailStr, Field, HttpUrl


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=40)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: dict[str, Any]


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=120)
    password: str = Field(min_length=12, max_length=200)
    role: Literal["admin", "analyst", "sales", "viewer"] = "sales"


class UserUpdate(BaseModel):
    is_active: bool | None = None
    role: Literal["admin", "analyst", "sales", "viewer"] | None = None


class ManualImport(BaseModel):
    original_url: HttpUrl
    title: str = Field(min_length=2, max_length=500)
    content_text: str = Field(min_length=20, max_length=50000)
    published_at: datetime | None = None
    source_name: str = Field(min_length=2, max_length=200)
    import_type: Literal["wechat", "web"] = "wechat"
    industry: str | None = None
    ocr_result: str | None = Field(default=None, max_length=50000)


class SourceUpdate(BaseModel):
    enabled: bool | None = None
    schedule_minutes: int | None = Field(default=None, ge=15, le=10080)
    backfill_enabled: bool | None = None
    backfill_page_limit: int | None = Field(default=None, ge=1, le=500)


class SavedSearchCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    filters: dict[str, Any]


class ReviewRequest(BaseModel):
    action: Literal["approve", "reject", "needs_changes"]
    notes: str = Field(default="", max_length=2000)


class CrawlBatchCreate(BaseModel):
    source_ids: list[str] | None = None


class BackfillCreate(BaseModel):
    source_id: str
    date_from: datetime
    date_to: datetime
    page_limit: int = Field(default=25, ge=1, le=500)

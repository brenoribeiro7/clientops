from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class LoginInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str
    password: str = Field(max_length=512)


class ChangePasswordInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    current_password: str = Field(max_length=512)
    new_password: str = Field(max_length=512)


class UserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=160)
    email: str = Field(max_length=254)


class UserPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=160)


class EmptyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class UserData(BaseModel):
    id: UUID
    name: str
    email: str
    role: str
    status: str
    must_change_password: bool
    version: int


class UserResponse(BaseModel):
    data: UserData


class UserSecretResponse(BaseModel):
    data: UserData
    temporary_password: str


class UserPage(BaseModel):
    data: list[UserData]
    page: dict[str, int]


class SessionData(BaseModel):
    user: UserData
    expires_at: datetime
    idle_expires_at: datetime
    csrf_token: str
    server_now: datetime


class SessionResponse(BaseModel):
    data: SessionData

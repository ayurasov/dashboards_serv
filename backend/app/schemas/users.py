"""Схемы пользователей, сессий, подразделений и доступа."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import EmailStr, Field, computed_field, field_validator

from .common import Input, Schema

Role = Literal["admin", "user"]
Level = Literal["viewer", "editor", "manager"]
ServiceLevel = Literal["none", "viewer", "editor", "manager"]
OrgScope = Literal["company", "branch", "unit"]


class DepartmentOut(Schema):
    id: int
    name: str
    code: str | None = None


class DepartmentIn(Input):
    name: str = Field(min_length=1, max_length=200)
    code: str | None = Field(default=None, max_length=50)


class AccessOut(Schema):
    service_key: str
    level: ServiceLevel
    org_scope: OrgScope | None = None

    @computed_field  # совместимость с 0.1.0
    @property
    def department_scope(self) -> bool:
        return self.org_scope is not None and self.org_scope != "company"


class AccessIn(Input):
    service_key: str
    level: ServiceLevel
    org_scope: OrgScope | None = None
    # Совместимость с 0.1.0: «только свои подразделения» = своя ветка структуры
    department_scope: bool = False


class UserOut(Schema):
    id: int
    username: str
    full_name: str
    email: str | None = None
    position: str | None = None
    phone: str | None = None
    role: Role
    is_active: bool
    must_change_password: bool
    created_at: datetime
    last_login_at: datetime | None = None
    departments: list[DepartmentOut] = []
    access: list[AccessOut] = []
    has_avatar: bool = False


class MeOut(UserOut):
    avatar: str | None = None
    csrf_token: str = ""


class LoginIn(Input):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=200)


class ProfileIn(Input):
    full_name: str | None = Field(default=None, max_length=200)
    email: EmailStr | None | Literal[""] = None
    position: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=50)
    avatar: str | None = None

    @field_validator("full_name")
    @classmethod
    def _name(cls, v):
        if v is not None and not v.strip():
            raise ValueError("ФИО не может быть пустым")
        return v

    @field_validator("avatar")
    @classmethod
    def _avatar(cls, v):
        if v and not v.startswith("data:image/"):
            raise ValueError("Аватар должен быть изображением")
        if v and len(v) > 2_000_000:
            raise ValueError("Изображение слишком большое (до 1,5 МБ)")
        return v


class ChangePasswordIn(Input):
    current_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=1, max_length=72)


class SessionOut(Schema):
    id: str
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime
    ip_address: str
    user_agent: str
    current: bool = False


class UserCreateIn(Input):
    username: str = Field(min_length=2, max_length=100, pattern=r"^[A-Za-z0-9._@-]+$")
    full_name: str = Field(min_length=1, max_length=200)
    email: EmailStr | None | Literal[""] = None
    position: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=50)
    role: Role = "user"
    password: str | None = Field(default=None, max_length=72)
    department_ids: list[int] = []
    access: list[AccessIn] = []


class UserUpdateIn(Input):
    full_name: str | None = Field(default=None, min_length=1, max_length=200)
    email: EmailStr | None | Literal[""] = None
    position: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=50)
    role: Role | None = None
    is_active: bool | None = None
    department_ids: list[int] | None = None


class UserCreatedOut(Schema):
    user: UserOut
    temporary_password: str | None = None


class PasswordResetOut(Schema):
    temporary_password: str

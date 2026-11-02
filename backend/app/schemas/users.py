"""Схемы пользователей, сессий, подразделений и доступа."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import EmailStr, Field, computed_field, field_validator

from .common import Input, Schema

Role = Literal["admin", "user"]
Level = Literal["viewer", "editor", "manager"]
ServiceLevel = Literal["none", "viewer", "editor", "manager"]
OrgScope = Literal["company", "branch", "unit"]
AuthSource = Literal["local", "ldap"]
UserStatus = Literal["active", "disabled", "no_access"]
# Способ входа новой учётной записи: пароль системы, учётная запись домена или «без доступа»
AccessMethod = Literal["password", "ldap", "none"]
GrantMethod = Literal["password", "ldap"]


class DepartmentOut(Schema):
    id: int
    name: str
    code: str | None = None


class DepartmentIn(Input):
    name: str = Field(min_length=1, max_length=200)
    code: str | None = Field(default=None, max_length=50)


class UnitRef(Schema):
    """Подразделение структуры: путь — названия от корня через « / »."""

    id: int
    name: str
    path: str


class ProfileRef(Schema):
    id: int
    key: str
    name: str


class ManagerRef(Schema):
    """Непосредственный руководитель; source — explicit (назначен явно) · structure (по структуре)."""

    id: int
    username: str
    full_name: str
    source: str


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
    status: UserStatus = "active"
    must_change_password: bool
    created_at: datetime
    last_login_at: datetime | None = None
    # Основное подразделение (с путём), непосредственный руководитель, профиль доступа
    department: UnitRef | None = None
    manager: ManagerRef | None = None
    profile: ProfileRef | None = None
    capabilities: list[str] = []
    auth_source: AuthSource = "local"
    has_password: bool = False
    auth_linked_at: datetime | None = None
    # Совместимость с 0.1.0: основное и дополнительные подразделения, строки доступа к службам
    departments: list[DepartmentOut] = []
    access: list[AccessOut] = []
    has_avatar: bool = False


class InboxBadgeOut(Schema):
    available: bool = False
    pending: int = 0


class MeOut(UserOut):
    avatar: str | None = None
    csrf_token: str = ""
    # Действующий доступ (ADR-0009): интерфейс скрывает недоступные разделы и кнопки
    effective_access: dict[str, Any] = {}
    # «Входящие данные» (ADR-0011): доступны ли (data.manage или право применять набор) и сколько ожидающих
    # элементов пользователь может применить — счётчик в меню без отдельных запросов
    inbox: InboxBadgeOut = Field(default_factory=InboxBadgeOut)


class UsersSummary(Schema):
    total: int
    active: int
    disabled: int
    no_access: int
    ldap: int
    admins: int


class UserListOut(Schema):
    items: list[UserOut]
    total: int
    summary: UsersSummary


class LoginIn(Input):
    username: str = Field(min_length=1, max_length=200)
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
    # password — пароль системы (без пароля — временный, показывается один раз); ldap — вход по домену;
    # none — «без доступа», доступ выдаётся позже
    access_method: AccessMethod = "password"
    password: str | None = Field(default=None, max_length=72)
    department_id: int | None = None
    profile_id: int | None = None
    capabilities: list[str] = []
    # Совместимость с 0.1.0: первое — основное подразделение, остальные — дополнительная область доступа
    department_ids: list[int] = []
    access: list[AccessIn] = []


class UserUpdateIn(Input):
    full_name: str | None = Field(default=None, min_length=1, max_length=200)
    email: EmailStr | None | Literal[""] = None
    position: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=50)
    role: Role | None = None
    is_active: bool | None = None
    department_id: int | None = None
    profile_id: int | None = None
    capabilities: list[str] | None = None
    # Совместимость с 0.1.0
    department_ids: list[int] | None = None


class GrantAccessIn(Input):
    method: GrantMethod = "password"


class UserCreatedOut(Schema):
    user: UserOut
    temporary_password: str | None = None


class PasswordResetOut(Schema):
    temporary_password: str
    user: UserOut | None = None


class LdapTestIn(Input):
    """Проверка входа по домену: без логина — подключение и служебная привязка, с логином — и поиск."""

    login: str | None = Field(default=None, max_length=200)

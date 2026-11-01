"""Вход (пароль системы или учётная запись домена), выход, профиль, смена пароля, активные сессии."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...core.config import settings
from ...core.db import get_db, utcnow
from ...core.errors import AppError, Forbidden, NotFound, TooManyRequests, Unauthorized, ValidationFailed
from ...core.ratelimit import SlidingWindowLimiter
from ...core.security import burn_password_check, hash_password, verify_password
from ...models import User, UserSession
from ...schemas.common import Ok
from ...schemas.users import ChangePasswordIn, LoginIn, MeOut, ProfileIn, SessionOut
from ...services import access, audit, ldap_auth, org, sessions
from ...services.users import find_local, serialize_user, validate_password
from ..deps import current_session, current_user

router = APIRouter(prefix="/api/auth", tags=["Вход и профиль"])

login_limiter = SlidingWindowLimiter(settings.login_rate_limit, settings.login_rate_window_seconds)


def me_payload(db: Session, user: User, session: UserSession) -> MeOut:
    access.invalidate(user)
    data = serialize_user(user, org.snapshot(db)).model_dump()
    return MeOut(**data, avatar=user.avatar, csrf_token=session.csrf_token,
                 effective_access=access.effective(user).as_dict())


def _set_cookies(response: Response, token: str, csrf: str) -> None:
    max_age = settings.session_lifetime_hours * 3600
    response.set_cookie(settings.session_cookie_name, token, max_age=max_age, httponly=True,
                        secure=settings.session_cookie_secure, samesite="lax", path="/")
    response.set_cookie(settings.csrf_cookie_name, csrf, max_age=max_age, httponly=False,
                        secure=settings.session_cookie_secure, samesite="lax", path="/")


def _clear_cookies(response: Response) -> None:
    response.delete_cookie(settings.session_cookie_name, path="/")
    response.delete_cookie(settings.csrf_cookie_name, path="/")


@router.get("/config", summary="Способы входа для страницы входа")
def login_config():
    """Включён ли вход по учётной записи домена и подсказка к нему (ADR-0008). Без входа в систему."""
    config = ldap_auth.current_config()
    return {"ldap": {"enabled": config is not None, "hint": config.login_hint if config else ""}}


def _local_password_ok(user: User | None, password: str) -> bool:
    """Пароль системы — только у локальной учётной записи; пароль доменной в системе не проверяется.
    Без кандидата время ответа выравнивается холостой проверкой bcrypt."""
    if user is None or user.auth_source == ldap_auth.SOURCE_LDAP or not user.password_hash:
        burn_password_check()
        return False
    return verify_password(password, user.password_hash)


@router.post("/login", response_model=MeOut, summary="Вход по логину и паролю (системы или домена)")
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    """Порядок (ADR-0008): каталог подтвердил пароль → вход; иначе локальная учётная запись не из
    домена с совпавшим паролем; доменная учётная запись при недоступном каталоге — 503; каталог
    подтвердил пароль, но учётной записи нет — 403; иначе 401."""
    ip = audit.client_ip(request)
    login_value = body.username.strip()
    limiter_key = f"{ip}:{login_value.lower()}"
    if wait := login_limiter.blocked_for(limiter_key):
        raise TooManyRequests(f"Слишком много неудачных попыток. Повторите через {wait} с")
    local = find_local(db, login_value)
    # Проверка в каталоге (сеть) и bcrypt (~0,3 с процессора) — без соединения с базой: оно возвращается в пул
    db.commit()
    directory = ldap_auth.authenticate(db, login_value, body.password, request)
    user = directory.user
    if user is None and _local_password_ok(local, body.password):
        user = local
    if user is None:
        if directory.error == "directory_unavailable" and local is not None \
                and local.auth_source == ldap_auth.SOURCE_LDAP:
            raise AppError("Сервер домена не отвечает — попробуйте войти позже", code="directory_unavailable",
                           status_code=503)
        if directory.error == "no_account":
            raise Forbidden("Учётной записи в системе нет — обратитесь к администратору", code="no_account")
        login_limiter.hit(limiter_key)
        raise Unauthorized("Неверный логин или пароль", code="invalid_credentials")
    if not user.is_active:
        db.commit()  # привязка к каталогу или созданная при первом входе учётная запись сохраняются
        raise AppError("Учётная запись отключена. Обратитесь к администратору",
                       code="account_disabled", status_code=403)
    login_limiter.reset(limiter_key)
    token, session = sessions.create_session(db, user, ip, request.headers.get("user-agent", ""))
    user.last_login_at = utcnow()
    via_domain = directory.user is not None
    audit.record(db, user, entity_type="session", action="login",
                 summary="Вход в систему по учётной записи домена" if via_domain else "Вход в систему",
                 request=request)
    db.commit()
    _set_cookies(response, token, session.csrf_token)
    return me_payload(db, user, session)


@router.post("/logout", response_model=Ok, summary="Выход")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    session = sessions.resolve_session(db, request.cookies.get(settings.session_cookie_name))
    if session is not None:
        sessions.revoke(db, session.id)
        db.commit()
    _clear_cookies(response)
    return Ok(message="Вы вышли из системы")


@router.get("/me", response_model=MeOut, summary="Текущий пользователь и его действующий доступ")
def me(session: UserSession = Depends(current_session), user: User = Depends(current_user),
       db: Session = Depends(get_db)):
    return me_payload(db, user, session)


@router.put("/profile", response_model=MeOut, summary="Изменить свой профиль")
def update_profile(body: ProfileIn, request: Request, session: UserSession = Depends(current_session),
                   user: User = Depends(current_user), db: Session = Depends(get_db)):
    fields = body.model_dump(exclude_unset=True)
    if fields.get("email"):
        taken = db.scalar(select(User.id).where(func.lower(User.email) == fields["email"].lower(),
                                                User.id != user.id))
        if taken:
            raise ValidationFailed("Этот e-mail уже используется", fields={"email": "Уже используется"})
    before = {"full_name": user.full_name, "email": user.email, "position": user.position, "phone": user.phone}
    if "full_name" in fields:
        user.full_name = fields["full_name"].strip()
    for key in ("email", "position", "phone", "avatar"):
        if key in fields:
            setattr(user, key, (fields[key] or "").strip() or None)
    after = {"full_name": user.full_name, "email": user.email, "position": user.position, "phone": user.phone}
    b, a = audit.diff(before, after)
    if b or a or "avatar" in fields:
        audit.record(db, user, entity_type="user", entity_id=user.id, action="update",
                     summary="Изменён профиль", before=b, after=a, request=request)
    db.commit()
    return me_payload(db, user, session)


@router.post("/change-password", response_model=Ok, summary="Сменить пароль")
def change_password(body: ChangePasswordIn, request: Request, session: UserSession = Depends(current_session),
                    user: User = Depends(current_user), db: Session = Depends(get_db)):
    if user.auth_source == ldap_auth.SOURCE_LDAP:
        raise AppError("Вы входите по учётной записи домена — пароль меняется в домене",
                       code="directory_password", status_code=409)
    if not verify_password(body.current_password, user.password_hash):
        raise ValidationFailed("Текущий пароль указан неверно", fields={"current_password": "Неверный пароль"})
    if body.current_password == body.new_password:
        raise ValidationFailed("Новый пароль совпадает с текущим", fields={"new_password": "Совпадает с текущим"})
    validate_password(body.new_password, user)
    user.password_hash = hash_password(body.new_password)
    user.must_change_password = False
    user.password_changed_at = utcnow()
    closed = sessions.revoke_all(db, user.id, except_id=session.id)
    audit.record(db, user, entity_type="user", entity_id=user.id, action="password",
                 summary="Пароль изменён пользователем", request=request)
    db.commit()
    message = "Пароль изменён"
    if closed:
        message += f"; завершено других сессий: {closed}"
    return Ok(message=message)


@router.get("/sessions", response_model=list[SessionOut], summary="Мои активные сессии")
def my_sessions(session: UserSession = Depends(current_session), db: Session = Depends(get_db)):
    return [SessionOut(id=s.id[:16], created_at=s.created_at, last_seen_at=s.last_seen_at, expires_at=s.expires_at,
                       ip_address=s.ip_address, user_agent=s.user_agent, current=s.id == session.id)
            for s in sessions.list_sessions(db, session.user_id)]


@router.delete("/sessions/others", response_model=Ok, summary="Завершить все сессии, кроме текущей")
def close_other_sessions(session: UserSession = Depends(current_session), db: Session = Depends(get_db)):
    closed = sessions.revoke_all(db, session.user_id, except_id=session.id)
    db.commit()
    return Ok(message=f"Завершено сессий: {closed}")


@router.delete("/sessions/{session_id}", response_model=Ok, summary="Завершить сессию")
def close_session(session_id: str, session: UserSession = Depends(current_session), db: Session = Depends(get_db)):
    for s in sessions.list_sessions(db, session.user_id):
        if s.id.startswith(session_id) and len(session_id) >= 8:
            if s.id == session.id:
                raise ValidationFailed("Текущую сессию завершает кнопка «Выйти»")
            sessions.revoke(db, s.id)
            db.commit()
            return Ok(message="Сессия завершена")
    raise NotFound("Сессия не найдена")

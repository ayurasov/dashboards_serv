"""Auth router: login, me, change password."""
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import User, UserServiceAccess, RoleEnum, SERVICE_KEYS
from ..security import verify_password, create_access_token, hash_password
from ..deps import get_current_user
from ..schemas import (
    LoginRequest, Token, ChangePasswordRequest, UserOut, ProfileUpdate,
    UserServiceAccessOut,
)
from ..audit import log_action

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=Token)
def login(body: LoginRequest, request: Request, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == body.username).first()
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверный логин или пароль")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Учётная запись отключена")
    token = create_access_token({"sub": user.username, "role": user.role.value})
    return Token(
        access_token=token,
        role=user.role.value,
        username=user.username,
        full_name=user.full_name,
        must_change_password=user.must_change_password,
    )


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


@router.get("/my-access", response_model=list[UserServiceAccessOut])
def my_access(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Own per-service access. A global admin implicitly administers every service."""
    if user.role == RoleEnum.ADMIN:
        return [UserServiceAccessOut(id=0, user_id=user.id, service_key=key, access_level="admin")
                for key in SERVICE_KEYS]
    return (db.query(UserServiceAccess)
            .filter(UserServiceAccess.user_id == user.id)
            .order_by(UserServiceAccess.service_key)
            .all())


MAX_AVATAR_CHARS = 2_000_000  # ~1.5 MB of image once base64-decoded


@router.put("/profile", response_model=UserOut)
def update_profile(body: ProfileUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Any authenticated user may edit their own name, contacts and avatar."""
    fields = body.model_dump(exclude_unset=True)
    if "avatar" in fields and fields["avatar"] and len(fields["avatar"]) > MAX_AVATAR_CHARS:
        raise HTTPException(status_code=400, detail="Изображение слишком большое (максимум 1,5 МБ)")
    if fields.get("email"):
        taken = db.query(User).filter(User.email == fields["email"], User.id != user.id).first()
        if taken:
            raise HTTPException(status_code=400, detail="Этот e-mail уже используется")

    if "full_name" in fields and not fields["full_name"].strip():
        raise HTTPException(status_code=400, detail="ФИО не может быть пустым")

    before = {"full_name": user.full_name, "email": user.email, "phone": user.phone}
    if "full_name" in fields:
        user.full_name = fields["full_name"].strip()
    # Blank contact fields mean "clear it", so normalise empty strings to NULL.
    for key in ("email", "position", "phone", "avatar"):
        if key in fields:
            setattr(user, key, (fields[key] or "").strip() or None)

    log_action(db, user, "user", str(user.id), "update", before=before,
               after={"full_name": user.full_name, "email": user.email, "phone": user.phone})
    db.commit()
    db.refresh(user)
    return user


@router.post("/change-password")
def change_password(body: ChangePasswordRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not verify_password(body.old_password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Старый пароль неверен")
    user.hashed_password = hash_password(body.new_password)
    user.must_change_password = False
    log_action(db, user, "user", str(user.id), "update",
               before={"password": "***"}, after={"password": "***"})
    db.commit()
    return {"ok": True, "message": "Пароль изменён"}

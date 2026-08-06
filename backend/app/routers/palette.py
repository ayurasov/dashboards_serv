"""Colour palette router."""
import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import ColorPalette, User
from ..deps import get_current_user, require_admin
from ..schemas import ColorPaletteCreate, ColorPaletteOut
from ..audit import log_action

router = APIRouter(prefix="/api/palette", tags=["palette"])


def _out(p: ColorPalette) -> ColorPaletteOut:
    try:
        colors = json.loads(p.colors_json or "{}")
    except json.JSONDecodeError:
        colors = {}
    return ColorPaletteOut(id=p.id, name=p.name, scope=p.scope,
                           module_key=p.module_key, colors=colors, is_active=p.is_active)


def _get_or_404(db: Session, palette_id: int) -> ColorPalette:
    p = db.query(ColorPalette).filter(ColorPalette.id == palette_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Палитра не найдена")
    return p


@router.get("", response_model=ColorPaletteOut)
def get_active_palette(module_key: str | None = None, db: Session = Depends(get_db),
                       _: User = Depends(get_current_user)):
    q = db.query(ColorPalette).filter(ColorPalette.is_active.is_(True))
    palette = None
    if module_key:
        palette = q.filter(ColorPalette.module_key == module_key).first()
    if not palette:
        palette = q.filter(ColorPalette.scope == "global").first()
    if not palette:
        raise HTTPException(status_code=404, detail="Активная палитра не найдена")
    return _out(palette)


@router.get("/all", response_model=list[ColorPaletteOut])
def list_palettes(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return [_out(p) for p in db.query(ColorPalette).order_by(ColorPalette.id).all()]


@router.post("", response_model=ColorPaletteOut)
def create_palette(body: ColorPaletteCreate, db: Session = Depends(get_db),
                   admin: User = Depends(require_admin)):
    if body.is_active:
        _deactivate_siblings(db, body.scope, body.module_key)
    p = ColorPalette(name=body.name, scope=body.scope, module_key=body.module_key,
                     colors_json=json.dumps(body.colors, ensure_ascii=False),
                     is_active=body.is_active)
    db.add(p)
    db.flush()
    log_action(db, admin, "palette", p.id, "create", after={"name": p.name})
    db.commit()
    db.refresh(p)
    return _out(p)


@router.put("/{palette_id}", response_model=ColorPaletteOut)
def update_palette(palette_id: int, body: ColorPaletteCreate, db: Session = Depends(get_db),
                   admin: User = Depends(require_admin)):
    p = _get_or_404(db, palette_id)
    before = {"name": p.name, "colors": p.colors_json}
    p.name = body.name
    p.scope = body.scope
    p.module_key = body.module_key
    p.colors_json = json.dumps(body.colors, ensure_ascii=False)
    if body.is_active and not p.is_active:
        _deactivate_siblings(db, p.scope, p.module_key)
        p.is_active = True
    db.flush()
    log_action(db, admin, "palette", p.id, "update", before=before, after={"name": p.name})
    db.commit()
    db.refresh(p)
    return _out(p)


@router.put("/{palette_id}/activate", response_model=ColorPaletteOut)
def activate_palette(palette_id: int, db: Session = Depends(get_db),
                     admin: User = Depends(require_admin)):
    p = _get_or_404(db, palette_id)
    _deactivate_siblings(db, p.scope, p.module_key)
    p.is_active = True
    db.flush()
    log_action(db, admin, "palette", p.id, "update", after={"is_active": True})
    db.commit()
    db.refresh(p)
    return _out(p)


@router.delete("/{palette_id}")
def delete_palette(palette_id: int, db: Session = Depends(get_db),
                   admin: User = Depends(require_admin)):
    p = _get_or_404(db, palette_id)
    log_action(db, admin, "palette", p.id, "delete", before={"name": p.name})
    db.delete(p)
    db.commit()
    return {"deleted": palette_id}


def _deactivate_siblings(db: Session, scope: str, module_key: str | None):
    (db.query(ColorPalette)
     .filter(ColorPalette.scope == scope, ColorPalette.module_key == module_key)
     .update({ColorPalette.is_active: False}, synchronize_session=False))

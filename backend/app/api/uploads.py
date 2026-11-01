"""Загрузка файлов и выдача файлов для скачивания."""
from __future__ import annotations

from datetime import date
from urllib.parse import quote

from fastapi import UploadFile
from fastapi.responses import Response

from ..core.config import settings
from ..core.errors import AppError, ValidationFailed

MIME = {
    "pdf": "application/pdf",
    "csv": "text/csv; charset=utf-8",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


async def read_upload(file: UploadFile) -> bytes:
    limit = settings.max_upload_mb * 1024 * 1024
    raw = await file.read(limit + 1)
    if len(raw) > limit:
        raise AppError(f"Файл больше {settings.max_upload_mb} МБ", code="payload_too_large", status_code=413)
    if not raw:
        raise ValidationFailed("Файл пустой")
    return raw


_TRANSLIT = dict(zip(
    "абвгдеёжзийклмнопрстуфхцчшщъыьэюя",
    ["a", "b", "v", "g", "d", "e", "e", "zh", "z", "i", "y", "k", "l", "m", "n", "o", "p", "r", "s", "t",
     "u", "f", "kh", "ts", "ch", "sh", "shch", "", "y", "", "e", "yu", "ya"], strict=True))


def ascii_filename(name: str) -> str:
    """Имя файла латиницей — для старых клиентов, которые не понимают filename* (RFC 5987)."""
    out = []
    for ch in name:
        low = ch.lower()
        if low in _TRANSLIT:
            t = _TRANSLIT[low]
            out.append(t.capitalize() if ch != low else t)
        elif ch.isascii() and (ch.isalnum() or ch in "._-"):
            out.append(ch)
        else:
            out.append("-" if ch.isspace() else "")
    text = "-".join(part for part in "".join(out).split("-") if part)
    return text.replace("-.", ".")


def file_response(content: bytes, filename: str) -> Response:
    """Ответ-файл. Имя — по-русски с датой; заголовок по RFC 5987 для любых браузеров."""
    ext = filename.rsplit(".", 1)[-1].lower()
    stem = filename.rsplit(".", 1)[0]
    full = f"{stem} {date.today().isoformat()}.{ext}"
    ascii_name = ascii_filename(full) or f"report.{ext}"
    disposition = f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(full)}"
    return Response(content=content, media_type=MIME.get(ext, "application/octet-stream"),
                    headers={"Content-Disposition": disposition, "Cache-Control": "no-store"})

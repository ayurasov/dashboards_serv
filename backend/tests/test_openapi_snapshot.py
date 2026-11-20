"""Снапшот контракта API: docs/openapi.yaml совпадает со схемой приложения.

Живую документацию отдаёт работающий сервер (/api/docs); снапшот в git версионирует контракт
и виден в ревью. Изменились схемы или маршруты — обновите снапшот (аудит 2026-11-20, E3):

    cd backend && python - <<'PY'
    from app.main import app
    import yaml
    yaml.safe_dump(app.openapi(), open('../docs/openapi.yaml', 'w', encoding='utf-8'),
                   allow_unicode=True, sort_keys=True, width=100)
    PY
"""
from pathlib import Path

import yaml

SNAPSHOT = Path(__file__).resolve().parents[2] / "docs" / "openapi.yaml"


def test_openapi_snapshot_matches_app():
    from app.main import app

    assert SNAPSHOT.exists(), "нет docs/openapi.yaml — сгенерируйте снапшот (см. докстринг файла)"
    with open(SNAPSHOT, encoding="utf-8") as f:
        snapshot = yaml.safe_load(f)
    live = app.openapi()
    assert snapshot == live, (
        "docs/openapi.yaml разошёлся с приложением: обновите снапшот командой из докстринга "
        "и проверьте изменения контракта в ревью"
    )

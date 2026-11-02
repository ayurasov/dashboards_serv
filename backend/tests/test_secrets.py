"""Секреты подключений: шифрование ключом из SECRET_KEY, назначение, привязка к адресу и владельцу."""
from __future__ import annotations

import pytest

from app.core import secrets
from app.core.config import settings


def test_round_trip_and_ciphertext_hides_value():
    token = secrets.encrypt("integration", {"token": "очень-секретно"})
    assert "очень" not in token and "секретно" not in token
    assert secrets.decrypt("integration", token) == {"token": "очень-секретно"}


def test_key_is_derived_from_purpose_and_secret_key(monkeypatch):
    token = secrets.encrypt("integration", "x")
    with pytest.raises(secrets.SecretUnreadable):
        secrets.decrypt("jira-token", token)
    monkeypatch.setattr(settings, "secret_key", "другой-ключ-" + "0" * 32)
    with pytest.raises(secrets.SecretUnreadable) as exc:
        secrets.decrypt("integration", token)
    assert "SECRET_KEY" in exc.value.detail and exc.value.code == "secret_unreadable"


def test_key_formula_matches_burndown():
    import base64
    import hashlib

    expected = base64.urlsafe_b64encode(hashlib.sha256(f"integration:{settings.secret_key}".encode()).digest())
    assert secrets._key("integration") == expected


def test_seal_binds_to_url_and_owner():
    token, bound = secrets.seal("integration", {"password": "p"}, "HTTPS://Jira.Company.ru/jira/",
                                owner="integration:1")
    assert bound == "https://jira.company.ru/jira"
    assert secrets.unseal("integration", token, bound, "https://jira.company.ru/jira", owner="integration:1") == \
        {"password": "p"}
    with pytest.raises(secrets.SecretBindingError) as exc:
        secrets.unseal("integration", token, bound, "https://evil.ru", owner="integration:1")
    assert "введите токен или пароль заново" in exc.value.detail
    # Подмена адреса привязки в базе: внутри шифра адрес прежний
    with pytest.raises(secrets.SecretBindingError):
        secrets.unseal("integration", token, "https://evil.ru", "https://evil.ru", owner="integration:1")
    # Шифр перенесён в другую строку
    with pytest.raises(secrets.SecretBindingError):
        secrets.unseal("integration", token, bound, bound, owner="integration:2")


def test_problem_text():
    token, bound = secrets.seal("integration", {"t": "x"}, "https://a.ru")
    assert secrets.problem("integration", token, bound, "https://a.ru") is None
    assert "https://b.ru" in secrets.problem("integration", token, bound, "https://b.ru")
    assert secrets.problem("integration", None, None, "https://a.ru") is None
    assert "повреждён" in secrets.problem("integration", secrets.encrypt("integration", [1]), bound, "https://a.ru")

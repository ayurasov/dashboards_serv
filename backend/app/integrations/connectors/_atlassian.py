"""Общее для Jira и Confluence — подключение как в burndown_tool:

- cloud        — Cloud, email + API-токен (Basic);
- server       — Server / Data Center, персональный токен (Personal Access Token, Bearer);
- server_basic — Server / Data Center, логин + пароль (Basic в UTF-8);
- «Проверять сертификат» (verify_tls), прокси — из окружения сервера, узлы — <ВИД>_ALLOWED_HOSTS.

Ошибки входа объясняются по-атлассиански: CAPTCHA после неудачных входов (заголовок
X-Authentication-Denied-Reason), 401 — что проверить, 403 — сообщение Jira/Confluence.
"""
from __future__ import annotations

from ..base import Field, Option
from ..http import HttpClient, HttpResponse, IntegrationError, error_text

INSTANCE_TYPES = ("cloud", "server", "server_basic")
INSTANCE_OPTIONS = (
    Option("cloud", "Cloud — email и API-токен"),
    Option("server", "Server / Data Center — персональный токен (PAT)"),
    Option("server_basic", "Server / Data Center — логин и пароль"),
)


def connection_fields(product: str, placeholder: str, url_hint: str) -> tuple[Field, ...]:
    return (
        Field("base_url", f"Адрес {product}", "url", required=True, placeholder=placeholder, hint=url_hint),
        Field("instance", "Тип подключения", "select", options=INSTANCE_OPTIONS, default="server", required=True,
              hint="Cloud — REST API 3 и вход по email и API-токену; Server / Data Center — REST API 2 и вход по "
                   "персональному токену (рекомендуется) или по логину и паролю"),
        Field("login", "Email или логин", required=True, show_if={"instance": ("cloud", "server_basic")},
              hint="Cloud — email учётной записи Atlassian; Server — логин служебной учётной записи"),
        Field("token", "API-токен, персональный токен или пароль", "password", required=True, secret=True,
              hint="Cloud — API-токен (id.atlassian.com → Security → API tokens); Server — Personal Access Token "
                   "из профиля или пароль. Хранится зашифрованным и уходит только на адрес, для которого введён"),
        Field("verify_tls", "Проверять сертификат", "bool", default=True,
              hint="Выключайте только для самоподписанного или корпоративного сертификата"),
    )


def client_options(config: dict, secrets: dict) -> dict:
    """Аргументы self.http(): Bearer для персонального токена, иначе Basic (логин и токен или пароль)."""
    token = secrets.get("token") or ""
    if config.get("instance") == "server":
        return {"headers": {"Authorization": f"Bearer {token}"}}
    return {"auth": (config.get("login") or "", token)}


def api_version(config: dict) -> str:
    return "3" if config.get("instance") == "cloud" else "2"


def call(client: HttpClient, product: str, method: str, path: str, *, allow: tuple[int, ...] = (),
         not_found: str | None = None, **kwargs) -> HttpResponse:
    """Запрос к Jira или Confluence: 200/201 и статусы из allow возвращаются, вход и права объясняются,
    остальное — ошибкой каркаса (IntegrationError)."""
    resp = client.request(method, path, expect=(200, 201, 204, 401, 403, *allow), not_found=not_found, **kwargs)
    if resp.status in (401, 403) and "CAPTCHA" in resp.header("x-authentication-denied-reason").upper():
        raise IntegrationError(
            f"{product} требует ввести CAPTCHA для этой учётной записи (было несколько неудачных входов): войдите в "
            f"{product} через браузер под этой учётной записью, пройдите проверку и повторите",
            code="captcha", short=f"{product} требует ввести CAPTCHA для учётной записи подключения",
            status=resp.status)
    if resp.status == 401:
        raise IntegrationError(
            f"{product} отклонила логин или токен (401). Проверьте тип подключения, логин и пароль или токен; если "
            f"в {product} отключён вход по паролю (Basic), используйте персональный токен (PAT)",
            code="auth", short=f"{product} отклонила логин или пароль подключения (401)", status=401)
    if resp.status == 403:
        text = error_text(resp)
        raise IntegrationError(f"Недостаточно прав в {product} (403)" + (f": {text}" if text else ""),
                               code="forbidden", short=f"Недостаточно прав в {product} (403)", status=403)
    return resp


def get_json(client: HttpClient, product: str, path: str, *, not_found: str | None = None, **kwargs) -> dict:
    return client.parse(call(client, product, "GET", path, not_found=not_found, **kwargs), dict)

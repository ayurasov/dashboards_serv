"""HTTP-клиент подключений против поддельного сервера: адрес и разрешённые узлы, перенаправления, повтор
429/503, предел размера, неожиданный ответ, ошибки доступа, подробные и краткие тексты, Basic в UTF-8."""
from __future__ import annotations

import base64
import time

import pytest

from app.integrations import http
from app.integrations.http import HttpClient, IntegrationError, check_base_url
from tests.fake_http import FakeServer


@pytest.fixture()
def server(monkeypatch):
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.delenv("FAKE_ALLOWED_HOSTS", raising=False)
    with FakeServer() as fake:
        yield fake


def client(server, **kwargs) -> HttpClient:
    sleeps: list[float] = []
    kwargs.setdefault("sleep", sleeps.append)
    c = HttpClient(server.url, kind="fake", title="Система", **kwargs)
    c.sleeps = sleeps
    return c


@pytest.mark.parametrize(("url", "code"), [
    ("ftp://host", "bad_url"), ("host.ru", "bad_url"), ("https://user:pw@host.ru", "bad_url"),
    ("https://host.ru/?a=1", "bad_url"), ("https://host.ru/#x", "bad_url"), ("https://ho st.ru", "bad_url"),
    ("https://host.ru:99999", "bad_url"), ("https://", "bad_url"),
])
def test_bad_urls(url, code):
    with pytest.raises(IntegrationError) as exc:
        check_base_url(url)
    assert exc.value.code == code


def test_url_is_normalized_and_path_allowed():
    assert check_base_url(" https://jira.company.ru/jira/ ") == "https://jira.company.ru/jira"


def test_allowed_hosts(monkeypatch):
    monkeypatch.setenv("JIRA_ALLOWED_HOSTS", "jira.company.ru, .corp.ru")
    assert check_base_url("https://jira.company.ru", kind="jira")
    assert check_base_url("https://a.b.corp.ru", kind="jira")
    assert check_base_url("https://corp.ru", kind="jira")
    with pytest.raises(IntegrationError) as exc:
        check_base_url("https://evil.ru", kind="jira")
    assert exc.value.code == "host_not_allowed" and "JIRA_ALLOWED_HOSTS" in exc.value.detail
    with pytest.raises(IntegrationError):
        check_base_url("https://notcorp.ru", kind="jira")
    monkeypatch.delenv("JIRA_ALLOWED_HOSTS")
    assert check_base_url("https://evil.ru", kind="jira")  # пусто — без ограничения
    assert http.allowed_hosts_env("bitrix24") == "BITRIX24_ALLOWED_HOSTS"


def test_json_request_and_headers(server):
    server.route("GET", "/api/meta", lambda r: (200, {"name": "Пульс", "version": "1.2"}))
    c = client(server, headers={"Authorization": "Bearer t"})
    assert c.get_json("api/meta")["name"] == "Пульс"
    request = server.requests[-1]
    assert request.headers["authorization"] == "Bearer t" and request.headers["accept"] == "application/json"
    assert c.calls == 1 and "запрос" in c.stats()


def test_basic_auth_is_utf8(server):
    server.route("GET", "/me", lambda r: (200, {"ok": True}))
    client(server, auth=("служба", "пароль")).get_json("me")
    raw = server.requests[-1].headers["authorization"].split()[1]
    assert base64.b64decode(raw).decode("utf-8") == "служба:пароль"


def test_redirect_is_an_error_with_target(server):
    server.route("GET", "/old", lambda r: (302, b"", {"Location": "https://sso.company.ru/login?next=x"}))
    with pytest.raises(IntegrationError) as exc:
        client(server).get_json("old")
    assert exc.value.code == "redirect" and "https://sso.company.ru/login" in exc.value.detail
    assert "next=x" not in exc.value.detail
    assert "перенаправляет" in exc.value.message(detailed=False) and server.url not in exc.value.message(False)
    assert "администратору" in exc.value.message(False)
    assert len(server.requests) == 1, "перенаправление не выполняется"


def test_retry_on_429_with_retry_after(server):
    answers = iter([(429, {"message": "slow"}, {"Retry-After": "2"}), (429, {}, {"Retry-After": "30"}),
                    (200, {"ok": True})])
    server.route("GET", "/x", lambda r: next(answers))
    c = client(server)
    assert c.get_json("x") == {"ok": True}
    assert c.sleeps == [2.0, 10.0], "Retry-After не больше 10 с"
    assert len(server.requests) == 3


def test_503_retried_then_reported(server):
    server.route("GET", "/x", lambda r: (503, {"message": "maintenance"}))
    c = client(server)
    with pytest.raises(IntegrationError) as exc:
        c.get_json("x")
    assert exc.value.code == "unavailable" and len(server.requests) == 3 and c.sleeps == [1.0, 2.0]


def test_other_errors_are_not_retried(server):
    server.route("GET", "/x", lambda r: (500, {"errorMessages": ["boom"], "errors": {"jql": "плохой"}}))
    with pytest.raises(IntegrationError) as exc:
        client(server).get_json("x")
    assert exc.value.code == "http_error" and "boom" in exc.value.detail and "jql: плохой" in exc.value.detail
    assert len(server.requests) == 1


@pytest.mark.parametrize(("status", "code"), [(401, "auth"), (403, "forbidden"), (404, "not_found"),
                                              (429, "rate_limited")])
def test_access_errors(server, status, code):
    server.route("GET", "/x", lambda r: (status, {"message": "nope"}))
    with pytest.raises(IntegrationError) as exc:
        client(server).get_json("x")
    assert exc.value.code == code and exc.value.status == status


def test_not_json_response(server):
    server.route("GET", "/x", lambda r: (200, "<html>Вход в систему</html>"))
    server.route("GET", "/list", lambda r: (200, {"not": "a list"}))
    c = client(server)
    with pytest.raises(IntegrationError) as exc:
        c.get_json("x")
    assert exc.value.code == "bad_response" and "страница входа" in exc.value.detail
    with pytest.raises(IntegrationError) as exc:
        c.get_json("list", kind=list)
    assert exc.value.code == "bad_response"


def test_size_limit_by_content_length(server):
    server.route("GET", "/big", lambda r: (200, b"x" * 5000))
    c = client(server, max_bytes=1000)
    with pytest.raises(IntegrationError) as exc:
        c.get_bytes("big")
    assert exc.value.code == "too_large"
    assert client(server, max_bytes=10_000).get_bytes("big") == b"x" * 5000


def test_streamed_body_over_limit(monkeypatch):
    """Ответ без Content-Length считается по мере чтения."""
    import socket
    import threading

    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen(1)

    def serve():
        conn, _ = sock.accept()
        conn.recv(4096)
        conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nConnection: close\r\n\r\n" + b"1" * 3000)
        conn.close()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    c = HttpClient(f"http://127.0.0.1:{sock.getsockname()[1]}", title="Система", max_bytes=1000)
    with pytest.raises(IntegrationError) as exc:
        c.get_bytes("x")
    thread.join(2)
    sock.close()
    assert exc.value.code == "too_large"


def test_connection_refused_and_short_message(server):
    port = server.server.server_address[1]
    server.stop()
    c = HttpClient(f"http://127.0.0.1:{port}", title="Пульс", detailed=False)
    with pytest.raises(IntegrationError) as exc:
        c.get_json("x")
    assert exc.value.code == "connect"
    assert f"127.0.0.1:{port}" in exc.value.detail
    short = exc.value.message(detailed=False)
    assert "127.0.0.1" not in short and "Не удалось подключиться к «Пульс»" in short and "администратору" in short
    server.start()  # фикстура остановит


def test_read_timeout(server):
    server.route("GET", "/slow", lambda r: (time.sleep(1.0), (200, {}))[1])
    with pytest.raises(IntegrationError) as exc:
        client(server, timeout=(1.0, 0.2)).get_json("slow")
    assert exc.value.code == "read_timeout"


def test_requests_stay_on_the_host(server):
    c = client(server)
    with pytest.raises(IntegrationError) as exc:
        c.request("GET", "https://other.example.com/x")
    assert exc.value.code == "bad_url"
    server.route("GET", "/abs", lambda r: (200, {"ok": 1}))
    assert c.get_json(f"{server.url}/abs") == {"ok": 1}


def test_no_cookies_option(server):
    server.route("GET", "/login", lambda r: (200, {"ok": True}, {"Set-Cookie": "sid=1; Path=/"}))
    server.route("GET", "/me", lambda r: (200, {"cookie": r.headers.get("cookie", "")}))
    with_cookies = client(server)
    with_cookies.get_json("login")
    assert with_cookies.get_json("me")["cookie"] == "sid=1"
    without = client(server, cookies=False)
    without.get_json("login")
    assert without.get_json("me")["cookie"] == ""


def test_record_health():
    class Row:
        last_ok_at = last_error_at = None
        last_error = ""

    row = Row()
    http.record_health(row, ok=False, error="Нет связи")
    assert row.last_error == "Нет связи" and row.last_error_at and row.last_ok_at is None
    http.record_health(row, ok=True)
    assert row.last_ok_at is not None


def test_error_to_app_error():
    assert IntegrationError("x", code="bad_url").to_app_error().status_code == 422
    error = IntegrationError("подробно", code="connect", short="кратко").to_app_error(detailed=False)
    assert error.status_code == 502 and error.detail.startswith("кратко") and error.code == "connect"


def test_non_latin_header_is_a_config_error(server):
    server.route("GET", "/x", lambda r: (200, {}))
    with pytest.raises(IntegrationError) as exc:
        client(server, headers={"Authorization": "Bearer токен"}).get_json("x")
    assert exc.value.code == "config" and "латиница" in exc.value.detail


# ---------------------------------------------------------------- повтор только безопасных запросов

@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
@pytest.mark.parametrize("status", [429, 503])
def test_changing_requests_are_not_retried(server, method, status):
    server.route(method, "/api/auth/login", lambda r: (status, {"message": "too many"}, {"Retry-After": "1"}))
    c = client(server)
    with pytest.raises(IntegrationError) as exc:
        c.request(method, "api/auth/login", json={"login": "svc"})
    assert exc.value.status == status
    assert len(server.requests) == 1, "вход у партнёра не повторяется — его ограничение попыток не тратится"
    assert c.sleeps == []


def test_changing_request_retried_only_on_request(server):
    answers = iter([(503, {}), (200, {"result": []})])
    server.route("POST", "/rest/crm.deal.list.json", lambda r: next(answers))
    c = client(server)
    assert c.post_json("rest/crm.deal.list.json", {}, retry=True) == {"result": []}, "чтение через POST — retry=True"
    assert len(server.requests) == 2 and c.sleeps == [1.0]


def test_safe_request_retry_can_be_turned_off(server):
    server.route("GET", "/x", lambda r: (429, {}))
    c = client(server)
    with pytest.raises(IntegrationError):
        c.request("GET", "x", retry=False)
    assert len(server.requests) == 1


# ---------------------------------------------------------------- секреты не выходят в тексты ошибок

def test_scrub_values_userinfo_and_path_segments():
    text = ("Ошибка https://svc:pa55word@host.ru/rest/7/abc/profile.json?code=abc — ответ: неверный ключ "
            "s3cr3t-key; путь /hooks/abc/ и %D0%BA%D0%BB%D1%8E%D1%87-42")
    clean = http.scrub(text, ["s3cr3t-key", "abc", "ключ-42"])
    assert "pa55word" not in clean and "svc:" not in clean and "https://…@host.ru" in clean
    assert "s3cr3t-key" not in clean and "%D0%BA%D0%BB" not in clean
    assert "/rest/7/…/profile.json" in clean and "/hooks/…/" in clean, "короткий секрет — как целый сегмент пути"
    assert "неверный ключ" in clean, "обычные слова не портятся"
    assert http.scrub("сообщение без секретов", []) == "сообщение без секретов"
    assert http.scrub_data({"a": ["x s3cr3t-key"], "n": 1}, ["s3cr3t-key"]) == {"a": ["x …"], "n": 1}


def test_client_errors_never_contain_secrets(server):
    secret = "Tk-9f8e7d6c5b4a"
    server.route("GET", f"/hook/{secret}/me", lambda r: (500, {"message": f"токен {secret} недействителен"}))
    server.route("GET", f"/hook/{secret}/gone", lambda r: (404, {}))
    server.route("GET", f"/hook/{secret}/html", lambda r: (200, f"<p>{secret}</p>"))
    server.route("GET", f"/hook/{secret}/moved", lambda r: (302, b"", {"Location": f"https://a:{secret}@sso.ru/x"}))
    for detailed in (True, False):
        c = client(server, secrets=(secret,), detailed=detailed)
        for path in ("me", "gone", "html", "moved"):
            with pytest.raises(IntegrationError) as exc:
                c.get_json(f"hook/{secret}/{path}")
            texts = (exc.value.detail, exc.value.short, exc.value.message(False), str(exc.value))
            assert not any(secret in t for t in texts), (path, texts)
    # Пароль Basic и токен Authorization — секреты клиента и без явного списка
    server.route("GET", "/echo", lambda r: (400, {"error": "bad password pa55-W0rd, token Bearer-xyz-123"}))
    with pytest.raises(IntegrationError) as exc:
        client(server, auth=("svc", "pa55-W0rd")).get_json("echo")
    assert "pa55-W0rd" not in exc.value.detail
    with pytest.raises(IntegrationError) as exc:
        client(server, headers={"Authorization": "Bearer Bearer-xyz-123"}).get_json("echo")
    assert "Bearer-xyz-123" not in exc.value.detail


def test_connection_error_text_is_scrubbed(server):
    secret = "hook-code-778899"
    port = server.server.server_address[1]
    server.stop()
    c = HttpClient(f"http://127.0.0.1:{port}", title="Bitrix24", secrets=(secret,))
    with pytest.raises(IntegrationError) as exc:
        c.request("POST", f"rest/1/{secret}/profile.json", retry=True)
    assert exc.value.code == "connect" and secret not in exc.value.detail
    server.start()


# ---------------------------------------------------------------- прокси и NO_PROXY

PROXY_VARS = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY")


@pytest.fixture()
def proxy_env(monkeypatch):
    """Окружение без прокси (у CI и среды разработки они свои): тест задаёт их сам."""
    for name in PROXY_VARS:
        monkeypatch.delenv(name, raising=False)
        monkeypatch.delenv(name.lower(), raising=False)
    monkeypatch.delenv("FAKE_ALLOWED_HOSTS", raising=False)
    return monkeypatch


@pytest.fixture()
def target_and_proxy():
    """Узел подключения и поддельный прокси HTTP: прокси получает запрос с полным адресом в строке запроса."""
    with FakeServer() as target, FakeServer() as proxy:
        target.route("GET", "/api/ping", lambda r: (200, {"via": "direct"}))
        proxy.route("GET", "/api/ping", lambda r: (200, {"via": "proxy"}))
        yield target, proxy


def _via(target) -> str:
    with HttpClient(target.url, kind="fake", title="Система") as c:
        return c.get_json("api/ping")["via"]


def test_requests_go_through_http_proxy(proxy_env, target_and_proxy):
    target, proxy = target_and_proxy
    proxy_env.setenv("HTTP_PROXY", proxy.url)
    assert _via(target) == "proxy"
    host = target.url.removeprefix("http://")
    assert proxy.requests[0].headers["host"] == host and not target.requests


@pytest.mark.parametrize("no_proxy", ["127.0.0.1", "localhost, 127.0.0.1", "{host}", "*", "127.0.0.0/8"])
def test_no_proxy_hosts_go_direct(proxy_env, target_and_proxy, no_proxy):
    target, proxy = target_and_proxy
    proxy_env.setenv("HTTP_PROXY", proxy.url)
    proxy_env.setenv("NO_PROXY", no_proxy.format(host=target.url.removeprefix("http://")))
    assert _via(target) == "direct" and not proxy.requests
    assert http.environ_proxy(target.url) == ""


def test_lowercase_no_proxy_is_honoured(proxy_env, target_and_proxy):
    target, proxy = target_and_proxy
    proxy_env.setenv("http_proxy", proxy.url)
    proxy_env.setenv("no_proxy", "127.0.0.1")
    assert _via(target) == "direct"
    proxy_env.setenv("no_proxy", ".company.ru")
    assert _via(target) == "proxy", "узел не из NO_PROXY — через прокси"


def test_unreachable_proxy_is_named_without_credentials(proxy_env):
    proxy_env.setenv("HTTP_PROXY", "http://svc:proxy-secret@127.0.0.1:9")
    proxy_env.setenv("HTTPS_PROXY", "http://svc:proxy-secret@proxy.company.ru:3128")
    assert http.environ_proxy("https://jira.company.ru/rest") == "http://proxy.company.ru:3128"
    with pytest.raises(IntegrationError) as exc, HttpClient("http://10.20.30.40:8080", kind="fake",
                                                            title="Система") as c:
        c.get_json("api/ping")
    assert exc.value.code in ("connect", "connect_timeout")
    assert "через прокси http://127.0.0.1:9" in exc.value.detail and "NO_PROXY" in exc.value.detail
    assert "proxy-secret" not in exc.value.detail and "svc:" not in exc.value.detail
    proxy_env.setenv("NO_PROXY", "10.0.0.0/8")
    assert http.environ_proxy("http://10.20.30.40:8080") == "", "NO_PROXY с маской сети"


@pytest.mark.parametrize(("no_proxy", "url", "direct"), [
    ("jira.company.ru", "https://jira.company.ru/rest", True),
    ("company.ru", "https://jira.company.ru", True),
    (".company.ru", "https://company.ru", True),
    ("*.company.ru", "https://a.b.company.ru:8443/x", True),
    ("jira.company.ru:8443", "https://jira.company.ru:8443", True),
    ("jira.company.ru:8443", "https://jira.company.ru", False),
    ("10.1.2.3:8080", "http://10.1.2.3:8080/odata", True),
    ("10.1.2.3:8080", "http://10.1.2.3/odata", False),
    ("10.0.0.0/8", "http://10.200.0.1", True),
    ("10.0.0.0/8", "http://11.0.0.1", False),
    ("[::1]:8080", "http://[::1]:8080", True),
    ("other.ru, , localhost", "http://localhost:5000", True),
    ("other.ru", "https://jira.company.ru", False),
    ("", "https://jira.company.ru", False),
])
def test_bypass_proxy_rules(proxy_env, no_proxy, url, direct):
    proxy_env.setenv("NO_PROXY", no_proxy)
    assert http.bypass_proxy(url) is direct

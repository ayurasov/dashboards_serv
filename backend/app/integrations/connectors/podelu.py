"""«По Делу» (todo-planner): структура и сотрудники, данные из вложений задач (ADR-0011, таблица «Коннекторы 0.4.0»).

Два режима подключения (настройка mode):
- «Ключ интеграции» (key, по умолчанию; «По Делу» 1.4.5 и новее, ADR-0058 там) — у «Дашбордов» свой ключ
  podelu_… с областями доступа: org.read (структура), users.read (сотрудники), tasks.attachments.read (задачи
  и файлы выбранных для ключа списков), tasks.comment (комментарии в них). Запросы — /api/integrations/v1 с
  Authorization: Bearer, без cookie и CSRF; предел частоты — на ключ (INTEGRATION_RATE_LIMIT «По Делу»,
  по умолчанию 120 запросов в минуту). Ключ выпускает администратор «По Делу»: «Настройки → Интеграции → Ключи
  интеграций», система «Дашборды», код dashboards;
- «Служебная учётная запись» (session; для «По Делу» до 1.4.5): GET /api/auth/csrf-token → POST /api/auth/login
  (X-CSRF-Token, Referer, Origin) → запросы → POST /api/auth/logout — всегда, и после ошибки. Права учётной записи
  в «По Делу»: полномочия «Ведёт структуру компании» (org.manage) и «Ведёт учётные записи» (users.manage),
  участник (просмотр) выделенного списка задач; роль администратора не нужна.
Подключения, сохранённые до режима ключа (без mode), работают служебной учётной записью (stored_config).

«Синхронизировать структуру»:
- структура: GET /api/integrations/v1/org/export (ключ; у руководителей — userId) или /api/org/export (сессия) —
  podelu.org-structure → dashboards.org-structure → элемент входящих набора «Структура компании» (план
  и применение — движок org_transfer; «применять сразу» — по правилу «Подключение» × «Структура компании»).
  Подразделения сопоставляются по пути, их внешний ID — ключ подразделения в «По Делу»; типы уровней, которых
  нет в настройках структуры, заменяются типом по умолчанию; настройки структуры «По Делу» не применяются;
  руководитель с userId, уже пришедший из «По Делу», находится по нему, даже если его email в «По Делу» сменился;
- сотрудники: GET /api/integrations/v1/users/export?format=json&inactive=0 (ключ; у каждой записи userId) или
  /api/users/export?format=json&inactive=0 и /api/users/admin/all (сессия: id сотрудников) → строки быстрой
  загрузки, источник podelu (ctx.plans.org_list): сопоставление по id «По Делу» (external_id сотрудника
  с org_source = podelu), затем по email; новые сотрудники — «Без доступа» (без пароля); роли, полномочия
  и активность из «По Делу» не переносятся. Применение — по правилу «Подключение» × «Сотрудники» и только когда
  структура уже совпадает с «По Делу» (иначе — план без записи). «Отключать отсутствующих» — отключаются
  сотрудники, пришедшие из «По Делу» (org_source = podelu), которых нет среди активных в выгрузке; служебная
  учётная запись подключения (в режиме сессии) и сотрудники других источников не отключаются.

Ключ и пароль привязаны к обоим адресам (secret_url: «адрес → адрес для запросов сервера»): изменили любой
из них — секрет вводится заново.

«Забрать данные из задач»: файлы задач (только Excel, CSV, JSON) → «Входящие» с source_ref
podelu:<задача>:<вложение>:<sha256>; повтор (ctx.inbox.seen) не скачивается; у элемента — пояснение «Задача
«<название>» · <кто положил файл>»; задача отмечается комментарием «Файл «…» принят в «Дашборды»: <статус>»
(и ссылкой на «Входящие», если задан PUBLIC_URL).
- ключ: GET /api/integrations/v1/tasks?hasAttachments=1&updatedSince=<since>&cursor=…&limit=200 (необязательно
  listId — один из списков ключа, по умолчанию все списки ключа; tags — при одной метке) — задачи по возрастанию
  activityAt; файл задачи меняет activityAt, поэтому курсор (ctx.state) — только since: самое позднее activityAt
  обработанной задачи, оно сохраняется после каждой задачи (предел частоты или сбой посреди запуска — следующий
  запуск продолжит с места остановки). Файлы задачи — GET …/tasks/<id>/attachments (с sha256: уже забранные не
  скачиваются), содержимое — …/attachments/<id>/content; кто положил файл — по выгрузке сотрудников (один раз
  за запуск, если у ключа есть users.read); отметка — POST …/tasks/<id>/comments (без повтора);
  403 comments_disabled — предупреждение. Файлы результатов поручений API ключей не отдаёт;
- сессия: задачи списка data_list (и меток data_tags) с вложениями → файлы задачи и её результатов. Курсор:
  since — самое позднее updatedAt задач списка, tasks — число вложений и SHA-256 уже забранных файлов по задачам:
  загрузка вложения в «По Делу» до 1.4.5 не меняет updatedAt задачи, поэтому задача берётся и тогда, когда
  изменилось число её вложений.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote

from ...core.config import settings
from ...models import InboxRule, name_key
from ...services import inbox_datasets, org, org_admin
from ...services.inbox import plan_errors
from ...services.org_import import EMAIL, Row, split_path
from ...services.org_transfer import FORMAT as STRUCTURE_FORMAT
from ...services.org_transfer import StructureFormatError
from ..base import Action, CheckResult, Connector, Field, Option, RunContext, RunResult, register
from ..http import IntegrationError
from .common import (
    KEY_MODE,
    MODE_LABELS,
    SESSION_MODE,
    KeyApi,
    PartnerSession,
    connection_mode,
    download_limit,
    inbox_limit,
    is_data_file,
    iso,
    joined_urls,
    parse_time,
    sha256,
    status_text,
)

TITLE = "По Делу"
ORG_FORMAT = "podelu.org-structure"
EMPLOYEES_FORMAT = "podelu.employees"
ORG_RIGHT, USERS_RIGHT = "org.manage", "users.manage"
RIGHT_LABELS = {ORG_RIGHT: "«Ведёт структуру компании» (org.manage)",
                USERS_RIGHT: "«Ведёт учётные записи» (users.manage)"}
NO_ORG = (f"У служебной учётной записи нет права выгружать структуру в «{TITLE}» — нужно полномочие "
          f"{RIGHT_LABELS[ORG_RIGHT]}")
NO_USERS = (f"У служебной учётной записи нет права выгружать сотрудников в «{TITLE}» — нужно полномочие "
            f"{RIGHT_LABELS[USERS_RIGHT]}")
PAGE_SIZE = 200
MAX_PAGES = 50
MAX_TRACKED_TASKS = 5000
MAX_DETAILS = 50
NOTE_LIMIT = 500

# --- API ключей интеграций «По Делу» 1.4.5+ (ADR-0058 «По Делу»)
V1 = "api/integrations/v1"
KEY_PREFIX = "podelu_"
SCOPE_ORG, SCOPE_USERS = "org.read", "users.read"
SCOPE_TASKS, SCOPE_COMMENT = "tasks.attachments.read", "tasks.comment"
# Подписи областей — как в «По Делу» («Настройки → Интеграции → Ключи интеграций»)
SCOPE_LABELS = {SCOPE_ORG: "«Структура компании» (org.read)", SCOPE_USERS: "«Сотрудники» (users.read)",
                SCOPE_TASKS: "«Задачи и вложения» (tasks.attachments.read)",
                SCOPE_COMMENT: "«Комментарии к задачам» (tasks.comment)"}
KEYS_PLACE = f"«{TITLE}» → «Настройки → Интеграции → Ключи интеграций»"
NO_API = (f"По адресу подключения нет API ключей интеграций «{TITLE}» (/{V1}/ping, 404): «{TITLE}» старше 1.4.5 или "
          f"адрес указан неверно. Обновите «{TITLE}» до 1.4.5 или выберите режим «Служебная учётная запись (для "
          "версий до 1.4.5)»")
# Названий списков ключа «По Делу» не отдаёт (только listTitle у задач): не больше стольких запросов на списки
# без задач среди первой страницы
MAX_LIST_PROBES = 10
COMMENT_LIMIT = 10000


# ---------------------------------------------------------------- форматы «По Делу» → наши

def structure_bundle(doc: Any, head_emails: dict[str, str] | None = None) -> dict:
    """podelu.org-structure версии 1 → dashboards.org-structure версии 1 (набор «Структура компании»).
    head_emails — {id сотрудника «По Делу»: email в «Дашбордах»}: руководитель из API ключей (с userId) находится
    по нему, даже если email в «По Делу» уже другой."""
    if not isinstance(doc, dict) or doc.get("format") != ORG_FORMAT:
        raise StructureFormatError(f"Это не файл структуры «{TITLE}» (нужен format: {ORG_FORMAT})")
    if doc.get("version") != 1:
        raise StructureFormatError(f"Версия файла структуры «{TITLE}» {doc.get('version')} не поддерживается — нужна 1")
    items = doc.get("departments")
    if not isinstance(items, list):
        raise StructureFormatError(f"В файле структуры «{TITLE}» нет списка подразделений")
    head_emails = head_emails or {}
    departments = []
    for raw in items:
        if not isinstance(raw, dict):
            continue
        heads = []
        for h in raw.get("heads") or []:
            if not isinstance(h, dict):
                continue
            email = head_emails.get(str(h.get("userId") or "")) or str(h.get("email") or "")
            if email.strip():
                heads.append({"email": email.strip().lower(), "name": "", "primary": bool(h.get("primary"))})
        key = str(raw.get("key") or "")
        departments.append({"key": key, "name": raw.get("name"), "parent": raw.get("parent") or None,
                            "kind": raw.get("kind") or "department", "sort_order": raw.get("sortOrder") or 0,
                            "code": None, "external_id": key or None, "heads": heads})
    settings = doc.get("settings") if isinstance(doc.get("settings"), dict) else {}
    return {"format": STRUCTURE_FORMAT, "version": 1, "exported_at": doc.get("exportedAt"),
            "app": f"{TITLE} {doc.get('app') or ''}".strip(), "source": "podelu",
            "settings": {k: settings[k] for k in ("org_unit_kinds", "org_max_depth", "org_default_view")
                         if k in settings},
            "departments": departments}


def employees_document(doc: Any) -> dict:
    """podelu.employees версии 1 → dashboards.employees версии 1 (набор «Сотрудники», загрузка файла вручную).
    Роль, полномочия, активность и способ входа не переносятся: доступ в «Дашбордах» выдаётся здесь."""
    if not isinstance(doc, dict) or doc.get("format") != EMPLOYEES_FORMAT:
        raise StructureFormatError(f"Это не файл сотрудников «{TITLE}» (нужен format: {EMPLOYEES_FORMAT})")
    records = []
    for e in doc.get("employees") or []:
        if not isinstance(e, dict):
            continue
        records.append({
            "email": e.get("email"), "login": e.get("login"), "full_name": e.get("name"), "position": e.get("position"),
            "department": e.get("department") or [], "manager": e.get("manager") or "",
            "reports_to_none": bool(e.get("reportsToNone")),
            "heads": [{"department": h.get("department") or [], "primary": bool(h.get("primary"))}
                      for h in e.get("heads") or [] if isinstance(h, dict)],
            "external_id": e.get("externalId") or None,
        })
    return {"format": "dashboards.employees", "version": 1, "employees": records}


# Файлы «По Делу», положенные во «Входящие» вручную (папка, загрузка), распознаются как структура и сотрудники
inbox_datasets.register_json_format(ORG_FORMAT, "structure", structure_bundle)
inbox_datasets.register_json_format(EMPLOYEES_FORMAT, "employees", employees_document)


def rights(user: dict) -> dict[str, bool]:
    """Права учётной записи «По Делу» по ответу входа: администратор — все полномочия."""
    admin = user.get("globalRole") == "admin"
    caps = user.get("capabilities") if isinstance(user.get("capabilities"), list) else []
    return {"admin": admin, ORG_RIGHT: admin or ORG_RIGHT in caps, USERS_RIGHT: admin or USERS_RIGHT in caps}


def find_list(lists: list, ref: str) -> dict | None:
    """Список по id или по названию (без учёта регистра и лишних пробелов)."""
    ref = (ref or "").strip()
    items = [x for x in lists if isinstance(x, dict) and x.get("id")]
    found = next((x for x in items if str(x["id"]) == ref), None)
    if found is None:
        named = [x for x in items if name_key(str(x.get("title") or "")) == name_key(ref)]
        found = named[0] if len(named) == 1 else None
    return found


def list_label(item: dict) -> str:
    """«Название» списка или его id, если названия «По Делу» не сообщила."""
    return f"«{item['title']}»" if item.get("title") else str(item.get("id"))


def task_note(title: Any, author: str = "") -> str:
    """Пояснение элемента входящих: «Задача «<название>» · <кто положил файл>» (до 500 символов)."""
    tail = f" · {author}" if author else ""
    room = NOTE_LIMIT - len("Задача «»") - len(tail)
    name = " ".join(str(title or "без названия").split())
    if len(name) > room:
        name = name[:max(room - 1, 1)] + "…"
    return f"Задача «{name}»{tail}"[:NOTE_LIMIT]


def comments_allowed(item: dict) -> bool:
    settings = item.get("settings") if isinstance(item.get("settings"), dict) else {}
    return settings.get("allowComments", True) is not False


class UploaderNames:
    """Имена сотрудников «По Делу» по id для пояснения элемента входящих: выгрузка сотрудников (users.read) —
    один раз за запуск и только когда понадобилось имя. Без области — без имени."""

    def __init__(self, api: KeyApi, allowed: bool):
        self.api = api
        self.allowed = allowed
        self.names: dict[str, str] | None = None

    def get(self, *user_ids: Any) -> str:
        if not self.allowed:
            return ""
        if self.names is None:
            self.names = {}
            try:
                doc = self.api.get("users/export", params={"format": "json"})
            except IntegrationError as exc:
                if exc.code == "rate_limited":
                    raise
                doc = {}
            for e in doc.get("employees") or []:
                if isinstance(e, dict) and e.get("userId"):
                    self.names[str(e["userId"])] = " ".join(str(e.get("name") or e.get("email") or "").split())
        return next((self.names[str(u)] for u in user_ids if u and self.names.get(str(u))), "")


# ---------------------------------------------------------------- коннектор

@register
class PodeluConnector(Connector):
    kind = "podelu"
    title = TITLE
    description = ("Структура и сотрудники из «По Делу»; данные — вложения задач списков с данными во «Входящие», "
                   "задача отмечается комментарием. Подключение — ключом интеграции «По Делу» 1.4.5 и новее "
                   "(области org.read, users.read, tasks.attachments.read, tasks.comment) или, для более ранних "
                   "версий, служебной учётной записью с полномочиями org.manage и users.manage")
    fields = (
        Field("base_url", "Адрес «По Делу»", "url", required=True, placeholder="https://podelu.company.ru",
              hint="Адрес, по которому сотрудники открывают «По Делу»"),
        Field("server_url", "Адрес для запросов сервера", "url", placeholder="http://host.docker.internal:5000",
              hint="Необязательно: если сервер «Дашбордов» видит «По Делу» по другому адресу (например, оба в Docker "
                   "на одной машине). Ключ и пароль привязаны к обоим адресам: изменили любой — введите их заново"),
        Field("mode", "Режим подключения", "select", required=True, default=KEY_MODE,
              options=(Option(KEY_MODE, "Ключ интеграции (По Делу 1.4.5 и новее)"),
                       Option(SESSION_MODE, "Служебная учётная запись (для версий до 1.4.5)")),
              hint="Рекомендуется ключ интеграции: у «Дашбордов» свой ключ только с нужными областями, без входа "
                   "учётной записью. Служебная учётная запись — для «По Делу» до 1.4.5, где ключей для других "
                   "систем нет"),
        Field("key", "Ключ интеграции", "password", required=True, secret=True, placeholder="podelu_…",
              show_if={"mode": (KEY_MODE,)},
              hint="Выпускает администратор «По Делу»: «Настройки → Интеграции → Ключи интеграций» — система "
                   "«Дашборды», код dashboards, области «Структура компании» (org.read), «Сотрудники» (users.read), "
                   "«Задачи и вложения» (tasks.attachments.read), «Комментарии к задачам» (tasks.comment) и списки "
                   "задач с данными. Ключ показывается один раз"),
        Field("login", "Служебная учётная запись", required=True, placeholder="dashboards-sync",
              show_if={"mode": (SESSION_MODE,)},
              hint="Логин или email в «По Делу»: полномочия «Ведёт структуру компании» и «Ведёт учётные записи», "
                   "участник (просмотр) списка с данными; роль администратора не нужна"),
        Field("password", "Пароль", "password", required=True, secret=True, show_if={"mode": (SESSION_MODE,)}),
        Field("verify_tls", "Проверять TLS-сертификат", "bool", default=True,
              hint="Выключите только для самоподписанного или корпоративного сертификата"),
        Field("data_list", "Список задач с данными", placeholder="Данные для дашбордов",
              hint="Ключ интеграции: необязательно — id или название одного из списков ключа; пусто — все списки "
                   "ключа. Служебная учётная запись: id или название списка, в задачи которого кладут выгрузки "
                   "(учётная запись — его участник). Списки — в результате проверки подключения"),
        Field("data_tags", "Метки задач", "list",
              hint="Необязательно: только задачи с одной из этих меток"),
        Field("create_missing_units", "Создавать недостающие подразделения", "bool", default=True,
              hint="Подразделения «По Делу», которых нет в структуре, создаются; выключено — обновляются только "
                   "существующие, сотрудники новых подразделений не переводятся и не создаются"),
        Field("deactivate_missing", "Отключать отсутствующих сотрудников", "bool", default=False,
              hint="Сотрудники, пришедшие из «По Делу», которых там больше нет среди активных, отключаются"),
        Field("mark_processed", "Отмечать задачу комментарием", "bool", default=True,
              hint="Комментарий в задаче: «Файл «…» принят в «Дашборды»: <статус>» (со ссылкой на «Входящие», если "
                   "на сервере задан PUBLIC_URL); в списке должны быть разрешены комментарии, ключу нужна область "
                   "«Комментарии к задачам» (tasks.comment)"),
    )
    actions = (
        Action("sync", "Синхронизировать структуру",
               "Подразделения и сотрудники из «По Делу»: план и применение по правилам «Входящих» "
               "(источник «Подключение», наборы «Структура компании» и «Сотрудники»)"),
        Action("pull", "Забрать данные из задач",
               "Новые вложения задач списков с данными — во «Входящие»; задача отмечается комментарием"),
    )
    url_field = "base_url"
    order = 10
    counter_labels = {
        # «Синхронизировать структуру»: план структуры и сотрудников (structure_item — номер элемента, не счётчик)
        "structure_create": "подразделений: новых", "structure_update": "подразделений: изменений",
        "structure_heads": "руководителей назначить", "structure_errors": "ошибок в структуре",
        "users_create": "сотрудников: новых", "users_update": "сотрудников: изменений",
        "users_unchanged": "сотрудников без изменений", "users_deactivate": "сотрудников отключить",
        "users_departments": "подразделений для сотрудников", "users_errors": "ошибок у сотрудников",
        "users_skipped": "сотрудников пропущено",
        # «Забрать данные из задач»: tasks — задачи списка (сессия) или задачи с изменившимися файлами (ключ)
        "tasks": "задач просмотрено", "candidates": "задач с новыми вложениями", "comments": "задач отмечено",
        "comment_errors": "не удалось отметить", "comments_disabled": "не отмечено: комментарии выключены",
    }
    # Ключ и пароль уходят на адрес для запросов сервера (если он задан): привязка — к обоим адресам в обоих режимах
    secret_url_fields = ("base_url", "server_url")

    @classmethod
    def validate_config(cls, config: dict) -> dict:
        config = dict(config or {})
        if not config.get("mode"):
            # Новое подключение — по ключу; запрос с логином служебной учётной записи и без режима — как раньше
            config["mode"] = connection_mode(config)
        out = super().validate_config(config)
        if out.get("server_url") == out.get("base_url"):
            out["server_url"] = None
        return out

    @classmethod
    def stored_config(cls, config: dict | None) -> dict:
        """Подключение, сохранённое до режима ключа (без mode), — служебная учётная запись."""
        out = super().stored_config(config)
        if out.get("mode") not in MODE_LABELS:
            out["mode"] = connection_mode(out)
        return out

    @classmethod
    def secret_url(cls, config: dict) -> str:
        return joined_urls(config.get("base_url"), config.get("server_url"))

    @property
    def url(self) -> str | None:
        """Запросы — на адрес для запросов сервера, если он задан."""
        return self.config.get("server_url") or self.config.get("base_url")

    @property
    def mode(self) -> str:
        return connection_mode(self.config)

    # --- сессия и ключ
    def session(self) -> PartnerSession:
        if not self.url:
            raise IntegrationError("Не задан адрес «По Делу»", code="config")
        return PartnerSession(self.url, kind=self.kind, title=TITLE, login=self.config.get("login") or "",
                              password=self.secrets.get("password") or "", csrf_path="api/auth/csrf-token",
                              verify=bool(self.config.get("verify_tls", True)), detailed=self.detailed,
                              max_bytes=download_limit())

    def key_api(self) -> KeyApi:
        key = (self.secrets.get("key") or "").strip()
        if not key.startswith(KEY_PREFIX):
            raise IntegrationError(f"Ключ интеграции «{TITLE}» начинается с {KEY_PREFIX} — проверьте ключ",
                                   code="config")
        client = self.http(headers={"Authorization": f"Bearer {key}"}, cookies=False, max_bytes=download_limit())
        return KeyApi(client, title=TITLE, prefix=V1, place=KEYS_PLACE, no_api=NO_API)

    @staticmethod
    def key_info(ping: dict) -> tuple[list[str], list[str]]:
        """(области ключа, списки ключа) из ответа /ping."""
        scopes = [str(s) for s in ping.get("scopes") or [] if isinstance(s, str)]
        lists = [str(x) for x in ping.get("listIds") or [] if x not in (None, "")]
        return scopes, lists

    # --- проверка
    def check(self) -> CheckResult:
        if self.mode == KEY_MODE:
            return self.check_key()
        return self.check_session()

    def check_session(self) -> CheckResult:
        with self.session() as s:
            user = s.user
            can = rights(user)
            missing: list[str] = []
            warnings: list[str] = []
            version, departments = "", None
            if can[ORG_RIGHT]:
                try:
                    exported = s.get_json("api/org/export", denied=NO_ORG)
                    version = str(exported.get("app") or "")
                    departments = len(exported.get("departments") or [])
                except IntegrationError as exc:
                    if exc.code != "forbidden":
                        raise
                    can[ORG_RIGHT] = False
            for right in (ORG_RIGHT, USERS_RIGHT):
                if not can[right]:
                    missing.append(f"полномочие {RIGHT_LABELS[right]}")
            lists = s.get_json("api/lists", kind=list)
            chosen = None
            ref = self.config.get("data_list")
            if ref:
                chosen = find_list(lists, ref)
                if chosen is None:
                    missing.append(f"доступ к списку «{ref}» (служебная учётная запись должна быть его участником)")
                elif self.config.get("mark_processed", True) and not comments_allowed(chosen):
                    warnings.append(f"в списке «{chosen.get('title')}» выключены комментарии — задачи не будут "
                                    "отмечаться")
            else:
                warnings.append("список задач с данными не выбран — «Забрать данные из задач» недоступно")
            if can["admin"]:
                warnings.append(f"учётная запись — администратор «{TITLE}»: достаточно полномочий org.manage и "
                                "users.manage")
        name = user.get("name") or user.get("login") or self.config.get("login")
        details = {
            "mode": SESSION_MODE, "version": version, "user": {"login": user.get("login"), "name": user.get("name")},
            "admin": can["admin"], "capabilities": [r for r in (ORG_RIGHT, USERS_RIGHT) if can[r]],
            "departments": departments, "missing": missing, "warnings": warnings,
            "lists": [{"id": x.get("id"), "title": x.get("title")} for x in lists if isinstance(x, dict)],
            "data_list": {"id": chosen.get("id"), "title": chosen.get("title"),
                          "comments": comments_allowed(chosen)} if chosen else None,
        }
        where = f"«{TITLE}» {version}".strip() if version else f"«{TITLE}»"
        if missing:
            return CheckResult(False, f"Вход в {where} как {name} выполнен, но не хватает: " + "; ".join(missing),
                               details)
        parts = [f"Подключено к {where} как {name}"]
        if departments is not None:
            parts.append(f"подразделений: {departments}")
        if chosen:
            parts.append(f"список «{chosen.get('title')}»")
        message = ", ".join(parts) + (f". Внимание: {'; '.join(warnings)}" if warnings else "")
        return CheckResult(True, message, details)

    def check_key(self) -> CheckResult:
        """Ключ: версия, название и области ключа, списки ключа (названия — по задачам), чего не хватает
        включённым возможностям. Проверка успешна, если работает хотя бы одно действие: ключ может быть выпущен
        только для структуры или только для файлов задач (второе подключение «По Делу» со своим ключом)."""
        ref = (self.config.get("data_list") or "").strip()
        mark = bool(self.config.get("mark_processed", True))
        with self.key_api() as api:
            ping = api.ping("podelu")
            scopes, list_ids = self.key_info(ping)
            departments = None
            if SCOPE_ORG in scopes:
                departments = len(api.get("org/export").get("departments") or [])
            lists = self._key_lists(api, scopes, list_ids)
        version = str(ping.get("version") or "")
        key = ping.get("key") if isinstance(ping.get("key"), dict) else {}
        key_name = api.key_name or "без названия"
        missing: list[str] = []
        problems: list[str] = []
        if SCOPE_ORG not in scopes:
            missing.append(f"область {SCOPE_LABELS[SCOPE_ORG]} — для «Синхронизировать структуру»")
        if SCOPE_USERS not in scopes:
            missing.append(f"область {SCOPE_LABELS[SCOPE_USERS]} — для сотрудников в «Синхронизировать структуру»")
        files = SCOPE_TASKS in scopes and bool(list_ids)
        if not files:
            missing.append(f"область {SCOPE_LABELS[SCOPE_TASKS]} со списками задач — для «Забрать данные из задач»")
        if mark and SCOPE_COMMENT not in scopes:
            missing.append(f"область {SCOPE_LABELS[SCOPE_COMMENT]} — для «Отмечать задачу комментарием»")
        chosen = find_list(lists, ref) if ref else None
        if ref and chosen is None and files:
            problems.append(f"доступ ключа к списку «{ref}» — выберите список для ключа или оставьте «Список задач "
                            "с данными» пустым (тогда берутся все списки ключа)")
        ok = not problems and (files or (SCOPE_ORG in scopes and SCOPE_USERS in scopes))
        details = {
            "mode": KEY_MODE, "version": version, "key": {"name": api.key_name, "app": key.get("app")},
            "scopes": scopes, "departments": departments, "lists": lists,
            "data_list": chosen, "missing": [*problems, *missing],
        }
        where = f"«{TITLE}» {version}".strip() if version else f"«{TITLE}»"
        lacking = "; ".join([*problems, *missing])
        if not ok:
            return CheckResult(False, f"Ключ «{key_name}» принят в {where}, но не хватает: {lacking} — {KEYS_PLACE}",
                               details)
        parts = [f"Подключено к {where} по ключу «{key_name}»"]
        if departments is not None:
            parts.append(f"подразделений: {departments}")
        if chosen:
            parts.append(f"список {list_label(chosen)}")
        elif files:
            parts.append(f"списки ключа: {', '.join(list_label(x) for x in lists)}")
        message = ", ".join(parts)
        if missing:
            message += f". Не хватает: {lacking} — добавьте ключу: {KEYS_PLACE}"
        return CheckResult(True, message, details)

    def _key_lists(self, api: KeyApi, scopes: list[str], list_ids: list[str]) -> list[dict]:
        """Списки ключа [{id, title}]: названий «По Делу» не отдаёт — они берутся из задач (listTitle): первая
        страница задач всех списков ключа, затем по задаче из каждого списка без названия (не больше
        MAX_LIST_PROBES запросов). Список без задач — без названия."""
        titles: dict[str, str] = {}

        def collect(page: dict) -> None:
            for task in page.get("items") or []:
                if isinstance(task, dict) and task.get("listId") and task.get("listTitle"):
                    titles.setdefault(str(task["listId"]), str(task["listTitle"]))

        if SCOPE_TASKS in scopes and list_ids:
            collect(api.get("tasks", params={"limit": PAGE_SIZE}))
            for list_id in [i for i in list_ids if i not in titles][:MAX_LIST_PROBES]:
                try:
                    collect(api.get("tasks", params={"listId": list_id, "limit": 1}))
                except IntegrationError as exc:
                    if exc.code != "not_found":     # список удалён в «По Делу» — без названия
                        raise
        return [{"id": list_id, "title": titles.get(list_id)} for list_id in list_ids]

    # --- действия
    def run(self, action: str, ctx: RunContext) -> RunResult:
        self.action(action)
        if action == "sync":
            return self.sync(ctx)
        return self.pull(ctx)

    # ================================================================ структура и сотрудники

    def sync(self, ctx: RunContext) -> RunResult:
        if self.mode == KEY_MODE:
            exported, employees, ids, keep = self._export_key()
        else:
            exported, employees, ids, keep = self._export_session()
        # Сеть закончилась (сессия закрыта) — дальше только движки «Дашбордов»
        snap = org.build_snapshot(ctx.db)
        head_emails = {p.external_id: p.email for p in snap.people.values()
                       if p.org_source == "podelu" and p.external_id and p.email}
        try:
            bundle = structure_bundle(exported, head_emails)
        except StructureFormatError as exc:
            raise IntegrationError(f"«{TITLE}» вернула неожиданную выгрузку структуры: {exc.detail}",
                                   code="bad_response") from None
        if not isinstance(employees, dict) or employees.get("format") != EMPLOYEES_FORMAT:
            raise IntegrationError(f"«{TITLE}» вернула неожиданную выгрузку сотрудников (нужен format: "
                                   f"{EMPLOYEES_FORMAT})", code="bad_response")
        notes: list[str] = []
        counters: dict[str, int] = {}
        structure = self._structure(ctx, bundle, notes, counters)
        team = self._employees(ctx, employees, ids, structure, notes, counters, keep)
        message = f"{structure['text']}. {team['text']}"
        details = {"mode": self.mode, "structure": {k: v for k, v in structure.items() if k != "text"},
                   "employees": {k: v for k, v in team.items() if k != "text"}}
        if notes:
            details["notes"] = notes[:MAX_DETAILS]
        errors = [*structure.get("errors", []), *team.get("errors", [])]
        if errors or team.get("skipped"):
            return RunResult.partial(message, "; ".join(errors[:5]), counters=counters, details=details)
        return RunResult.ok(message, counters=counters, details=details)

    def _export_session(self) -> tuple[Any, Any, dict[str, str], set[str]]:
        """Выгрузки служебной учётной записью: (структура, сотрудники, {email: id «По Делу»}, служебные логины)."""
        with self.session() as s:
            can = rights(s.user)
            missing = [RIGHT_LABELS[r] for r in (ORG_RIGHT, USERS_RIGHT) if not can[r]]
            if missing:
                raise IntegrationError(f"У служебной учётной записи «{TITLE}» нет полномочий: {', '.join(missing)} — "
                                       f"выдайте их в «{TITLE}» (Пользователи → полномочия)", code="forbidden")
            account = s.user
            exported = s.get_json("api/org/export", denied=NO_ORG)
            employees = s.get_json("api/users/export", params={"format": "json", "inactive": "0"}, denied=NO_USERS)
            people = s.get_json("api/users/admin/all", kind=list, denied=NO_USERS)
        ids = {str(p.get("email") or "").strip().lower(): str(p.get("id")) for p in people
               if isinstance(p, dict) and p.get("id") and p.get("email") and not p.get("isSystem")}
        return exported, employees, ids, self._service_account(account)

    def _export_key(self) -> tuple[Any, Any, dict[str, str], set[str]]:
        """Выгрузки по ключу (org.read, users.read): у сотрудников и руководителей — userId; служебной учётной
        записи нет — исключать из сотрудников и из отключения некого."""
        with self.key_api() as api:
            scopes, _lists = self.key_info(api.ping("podelu"))
            missing = [SCOPE_LABELS[s] for s in (SCOPE_ORG, SCOPE_USERS) if s not in scopes]
            if missing:
                raise IntegrationError(f"У ключа «{api.key_name}» нет областей: {', '.join(missing)} — добавьте их "
                                       f"ключу: {KEYS_PLACE}", code="insufficient_scope",
                                       short=f"У ключа интеграции «{TITLE}» не хватает областей доступа")
            exported = api.get("org/export")
            employees = api.get("users/export", params={"format": "json", "inactive": "0"})
        records = employees.get("employees") if isinstance(employees, dict) else None
        ids = {str(e.get("email") or "").strip().lower(): str(e["userId"]) for e in records or []
               if isinstance(e, dict) and e.get("userId") and e.get("email")}
        return exported, employees, ids, set()

    def _structure(self, ctx: RunContext, bundle: dict, notes: list[str], counters: dict) -> dict:
        kinds = org_admin.get_settings(ctx.db)["unit_kinds"]
        known = {k["value"] for k in kinds}
        default = org_admin.default_kind(kinds)
        replaced = sorted({d["kind"] for d in bundle["departments"] if d["kind"] not in known})
        for item in bundle["departments"]:
            if item["kind"] not in known:
                item["kind"] = default
        if replaced:
            kinds_text = ", ".join(f"«{k}»" for k in replaced)
            notes.append(f"Типы уровней «{TITLE}» {kinds_text} не заданы в настройках структуры — подразделения "
                         f"этих типов получили тип «{default}»")
        plan = ctx.plans.structure(bundle)
        if not self.config.get("create_missing_units", True):
            new = {d["key"] for d in plan["departments"] if d["action"] == "create"}
            if new:
                paths = ", ".join(d["path"] for d in plan["departments"] if d["key"] in new)
                notes.append(f"Не созданы подразделения (выключено «Создавать недостающие подразделения»): "
                             f"{paths}"[:600])
                bundle["departments"] = [d for d in bundle["departments"] if d["key"] not in new]
                plan = ctx.plans.structure(bundle)
        summary = plan["summary"]
        counters.update(structure_create=summary["create"], structure_update=summary["update"],
                        structure_heads=summary["add_heads"], structure_errors=summary["errors"])
        changes = f"создать {summary['create']}, изменить {summary['update']}, руководителей {summary['add_heads']}"
        out: dict = {"summary": summary, "missing_in_file": len(plan.get("missing_in_file") or [])}
        if not (summary["create"] or summary["update"] or summary["add_heads"] or summary["errors"]):
            return {**out, "status": "unchanged", "ready": True, "text": "Структура: без изменений"}
        canonical = json.dumps({k: bundle[k] for k in ("settings", "departments")}, ensure_ascii=False, sort_keys=True)
        ref = f"podelu:org-structure:{sha256(canonical.encode())[:32]}"
        previous = ctx.inbox.seen(ref)
        if previous is not None and previous.status in ("received", "recognized", "pending"):
            out.update(status="waiting", item=previous.id, ready=False)
            if not previous.plan_ok:
                out["errors"] = [f"структура: {e}" for e in (plan_errors(previous.plan) or [previous.message])[:5]]
            return {**out, "text": f"Структура: {changes} — уже ожидает решения на экране «Входящие» "
                                   f"(элемент №{previous.id})"}
        content = json.dumps(bundle, ensure_ascii=False, indent=1).encode()
        stamp = datetime.now(UTC).strftime("%Y-%m-%d-%H%M")
        item = ctx.inbox.add(content, f"podelu-structure-{stamp}.json", dataset="structure", source_ref=ref,
                             content_type="application/json", options={"apply_settings": False})
        out.update(item=item.id, status=item.status, ready=item.status == "applied")
        counters["structure_item"] = item.id
        if item.status == "applied":
            return {**out, "text": f"Структура: {changes} — применено (элемент входящих №{item.id})"}
        if item.status == "pending" and item.plan_ok:
            return {**out, "text": f"Структура: {changes} — ожидает подтверждения на экране «Входящие» "
                                   f"(элемент №{item.id}): {item.message}"}
        errors = plan_errors(item.plan) or [item.error or item.message or status_text(item)]
        out["errors"] = [f"структура: {e}" for e in errors[:5]]
        return {**out, "text": f"Структура: не применена — {status_text(item)} (элемент входящих №{item.id})"}

    def _employees(self, ctx: RunContext, document: dict, ids: dict[str, str], structure: dict, notes: list[str],
                   counters: dict, keep: set[str]) -> dict:
        snap = org.build_snapshot(ctx.db)
        rows, skipped = self.rows(document, ids, snap, notes, org_admin.get_settings(ctx.db)["max_depth"], keep)
        if not rows:
            message = f"выгрузка сотрудников «{TITLE}» пуста — сотрудники не синхронизируются"
            return {"summary": {}, "applied": False, "skipped": skipped[:MAX_DETAILS], "errors": [message],
                    "text": f"Сотрудники: {message}"}
        rule = ctx.db.get(InboxRule, ("integration", "employees"))
        reason = ""
        if not structure.get("ready"):
            reason = "сначала примените структуру" + (f" (элемент входящих №{structure['item']})"
                                                      if structure.get("item") else "")
        elif rule is None or not rule.auto_apply:
            reason = ("для источника «Подключение» и набора «Сотрудники» не включено «применять сразу» (экран "
                      "«Входящие» → «Правила»)")
        apply = not reason
        deactivate = bool(self.config.get("deactivate_missing"))
        result = ctx.plans.org_list(rows, apply=apply, create_missing=True, deactivate_missing=deactivate,
                                    keep=keep)
        errors: list[str] = []
        if apply and not result.get("applied") and result["summary"]["errors"]:
            # Строки с ошибками пропускаются — остальные сотрудники применяются (ошибки — в журнале запуска)
            bad = {u["line"] for u in result["users"] if u["errors"]}
            for user in result["users"]:
                if user["errors"]:
                    skipped.append(f"{user['name'] or user['email']}: {'; '.join(user['errors'])}")
            rows = [r for r in rows if r.line not in bad]
            result = ctx.plans.org_list(rows, apply=True, create_missing=True, deactivate_missing=deactivate,
                                        keep=keep)
            if not result.get("applied"):
                errors = [f"сотрудники: {e}" for e in plan_errors(result, 5)] or ["сотрудники: план не применён"]
        summary = result["summary"]
        counters.update(users_create=summary["create_users"], users_update=summary["update_users"],
                        users_unchanged=summary["unchanged"], users_deactivate=summary["deactivate_users"],
                        users_departments=summary["create_departments"], users_errors=summary["errors"],
                        users_skipped=len(skipped))
        if not apply and summary["errors"]:
            notes.extend(f"план сотрудников: {e}" for e in plan_errors(result, 5))
        numbers = (f"создано {summary['create_users']}, изменено {summary['update_users']}, без изменений "
                   f"{summary['unchanged']}")
        if summary["deactivate_users"]:
            numbers += f", отключено {summary['deactivate_users']}"
        if skipped:
            numbers += f", пропущено {len(skipped)}"
        out = {"summary": summary, "applied": bool(result.get("applied")), "skipped": skipped[:MAX_DETAILS],
               "errors": errors}
        if result.get("applied"):
            return {**out, "text": f"Сотрудники: {numbers}"}
        if reason:
            plan_numbers = (f"создать {summary['create_users']}, изменить {summary['update_users']}, без изменений "
                            f"{summary['unchanged']}")
            return {**out, "reason": reason, "text": f"Сотрудники: план — {plan_numbers}; не применено: {reason}"}
        return {**out, "text": f"Сотрудники: не применены — {'; '.join(errors) or 'в плане ошибки'}"}

    def rows(self, document: dict, ids: dict[str, str], snap: org.OrgSnapshot, notes: list[str], max_depth: int,
             service: set[str] | None = None) -> tuple[list[Row], list]:
        """Записи podelu.employees → строки быстрой загрузки (источник podelu). ids — {email: id «По Делу»}.
        Строки, которые движок отверг бы целиком (нет email, нет подразделения у нового, путь глубже предела),
        пропускаются с пояснением; служебная учётная запись подключения (service — логин и email) сотрудником не
        считается."""
        service = service or set()
        by_external = {p.external_id: p for p in snap.people.values() if p.org_source == "podelu" and p.external_id}
        by_email: dict[str, list] = {}
        for p in snap.people.values():
            if p.email:
                by_email.setdefault(p.email.lower(), []).append(p)
        paths = {tuple(name_key(n) for n in snap.path_names(u)) for u in snap.units}
        create_units = bool(self.config.get("create_missing_units", True))
        rows: list[Row] = []
        skipped: list[str] = []
        for line, raw in enumerate(document.get("employees") or [], start=1):
            if not isinstance(raw, dict):
                continue
            email = str(raw.get("email") or "").strip().lower()
            name = " ".join(str(raw.get("name") or "").split())
            if email in service or str(raw.get("login") or "").strip().lower() in service:
                continue
            if not EMAIL.match(email):
                skipped.append(f"{name or 'без имени'}: нет email или он некорректный")
                continue
            external = ids.get(email, "")
            person = by_external.get(external) if external else None
            if person is None and len(by_email.get(email, [])) == 1:
                person = by_email[email][0]
            department = split_path(raw.get("department") or [])
            exists = tuple(name_key(n) for n in department) in paths
            if not department or (not create_units and not exists):
                why = "в «По Делу» не указано подразделение" if not department else \
                    f"подразделения «{' / '.join(department)}» нет в структуре"
                if person is not None and person.department_id in snap.units:
                    department = snap.path_names(person.department_id)
                    notes.append(f"{name or email}: {why} — подразделение не меняется")
                else:
                    skipped.append(f"{name or email}: {why} — сотрудник не создаётся")
                    continue
            if len(department) > max_depth:
                skipped.append(f"{name or email}: путь подразделения глубже предела вложенности")
                continue
            heads = [split_path(h.get("department") or []) for h in raw.get("heads") or [] if isinstance(h, dict)]
            manager = str(raw.get("manager") or "").strip().lower()
            rows.append(Row(line=line, email=email, name=name, login=str(raw.get("login") or "").strip(),
                            department=department, position=" ".join(str(raw.get("position") or "").split()) or None,
                            manager_email=manager if EMAIL.match(manager) else "",
                            is_head=department in heads, external_id=external))
        # Явный руководитель, которого нет ни в выгрузке, ни в системе, сделал бы ошибкой всю строку
        known = {r.email for r in rows} | set(by_email)
        for row in rows:
            if row.manager_email and row.manager_email not in known:
                notes.append(f"{row.name or row.email}: руководитель {row.manager_email} не найден — не назначается")
                row.manager_email = ""
        return rows, skipped

    @staticmethod
    def _service_account(account: dict | None) -> set[str]:
        """Логин и email служебной учётной записи «По Делу»: её нет в строках сотрудников (rows), и отключать её
        как «отсутствующую» нельзя."""
        return {str((account or {}).get(k) or "").strip().lower() for k in ("login", "email")} - {""}

    # ================================================================ данные из задач

    def pull(self, ctx: RunContext) -> RunResult:
        if self.mode == KEY_MODE:
            return self.pull_key(ctx)
        return self.pull_session(ctx)

    def pull_key(self, ctx: RunContext) -> RunResult:
        """Файлы задач списков ключа (или выбранного списка) по курсору activityAt — см. описание модуля."""
        ref = (self.config.get("data_list") or "").strip()
        tags = [t for t in self.config.get("data_tags") or [] if t]
        counters = {"tasks": 0, "candidates": 0, "files": 0, "added": 0, "seen": 0, "skipped_type": 0,
                    "too_large": 0, "comments": 0, "comment_errors": 0, "comments_disabled": 0}
        details: list[dict] = []
        notes: list[str] = []
        comment_errors: list[str] = []
        stopped = ""
        state = ctx.state
        with self.key_api() as api:
            scopes, list_ids = self.key_info(api.ping("podelu"))
            if SCOPE_TASKS not in scopes or not list_ids:
                raise IntegrationError(f"У ключа «{api.key_name}» нет области {SCOPE_LABELS[SCOPE_TASKS]} со списками "
                                       f"задач — добавьте её и списки с данными: {KEYS_PLACE}",
                                       code="insufficient_scope",
                                       short=f"У ключа интеграции «{TITLE}» нет доступа к задачам")
            chosen = None
            if ref:
                lists = [{"id": ref, "title": None}] if ref in list_ids else self._key_lists(api, scopes, list_ids)
                chosen = find_list(lists, ref)
                if chosen is None:
                    raise IntegrationError(f"Список «{ref}» не открыт ключу «{api.key_name}» — выберите его для ключа "
                                           f"({KEYS_PLACE}) или оставьте «Список задач с данными» пустым: тогда "
                                           "берутся все списки ключа", code="not_found")
            scope = {"lists": [chosen["id"]] if chosen else sorted(list_ids), "tags": sorted(tags)}
            if state.get("mode") != KEY_MODE:
                state.clear()           # курсор служебной учётной записи (updatedAt и вложения) здесь не годится
            previous = state.get("scope") if isinstance(state.get("scope"), dict) else {}
            if previous.get("tags") != scope["tags"] or set(scope["lists"]) - set(previous.get("lists") or []):
                state.pop("since", None)    # новый список или другие метки — задачи берутся с начала
            state.update(mode=KEY_MODE, scope=scope)
            params: dict[str, Any] = {"hasAttachments": "1", "limit": PAGE_SIZE}
            if chosen:
                params["listId"] = chosen["id"]
            if len(tags) == 1:
                params["tags"] = tags[0]   # у «По Делу» метки через запятую — все сразу; «одна из» — отбором здесь
            if state.get("since"):
                params["updatedSince"] = state["since"]
            mark = bool(self.config.get("mark_processed", True))
            if mark and SCOPE_COMMENT not in scopes:
                mark = False
                notes.append(f"у ключа нет области {SCOPE_LABELS[SCOPE_COMMENT]} — задачи не отмечаются")
            names = UploaderNames(api, SCOPE_USERS in scopes)
            silent: set[str] = set()       # списки, где владелец отключил комментарии
            titles: dict[str, str] = {}
            done: set[str] = set()
            try:
                for _page in range(MAX_PAGES):
                    page = api.get("tasks", params=params)
                    for task in page.get("items") or []:
                        if not isinstance(task, dict) or not task.get("id"):
                            continue
                        task_id, list_id = str(task["id"]), str(task.get("listId") or "")
                        if task.get("listTitle"):
                            titles[list_id] = str(task["listTitle"])
                        wanted = not tags or set(tags) & set(task.get("tags") or [])
                        if wanted and task_id not in done:
                            done.add(task_id)
                            counters["tasks"] += 1
                            lines = self._key_task_files(ctx, api, task, names, counters, details)
                            if lines and mark and list_id not in silent:
                                self._key_comment(api, task, lines, counters, comment_errors, notes, silent, titles)
                        moment = parse_time(task.get("activityAt"))
                        if moment is not None and (parse_time(state.get("since")) or moment) <= moment:
                            state["since"] = iso(moment)    # задача обработана — следующий запуск начнёт с неё
                    cursor = page.get("nextCursor")
                    if not cursor:
                        break
                    params["cursor"] = cursor
                else:
                    notes.append(f"просмотрено {MAX_PAGES * PAGE_SIZE} задач — остальные заберёт следующий запуск")
            except IntegrationError as exc:
                if exc.code != "rate_limited":
                    raise
                stopped = exc.message(self.detailed)
        if chosen:
            label = f"Список {list_label({**chosen, 'title': titles.get(chosen['id']) or chosen.get('title')})}"
        else:
            label = f"Списки ключа «{api.key_name}» ({len(list_ids)})"
        message = (f"{label}: задач с новыми вложениями {counters['candidates']}, файлов во «Входящие» "
                   f"{counters['added']}, уже забранных {counters['seen']}")
        if counters["skipped_type"] or counters["too_large"]:
            message += f", пропущено {counters['skipped_type'] + counters['too_large']} (не данные или слишком большие)"
        result_details: dict[str, Any] = {
            "mode": KEY_MODE, "lists": [{"id": i, "title": titles.get(i)} for i in scope["lists"]],
            "files": details[:MAX_DETAILS]}
        if notes:
            result_details["notes"] = notes[:MAX_DETAILS]
        if stopped:
            result_details["stopped"] = stopped
            return RunResult.partial(f"{message}; остановлено: {stopped} — следующий запуск продолжит с места "
                                     "остановки", stopped, counters=counters, details=result_details)
        if comment_errors:
            result_details["comment_errors"] = comment_errors[:10]
            return RunResult.partial(message + f"; не удалось отметить задач: {counters['comment_errors']}",
                                     comment_errors[0], counters=counters, details=result_details)
        if counters["comments_disabled"]:
            message += f"; не отмечено задач: {counters['comments_disabled']} (комментарии выключены)"
        return RunResult.ok(message, counters=counters, details=result_details)

    def _key_task_files(self, ctx: RunContext, api: KeyApi, task: dict, names: UploaderNames, counters: dict,
                        details: list) -> list[str]:
        """Новые файлы задачи → «Входящие» (уже забранные — по sha256 из списка файлов, без скачивания); строки
        комментария-отметки."""
        task_id = str(task["id"])
        path = f"tasks/{quote(task_id, safe='')}/attachments"
        lines: list[str] = []
        for attachment in api.get(path).get("items") or []:
            if not isinstance(attachment, dict) or not attachment.get("id"):
                continue
            att_id, name = str(attachment["id"]), str(attachment.get("fileName") or "файл")
            counters["files"] += 1
            if not is_data_file(name):
                counters["skipped_type"] += 1
                continue
            if int(attachment.get("size") or 0) > inbox_limit():
                counters["too_large"] += 1
                details.append({"file": name, "task": task.get("title"), "status": "пропущен: больше INBOX_MAX_MB"})
                continue
            listed = str(attachment.get("sha256") or "").lower()
            if listed and ctx.inbox.seen(f"podelu:{task_id}:{att_id}:{listed}") is not None:
                counters["seen"] += 1
                continue
            content = api.request("GET", f"{path}/{quote(att_id, safe='')}/content").content
            digest = sha256(content)
            ref = f"podelu:{task_id}:{att_id}:{digest}"
            if digest != listed and ctx.inbox.seen(ref) is not None:
                counters["seen"] += 1
                continue
            author = names.get(attachment.get("uploadedBy"), task.get("createdBy"))
            item = ctx.inbox.add(content, name, source_ref=ref, content_type=str(attachment.get("mimeType") or ""),
                                 note=task_note(task.get("title"), author))
            counters["added"] += 1
            counters[f"status_{item.status}"] = counters.get(f"status_{item.status}", 0) + 1
            status = status_text(item)
            lines.append(f"Файл «{name}» принят в «Дашборды»: {status}")
            details.append({"item": item.id, "file": name, "status": status})
        if lines:
            counters["candidates"] += 1
            if settings.public_url:
                lines.append(f"Входящие данные: {settings.public_url}/inbox")
        return lines

    def _key_comment(self, api: KeyApi, task: dict, lines: list[str], counters: dict, errors: list[str],
                     notes: list[str], silent: set[str], titles: dict[str, str]) -> None:
        """Отметка задачи комментарием системы (tasks.comment; POST без повтора). Владелец списка отключил
        комментарии (403 comments_disabled) — предупреждение, задачи этого списка дальше не отмечаются."""
        task_id, list_id = str(task["id"]), str(task.get("listId") or "")
        try:
            api.post(f"tasks/{quote(task_id, safe='')}/comments", {"text": "\n".join(lines)[:COMMENT_LIMIT]})
            counters["comments"] += 1
        except IntegrationError as exc:
            if exc.code == "rate_limited":
                raise
            if exc.code == "comments_disabled":
                counters["comments_disabled"] += 1
                silent.add(list_id)
                where = f"«{titles[list_id]}»" if titles.get(list_id) else list_id
                notes.append(f"в списке {where} владелец отключил комментарии — задачи не отмечаются")
                return
            counters["comment_errors"] += 1
            errors.append(f"«{task.get('title')}»: {exc.message(self.detailed)}")

    def pull_session(self, ctx: RunContext) -> RunResult:
        ref = (self.config.get("data_list") or "").strip()
        if not ref:
            raise IntegrationError("Не выбран список задач с данными — укажите его в настройках подключения (доступные "
                                   "списки — в результате проверки)", code="config")
        tags = [t for t in self.config.get("data_tags") or [] if t]
        counters = {"tasks": 0, "candidates": 0, "files": 0, "added": 0, "seen": 0, "skipped_type": 0,
                    "too_large": 0, "comments": 0, "comment_errors": 0}
        details: list[dict] = []
        comment_errors: list[str] = []
        with self.session() as s:
            chosen = find_list(s.get_json("api/lists", kind=list), ref)
            if chosen is None:
                raise IntegrationError(f"Список «{ref}» в «{TITLE}» не найден или недоступен — служебная учётная "
                                       "запись должна быть участником списка", code="not_found")
            state = ctx.state
            for stale in ("mode", "scope"):     # курсор режима ключа (activityAt) здесь не годится
                state.pop(stale, None)
            if state.get("list") != chosen["id"]:
                state.pop("since", None)
                state.pop("tasks", None)
            since = parse_time(state.get("since"))
            known: dict = state.get("tasks") if isinstance(state.get("tasks"), dict) else {}
            tasks = self._tasks(s, chosen["id"], tags)
            counters["tasks"] = len(tasks)
            newest = since
            tracked: dict = {}
            names: dict[str, str] = {}
            mark = bool(self.config.get("mark_processed", True)) and comments_allowed(chosen)
            for task in tasks:
                updated = parse_time(task.get("updatedAt"))
                if updated is not None and (newest is None or updated > newest):
                    newest = updated
                count = int(task.get("attachmentCount") or 0)
                if count <= 0:
                    continue
                previous = known.get(task["id"]) if isinstance(known.get(task["id"]), dict) else {}
                changed = previous.get("n") != count or since is None or updated is None or updated > since
                if not changed:
                    tracked[task["id"]] = previous
                    continue
                counters["candidates"] += 1
                files = dict(previous.get("files") or {})
                lines = self._task_files(ctx, s, task, files, names, counters, details)
                tracked[task["id"]] = {"n": count, "files": files}
                if lines and mark:
                    try:
                        s.post_json(f"api/tasks/{task['id']}/comments", {"text": "\n".join(lines)}, expect=(200, 201))
                        counters["comments"] += 1
                    except IntegrationError as exc:
                        counters["comment_errors"] += 1
                        comment_errors.append(f"«{task.get('title')}»: {exc.message(self.detailed)}")
        state["list"] = chosen["id"]
        if newest is not None:
            state["since"] = newest.isoformat() + "Z"
        state["tasks"] = dict(list(tracked.items())[:MAX_TRACKED_TASKS])
        message = (f"Список «{chosen.get('title')}»: задач с новыми вложениями {counters['candidates']}, файлов во "
                   f"«Входящие» {counters['added']}, уже забранных {counters['seen']}")
        if counters["skipped_type"] or counters["too_large"]:
            message += f", пропущено {counters['skipped_type'] + counters['too_large']} (не данные или слишком большие)"
        result_details: dict[str, Any] = {"mode": SESSION_MODE,
                                          "list": {"id": chosen["id"], "title": chosen.get("title")},
                                          "files": details[:MAX_DETAILS]}
        if self.config.get("mark_processed", True) and not mark:
            result_details["notes"] = [f"в списке «{chosen.get('title')}» выключены комментарии — задачи не "
                                       "отмечаются"]
        if comment_errors:
            result_details["comment_errors"] = comment_errors[:10]
            return RunResult.partial(message + f"; не удалось отметить задач: {counters['comment_errors']}",
                                     comment_errors[0], counters=counters, details=result_details)
        return RunResult.ok(message, counters=counters, details=result_details)

    def _tasks(self, s: PartnerSession, list_id: str, tags: list[str]) -> list[dict]:
        params: dict = {"listId": list_id, "pageSize": PAGE_SIZE, "sort": "updatedAt", "order": "desc"}
        if tags:
            params["tags"] = ",".join(tags)
        tasks: list[dict] = []
        for _page in range(MAX_PAGES):
            page = s.get_json("api/v2/tasks", params=params)
            tasks.extend(t for t in page.get("items") or [] if isinstance(t, dict) and t.get("id"))
            cursor = page.get("nextCursor")
            if not page.get("hasMore") or not cursor:
                break
            params["cursor"] = cursor
        return tasks

    def _task_files(self, ctx: RunContext, s: PartnerSession, task: dict, files: dict, names: dict, counters: dict,
                    details: list) -> list[str]:
        """Новые файлы задачи и её результатов → «Входящие»; files — {вложение: sha256} уже забранных."""
        task_id = task["id"]
        attachments = [a for a in s.get_json(f"api/tasks/{task_id}/attachments", kind=list) if isinstance(a, dict)]
        for result in s.get_json(f"api/tasks/{task_id}/results", kind=list):
            if isinstance(result, dict):
                attachments += [a for a in result.get("attachments") or [] if isinstance(a, dict)]
        lines: list[str] = []
        seen_ids: set[str] = set()
        for attachment in attachments:
            att_id, name = str(attachment.get("id") or ""), str(attachment.get("fileName") or "файл")
            if not att_id or att_id in seen_ids:
                continue
            seen_ids.add(att_id)
            counters["files"] += 1
            if not is_data_file(name):
                counters["skipped_type"] += 1
                continue
            if int(attachment.get("size") or 0) > inbox_limit():
                counters["too_large"] += 1
                details.append({"file": name, "task": task.get("title"), "status": "пропущен: больше INBOX_MAX_MB"})
                continue
            known = files.get(att_id)
            if known and ctx.inbox.seen(f"podelu:{task_id}:{att_id}:{known}") is not None:
                counters["seen"] += 1
                continue
            content = s.request("GET", f"api/tasks/{task_id}/attachments/{att_id}/content").content
            digest = files[att_id] = sha256(content)
            ref = f"podelu:{task_id}:{att_id}:{digest}"
            if ctx.inbox.seen(ref) is not None:
                counters["seen"] += 1
                continue
            author = self._name(s, attachment.get("uploadedBy") or task.get("createdBy"), names)
            item = ctx.inbox.add(content, name, source_ref=ref, content_type=str(attachment.get("mimeType") or ""),
                                 note=task_note(task.get("title"), author))
            counters["added"] += 1
            counters[f"status_{item.status}"] = counters.get(f"status_{item.status}", 0) + 1
            status = status_text(item)
            lines.append(f"Файл «{name}» принят в «Дашборды»: {status}")
            details.append({"item": item.id, "file": name, "status": status})
        if lines and settings.public_url:
            lines.append(f"Входящие данные: {settings.public_url}/inbox")
        return lines

    def _name(self, s: PartnerSession, user_id: Any, names: dict) -> str:
        """Имя сотрудника «По Делу» по id — для пояснения элемента входящих (кто положил файл)."""
        key = str(user_id or "")
        if not key:
            return ""
        if key not in names:
            try:
                user = s.get_json(f"api/users/{key}")
                names[key] = str(user.get("name") or user.get("email") or key)
            except IntegrationError:
                names[key] = key
        return names[key]

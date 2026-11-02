"""«Почтовый ящик (Exchange)»: вложения писем выделенной папки → «Входящие» (ADR-0011, таблица «Коннекторы 0.4.0»).

Способы подключения (mailbox.py): Exchange Server по EWS (exchangelib, NTLM или Basic), Microsoft 365 через
Microsoft Graph (приложение: тенант, client id, секрет; права Mail.ReadWrite на ящик), IMAP — запасной путь для
любого сервера (стандартная библиотека).

«Забрать вложения»: письма папки от разрешённых отправителей (email или домен; по заголовку From) — непрочитанные,
если включено «Помечать прочитанными», иначе новые после курсора (ctx.state); файлы данных (Excel, CSV, JSON) →
«Входящие» с source_ref exchange:<Message-ID>:<имя вложения>:<sha256> (повтор — ctx.inbox.seen — не кладётся);
набор — по правилу «шаблон темы = набор» или распознаётся по файлу. Обработанное письмо помечается прочитанным
и/или переносится в папку; письма других отправителей не трогаются.
"""
from __future__ import annotations

import re
from typing import Any

from ...core.errors import AppError, ValidationFailed
from ...services import inbox_datasets
from ..base import Action, CheckResult, Connector, Field, Option, RunContext, RunResult, register
from ..http import IntegrationError, allowed_hosts, allowed_hosts_env, host_allowed
from .common import is_data_file, matches, rule_lines, secret_url, sha256, status_text
from .mailbox import GRAPH_URL, LOGIN_URL, EwsBox, GraphBox, ImapBox, Mail, Mailbox

TITLE = "Почтовый ящик (Exchange)"
MODES = {"ews": "Exchange Server (EWS)", "graph": "Microsoft 365 (Graph)", "imap": "IMAP"}
HOST = re.compile(r"^(?=.{1,253}$)[A-Za-z0-9](?:[A-Za-z0-9-]{0,62}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,62}"
                  r"[A-Za-z0-9])?)*$")
SENDER = re.compile(r"^(?:[^@\s]+@)?[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
MAX_DETAILS = 50
MAX_PROCESS = 100        # писем от разрешённых отправителей за запуск
# Ошибки связи и доступа — общие для ящика: на них запуск останавливается; прочие — ошибка одного письма
SYSTEMIC = ("auth", "connect", "connect_timeout", "read_timeout", "tls", "session", "forbidden", "rate_limited",
            "unavailable", "dependency_missing")


def senders(values: list[str] | None) -> list[str]:
    """Разрешённые отправители: email или домен («company.ru», «@company.ru», «*.company.ru» — домен и поддомены)."""
    out = []
    for value in values or []:
        text = value.strip().lower()
        text = text[1:] if text.startswith("@") else text
        text = text[2:] if text.startswith("*.") else text
        if text:
            out.append(text)
    return out


def sender_allowed(sender: str, allowed: list[str]) -> bool:
    address = (sender or "").strip().lower()
    if "@" not in address:
        return False
    domain = address.rsplit("@", 1)[1]
    return any(address == a if "@" in a else (domain == a or domain.endswith("." + a)) for a in allowed)


def subject_rules(text: str | None) -> list[tuple[str, str]]:
    """«шаблон темы = набор» по строке → [(шаблон, ключ набора)]; * — любые символы, без учёта регистра."""
    try:
        lines = rule_lines(text)
    except ValueError as exc:
        raise ValidationFailed(f"Тема → набор, строка {exc.args[0]}: нужно «шаблон темы = набор»",
                               fields={"config.subject_rules": "Неверная строка"}) from None
    out = []
    for number, pattern, dataset in lines:
        if inbox_datasets.get(dataset) is None:
            known = ", ".join(d.key for d in inbox_datasets.all_datasets())
            raise ValidationFailed(f"Тема → набор, строка {number}: набора «{dataset}» нет (наборы: {known})",
                                   fields={"config.subject_rules": "Неизвестный набор"})
        out.append((pattern if any(ch in pattern for ch in "*?[") else f"*{pattern}*", dataset))
    return out


@register
class ExchangeConnector(Connector):
    kind = "exchange"
    title = TITLE
    description = ("Вложения писем выделенной папки почтового ящика → «Входящие» (отправитель из разрешённого "
                   "списка); письмо помечается прочитанным и переносится. Exchange Server (EWS), Microsoft 365 "
                   "(Graph) или IMAP")
    fields = (
        Field("mode", "Подключение", "select", required=True, default="imap",
              options=(Option("ews", MODES["ews"]), Option("graph", MODES["graph"]), Option("imap", MODES["imap"])),
              hint="EWS — свой Exchange Server; Microsoft Graph — Microsoft 365; IMAP — любой почтовый сервер"),
        # EWS
        Field("ews_url", "Адрес EWS", "url", required=True, show_if={"mode": ("ews",)},
              placeholder="https://mail.company.ru/EWS/Exchange.asmx"),
        Field("ews_auth", "Проверка подлинности", "select", default="ntlm", show_if={"mode": ("ews",)},
              options=(Option("ntlm", "NTLM"), Option("basic", "Basic"))),
        # Graph
        Field("tenant", "Тенант (Directory ID)", required=True, show_if={"mode": ("graph",)},
              placeholder="company.onmicrosoft.com"),
        Field("client_id", "Идентификатор приложения (Client ID)", required=True, show_if={"mode": ("graph",)}),
        Field("client_secret", "Секрет приложения", "password", required=True, secret=True,
              show_if={"mode": ("graph",)},
              hint="Права приложения Mail.ReadWrite; доступ лучше ограничить этим ящиком (ApplicationAccessPolicy)"),
        Field("graph_url", "Адрес Microsoft Graph", "url", placeholder=GRAPH_URL, show_if={"mode": ("graph",)},
              hint="Необязательно: другой адрес — для национальных облаков Microsoft"),
        Field("login_url", "Адрес входа Microsoft", "url", placeholder=LOGIN_URL, show_if={"mode": ("graph",)}),
        # IMAP
        Field("imap_host", "Сервер IMAP", required=True, show_if={"mode": ("imap",)}, placeholder="imap.company.ru"),
        Field("imap_port", "Порт", "int", default=993, min=1, max=65535, show_if={"mode": ("imap",)}),
        Field("imap_ssl", "SSL/TLS", "bool", default=True, show_if={"mode": ("imap",)},
              hint="Выключено — обычное соединение с переходом на STARTTLS, если сервер его поддерживает"),
        # EWS и IMAP
        Field("username", "Учётная запись", required=True, show_if={"mode": ("ews", "imap")},
              placeholder="DOMAIN\\dashboards или data@company.ru"),
        Field("password", "Пароль", "password", required=True, secret=True, show_if={"mode": ("ews", "imap")}),
        Field("mailbox", "Почтовый ящик", show_if={"mode": ("ews", "graph")}, placeholder="data@company.ru",
              hint="EWS — пусто, если ящик принадлежит учётной записи; Microsoft Graph — обязательно"),
        Field("verify_tls", "Проверять TLS-сертификат", "bool", default=True,
              hint="Выключите только для самоподписанного или корпоративного сертификата"),
        # Письма
        Field("folder", "Папка", default="Входящие", placeholder="Входящие/Выгрузки",
              hint="Папка с письмами; вложенная — через «/»"),
        Field("allowed_senders", "Разрешённые отправители", "list", required=True,
              placeholder="1c@company.ru, company.ru",
              hint="Email или домен (вместе с поддоменами); письма других отправителей не трогаются. Отправитель "
                   "берётся из заголовка From — на почтовом сервере должны работать SPF, DKIM и DMARC"),
        Field("mark_read", "Помечать прочитанными", "bool", default=True,
              hint="Забираются непрочитанные письма; выключено — новые письма после прошлого запуска"),
        Field("move_to", "Перенести в папку", placeholder="Входящие/Обработано",
              hint="Необязательно: папка для обработанных писем"),
        Field("subject_rules", "Тема → набор", "text", placeholder="Недельный отчёт* = tp-weekly\n*ЗУП* = hr-months",
              hint="Необязательно: по строке «шаблон темы = набор» (* — любые символы); без правила набор "
                   "распознаётся по файлу"),
        # Секрет привязан к адресу, куда он уходит, — у каждого способа подключения свой (поле не показывается)
        Field("endpoint", "Секрет привязан к адресу", show_if={"mode": ()}),
    )
    actions = (Action("fetch", "Забрать вложения",
                      "Вложения писем разрешённых отправителей — во «Входящие»; письмо помечается прочитанным и/или "
                      "переносится"),)
    url_field = "endpoint"

    @classmethod
    def validate_config(cls, config: dict) -> dict:
        out = super().validate_config({k: v for k, v in (config or {}).items() if k != "endpoint"})
        mode = out["mode"]
        if mode == "graph" and not out.get("mailbox"):
            raise ValidationFailed("Обязательное поле: Почтовый ящик", fields={"config.mailbox": "Обязательное поле"})
        if mode == "imap":
            host = (out.get("imap_host") or "").strip().lower()
            if not HOST.match(host):
                raise ValidationFailed("Сервер IMAP — имя узла или IP-адрес без схемы и порта",
                                       fields={"config.imap_host": "Недопустимое значение"})
            if not host_allowed(host, allowed_hosts(cls.kind)):
                raise ValidationFailed(f"Подключение к {host} запрещено настройками сервера "
                                       f"({allowed_hosts_env(cls.kind)})", code="host_not_allowed",
                                       fields={"config.imap_host": "Узел не разрешён"})
            out["imap_host"] = host
        bad = [s for s in senders(out.get("allowed_senders")) if not SENDER.match(s)]
        if bad:
            raise ValidationFailed(f"Разрешённые отправители: «{bad[0]}» — нужен email или домен",
                                   fields={"config.allowed_senders": "Недопустимое значение"})
        subject_rules(out.get("subject_rules"))
        out["endpoint"] = cls.endpoint(out)
        return out

    @staticmethod
    def endpoint(config: dict) -> str:
        mode = config.get("mode")
        if mode == "ews":
            return config.get("ews_url") or ""
        if mode == "graph":
            login = (config.get("login_url") or LOGIN_URL).rstrip("/")
            return secret_url(f"{login}/{config.get('tenant') or ''}", config.get("graph_url") or GRAPH_URL)
        scheme = "imaps" if config.get("imap_ssl", True) else "imap"
        return f"{scheme}://{config.get('imap_host') or ''}:{config.get('imap_port') or 993}"

    # --- ящик
    def box(self) -> Mailbox:
        c, mode = self.config, self.config.get("mode")
        verify = bool(c.get("verify_tls", True))
        folder = c.get("folder") or "Входящие"
        if mode == "graph":
            return GraphBox(tenant=c.get("tenant") or "", client_id=c.get("client_id") or "",
                            client_secret=self.secrets.get("client_secret") or "", mailbox=c.get("mailbox") or "",
                            folder=folder, graph_url=c.get("graph_url"), login_url=c.get("login_url"), verify=verify,
                            detailed=self.detailed)
        if mode == "ews":
            mailbox = c.get("mailbox") or (c.get("username") if "@" in (c.get("username") or "") else "")
            if not mailbox:
                raise IntegrationError("Укажите почтовый ящик (учётная запись — не адрес почты)", code="config")
            return EwsBox(url=c.get("ews_url") or "", username=c.get("username") or "",
                          password=self.secrets.get("password") or "", mailbox=mailbox, folder=folder,
                          auth=c.get("ews_auth") or "ntlm", verify=verify)
        return ImapBox(host=c.get("imap_host") or "", port=int(c.get("imap_port") or 993),
                       use_ssl=bool(c.get("imap_ssl", True)), login=c.get("username") or "",
                       password=self.secrets.get("password") or "", folder=folder, verify=verify)

    @property
    def folder(self) -> str:
        return self.config.get("folder") or "Входящие"

    # --- проверка
    def check(self) -> CheckResult:
        mode = self.config.get("mode")
        with self.box() as box:
            total, unread = box.stats()
            move_to = self.config.get("move_to")
            if move_to and not box.folder_exists(move_to):
                return CheckResult(False, f"Ящик доступен, но папки «{move_to}» для обработанных писем нет — создайте "
                                          "её или исправьте настройку", {"total": total, "unread": unread})
        details = {"mode": mode, "folder": self.folder, "total": total, "unread": unread}
        return CheckResult(True, f"Ящик доступен ({MODES[mode]}): в папке «{self.folder}» писем {total}, "
                                 f"непрочитанных {unread}", details)

    # --- запуск
    def run(self, action: str, ctx: RunContext) -> RunResult:
        self.action(action)
        allowed = senders(self.config.get("allowed_senders"))
        rules = subject_rules(self.config.get("subject_rules"))
        unread_only = bool(self.config.get("mark_read", True))
        move_to = self.config.get("move_to") or ""
        fingerprint = f"{self.config.get('endpoint')}|{self.folder}"
        state = ctx.state
        cursor = state.get("cursor") if state.get("source") == fingerprint else None
        counters = {"messages": 0, "processed": 0, "skipped_sender": 0, "files": 0, "added": 0, "seen": 0,
                    "skipped_type": 0, "too_large": 0, "errors": 0}
        details: list[dict] = []
        errors: list[str] = []
        with self.box() as box:
            # Непрочитанные берутся все: письмо, перенесённое в папку позже, имеет старое время получения
            mails = box.messages(unread_only=unread_only, cursor=None if unread_only else cursor)
            # Курсор продвигается только до первого письма с ошибкой и до предела обработки: дальше — в следующий раз
            done: list[Mail] = []
            advancing = True
            for mail in mails:
                if counters["processed"] >= MAX_PROCESS:
                    break
                counters["messages"] += 1
                if not sender_allowed(mail.sender, allowed):
                    counters["skipped_sender"] += 1      # чужие письма не трогаются, курсор проходит мимо
                    if advancing:
                        done.append(mail)
                    continue
                dataset = next((d for pattern, d in rules if matches([pattern], mail.subject)), None)
                try:
                    self._take(ctx, box, mail, dataset, counters, details)
                except (AppError, IntegrationError) as exc:
                    if isinstance(exc, IntegrationError) and exc.code in SYSTEMIC:
                        raise            # связь с ящиком потеряна — весь запуск «ошибка», повтор в следующий раз
                    counters["errors"] += 1
                    text = exc.detail if isinstance(exc, AppError) else exc.message(self.detailed)
                    errors.append(f"письмо «{mail.subject}» от {mail.sender}: {text}")
                    advancing = False    # письмо не отмечается — повтор в следующий раз
                    continue
                if unread_only:
                    box.mark_read(mail)
                if move_to:
                    box.move(mail, move_to)
                counters["processed"] += 1
                if advancing:
                    done.append(mail)
            new_cursor = box.cursor(done, cursor)
        state["source"] = fingerprint
        if new_cursor is not None:
            state["cursor"] = new_cursor
        message = (f"Писем от разрешённых отправителей {counters['processed']}, файлов во «Входящие» "
                   f"{counters['added']}, уже забранных {counters['seen']}")
        if counters["skipped_sender"]:
            message += f"; писем других отправителей (не тронуты) {counters['skipped_sender']}"
        if counters["skipped_type"] or counters["too_large"]:
            message += f"; пропущено вложений {counters['skipped_type'] + counters['too_large']} (не данные или " \
                       "слишком большие)"
        result_details: dict[str, Any] = {"mode": self.config.get("mode"), "folder": self.folder,
                                          "files": details[:MAX_DETAILS]}
        if errors:
            result_details["errors"] = errors[:10]
            return RunResult.partial(message + f"; писем с ошибкой {counters['errors']}", errors[0],
                                     counters=counters, details=result_details)
        return RunResult.ok(message, counters=counters, details=result_details)

    def _take(self, ctx: RunContext, box: Mailbox, mail: Mail, dataset: str | None, counters: dict,
              details: list) -> None:
        reference = mail.message_id or mail.key
        for attachment in box.attachments(mail):
            counters["files"] += 1
            if not is_data_file(attachment.name):
                counters["skipped_type"] += 1
                continue
            if attachment.content is None:
                counters["too_large"] += 1
                details.append({"file": attachment.name, "subject": mail.subject, "sender": mail.sender,
                                "status": "пропущен: больше INBOX_MAX_MB"})
                continue
            ref = f"exchange:{reference}:{attachment.name}:{sha256(attachment.content)}"
            if ctx.inbox.seen(ref) is not None:
                counters["seen"] += 1
                continue
            item = ctx.inbox.add(attachment.content, attachment.name, dataset=dataset, source_ref=ref,
                                 content_type=attachment.content_type)
            counters["added"] += 1
            counters[f"status_{item.status}"] = counters.get(f"status_{item.status}", 0) + 1
            details.append({"item": item.id, "file": attachment.name, "subject": mail.subject, "sender": mail.sender,
                            "received": mail.received, "status": status_text(item)})

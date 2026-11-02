"""Bitrix24: сделки CRM → показатели продаж сквозного отчёта (ADR-0011).

Подключение — входящий вебхук REST (https://портал/rest/<пользователь>/<код>/). Код доступа — в самом адресе,
поэтому вебхук хранится секретом (зашифрован, в сообщениях об ошибках заменяется на «…»). Адрес портала —
отдельная настройка: к нему привязан вебхук (сменили адрес — вебхук вводится заново) и по нему проверяется
BITRIX24_ALLOWED_HOSTS; вебхук должен быть выдан этим же порталом.

«Обновить показатели продаж»: crm.deal.list с фильтром по CLOSEDATE, STAGE_ID (или STAGE_SEMANTIC_ID = S —
«успешно»), CATEGORY_ID и списком полей select, постранично по 50 (start / next) с паузой между страницами;
на QUERY_LIMIT_EXCEEDED — пауза и повтор. Ответственный (ASSIGNED_BY_ID) → подразделение: по email сотрудника
(user.get → наш пользователь с тем же email) или по отделу Bitrix24 (user.get → UF_DEPARTMENT → соответствие
отделов или название отдела из department.get); явное соответствие ответственных — сильнее.
Пишутся (каждый — если задан ключ): выручка — сумма OPPORTUNITY выигранных сделок месяца (финансовый),
число выигранных сделок (операционный), воронка — сумма открытых сделок (финансовый; снимок на момент запуска —
только в текущий месяц).
"""
from __future__ import annotations

import re
import time
from collections import Counter, defaultdict
from urllib.parse import urlsplit

from ...core.errors import ValidationFailed
from ..base import Action, CheckResult, Connector, Field, Option, RunContext, RunResult, register
from ..http import HttpClient, IntegrationError
from . import _metrics as metrics

PAGE = 50                 # Bitrix24 отдаёт списки по 50
PAGE_PAUSE = 0.5          # пауза между страницами: не больше 2 запросов в секунду
LIMIT_ATTEMPTS = 4        # повторов на QUERY_LIMIT_EXCEEDED (после повторов 429/503 HTTP-клиента)
LIMIT_PAUSE = 2.0
MAX_ITEMS = 50000
IDS_PER_CALL = 50
EXPECT = (200, 400, 401, 403, 404, 429, 500, 503)
DEAL_SELECT = ["ID", "OPPORTUNITY", "CURRENCY_ID", "STAGE_ID", "CATEGORY_ID", "ASSIGNED_BY_ID", "CLOSEDATE", "CLOSED"]
WEBHOOK = re.compile(r"^(?P<prefix>.*?/)?rest/(?P<user>\d+)/(?P<code>[A-Za-z0-9_]+)/?$")
SHORT_WEBHOOK = re.compile(r"^/?(?P<user>\d+)/(?P<code>[A-Za-z0-9_]+)/?$")
AMOUNT_UNITS = {"rub": (1.0, "₽"), "thousand": (0.001, "тыс. ₽"), "million": (0.000001, "млн ₽")}
AUTH_ERRORS = {"expired_token", "invalid_token", "invalid_credentials", "no_auth_found", "wrong_auth_type",
               "authorization_error", "password_expired"}
SCOPE_ERRORS = {"insufficient_scope", "access_denied", "error_access_denied", "user_access_error"}
METHOD_ERRORS = {"error_method_not_found", "method_not_found"}

sleep = time.sleep  # подменяется в тестах


class Bitrix:
    """Вызовы REST Bitrix24 через входящий вебхук: ошибки Bitrix24 — понятным текстом, без кода вебхука."""

    def __init__(self, client: HttpClient, base: str, secrets: tuple[str, ...]):
        self.client = client
        self.base = base
        self.secrets = tuple(s for s in secrets if s)

    def scrub(self, text: str) -> str:
        for secret in self.secrets:
            text = text.replace(secret, "…")
        return text

    def clean(self, exc: IntegrationError) -> IntegrationError:
        return IntegrationError(self.scrub(exc.detail), code=exc.code, short=self.scrub(exc.short), status=exc.status)

    def call(self, method: str, params: dict | None = None) -> dict:
        for attempt in range(1, LIMIT_ATTEMPTS + 1):
            try:
                resp = self.client.request("POST", f"{self.base}{method}.json", json=params or {}, expect=EXPECT)
            except IntegrationError as exc:
                raise self.clean(exc) from None
            try:
                data = resp.json()
            except (ValueError, UnicodeDecodeError):
                data = None
            error = str(data.get("error") or "") if isinstance(data, dict) else ""
            if error.upper() == "QUERY_LIMIT_EXCEEDED" or (resp.status in (429, 503) and not error):
                if attempt < LIMIT_ATTEMPTS:
                    sleep(LIMIT_PAUSE * attempt)
                    continue
                raise IntegrationError("Bitrix24 ограничил частоту запросов (QUERY_LIMIT_EXCEEDED) — запуск прерван, "
                                       "повторите позже", code="rate_limited",
                                       short="Bitrix24 ограничил частоту запросов — повторите позже",
                                       status=resp.status)
            if error or resp.status != 200:
                raise self.error(method, resp.status, error, str((data or {}).get("error_description") or "")
                                 if isinstance(data, dict) else "")
            if not isinstance(data, dict) or "result" not in data:
                raise IntegrationError(f"Bitrix24 вернул неожиданный ответ на {method} — проверьте адрес портала и "
                                       "вебхук; возможно, отвечает страница входа или прокси", code="bad_response",
                                       short="Bitrix24 вернул неожиданный ответ")
            return data
        raise AssertionError("unreachable")  # pragma: no cover

    def error(self, method: str, status: int, error: str, description: str) -> IntegrationError:
        text = self.scrub(f"{error}: {description}" if description else error)[:300]
        key = error.lower()
        scope = key in SCOPE_ERRORS or (status == 403 and key not in AUTH_ERRORS)
        if scope:
            return IntegrationError(f"У вебхука нет прав на {method} ({text or status}) — добавьте права «CRM» и "
                                    "«Пользователи» в настройках входящего вебхука", code="forbidden",
                                    short="У вебхука Bitrix24 недостаточно прав", status=status)
        if key in AUTH_ERRORS or status == 401:
            return IntegrationError(f"Bitrix24 отклонил вебхук ({text or status}) — вебхук удалили, выпустили заново "
                                    "или он выдан другим порталом: введите адрес вебхука заново", code="auth",
                                    short="Bitrix24 отклонил вебхук подключения", status=status)
        if key in METHOD_ERRORS or status == 404:
            return IntegrationError(f"Метод {method} недоступен на портале ({text or status})", code="not_found",
                                    short=f"Bitrix24: метод {method} недоступен", status=status)
        return IntegrationError(f"Bitrix24 вернул ошибку на {method}: {text or status}", code="http_error",
                                short=f"Bitrix24 вернул ошибку ({status})", status=status)

    def items(self, method: str, params: dict | None = None) -> list[dict]:
        """Список постранично: start = 0, 50, … пока Bitrix24 возвращает next."""
        out: list[dict] = []
        start = 0
        while True:
            data = self.call(method, {**(params or {}), "start": start})
            result = data["result"]
            if isinstance(result, dict) and isinstance(result.get("items"), list):
                result = result["items"]
            if not isinstance(result, list):
                raise IntegrationError(f"Bitrix24 вернул на {method} не список", code="bad_response")
            out.extend(r for r in result if isinstance(r, dict))
            following = data.get("next")
            if following in (None, "") or not result:
                return out
            if len(out) >= MAX_ITEMS:
                raise IntegrationError(f"{method}: больше {MAX_ITEMS} записей — сузьте фильтр (воронки)",
                                       code="too_large")
            start = int(following)
            sleep(PAGE_PAUSE)


def _ids(values) -> list[str]:
    return sorted({str(v).strip() for v in values if str(v or "").strip().isdigit()}, key=int)


def amount(value) -> float:
    try:
        return float(str(value or 0).replace(",", ".").replace(" ", ""))
    except ValueError:
        return 0.0


@register
class Bitrix24Connector(Connector):
    kind = "bitrix24"
    title = "Bitrix24"
    description = ("Сделки CRM → показатели продаж сквозного отчёта: выручка (сумма выигранных сделок за месяц), "
                   "число выигранных сделок и сумма открытых сделок — по подразделениям ответственных, помесячно. "
                   "Подключение — входящий вебхук REST с правами «CRM» и «Пользователи»; узлы ограничивает "
                   "BITRIX24_ALLOWED_HOSTS")
    url_field = "portal_url"
    fields = (
        Field("portal_url", "Адрес портала", "url", required=True, placeholder="https://company.bitrix24.ru",
              hint="Адрес портала Bitrix24 без пути; вебхук должен быть выдан этим порталом"),
        Field("webhook", "Входящий вебхук", "password", required=True, secret=True,
              placeholder="https://company.bitrix24.ru/rest/1/abcdef0123456789/",
              hint="Адрес вебхука целиком (Bitrix24 → Разработчикам → Другое → Входящий вебхук; права «CRM» и "
                   "«Пользователи», для сопоставления по отделам — и «Структура компании»). В адресе — код доступа, "
                   "поэтому вебхук хранится зашифрованным и не показывается"),
        Field("verify_tls", "Проверять сертификат", "bool", default=True,
              hint="Выключайте только для коробочного портала с самоподписанным сертификатом"),
        Field("categories", "Воронки (CATEGORY_ID)", "list", placeholder="0, 3",
              hint="Номера направлений сделок через запятую; основная воронка — 0; пусто — все воронки"),
        Field("won_stages", "Стадии «успешно»", "list", placeholder="WON, C3:WON",
              hint="STAGE_ID стадий, которые считаются выигранными, через запятую (у воронки N — с префиксом CN:); "
                   "пусто — все стадии с семантикой «успешно» (STAGE_SEMANTIC_ID = S)"),
        Field("mapping", "Подразделение сделки", "select", default="email",
              options=(Option("email", "По email ответственного — подразделение нашего сотрудника"),
                       Option("department", "По отделу ответственного в Bitrix24")),
              hint="Ответственный за сделку (ASSIGNED_BY_ID) → подразделение структуры. По email — сотрудник с тем "
                   "же email в «Структуре компании»; по отделу — первый отдел сотрудника в Bitrix24 (user.get)"),
        Field("department_map", "Соответствие отделов Bitrix24", "list", show_if={"mapping": ("department",)},
              placeholder="12 = SALES-1, Отдел продаж Москва = SALES-MSK",
              hint="Строки «ID или название отдела Bitrix24 = код или путь подразделения у нас»; отдел без "
                   "соответствия сопоставляется по названию или коду, если оно однозначно"),
        Field("user_map", "Соответствие ответственных", "list", placeholder="ivanov@company.ru = SALES-1, 15 = COMM",
              hint="Строки «email или ID пользователя Bitrix24 = код подразделения» — сильнее правил выше"),
        Field("revenue_indicator", "Показатель выручки", default="crm.revenue",
              hint="Ключ показателя: сумма OPPORTUNITY выигранных сделок, закрытых в месяце (класс «Финансовые»); "
                   "нет в каталоге — создаётся «Выручка по сделкам (Bitrix24)»; пусто — не писать"),
        Field("deals_indicator", "Показатель числа сделок", default="crm.deals_won",
              hint="Число выигранных сделок, закрытых в месяце; нет в каталоге — создаётся «Выиграно сделок "
                   "(Bitrix24)»; пусто — не писать"),
        Field("pipeline_indicator", "Показатель воронки", default="crm.pipeline",
              hint="Сумма открытых сделок (CLOSED = N) — снимок на момент запуска, пишется в текущий месяц; нет в "
                   "каталоге — создаётся «Открытые сделки (Bitrix24)»; пусто — не писать"),
        Field("amount_unit", "Единица сумм", "select", default="million",
              options=(Option("rub", "₽"), Option("thousand", "тыс. ₽"), Option("million", "млн ₽")),
              hint="В чём записывать выручку и воронку (как у показателей «Финансовые» каталога — обычно млн ₽). "
                   "Суммы в разных валютах складываются без пересчёта — об этом будет предупреждение"),
        metrics.months_field(),
        metrics.owner_field("commercial"),
    )
    actions = (
        Action("sales", "Обновить показатели продаж",
               "Сделки за текущий и прошлый месяц (или за настроенное число месяцев) → выручка, число выигранных "
               "сделок и воронка по подразделениям в сквозной отчёт"),
        Action("preview", "Проверить без записи", "Посчитать значения и показать план — без записи и без создания "
                                                  "показателей", schedulable=False),
    )

    @classmethod
    def validate_config(cls, config: dict) -> dict:
        out = super().validate_config(config)
        bad = [c for c in out.get("categories") or [] if not c.isdigit()]
        if bad:
            raise ValidationFailed(f"Воронка — номер направления (CATEGORY_ID): «{bad[0]}»",
                                   fields={"config.categories": "Только числа"})
        bad = [s for s in out.get("won_stages") or [] if not re.match(r"^[A-Za-z0-9_:\-]{1,50}$", s)]
        if bad:
            raise ValidationFailed(f"Стадия — STAGE_ID (латиница, цифры, «:», «_»): «{bad[0]}»",
                                   fields={"config.won_stages": "Некорректная стадия"})
        metrics.parse_pairs(out.get("department_map"), "config.department_map", "Соответствие отделов")
        metrics.parse_pairs(out.get("user_map"), "config.user_map", "Соответствие ответственных")
        keys = [out.get(k) for k in ("revenue_indicator", "deals_indicator", "pipeline_indicator")]
        if not any(keys):
            raise ValidationFailed("Задайте хотя бы один показатель: выручку, число сделок или воронку",
                                   fields={"config.revenue_indicator": "Нужен хотя бы один показатель"})
        for name in ("revenue_indicator", "deals_indicator", "pipeline_indicator"):
            if out.get(name) and not metrics.KEY_PATTERN.match(out[name]):
                raise ValidationFailed("Ключ показателя — латиница в нижнем регистре, цифры, «.», «_», «-»",
                                       fields={f"config.{name}": "Некорректный ключ"})
        given = [k for k in keys if k]
        if len(set(given)) != len(given):
            raise ValidationFailed("Выручка, число сделок и воронка пишутся в разные показатели",
                                   fields={"config.deals_indicator": "Ключ уже занят другим показателем"})
        return out

    # --- подключение
    def endpoint(self) -> tuple[str, tuple[str, ...]]:
        """Адрес методов вебхука и его секретные части (для вычистки из сообщений)."""
        raw = (self.secrets.get("webhook") or "").strip()
        portal = urlsplit(self.url or "")
        if re.match(r"^https?://", raw, re.IGNORECASE):
            parts = urlsplit(raw)
            if parts.netloc.lower() != portal.netloc.lower():
                raise IntegrationError(f"Вебхук выдан другим порталом ({parts.hostname}), а в подключении — "
                                       f"{portal.hostname}: адрес портала и вебхука должны совпадать", code="config",
                                       short="Вебхук Bitrix24 не соответствует адресу портала")
            match = WEBHOOK.match(parts.path)
        else:
            match = SHORT_WEBHOOK.match(raw) or WEBHOOK.match(raw)
        if not match:
            raise IntegrationError("Вебхук — адрес вида https://портал/rest/1/код/ (скопируйте его целиком из "
                                   "настроек входящего вебхука)", code="config", short="Вебхук Bitrix24 задан неверно")
        user, code = match.group("user"), match.group("code")
        base = f"{portal.scheme}://{portal.netloc}{(portal.path or '').rstrip('/')}/rest/{user}/{code}/"
        return base, (f"{user}/{code}", code)

    def bitrix(self, client: HttpClient) -> Bitrix:
        base, secrets = self.endpoint()
        return Bitrix(client, base, secrets)

    def client(self) -> HttpClient:
        return self.http(sleep=sleep)

    def check(self) -> CheckResult:
        with self.client() as client:
            bx = self.bitrix(client)
            profile = bx.call("profile")["result"]
            try:
                scopes = bx.call("scope")["result"]
            except IntegrationError:
                scopes = None
        profile = profile if isinstance(profile, dict) else {}
        name = " ".join(str(profile.get(k) or "").strip() for k in ("NAME", "LAST_NAME")).strip() or "—"
        host = urlsplit(self.url or "").hostname
        message = f"Подключено к порталу {host} как {name} (ID {profile.get('ID', '—')})"
        if profile.get("ADMIN"):
            message += ", администратор портала"
        warnings = []
        if isinstance(scopes, list):
            message += " · права вебхука: " + (", ".join(map(str, scopes)) or "нет")
            if "crm" not in scopes:
                warnings.append("у вебхука нет прав «CRM» — сделки не прочитать")
            if not {"user", "user_basic", "user_brief"} & set(scopes):
                warnings.append("у вебхука нет прав «Пользователи» — ответственных не сопоставить с подразделениями")
            if self.config.get("mapping") == "department" and "department" not in scopes:
                warnings.append("у вебхука нет прав «Структура компании» — отделы сопоставляются только по ID")
        keys = [self.config.get(k) for k in ("revenue_indicator", "deals_indicator", "pipeline_indicator")]
        targets = list(metrics.parse_pairs(self.config.get("department_map"), "", "").values()) + \
            list(metrics.parse_pairs(self.config.get("user_map"), "", "").values())
        warnings += metrics.diagnose([k for k in keys if k], targets)
        if warnings:
            message += ". Внимание: " + "; ".join(warnings)
        return CheckResult(True, message, {"portal": host, "user": name, "user_id": profile.get("ID"),
                                           "scopes": scopes, "warnings": warnings})

    # --- запуск
    def specs(self) -> dict[str, metrics.IndicatorSpec]:
        scale_unit = AMOUNT_UNITS[self.config.get("amount_unit") or "million"][1]
        out = {}
        for role, name, unit, data_class in (
                ("revenue", "Выручка по сделкам (Bitrix24)", scale_unit, "financial"),
                ("deals", "Выиграно сделок (Bitrix24)", "шт.", "operational"),
                ("pipeline", "Открытые сделки (Bitrix24)", scale_unit, "financial")):
            key = self.config.get(f"{role}_indicator")
            if key:
                out[role] = metrics.IndicatorSpec(key=key, name=name, unit=unit, data_class=data_class,
                                                  description=f"Сделки CRM Bitrix24: {name.split(' (')[0].lower()}")
        return out

    def deal_filter(self, extra: dict) -> dict:
        flt = dict(extra)
        categories = [int(c) for c in self.config.get("categories") or []]
        if categories:
            flt["CATEGORY_ID"] = categories
        return flt

    def owners(self, bx: Bitrix, user_ids: list[str], units: metrics.Units) -> tuple[dict[str, int | None],
                                                                                       dict[str, str]]:
        """Ответственный → подразделение и подпись ответственного (для списка несопоставленных)."""
        overrides = metrics.parse_pairs(self.config.get("user_map"), "config.user_map", "Соответствие ответственных")
        users: dict[str, dict] = {}
        for start in range(0, len(user_ids), IDS_PER_CALL):
            chunk = user_ids[start:start + IDS_PER_CALL]
            for user in bx.items("user.get", {"filter": {"ID": chunk}}):
                users[str(user.get("ID"))] = user
        mode = self.config.get("mapping") or "email"
        by_email: dict[str, int | None] = {}
        for person in units.snap.people.values():
            if person.email:
                by_email.setdefault(person.email.casefold(), units.snap.home_unit(person.id))
        departments = self.departments(bx, users.values(), units) if mode == "department" else {}
        result, labels = {}, {}
        for uid in user_ids:
            user = users.get(uid) or {}
            email = str(user.get("EMAIL") or "").strip().casefold()
            labels[uid] = " ".join(str(user.get(k) or "").strip() for k in ("NAME", "LAST_NAME")).strip() or \
                (f"ID {uid} (нет в user.get)" if not user else f"ID {uid}")
            override = overrides.get(uid) or (overrides.get(email) if email else None)
            if override:
                result[uid] = units.find(override)[0]
            elif mode == "email":
                result[uid] = by_email.get(email) if email else None
            else:
                dept = next(iter(user.get("UF_DEPARTMENT") or []), None)
                result[uid] = departments.get(str(dept)) if dept is not None else None
        return result, labels

    def departments(self, bx: Bitrix, users, units: metrics.Units) -> dict[str, int | None]:
        """Отдел Bitrix24 → подразделение: явное соответствие (по ID или названию), иначе название или код."""
        explicit = metrics.parse_pairs(self.config.get("department_map"), "config.department_map",
                                       "Соответствие отделов")
        wanted = _ids(d for u in users for d in (u.get("UF_DEPARTMENT") or [])[:1])
        names: dict[str, str] = {}
        if any(d not in explicit for d in wanted):
            try:
                names = {str(d.get("ID")): str(d.get("NAME") or "") for d in bx.items("department.get")}
            except IntegrationError as exc:
                if exc.code not in ("forbidden", "not_found"):
                    raise
        out = {}
        for dept in wanted:
            name = names.get(dept, "")
            ref = explicit.get(dept) or (explicit.get(name.casefold()) if name else None)
            out[dept] = units.find(ref)[0] if ref else units.by_name_or_code(name)
        return out

    def run(self, action: str, ctx: RunContext) -> RunResult:
        self.action(action)
        preview = action == "preview"
        specs = self.specs()
        months = metrics.window(self.config.get("months") or 2)
        current = months[-1]
        scale = AMOUNT_UNITS[self.config.get("amount_unit") or "million"][0]
        owner, origin = self.config.get("owner_service") or "commercial", f"подключение «{self.name}» (Bitrix24)"
        targets = metrics.ensure_indicators(ctx, specs.values(), owner, origin, create=False)
        units = metrics.Units.load(ctx.db)
        stages = self.config.get("won_stages") or []
        won_filter = self.deal_filter({">=CLOSEDATE": f"{months[0].start.isoformat()}T00:00:00",
                                       "<CLOSEDATE": f"{current.next_start.isoformat()}T00:00:00",
                                       **({"STAGE_ID": stages} if stages else {"STAGE_SEMANTIC_ID": "S"})})
        order = {"ID": "ASC"}
        with self.client() as client:
            bx = self.bitrix(client)
            won = bx.items("crm.deal.list", {"filter": won_filter, "select": DEAL_SELECT, "order": order}) \
                if {"revenue", "deals"} & set(specs) else []
            opened = bx.items("crm.deal.list", {"filter": self.deal_filter({"CLOSED": "N"}), "select": DEAL_SELECT,
                                                "order": order}) if "pipeline" in specs else []
            owner_ids = _ids(d.get("ASSIGNED_BY_ID") for d in [*won, *opened])
            owners, labels = self.owners(bx, owner_ids, units) if owner_ids else ({}, {})
            stats = client.stats()
        by_key = {m.key: m for m in months}
        sums: dict[tuple[str, str, int], float] = defaultdict(float)
        counts: Counter = Counter()
        unmapped: Counter = Counter()
        currencies = Counter(str(d.get("CURRENCY_ID") or "") for d in [*won, *opened] if d.get("CURRENCY_ID"))
        for deal in won:
            month = by_key.get(str(deal.get("CLOSEDATE") or "")[:7])
            unit = owners.get(str(deal.get("ASSIGNED_BY_ID") or "").strip())
            if month is None:
                continue
            if unit is None:
                unmapped[labels.get(str(deal.get("ASSIGNED_BY_ID")), "без ответственного")] += 1
                continue
            sums[("revenue", month.key, unit)] += amount(deal.get("OPPORTUNITY")) * scale
            counts[("deals", month.key, unit)] += 1
        for deal in opened:
            unit = owners.get(str(deal.get("ASSIGNED_BY_ID") or "").strip())
            if unit is None:
                unmapped[labels.get(str(deal.get("ASSIGNED_BY_ID")), "без ответственного")] += 1
                continue
            sums[("pipeline", current.key, unit)] += amount(deal.get("OPPORTUNITY")) * scale
            counts[("pipeline", current.key, unit)] += 1
        cells = []
        for (role, month_key, unit), total in sorted(sums.items()):
            if role in specs:
                n = counts[(role if role == "pipeline" else "deals", month_key, unit)]
                what = "открытых сделок" if role == "pipeline" else "выигранных сделок"
                cells.append(metrics.Cell(specs[role].key, unit, by_key[month_key], round(total, 6),
                                          f"из Bitrix24: {what} — {n}"))
        if "deals" in specs:
            cells += [metrics.Cell(specs["deals"].key, unit, by_key[m], float(n), "из Bitrix24: выигранные сделки")
                      for (role, m, unit), n in sorted(counts.items()) if role == "deals"]
        keys = {s.key for s in specs.values()}
        cells = metrics.zero_fill(ctx, cells, months, keys, units, "из Bitrix24")
        cells = metrics.branch_totals(cells, units.snap, keys)
        if not preview:
            metrics.create_pending(ctx, targets, specs.values(), owner, origin, {c.indicator for c in cells})
        ready = [c for c in cells if c.indicator in targets.found]
        written = metrics.write(ctx, ready, units, apply=not preview, label="")
        if not preview:
            metrics.remember(ctx, ready, months, keep=keys - set(targets.found))
        parts = [written.text(preview), f"выигранных сделок: {len(won)}"]
        if "pipeline" in specs:
            parts.append(f"открытых: {len(opened)}")
        warnings = list(targets.problems.values())
        if unmapped:
            parts.append(f"без подразделения: {sum(unmapped.values())}")
            warnings.append("сделки ответственных без подразделения не учтены: " + ", ".join(
                f"{who} — {n}" for who, n in unmapped.most_common(10)))
        if len(currencies) > 1:
            warnings.append("сделки в разных валютах (" + ", ".join(sorted(currencies)) + ") сложены без пересчёта")
        if targets.created:
            parts.append("созданы показатели: " + ", ".join(f"«{k}»" for k in targets.created))
        if targets.pending:
            head = "при записи будут созданы показатели" if preview else "не созданы показатели без значений"
            parts.append(f"{head}: " + ", ".join(f"«{k}»" for k in targets.pending))
        counters = {**written.counters(), "deals_won": len(won), "deals_open": len(opened),
                    "deals_unmapped": sum(unmapped.values()), "indicators_created": len(targets.created)}
        details = {"months": [m.key for m in months], "values": written.sample, "requests": stats,
                   **({"unmapped": dict(unmapped.most_common(50))} if unmapped else {}),
                   **({"currencies": dict(currencies)} if currencies else {}),
                   **({"warnings": warnings} if warnings else {})}
        message = " · ".join(parts)
        if targets.problems:
            return RunResult.partial(message, "; ".join(targets.problems.values()), counters=counters,
                                     details=details)
        return RunResult.ok(message + (". Внимание: " + "; ".join(warnings) if warnings else ""), counters=counters,
                            details=details)

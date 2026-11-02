"""Jira: показатели сквозного отчёта по JQL (ADR-0011) — подключение, поиск и признаки качества данных
как в burndown_tool.

Cloud — email + API-токен, REST API 3, поиск POST /rest/api/3/search/jql с nextPageToken (по 100 задач);
Server / Data Center — персональный токен (Bearer) или логин и пароль, REST API 2, поиск POST /rest/api/2/search
со startAt и validateQuery: false (по 500 задач). Не больше 5000 задач на один JQL — иначе значение не пишется.

Правило показателя (настройка «Правила показателей», список JSON):
    {"indicator": "jira.resolved",                       ключ показателя каталога; если его нет и задано name —
     "name": "Решено задач в Jira", "unit": "шт.",       показатель создаётся (класс «Операционные», свёртка —
     "direction": "higher_is_better", "rule": "threshold", "green": 50, "yellow": 30,     сумма)
     "measure": "count" | "sum",                         число задач или сумма поля
     "field": "timespent", "field_unit": "seconds",      для sum: timeestimate · timespent · timeoriginalestimate
                                                         (секунды → часы) или customfield_NNNNN (как есть)
     "jql": "project = SUP AND component = \"{unit_code}\" AND resolved >= \"{month_start}\" "
            "AND resolved < \"{next_month_start}\"",
     "units": {"SUP-OS": "AlterOS", "SUP-OFFICE": "AlterOffice"}}  код подразделения у нас → значение {unit_code}
                                                                  (или список кодов — тогда {unit_code} = код)
  либо вместо jql и units — "unit_jql": {"TECH": "project = TECH AND …", "IT": "…"}: свой JQL на подразделение.
Подстановки: {month} (ГГГГ-ММ), {month_start}, {month_end}, {next_month_start}, {unit_code}. JQL без подстановки
месяца — снимок «на сейчас» (например, открытый бэклог): значение пишется только в текущий месяц.

Значения пишутся через ctx.plans.indicator_values (как загрузка из файла) с комментарием «из Jira (JQL …)».
Признаки качества данных (как в burndown_tool) — в сводке запуска: done_with_remaining (закрыта, остаток
не обнулён), no_estimate (не закрыта, нет оценки и остатка), overspent (затрачено больше оценки).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

from ...core.errors import ValidationFailed
from ..base import Action, CheckResult, Connector, Field, RunContext, RunResult, register
from ..http import HttpClient, IntegrationError, error_text
from . import _atlassian as atlassian
from . import _metrics as metrics

PRODUCT = "Jira"
SEARCH_BATCH = 100    # задач в одном запросе Jira Cloud
SERVER_BATCH = 500    # Server / DC отдаёт до 1000 задач за запрос (меньший предел дочитывается постранично)
SEARCH_LIMIT = 5000
MAX_RULES = 50
MAX_UNITS = 200
MAX_JQL = 4000
TIME_FIELDS = {"timeestimate": "Оставшаяся оценка", "timespent": "Затраченное время",
               "timeoriginalestimate": "Первоначальная оценка"}
FIELD_UNITS = {"seconds": 1 / 3600, "minutes": 1 / 60, "hours": 1.0, "days": 8.0, "number": 1.0}
CUSTOM_FIELD = re.compile(r"^customfield_\d{1,12}$")
QUALITY_FIELDS = ("status", "timeestimate", "timespent", "timeoriginalestimate")
PROBLEMS = {
    "done_with_remaining": "закрыта, но остаток не обнулён",
    "no_estimate": "не закрыта, нет оценки и остатка",
    "overspent": "затрачено больше оценки",
}
JQL_VARS = (*metrics.MONTH_VARS, "unit_code")
RULE_KEYS = {*metrics.INDICATOR_KEYS, "measure", "field", "field_unit", "jql", "units", "unit_jql"}
PLACE = "config.rules"
SAMPLE_KEYS = 10

RULES_EXAMPLE = json.dumps([
    {"indicator": "jira.resolved", "name": "Решено задач в Jira", "unit": "шт.", "measure": "count",
     "jql": 'project = SUP AND component = "{unit_code}" AND resolved >= "{month_start}" '
            'AND resolved < "{next_month_start}"',
     "units": {"SUP-OS": "AlterOS", "SUP-OFFICE": "AlterOffice"}},
    {"indicator": "jira.spent_hours", "name": "Затрачено в Jira", "measure": "sum", "field": "timespent",
     "unit_jql": {"IT": 'project = IT AND worklogDate >= "{month_start}" AND worklogDate < "{next_month_start}"'}},
], ensure_ascii=False, indent=2)
RULES_HINT = (
    "Список JSON. В каждом правиле: indicator — ключ показателя (нет в каталоге и задано name — создаётся "
    "с unit, direction, rule, green, yellow; класс «Операционные»); measure — count (число задач) или sum "
    "(сумма поля field: timeestimate, timespent, timeoriginalestimate — секунды в часы, или customfield_NNNNN); "
    "jql — шаблон с подстановками {month_start}, {month_end}, {next_month_start}, {month} и {unit_code} вместе "
    "с units — список кодов подразделений или {код: значение {unit_code}} (компонент, метка, проект); либо "
    "unit_jql — {код подразделения: JQL}. Даты в JQL сравнивайте так: resolved >= \"{month_start}\" AND resolved "
    "< \"{next_month_start}\" (условие «<= {month_end}» в Jira не включает последний день). JQL без подстановки "
    "месяца — снимок «на сейчас»: пишется только в текущий месяц.")
NOT_FOUND = ("Поиск Jira не найден (404) — проверьте тип подключения: у Cloud — REST API 3 (/rest/api/3/search/jql), "
             "у Server / Data Center — REST API 2 (/rest/api/2/search)")


class QueryError(Exception):
    """Jira отклонила JQL (400) или задач больше предела — ячейка не считается, остальные считаются."""


@dataclass(frozen=True)
class Query:
    unit: str          # код или путь подразделения у нас
    jql: str           # шаблон JQL
    unit_value: str    # что подставить в {unit_code}


@dataclass(frozen=True)
class Rule:
    number: int
    indicator: metrics.IndicatorSpec
    measure: str
    field: str | None
    factor: float
    queries: tuple[Query, ...]

    @property
    def monthly(self) -> bool:
        return metrics.monthly(*(q.jql for q in self.queries))

    @property
    def title(self) -> str:
        return f"Правило {self.number} («{self.indicator.key}»)"

    def value(self, issues: list[dict]) -> float:
        if self.measure == "count":
            return float(len(issues))
        total = 0.0
        for issue in issues:
            raw = (issue.get("fields") or {}).get(self.field)
            if isinstance(raw, (int, float)) and not isinstance(raw, bool):
                total += raw
        return round(total * self.factor, 2)


def _fail(where: str, message: str) -> ValidationFailed:
    return ValidationFailed(f"{where}: {message}", fields={PLACE: message})


def _queries(raw: dict, where: str) -> list[Query]:
    jql, units, unit_jql = raw.get("jql"), raw.get("units"), raw.get("unit_jql")
    if unit_jql not in (None, "", {}, []):
        if jql or units:
            raise _fail(where, "задайте либо jql вместе с units, либо unit_jql — не всё сразу")
        if not isinstance(unit_jql, dict):
            raise _fail(where, "unit_jql — объект {\"код подразделения\": \"JQL\"}")
        out = [Query(str(code).strip(), str(text or "").strip(), str(code).strip()) for code, text in unit_jql.items()]
    else:
        if not isinstance(jql, str) or not jql.strip():
            raise _fail(where, "нужен jql (шаблон) вместе с units или unit_jql — свой JQL на подразделение")
        if isinstance(units, str):
            units = [u for u in re.split(r"[,\n;]", units) if u.strip()]
        if isinstance(units, list):
            pairs = [(str(u).strip(), str(u).strip()) for u in units]
        elif isinstance(units, dict):
            pairs = [(str(k).strip(), str(v if v is not None else "").strip()) for k, v in units.items()]
        else:
            raise _fail(where, "units — список кодов подразделений или объект {\"код\": \"значение {unit_code}\"}")
        if "{unit_code}" not in jql and len(pairs) > 1:
            raise _fail(where, "в JQL нет {unit_code}, а подразделений несколько — все получили бы одно значение")
        out = [Query(code, jql.strip(), value) for code, value in pairs]
    if not out:
        raise _fail(where, "не указано ни одного подразделения")
    if len(out) > MAX_UNITS:
        raise _fail(where, f"не больше {MAX_UNITS} подразделений")
    for query in out:
        if not query.unit or not query.jql or not query.unit_value:
            raise _fail(where, "пустой код подразделения, JQL или значение {unit_code}")
        if len(query.jql) > MAX_JQL:
            raise _fail(where, f"JQL длиннее {MAX_JQL} символов")
        metrics.check_template(query.jql, JQL_VARS, where, PLACE)
    return out


def parse_rules(text: str | None) -> list[Rule]:
    """Правила из настройки (JSON); ValidationFailed с полем config.rules при ошибке."""
    rules: list[Rule] = []
    seen: dict[tuple[str, str], int] = {}
    for number, raw in enumerate(metrics.load_list(text, PLACE, "Правила показателей", limit=MAX_RULES), start=1):
        where = f"Правило {number}"
        unknown = sorted(set(raw) - RULE_KEYS)
        if unknown:
            raise _fail(where, f"неизвестное поле «{unknown[0]}»")
        measure = metrics.choice(raw, "measure", ("count", "sum"), "count", where, PLACE)
        field_id, field_unit = None, "number"
        if measure == "sum":
            field_id = metrics.text(raw, "field")
            if field_id not in TIME_FIELDS and not CUSTOM_FIELD.match(field_id):
                raise _fail(where, "для measure «sum» укажите field: timeestimate, timespent, timeoriginalestimate "
                                   "или customfield_NNNNN (числовое поле)")
            field_unit = metrics.choice(raw, "field_unit", tuple(FIELD_UNITS),
                                        "seconds" if field_id in TIME_FIELDS else "number", where, PLACE)
        elif raw.get("field") or raw.get("field_unit"):
            raise _fail(where, "field и field_unit — только для measure «sum»")
        unit = "шт." if measure == "count" else ("" if field_unit == "number" else "ч")
        spec = metrics.indicator_spec(raw, where, PLACE, unit=unit, data_class="operational")
        queries = _queries(raw, where)
        for query in queries:
            cell = (spec.key, query.unit.casefold())
            if cell in seen:
                raise _fail(where, f"«{spec.key}» для «{query.unit}» уже считает правило {seen[cell]}")
            seen[cell] = number
        rules.append(Rule(number, spec, measure, field_id, FIELD_UNITS[field_unit], tuple(queries)))
    return rules


def jql_string(value: str) -> str:
    """Значение для подстановки внутрь кавычек JQL."""
    return value.replace("\\", "\\\\").replace('"', '\\"')


def problems(fields: dict) -> list[str]:
    """Признаки, из-за которых сумма часов может вводить в заблуждение (как issue_problems в burndown_tool)."""
    status = fields.get("status") if isinstance(fields.get("status"), dict) else {}
    done = (status.get("statusCategory") or {}).get("key") == "done"

    def num(name: str) -> float:
        value = fields.get(name)
        return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else 0.0

    remaining, spent, estimate = num("timeestimate"), num("timespent"), num("timeoriginalestimate")
    out = []
    if done and remaining > 0:
        out.append("done_with_remaining")
    if not done and not (remaining > 0 or estimate > 0):
        out.append("no_estimate")
    if estimate > 0 and spent > estimate:
        out.append("overspent")
    return out


class Quality:
    """Признаки качества данных по уникальным задачам всех поисков запуска."""

    def __init__(self):
        self.issues: dict[str, list[str]] = {}

    def add(self, issues: list[dict]) -> None:
        for issue in issues:
            key = str(issue.get("key") or issue.get("id") or "")
            if key and key not in self.issues:
                self.issues[key] = problems(issue.get("fields") or {})

    def counters(self) -> dict[str, int]:
        return {p: sum(1 for found in self.issues.values() if p in found) for p in PROBLEMS}

    def samples(self) -> dict[str, list[str]]:
        out = {p: sorted(k for k, found in self.issues.items() if p in found)[:SAMPLE_KEYS] for p in PROBLEMS}
        return {p: keys for p, keys in out.items() if keys}

    def text(self) -> str:
        found = [f"{PROBLEMS[p]} — {n}" for p, n in self.counters().items() if n]
        return "качество данных: " + ", ".join(found) if found else "проблем в данных задач не найдено"


class Search:
    """Поиск задач по JQL постранично, как в burndown_tool; одинаковый JQL за запуск — один раз."""

    def __init__(self, client: HttpClient, cloud: bool):
        self.client = client
        self.cloud = cloud
        self.batch = SEARCH_BATCH if cloud else SERVER_BATCH
        self.path = "rest/api/3/search/jql" if cloud else "rest/api/2/search"
        self.cache: dict[str, list[dict]] = {}

    def issues(self, jql: str, fields: list[str]) -> list[dict]:
        if jql in self.cache:
            return self.cache[jql]
        found: list[dict] = []
        start_at, token = 0, None
        while True:
            body: dict = {"jql": jql, "fields": fields, "maxResults": self.batch}
            if self.cloud:
                if token:
                    body["nextPageToken"] = token
            else:
                body.update(startAt=start_at, validateQuery=False)
            resp = atlassian.call(self.client, PRODUCT, "POST", self.path, json=body, allow=(400,),
                                  not_found=NOT_FOUND)
            if resp.status == 400:
                raise QueryError(f"Jira отклонила JQL: {error_text(resp) or 'ошибка в запросе (400)'}")
            data = self.client.parse(resp, dict)
            page = data.get("issues")
            if not isinstance(page, list):
                raise IntegrationError("Jira вернула ответ поиска без списка задач — проверьте адрес и тип подключения",
                                       code="bad_response")
            found.extend(i for i in page if isinstance(i, dict))
            start_at += len(page)
            token = data.get("nextPageToken")
            more = bool(token) if self.cloud else start_at < int(data.get("total") or 0)
            if not page or not more:
                break
            if len(found) >= SEARCH_LIMIT:
                raise QueryError(f"JQL находит больше {SEARCH_LIMIT} задач — значение не записано: уточните запрос")
        self.cache[jql] = found
        return found


@register
class JiraConnector(Connector):
    kind = "jira"
    title = "Jira"
    description = ("Показатели сквозного отчёта по JQL: число задач или сумма поля (оценка, остаток, затраты — "
                   "в часах) по подразделениям, помесячно; признаки качества данных — как в Burndown. Cloud — email "
                   "и API-токен (REST API 3), Server / Data Center — персональный токен или логин и пароль "
                   "(REST API 2). Узлы ограничивает JIRA_ALLOWED_HOSTS")
    fields = (
        *atlassian.connection_fields(
            "Jira", "https://jira.company.ru",
            "Адрес, по которому Jira открывается в браузере, с путём, если он есть (https://jira.company.ru/jira); "
            "Cloud — https://company.atlassian.net"),
        Field("rules", "Правила показателей", "text", required=True, hint=RULES_HINT, placeholder=RULES_EXAMPLE),
        metrics.months_field(),
        metrics.owner_field("it"),
    )
    actions = (
        Action("refresh", "Обновить показатели",
               "Выполнить JQL правил за текущий и прошлый месяц (или за настроенное число месяцев) и записать "
               "значения по подразделениям в сквозной отчёт; признаки качества данных — в сводке запуска"),
        Action("preview", "Проверить правила без записи",
               "Выполнить JQL и показать план: что запишется и что изменится, — без записи и без создания "
               "показателей", schedulable=False),
    )

    @classmethod
    def validate_config(cls, config: dict) -> dict:
        out = super().validate_config(metrics.json_text(config, "rules"))
        if not parse_rules(out["rules"]):
            raise ValidationFailed("Добавьте хотя бы одно правило показателя", fields={PLACE: "Нет правил"})
        out["rules"] = metrics.pretty(json.loads(out["rules"]))
        return out

    # --- подключение
    @property
    def cloud(self) -> bool:
        return self.config.get("instance") == "cloud"

    @property
    def api(self) -> str:
        return atlassian.api_version(self.config)

    def client(self) -> HttpClient:
        return self.http(**atlassian.client_options(self.config, self.secrets))

    def rules(self) -> list[Rule]:
        try:
            return parse_rules(self.config.get("rules"))
        except ValidationFailed as exc:
            raise IntegrationError(f"Правила показателей: {exc.detail}", code="config",
                                   short="Правила показателей подключения заданы с ошибкой") from None

    def check(self) -> CheckResult:
        rules = self.rules()
        with self.client() as client:
            me = atlassian.get_json(client, PRODUCT, f"rest/api/{self.api}/myself", not_found=(
                f"В Jira нет REST API {self.api} (api/myself не найден, 404) — проверьте адрес (с путём, если он "
                "есть) и тип подключения: Cloud — REST API 3, Server / Data Center — REST API 2"))
            try:
                info = atlassian.get_json(client, PRODUCT, f"rest/api/{self.api}/serverInfo")
            except IntegrationError:
                info = {}
        name = me.get("displayName") or me.get("name") or me.get("emailAddress") or "—"
        version, deployment = str(info.get("version") or ""), str(info.get("deploymentType") or "")
        parts = [f"Подключено как {name}"]
        if version or deployment:
            parts.append(" ".join(p for p in ("Jira", version, f"({deployment})" if deployment else "") if p))
        parts.append(f"REST API {self.api}")
        warnings = []
        if deployment == "Cloud" and not self.cloud:
            warnings.append("это Jira Cloud — выберите тип подключения «Cloud»")
        elif deployment in ("Server", "DataCenter") and self.cloud:
            warnings.append("это Jira Server / Data Center — выберите тип подключения Server")
        warnings += metrics.diagnose([r.indicator.key for r in rules], [q.unit for r in rules for q in r.queries])
        message = " · ".join(parts) + (". Внимание: " + "; ".join(warnings) if warnings else "")
        return CheckResult(True, message, {"user": name, "api": self.api, "version": version or None,
                                           "deployment": deployment or None, "rules": len(rules),
                                           "warnings": warnings})

    # --- запуск
    def run(self, action: str, ctx: RunContext) -> RunResult:
        self.action(action)
        preview = action == "preview"
        rules = self.rules()
        months = metrics.window(self.config.get("months") or 2)
        owner, origin = self.config.get("owner_service") or "it", f"подключение «{self.name}» (Jira, JQL)"
        specs = [r.indicator for r in rules]
        targets = metrics.ensure_indicators(ctx, specs, owner, origin, create=False)
        units = metrics.Units.load(ctx.db)
        errors = list(targets.problems.values())
        fields = sorted({*QUALITY_FIELDS, *(r.field for r in rules if r.field)})
        cells: list[metrics.Cell] = []
        taken: dict[tuple[str, int], int] = {}
        quality = Quality()
        with self.client() as client:
            search = Search(client, self.cloud)
            for rule in rules:
                if not targets.usable(rule.indicator.key):
                    continue
                for query in rule.queries:
                    unit_id, problem = units.find(query.unit)
                    if unit_id is None:
                        errors.append(f"{rule.title}: {problem}")
                        continue
                    if (rule.indicator.key, unit_id) in taken:
                        errors.append(f"{rule.title}: «{units.name(unit_id)}» уже считает правило "
                                      f"{taken[(rule.indicator.key, unit_id)]} (код и путь одного подразделения)")
                        continue
                    taken[(rule.indicator.key, unit_id)] = rule.number
                    for month in months if rule.monthly else months[-1:]:
                        jql = metrics.render(query.jql, {**month.values(), "unit_code": jql_string(query.unit_value)})
                        try:
                            issues = search.issues(jql, fields)
                        except QueryError as exc:
                            errors.append(f"{rule.title} · {units.name(unit_id)} · {month.label}: {exc}")
                            continue
                        quality.add(issues)
                        cells.append(metrics.Cell(rule.indicator.key, unit_id, month, rule.value(issues),
                                                  f"из Jira (JQL {jql})"))
            stats = client.stats()
        if not preview:
            known = set(targets.problems)
            metrics.create_pending(ctx, targets, specs, owner, origin, {c.indicator for c in cells})
            errors += [p for k, p in targets.problems.items() if k not in known]
        ready = [c for c in cells if c.indicator in targets.found]
        written = metrics.write(ctx, ready, units, apply=not preview, label="")
        parts = [written.text(preview), f"задач Jira: {len(quality.issues)}", quality.text()]
        if targets.created:
            parts.append("созданы показатели: " + ", ".join(f"«{k}»" for k in targets.created))
        if targets.pending:
            head = "при записи будут созданы показатели" if preview else "не созданы показатели без значений"
            parts.append(f"{head}: " + ", ".join(f"«{k}»" for k in targets.pending))
        counters = {**written.counters(), "issues": len(quality.issues), **quality.counters(),
                    "indicators_created": len(targets.created), "errors": len(errors)}
        details = {"months": [m.key for m in months], "values": written.sample, "problems": quality.samples(),
                   "requests": stats}
        if errors:
            details["errors"] = errors[:50]
        message = " · ".join(parts)
        if errors and not cells:
            return RunResult.failed("Ни одно значение не посчитано: " + "; ".join(errors[:5]), counters=counters,
                                    details=details)
        if errors:
            return RunResult.partial(message, "; ".join(errors[:10]), counters=counters, details=details)
        return RunResult.ok(message, counters=counters, details=details)

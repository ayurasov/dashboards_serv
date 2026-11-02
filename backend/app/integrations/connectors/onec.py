"""1С (OData): значения показателей из стандартного интерфейса OData 1С по настроенным запросам (ADR-0011).

Подключение — адрес …/odata/standard.odata/ информационной базы и пользователь 1С (Basic, логин и пароль
в UTF-8 — кириллица допустима); узлы ограничивает ONEC_ALLOWED_HOSTS. Проверка читает $metadata (XML) и
сверяет, что наборы из запросов опубликованы.

Запрос (настройка «Запросы», список JSON):
    {"name": "ФОТ",                                        название запроса (для журнала и комментария)
     "entity": "Document_НачислениеЗарплаты",             набор или виртуальная таблица с параметрами
                                         (AccumulationRegister_X/Turnovers(StartPeriod=datetime'{month_start}', …))
     "filter": "Date ge datetime'{month_start}' and Date le datetime'{month_end}' and Posted eq true",
     "select": "Подразделение_Key,СуммаНачислено",         $select (поля значения и подразделения добавятся сами)
     "value_field": "СуммаНачислено", "aggregate": "sum",  sum · count · avg
     "department_field": "Подразделение_Key",             подразделение 1С: Ref_Key, код или наименование
     "scale": 0.000001,                                    множитель (руб. → млн ₽)
     "indicator": "fin.payroll",                           показатель; нет в каталоге и задано indicator_name —
     "indicator_name": "ФОТ (1С)", "unit": "млн ₽", …}     создаётся (класс по умолчанию «Финансовые»)
Подстановки: {month_start} / {month_end} — 2026-10-01T00:00:00 / 2026-10-31T23:59:59 (для datetime'…'),
{month} — 2026-10, {next_month_start}. Запрос выполняется за каждый месяц окна ($format=json, страницы
$top/$skip или odata.nextLink); строки суммируются по подразделениям. Подразделение 1С → наше: явное
соответствие (Ref_Key, код или наименование 1С = код у нас), иначе по коду или наименованию справочника
подразделений (его Ref_Key, Code, Description читаются один раз за запуск).
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from dataclasses import dataclass
from urllib.parse import quote

from ...core.errors import ValidationFailed
from ...models import name_key
from ..base import Action, CheckResult, Connector, Field, Option, RunContext, RunResult, register
from ..http import HttpClient, IntegrationError
from . import _metrics as metrics

PLACE = "config.queries"
MAX_QUERIES = 30
MAX_ROWS = 200000
MAX_PAGES = 1000
EMPTY_REF = "00000000-0000-0000-0000-000000000000"
GUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
FIELD_NAME = re.compile(r"^[^\s,/?#&=()'\"]{1,200}(/[^\s,/?#&=()'\"]{1,200})*$")
VIRTUAL = re.compile(r"^(?P<base>.+)_(?P<table>Turnovers|Balance|BalanceAndTurnovers|SliceLast|SliceFirst)$")
QUERY_KEYS = {"name", "entity", "filter", "select", "expand", "value_field", "aggregate", "department_field",
              "unit_code", "scale", "indicator", "indicator_name", "unit", "direction", "rule", "green", "yellow",
              "rollup", "description", "data_class"}
VARS = metrics.MONTH_VARS
VALUE_SAFE = "'(),:/$"          # в значениях параметров запроса: кавычки и скобки OData не кодируются
PATH_SAFE = "/(),=':_-.$"       # путь набора: параметры виртуальной таблицы остаются как есть

QUERIES_EXAMPLE = """[
  {
    "name": "ФОТ",
    "entity": "Document_НачислениеЗарплаты",
    "filter": "Date ge datetime'{month_start}' and Date le datetime'{month_end}' and Posted eq true",
    "select": "Подразделение_Key,ВсегоНачислено",
    "value_field": "ВсегоНачислено",
    "aggregate": "sum",
    "department_field": "Подразделение_Key",
    "scale": 0.000001,
    "indicator": "fin.payroll"
  }
]"""
QUERIES_HINT = (
    "Список JSON. В каждом запросе: name; entity — набор ($metadata: Document_…, Catalog_…, "
    "AccumulationRegister_…) или виртуальная таблица AccumulationRegister_Имя/Turnovers("
    "StartPeriod=datetime'{month_start}', EndPeriod=datetime'{month_end}'); filter — $filter с подстановками "
    "{month_start} и {month_end} (2026-10-01T00:00:00 и 2026-10-31T23:59:59); select — $select; value_field "
    "и aggregate (sum, count, avg); department_field — поле подразделения (Ref_Key, код или наименование) или "
    "unit_code — одно наше подразделение для всех строк; scale — множитель (0.000001 — рубли в млн ₽); "
    "indicator — ключ показателя (нет в каталоге и задано indicator_name — создаётся с unit, direction, rule, "
    "green, yellow, data_class; по умолчанию «Финансовые»). Объект должен быть в составе стандартного "
    "интерфейса OData базы.")
INBOX_SNIPPET = '''Функция ОтправитьВДашборды(ПутьКФайлу, ИмяФайла, Набор = "indicators") Экспорт
    // Ключ интеграции «Дашбордов» с областью «приём файлов»: Интеграции → Ключи
    Ключ = "dash_…"; Граница = "dash" + СтрЗаменить(Строка(Новый УникальныйИдентификатор), "-", "");
    ПС = Символы.ВК + Символы.ПС;
    Начало = "--" + Граница + ПС + "Content-Disposition: form-data; name=""dataset""" + ПС + ПС + Набор + ПС
        + "--" + Граница + ПС + "Content-Disposition: form-data; name=""file""; filename=""" + ИмяФайла + """"
        + ПС + "Content-Type: application/octet-stream" + ПС + ПС;
    Части = Новый Массив;
    Части.Добавить(ПолучитьДвоичныеДанныеИзСтроки(Начало, КодировкаТекста.UTF8, Ложь));
    Части.Добавить(Новый ДвоичныеДанные(ПутьКФайлу));
    Части.Добавить(ПолучитьДвоичныеДанныеИзСтроки(ПС + "--" + Граница + "--" + ПС, КодировкаТекста.UTF8, Ложь));
    Запрос = Новый HTTPЗапрос("/api/inbound/v1/files");
    Запрос.Заголовки.Вставить("Authorization", "Bearer " + Ключ);
    Запрос.Заголовки.Вставить("Content-Type", "multipart/form-data; boundary=" + Граница);
    Запрос.УстановитьТелоИзДвоичныхДанных(СоединитьДвоичныеДанные(Части));
    Соединение = Новый HTTPСоединение("dashboards.company.ru", 443, , , , 60, Новый ЗащищенноеСоединениеOpenSSL);
    Ответ = Соединение.ОтправитьДляОбработки(Запрос);
    Если Ответ.КодСостояния <> 200 И Ответ.КодСостояния <> 201 Тогда
        ВызватьИсключение "Дашборды: " + Ответ.КодСостояния + " " + Ответ.ПолучитьТелоКакСтроку();
    КонецЕсли;
    Возврат Ответ.ПолучитьТелоКакСтроку(); // {"ok": true, "status": "applied" | "pending", …}
КонецФункции'''


@dataclass(frozen=True)
class Query:
    number: int
    name: str
    entity: str
    filter: str
    select: str
    expand: str
    value_field: str
    aggregate: str
    department_field: str
    unit_code: str
    scale: float
    indicator: metrics.IndicatorSpec

    @property
    def base(self) -> str:
        """Набор из $metadata: часть пути до «/» или «(»."""
        return re.split(r"[/(]", self.entity, maxsplit=1)[0]

    @property
    def title(self) -> str:
        return f"Запрос «{self.name}»"


def _fail(where: str, message: str) -> ValidationFailed:
    return ValidationFailed(f"{where}: {message}", fields={PLACE: message})


def _field(raw: dict, key: str, where: str, *, required: bool = False) -> str:
    value = metrics.text(raw, key)
    if not value:
        if required:
            raise _fail(where, f"укажите {key}")
        return ""
    if not FIELD_NAME.match(value):
        raise _fail(where, f"{key} — имя поля 1С (например, Подразделение_Key или Подразделение/Code)")
    return value


def parse_queries(text: object) -> list[Query]:
    out: list[Query] = []
    seen: dict[str, int] = {}
    for number, raw in enumerate(metrics.load_list(text, PLACE, "Запросы", limit=MAX_QUERIES), start=1):
        name = " ".join(metrics.text(raw, "name").split())[:100]
        where = f"Запрос {number}" + (f" «{name}»" if name else "")
        unknown = sorted(set(raw) - QUERY_KEYS)
        if unknown:
            raise _fail(where, f"неизвестное поле «{unknown[0]}»")
        if not name:
            raise _fail(where, "укажите name — название запроса")
        entity = metrics.text(raw, "entity")
        if not entity or re.search(r"[?#\\\s]|://|\.\.", entity.replace(" ", "")) or entity.startswith("/") \
                or len(entity) > 1000:
            raise _fail(where, "entity — имя набора из $metadata (например, Document_НачислениеЗарплаты) или путь "
                               "виртуальной таблицы без «?»")
        flt = metrics.text(raw, "filter")
        for value in (entity, flt):
            metrics.check_template(value, VARS, where, PLACE)
        if not metrics.monthly(entity, flt):
            raise _fail(where, "в entity или filter нет {month_start} / {month_end} — значения нельзя разнести по "
                               "месяцам")
        aggregate = metrics.choice(raw, "aggregate", ("sum", "count", "avg"), "sum", where, PLACE)
        value_field = _field(raw, "value_field", where, required=aggregate != "count")
        department_field = _field(raw, "department_field", where)
        unit_code = metrics.text(raw, "unit_code")
        if bool(department_field) == bool(unit_code):
            raise _fail(where, "укажите department_field (поле подразделения 1С) или unit_code — одно наше "
                               "подразделение для всех строк")
        select = [s.strip() for s in metrics.text(raw, "select").split(",") if s.strip()]
        if select:
            for extra in (value_field, department_field):
                if extra and extra.split("/")[0] not in select and extra not in select:
                    select.append(extra)
        scale = metrics.number(raw, "scale", where, PLACE)
        spec_raw = {k: v for k, v in raw.items() if k in metrics.INDICATOR_KEYS and k != "name"}
        spec_raw["name"] = raw.get("indicator_name") or ""
        spec = metrics.indicator_spec(spec_raw, where, PLACE, data_class="financial", allow_class=True,
                                      rollup="avg" if aggregate == "avg" else "sum")
        if spec.key in seen:
            raise _fail(where, f"показатель «{spec.key}» уже заполняет запрос {seen[spec.key]}")
        seen[spec.key] = number
        out.append(Query(number, name, entity, flt, ",".join(select), metrics.text(raw, "expand"), value_field,
                         aggregate, department_field, unit_code, 1.0 if scale is None else scale, spec))
    return out


def month_values(month: metrics.Month) -> dict[str, str]:
    """Подстановки для OData: даты — в формате datetime'…' 1С."""
    return {**month.values(), "month_start": f"{month.start.isoformat()}T00:00:00",
            "month_end": f"{month.end.isoformat()}T23:59:59",
            "next_month_start": f"{month.next_start.isoformat()}T00:00:00"}


def odata_path(entity: str, params: list[tuple[str, str]]) -> str:
    query = "&".join(f"{k}={quote(v, safe=VALUE_SAFE)}" for k, v in params if v != "")
    return quote(entity, safe=PATH_SAFE) + (f"?{query}" if query else "")


def lookup(row: dict, path: str):
    value = row
    for part in path.split("/"):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def to_number(value) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).replace(" ", "").replace(",", "."))
    except ValueError:
        return None


def parse_metadata(content: bytes) -> dict[str, set[str]]:
    """$metadata (EDMX, CSDL) → имена наборов (EntitySet), типов (EntityType) и функций (FunctionImport).
    Объявления DTD и сущностей не принимаются (защита от «бомб» XML)."""
    head = content[:4096].decode("utf-8", errors="replace").upper()
    if "<!DOCTYPE" in head or "<!ENTITY" in content.decode("utf-8", errors="replace").upper():
        raise IntegrationError("1С вернула $metadata с объявлениями DTD — такой ответ не принимается",
                               code="bad_response")
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        raise IntegrationError("Ответ на $metadata — не XML: проверьте адрес (он заканчивается на "
                               "/odata/standard.odata), возможно, отвечает страница входа или прокси",
                               code="bad_response", short="1С вернула неожиданный ответ на $metadata") from None
    out: dict[str, set[str]] = {"EntitySet": set(), "EntityType": set(), "FunctionImport": set()}
    for element in root.iter():
        tag = element.tag.rsplit("}", 1)[-1]
        if tag in out and element.get("Name"):
            out[tag].add(element.get("Name"))
    if not out["EntitySet"] and not out["EntityType"]:
        raise IntegrationError("В $metadata нет ни одного набора — проверьте адрес и состав стандартного интерфейса "
                               "OData базы", code="bad_response")
    return out


class OData:
    """Чтение наборов OData 1С постранично; ошибки 1С (odata.error) — понятным текстом."""

    def __init__(self, client: HttpClient, page: int):
        self.client = client
        self.page = page

    def get(self, path: str, what: str) -> dict:
        resp = self.client.request("GET", path, expect=(200, 400, 404, 500))
        if resp.status != 200:
            try:
                error = (resp.json() or {}).get("odata.error") or {}
            except (ValueError, UnicodeDecodeError, AttributeError):
                error = {}
            message = error.get("message") if isinstance(error, dict) else None
            text = (message.get("value") if isinstance(message, dict) else message) or ""
            hint = " — проверьте, что объект в составе стандартного интерфейса OData" if resp.status == 404 else ""
            raise IntegrationError(f"1С отклонила {what} ({resp.status}){': ' + str(text)[:300] if text else ''}{hint}",
                                   code="query", status=resp.status)
        return self.client.parse(resp, dict)

    def rows(self, entity: str, params: list[tuple[str, str]], what: str) -> list[dict]:
        out: list[dict] = []
        skip, server_paging = 0, False
        path = odata_path(entity, [*params, ("$top", str(self.page)), ("$skip", "0")])
        for _ in range(MAX_PAGES):
            data = self.get(path, what)
            value = data.get("value")
            if not isinstance(value, list):
                raise IntegrationError(f"1С вернула на {what} ответ без списка value", code="bad_response")
            out.extend(v for v in value if isinstance(v, dict))
            if len(out) > MAX_ROWS:
                raise IntegrationError(f"{what}: больше {MAX_ROWS} строк — сузьте $filter", code="too_large")
            link = data.get("odata.nextLink") or data.get("@odata.nextLink")
            if link:
                path = str(link) if re.match(r"^https?://", str(link), re.IGNORECASE) else str(link).lstrip("/")
                server_paging = True
                continue
            if server_paging or len(value) != self.page:
                return out
            skip += self.page
            path = odata_path(entity, [*params, ("$top", str(self.page)), ("$skip", str(skip))])
        raise IntegrationError(f"{what}: больше {MAX_PAGES} страниц", code="too_large")  # pragma: no cover


class Departments:
    """Подразделение 1С → подразделение структуры."""

    def __init__(self, units: metrics.Units, explicit: dict[str, str], mode: str, load):
        self.units, self.explicit, self.mode, self._load = units, explicit, mode, load
        self._catalog: dict[str, tuple[str, str]] | None = None

    def catalog(self) -> dict[str, tuple[str, str]]:
        if self._catalog is None:
            self._catalog = self._load()
        return self._catalog

    def label(self, value) -> str:
        raw = str(value or "").strip()
        if not raw or raw == EMPTY_REF:
            return "без подразделения"
        if GUID.match(raw) and raw.casefold() in (self._catalog or {}):
            code, description = self._catalog[raw.casefold()]
            return f"{description} ({code})" if code else description
        return raw or "без подразделения"

    def unit(self, value) -> int | None:
        raw = str(value or "").strip()
        if not raw or raw == EMPTY_REF:
            return None
        if raw.casefold() in self.explicit:
            return self.units.find(self.explicit[raw.casefold()])[0]
        code, description = raw, raw
        if GUID.match(raw):
            if self.mode == "map" and all(GUID.match(k) for k in self.explicit):
                return None
            code, description = self.catalog().get(raw.casefold(), ("", ""))
            for key in (code, description):
                if key and key.casefold() in self.explicit:
                    return self.units.find(self.explicit[key.casefold()])[0]
        if self.mode == "code" and code:
            return self.units.by_code.get(code.strip().casefold())
        if self.mode == "name" and description:
            found = self.units.by_name.get(name_key(description), [])
            return found[0] if len(found) == 1 else None
        return None


@register
class OneCConnector(Connector):
    kind = "onec"
    order = 70
    counter_labels = {"rows": "строк 1С", "rows_unmapped": "строк без подразделения"}
    title = "1С (OData)"
    description = (
        "Значения показателей сквозного отчёта из 1С (ЗУП, Бухгалтерия) через стандартный интерфейс OData "
        "по настроенным запросам — суммы, количества и средние по подразделениям, помесячно. Подключение — "
        "пользователь 1С с правом на чтение опубликованных объектов; узлы ограничивает ONEC_ALLOWED_HOSTS.\n\n"
        "Другой путь — 1С сама отправляет файл во «Входящие» (POST /api/inbound/v1/files с ключом интеграции, "
        "набор indicators: столбцы Подразделение, Показатель, Период, Значение — или любой другой набор). "
        "Пример для 1С:\n" + INBOX_SNIPPET)
    fields = (
        Field("base_url", "Адрес OData", "url", required=True,
              placeholder="https://1c.company.ru/zup/odata/standard.odata",
              hint="Адрес публикации базы на веб-сервере с /odata/standard.odata в конце (стандартный интерфейс OData "
                   "включается в конфигураторе: «Администрирование → Публикация на веб-сервере», состав — обработкой "
                   "«Настройка автоматического REST-сервиса» или УстановитьСоставСтандартногоИнтерфейсаOData)"),
        Field("login", "Пользователь 1С", required=True, hint="Отдельный пользователь с правами только на чтение"),
        Field("password", "Пароль", "password", required=True, secret=True,
              hint="Хранится зашифрованным и уходит только на адрес, для которого введён"),
        Field("verify_tls", "Проверять сертификат", "bool", default=True,
              hint="Выключайте только для самоподписанного или корпоративного сертификата"),
        Field("queries", "Запросы", "json", required=True, hint=QUERIES_HINT, placeholder=QUERIES_EXAMPLE),
        Field("department_catalog", "Справочник подразделений 1С", default="Catalog_ПодразделенияОрганизаций",
              hint="Набор, по Ref_Key которого находятся код (Code) и наименование (Description) подразделения 1С"),
        Field("department_match", "Сопоставление подразделений", "select", default="code",
              options=(Option("code", "По коду: код подразделения 1С = код у нас"),
                       Option("name", "По наименованию: наименование 1С = название у нас"),
                       Option("map", "Только по списку соответствий")),
              hint="Список соответствий ниже всегда сильнее"),
        Field("department_map", "Соответствие подразделений", "list",
              placeholder="000000012 = SALES, Бухгалтерия = FIN",
              hint="Строки «Ref_Key, код или наименование подразделения 1С = код или путь подразделения у нас»"),
        Field("page_size", "Строк на страницу", "int", default=1000, min=50, max=5000,
              hint="$top одного запроса к 1С; следующие страницы — $skip или odata.nextLink"),
        metrics.months_field(),
        metrics.owner_field("finance"),
    )
    actions = (
        Action("load", "Загрузить данные",
               "Выполнить запросы за текущий и прошлый месяц (или за настроенное число месяцев) и записать значения "
               "по подразделениям в сквозной отчёт"),
        Action("preview", "Проверить без записи",
               "Выполнить запросы и показать план — без записи и без создания показателей", schedulable=False),
    )

    @classmethod
    def validate_config(cls, config: dict) -> dict:
        out = super().validate_config(config)
        if out.get("base_url") and not out["base_url"].lower().endswith("/odata/standard.odata"):
            raise ValidationFailed("Адрес OData заканчивается на /odata/standard.odata "
                                   "(https://1c.company.ru/zup/odata/standard.odata)",
                                   fields={"config.base_url": "Нужен адрес …/odata/standard.odata"})
        if not parse_queries(out["queries"]):
            raise ValidationFailed("Добавьте хотя бы один запрос", fields={PLACE: "Нет запросов"})
        out["queries"] = metrics.load_list(out["queries"], PLACE, "")
        out["department_catalog"] = out.get("department_catalog") or "Catalog_ПодразделенияОрганизаций"
        metrics.parse_pairs(out.get("department_map"), "config.department_map", "Соответствие подразделений")
        return out

    def client(self) -> HttpClient:
        return self.http(auth=(self.config.get("login") or "", self.secrets.get("password") or ""))

    def queries(self) -> list[Query]:
        try:
            return parse_queries(self.config.get("queries"))
        except ValidationFailed as exc:
            raise IntegrationError(f"Запросы: {exc.detail}", code="config",
                                   short="Запросы подключения 1С заданы с ошибкой") from None

    def needs_catalog(self, queries: list[Query]) -> bool:
        """Справочник нужен, чтобы по Ref_Key узнать код и наименование подразделения 1С."""
        by_text = self.config.get("department_match") != "map" or any(
            not GUID.match(k) for k in metrics.parse_pairs(self.config.get("department_map"), "", ""))
        return by_text and any(q.department_field for q in queries)

    def problems(self, meta: dict[str, set[str]], queries: list[Query]) -> list[str]:
        sets = meta["EntitySet"]
        out = []
        for query in queries:
            if query.base in sets:
                continue
            virtual = VIRTUAL.match(query.base)
            if virtual and virtual.group("base") in sets:
                out.append(f"{query.title}: «{query.base}» — не набор; виртуальная таблица задаётся так: "
                           f"{virtual.group('base')}/{virtual.group('table')}(…)")
                continue
            similar = sorted(s for s in sets if s.casefold().startswith(query.base.split("_")[0].casefold()))
            out.append(f"{query.title}: набора «{query.base}» нет в $metadata — добавьте объект в состав "
                       "стандартного интерфейса OData" + (f" (есть, например: {', '.join(similar[:5])})"
                                                          if similar else ""))
        catalog = self.config.get("department_catalog") or ""
        if self.needs_catalog(queries) and catalog not in sets:
            out.append(f"справочника подразделений «{catalog}» нет в $metadata — без него подразделения 1С "
                       "сопоставляются только по списку соответствий")
        return out

    def check(self) -> CheckResult:
        queries = self.queries()
        with self.client() as client:
            content = client.request("GET", "$metadata", headers={"Accept": "application/xml"}).content
        meta = parse_metadata(content)
        problems = self.problems(meta, queries)
        sets = len(meta["EntitySet"])
        details = {"entity_sets": sets, "queries": len(queries), "problems": problems}
        if problems:
            return CheckResult(False, f"Подключено, опубликовано наборов: {sets}; в запросах ошибки: "
                                      + "; ".join(problems), details)
        warnings = metrics.diagnose([q.indicator.key for q in queries], [q.unit_code for q in queries if q.unit_code]
                                    + list(metrics.parse_pairs(self.config.get("department_map"), "", "").values()))
        details["warnings"] = warnings
        message = f"Подключено, опубликовано наборов: {sets}; запросов: {len(queries)}, наборы на месте"
        return CheckResult(True, message + (". Внимание: " + "; ".join(warnings) if warnings else ""), details)

    # --- запуск
    def load_catalog(self, odata: OData) -> dict[str, tuple[str, str]]:
        catalog = self.config.get("department_catalog") or "Catalog_ПодразделенияОрганизаций"
        rows = odata.rows(catalog, [("$format", "json"), ("$select", "Ref_Key,Code,Description")],
                          f"справочник «{catalog}»")
        return {str(r.get("Ref_Key") or "").casefold(): (str(r.get("Code") or "").strip(),
                                                          str(r.get("Description") or "").strip())
                for r in rows if r.get("Ref_Key")}

    def run(self, action: str, ctx: RunContext) -> RunResult:
        self.action(action)
        preview = action == "preview"
        queries = self.queries()
        months = metrics.window(self.config.get("months") or 2)
        owner, origin = self.config.get("owner_service") or "finance", f"подключение «{self.name}» (1С, OData)"
        specs = [q.indicator for q in queries]
        targets = metrics.ensure_indicators(ctx, specs, owner, origin, create=False)
        units = metrics.Units.load(ctx.db)
        explicit = metrics.parse_pairs(self.config.get("department_map"), "config.department_map",
                                       "Соответствие подразделений")
        errors = list(targets.problems.values())
        failed: set[str] = set()
        cells: list[metrics.Cell] = []
        unmapped: Counter = Counter()
        rows_total = 0
        with self.client() as client:
            odata = OData(client, int(self.config.get("page_size") or 1000))
            departments = Departments(units, explicit, self.config.get("department_match") or "code",
                                      lambda: self.load_catalog(odata))
            for query in queries:
                if not targets.usable(query.indicator.key):
                    continue
                fixed = None
                if query.unit_code:
                    fixed, problem = units.find(query.unit_code)
                    if fixed is None:
                        errors.append(f"{query.title}: {problem}")
                        failed.add(query.indicator.key)
                        continue
                for month in months:
                    values = month_values(month)
                    params = [("$format", "json"), ("$filter", metrics.render(query.filter, values)),
                              ("$select", query.select), ("$expand", query.expand)]
                    try:
                        rows = odata.rows(metrics.render(query.entity, values), params,
                                          f"запрос «{query.name}» за {month.label.lower()}")
                    except IntegrationError as exc:
                        if exc.code not in ("query", "too_large"):
                            raise
                        errors.append(exc.detail)
                        failed.add(query.indicator.key)
                        continue
                    rows_total += len(rows)
                    totals: dict[int, list[float]] = defaultdict(list)
                    for row in rows:
                        unit = fixed if fixed is not None else departments.unit(lookup(row, query.department_field))
                        if unit is None:
                            unmapped[departments.label(lookup(row, query.department_field))] += 1
                            continue
                        if query.aggregate == "count":
                            totals[unit].append(1.0)
                            continue
                        value = to_number(lookup(row, query.value_field))
                        if value is not None:
                            totals[unit].append(value)
                    for unit, values_list in totals.items():
                        if not values_list:
                            continue
                        total = sum(values_list) if query.aggregate != "avg" else sum(values_list) / len(values_list)
                        cells.append(metrics.Cell(query.indicator.key, unit, month, round(total * query.scale, 6),
                                                  f"из 1С: «{query.name}», строк — {len(values_list)}"))
            stats = client.stats()
        summable = {q.indicator.key for q in queries if q.aggregate != "avg"} - failed
        cells = metrics.zero_fill(ctx, cells, months, summable, units, "из 1С")
        cells = metrics.branch_totals(cells, units.snap, summable)
        if not preview:
            known = set(targets.problems)
            metrics.create_pending(ctx, targets, specs, owner, origin, {c.indicator for c in cells})
            errors += [p for k, p in targets.problems.items() if k not in known]
        ready = [c for c in cells if c.indicator in targets.found]
        written = metrics.write(ctx, ready, units, apply=not preview, label="")
        if not preview:
            metrics.remember(ctx, [c for c in ready if c.indicator in summable], months,
                             keep=failed | (set(q.indicator.key for q in queries) - set(targets.found)))
        parts = [written.text(preview), f"строк 1С: {rows_total}"]
        warnings = []
        if unmapped:
            parts.append(f"строк без подразделения: {sum(unmapped.values())}")
            warnings.append("строки подразделений 1С без соответствия не учтены: " + ", ".join(
                f"{who} — {n}" for who, n in unmapped.most_common(10)))
        if targets.created:
            parts.append("созданы показатели: " + ", ".join(f"«{k}»" for k in targets.created))
        pending = metrics.Pending.of(cells, targets, units, preview=preview,
                                     room=metrics.SAMPLE_ROWS - len(written.sample))
        parts += pending.parts
        counters = {**written.counters(), **pending.counters, "rows": rows_total,
                    "rows_unmapped": sum(unmapped.values()), "indicators_created": len(targets.created),
                    "errors": len(errors)}
        details = {"months": [m.key for m in months], "values": written.sample + pending.sample, "requests": stats,
                   **({"unmapped": dict(unmapped.most_common(50))} if unmapped else {}),
                   **({"errors": errors[:50]} if errors else {}), **({"warnings": warnings} if warnings else {})}
        message = " · ".join(parts) + (". Внимание: " + "; ".join(warnings) if warnings else "")
        if errors and not cells:
            return RunResult.failed("Ни одно значение не посчитано: " + "; ".join(errors[:5]), counters=counters,
                                    details=details)
        if errors:
            return RunResult.partial(message, "; ".join(errors[:10]), counters=counters, details=details)
        return RunResult.ok(message, counters=counters, details=details)

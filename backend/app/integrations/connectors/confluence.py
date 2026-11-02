"""Confluence: публикация сквозного отчёта страницей (ADR-0011) — клиент и публикация как в burndown_tool.

Страница — формат хранения Confluence (XHTML с макросами): вступление (страница обновляется автоматически),
панель статуса (tip / note / warning) с «почему такой статус», таблица подразделений и показателей с макросами
статуса Green / Yellow / Red / Grey, нарушения полноты данных, заметки руководителей и ссылка на отчёт.

Публикуется полный сквозной отчёт, как его видит администратор (reports.company_scorecard: вся компания или
выбранная ветка, все уровни, все классы данных, кроме скрытых настройкой «Скрыть финансовые показатели»): права
читателей страницы настраиваются в Confluence. Период — последний завершённый месяц (со сдвигом «Сдвиг периода»).
Ссылка «Открыть сквозной отчёт» ведёт на PUBLIC_URL/reports (переменная окружения сервера; не задана — без ссылки).

Публикация: страница ищется по сохранённому id (ctx.state, режим «одна страница»), затем по названию
в пространстве; найдена — обновляется с версией + 1 (на 409 «версия устарела» — перечитать и повторить один
раз), иначе создаётся под родительской страницей. Режим «каждую неделю» — новая страница на неделю
(к названию добавляется «— неделя N (дд.мм–дд.мм.гггг)», повтор в ту же неделю обновляет её).
"""
from __future__ import annotations

import html
import re
from datetime import timedelta
from urllib.parse import quote

from ...core.config import settings
from ...core.errors import ValidationFailed
from ...core.timeutil import local_now
from ...services import reports, traffic_light
from ...services.registry import DATA_CLASSES
from ..base import Action, CheckResult, Connector, Field, Option, RunContext, RunResult, register
from ..http import HttpClient, IntegrationError, error_text
from . import _atlassian as atlassian
from . import _metrics as metrics

PRODUCT = "Confluence"
SPACE_KEY = re.compile(r"^[A-Za-z0-9~_]{1,255}$")
TITLE_VARS = ("period", "period_key", "root")
DEFAULT_TITLE = "Сквозной отчёт компании"
STATUS_COLOURS = {"green": "Green", "yellow": "Yellow", "red": "Red", "gray": "Grey"}
PANELS = {"green": "tip", "yellow": "note", "red": "warning", "gray": "info"}
TABLE_COLUMNS = 8
VERSION_MESSAGE = "Дашборды компании: сквозной отчёт"
RIGHTS_HINT = ("Публикуется полный сквозной отчёт, как его видит администратор: вся компания (или выбранная "
               "ветка), все уровни и все классы данных, кроме скрытых ниже. Кто увидит страницу, решают права "
               "пространства и страницы в Confluence — выберите пространство с нужным кругом читателей")


def esc(value) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def status_macro(colour: str, title: str) -> str:
    return ('<ac:structured-macro ac:name="status"><ac:parameter ac:name="colour">' + colour +
            '</ac:parameter><ac:parameter ac:name="title">' + esc(title) + '</ac:parameter></ac:structured-macro>')


def light_macro(light: str, title: str | None = None) -> str:
    return status_macro(STATUS_COLOURS.get(light, "Grey"), title or traffic_light.LIGHT_LABELS.get(light, light))


def _table(head: list[str], rows: list[list[str]]) -> str:
    return ("<table><tbody><tr>" + "".join(f"<th>{esc(h)}</th>" for h in head) + "</tr>" +
            "".join("<tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>" for row in rows) + "</tbody></table>")


def _cell(cell: dict | None) -> str:
    if cell is None:
        return "—"
    if cell["missing"]:
        return status_macro("Red", traffic_light.MISSING_LABEL)
    value = reports.fmt_number(cell["value"])
    out = light_macro(cell["status"], value) if cell["status"] in ("green", "yellow", "red") else esc(value)
    if cell["target"] is not None and cell["value"] is not None:
        out += f"<br/><sub>цель {esc(reports.fmt_number(cell['target']))}</sub>"
    return out


def report_storage(data: dict, *, scope_text: str, updated: str, app_url: str = "") -> str:
    """Сквозной отчёт (scorecard_data) в формате хранения Confluence."""
    summary, units = data["summary"], data["units"]
    by_id = {u["id"]: u for u in units}
    light = summary["status"]
    out = [f"<p>Сквозной отчёт «Дашборды компании» за {esc(data['period_label'].lower())}: {esc(scope_text)}. "
           f"Страница обновляется автоматически — правки на ней будут заменены при следующей публикации. "
           f"Обновлено {esc(updated)}.</p>"]
    reasons = []
    for root in data["roots"]:
        unit = by_id.get(root)
        if unit is None:
            continue
        explanation = unit["explanation"]
        rated = unit.get("rated_count", unit["indicator_count"])
        head = (f"<p><strong>{esc(unit['name'])}</strong> — {esc(unit['status_label'].lower())}, статус по {rated} "
                f"показателям</p>" if rated else
                f"<p><strong>{esc(unit['name'])}</strong> — нет оценённых показателей за период</p>")
        lines = [item["text"] for item in explanation["items"]] or [explanation["text"]]
        if explanation["more"]:
            lines.append(f"и ещё {explanation['more']}")
        reasons.append(head + "<ul>" + "".join(f"<li>{esc(line)}</li>" for line in lines) + "</ul>")
    counts = summary["units"]
    tally = (f"Подразделений: критично — {counts.get('red', 0)}, внимание — {counts.get('yellow', 0)}, "
             f"норма — {counts.get('green', 0)}, нет оценки — {counts.get('gray', 0)}. "
             f"Нарушений полноты данных: {summary['missing_total']}.")
    out.append(f'<ac:structured-macro ac:name="{PANELS.get(light, "info")}"><ac:parameter ac:name="title">'
               f"Статус: {esc(summary['status_label'])}</ac:parameter><ac:rich-text-body>"
               "<p><strong>Почему такой статус</strong></p>" + "".join(reasons) + f"<p>{esc(tally)}</p>"
               "</ac:rich-text-body></ac:structured-macro>")
    indicators = data["indicators"]
    if not units:
        out.append("<p>В структуре компании нет подразделений.</p>")
    for start in range(0, max(len(indicators), 1), TABLE_COLUMNS):
        if not units:
            break
        chunk = indicators[start:start + TABLE_COLUMNS]
        out.append("<h2>Подразделения и показатели" + (" (продолжение)" if start else "") + "</h2>")
        head = ["Подразделение", "Статус", *[i["name"] + (f", {i['unit']}" if i["unit"] else "") for i in chunk]]
        rows = []
        for unit in units:
            indent = "&#160;" * 4 * unit["depth"]
            name = esc(unit["name"]) if unit["depth"] else f"<strong>{esc(unit['name'])}</strong>"
            status = light_macro(unit["status"], unit["status_label"]) + (" под контролем" if unit.get("note") else "")
            rows.append([indent + name, status, *[_cell(unit["cells"].get(i["key"])) for i in chunk]])
        out.append(_table(head, rows))
    if not indicators and units:
        out.append("<p>В каталоге нет активных показателей.</p>")
    violations = summary["violations"]
    out.append("<h2>Нарушения полноты данных</h2>")
    if violations:
        out.append(_table(["Подразделение", "Показатель"], [[esc(v["path"]), esc(v["indicator_name"])]
                                                            for v in violations]))
    else:
        out.append("<p>Все ожидаемые значения за период заполнены.</p>")
    notes = [u for u in units if u.get("note")]
    if notes:
        out.append("<h2>Заметки руководителей</h2>" + _table(
            ["Подразделение", "Заметка", "Автор"],
            [[esc(u["path"]), esc(f"{u['note']['status_label']}: {u['note']['comment']}"),
              esc((u["note"].get("author") or {}).get("full_name", ""))] for u in notes]))
    if app_url:
        out.append(f'<p><a href="{esc(app_url)}/reports">Открыть сквозной отчёт в «Дашбордах компании»</a> — '
                   "с панелью подразделения, динамикой за 12 месяцев и вводом значений.</p>")
    else:
        out.append("<p>Подробности — в разделе «Сквозной отчёт» «Дашбордов компании».</p>")
    return "".join(out)


class Pages:
    """Страницы Confluence через REST API content (как ConfluenceClient в burndown_tool)."""

    def __init__(self, client: HttpClient):
        self.client = client

    def _json(self, method: str, path: str, *, allow: tuple[int, ...] = (), not_found: str | None = None, **kwargs):
        resp = atlassian.call(self.client, PRODUCT, method, path, allow=allow, not_found=not_found, **kwargs)
        return resp, (self.client.parse(resp, dict) if resp.status in (200, 201) else None)

    def get(self, page_id: str) -> dict | None:
        resp, data = self._json("GET", f"rest/api/content/{quote(str(page_id))}", allow=(404,),
                                params={"expand": "version,space"})
        return data if resp.status == 200 else None

    def find(self, space: str, title: str) -> dict | None:
        _, data = self._json("GET", "rest/api/content", params={"spaceKey": space, "title": title, "type": "page",
                                                                "expand": "version,space"})
        results = data.get("results") or []
        return results[0] if results and isinstance(results[0], dict) else None

    def url(self, page: dict) -> str:
        links = page.get("_links") or {}
        webui = str(links.get("webui") or "")
        base = str(links.get("base") or self.client.base_url).rstrip("/")
        return f"{base}{webui}" if webui.startswith("/") else self.client.base_url

    def update(self, page: dict, space: str, title: str, body: str) -> dict:
        for attempt in (1, 2):
            version = int((page.get("version") or {}).get("number") or 1) + 1
            resp, data = self._json("PUT", f"rest/api/content/{quote(str(page['id']))}", allow=(409,), json={
                "id": str(page["id"]), "type": "page", "title": title, "space": {"key": space},
                "version": {"number": version, "message": VERSION_MESSAGE},
                "body": {"storage": {"value": body, "representation": "storage"}}},
                not_found=f"Страница {page['id']} пропала из Confluence во время публикации — повторите")
            if resp.status != 409:
                return {**data, "version": data.get("version") or {"number": version}}
            fresh = self.get(page["id"]) if attempt == 1 else None
            if fresh is None:
                break
            page = fresh
        raise IntegrationError(f"Страницу «{title}» одновременно изменили в Confluence (версия устарела, 409) — "
                               "опубликуйте отчёт ещё раз", code="conflict",
                               short="Страницу одновременно изменили в Confluence — опубликуйте ещё раз")

    def create(self, space: str, title: str, body: str, parent_id: str | None) -> dict:
        payload: dict = {"type": "page", "title": title, "space": {"key": space},
                         "body": {"storage": {"value": body, "representation": "storage"}}}
        if parent_id:
            payload["ancestors"] = [{"id": str(parent_id)}]
        resp, data = self._json("POST", "rest/api/content", allow=(400,), json=payload,
                                not_found="Родительская страница или пространство не найдены — проверьте настройки")
        if resp.status == 400:
            text = error_text(resp)
            if "title" in text.lower() and "exist" in text.lower():
                raise IntegrationError(f"Страница «{title}» уже есть в пространстве {space}, но не найдена поиском "
                                       "(возможно, она в корзине) — восстановите или удалите её либо измените шаблон "
                                       "названия", code="title_taken",
                                       short=f"Страница «{title}» уже есть в пространстве Confluence")
            raise IntegrationError(f"Confluence не создала страницу: {text or 'ошибка в запросе (400)'}",
                                   code="http_error", short="Confluence не создала страницу", status=400)
        return data


@register
class ConfluenceConnector(Connector):
    kind = "confluence"
    order = 40
    # Публикует полный сквозной отчёт (как у администратора — финансовые и персональные данные всей компании):
    # пользователь с integrations.manage без роли администратора не должен выносить его наружу
    admin_only = True
    admin_only_reason = "публикует полный сквозной отчёт"
    counter_labels = {"version": "версия страницы", "created": "страница создана", "units": "подразделений",
                      "indicators": "показателей", "violations": "нарушений полноты"}
    detail_labels = {"space": "Пространство", "space_name": "Название пространства"}
    title = "Confluence"
    description = ("Публикация сквозного отчёта страницей Confluence по расписанию: одна страница, которая "
                   "обновляется, или новая страница каждую неделю; статусы — макросами Confluence. Публикуется "
                   "полный отчёт, как его видит администратор, — права читателей настраиваются в Confluence. "
                   "Узлы ограничивает CONFLUENCE_ALLOWED_HOSTS")
    fields = (
        *atlassian.connection_fields(
            "Confluence", "https://confluence.company.ru",
            "Server — адрес, по которому Confluence открывается в браузере (с путём, если он есть); "
            "Cloud — с /wiki: https://company.atlassian.net/wiki"),
        Field("space", "Пространство (ключ)", required=True, placeholder="REPORTS", hint=RIGHTS_HINT),
        Field("parent_id", "Родительская страница (id)", placeholder="123456",
              hint="Числовой id страницы из её адреса (…pageId=123456 или /pages/123456/); пусто — в корне "
                   "пространства"),
        Field("title", "Название страницы", default=DEFAULT_TITLE,
              hint="Подстановки: {period} — «Октябрь 2026», {period_key} — 2026-10, {root} — вершина отчёта. "
                   "В режиме «каждую неделю» к названию добавляется неделя"),
        Field("mode", "Режим", "select", default="single",
              options=(Option("single", "Одна страница — обновляется при каждой публикации"),
                       Option("weekly", "Новая страница каждую неделю")),
              hint="Одна страница находится по сохранённому id, затем по названию; еженедельная — по названию"),
        Field("root", "Вершина отчёта", placeholder="Код или путь подразделения",
              hint="Подразделение, с которого начинается отчёт (код или путь через «/»); пусто — вся компания"),
        Field("period_offset", "Сдвиг периода", "int", default=0, min=0, max=24,
              hint="0 — последний завершённый месяц (по умолчанию), 1 — месяцем раньше и т. д."),
        Field("hide_financial", "Скрыть финансовые показатели", "bool", default=True,
              hint="Выручка, затраты, ФОТ и другие показатели класса «Финансовые» не попадут на страницу. "
                   + RIGHTS_HINT),
    )
    actions = (Action("publish", "Опубликовать сквозной отчёт",
                      "Отчёт за последний завершённый месяц — страницей в Confluence: обновить её (версия + 1) "
                      "или создать"),)

    @classmethod
    def validate_config(cls, config: dict) -> dict:
        out = super().validate_config(config)
        if out.get("instance") == "cloud" and out.get("base_url") and not out["base_url"].lower().endswith("/wiki"):
            raise ValidationFailed("Адрес Confluence Cloud — с /wiki: https://company.atlassian.net/wiki",
                                   fields={"config.base_url": "Для Cloud — с /wiki"})
        if out.get("space") and not SPACE_KEY.match(out["space"]):
            raise ValidationFailed("Ключ пространства — латиница, цифры, «_» или «~» (например, REPORTS)",
                                   fields={"config.space": "Латиница, цифры, «_», «~»"})
        if out.get("parent_id") and not out["parent_id"].isdigit():
            raise ValidationFailed("Родительская страница — числовой id из адреса страницы Confluence",
                                   fields={"config.parent_id": "Число"})
        out["title"] = " ".join((out.get("title") or DEFAULT_TITLE).split())[:200]
        metrics.check_template(out["title"], TITLE_VARS, "Название страницы", "config.title")
        return out

    def client(self) -> HttpClient:
        return self.http(**atlassian.client_options(self.config, self.secrets))

    def check(self) -> CheckResult:
        space_key = self.config.get("space") or ""
        with self.client() as client:
            me = atlassian.get_json(client, PRODUCT, "rest/api/user/current")
            if me.get("type") == "anonymous":
                raise IntegrationError("Confluence приняла запрос как анонимный — проверьте email (логин) и токен",
                                       code="auth", short="Confluence не узнала учётную запись подключения")
            space = atlassian.get_json(client, PRODUCT, f"rest/api/space/{quote(space_key)}",
                                       not_found=f"Пространство {space_key} не найдено или нет прав на него")
            parent = None
            if self.config.get("parent_id"):
                parent = Pages(client).get(self.config["parent_id"])
        name = me.get("displayName") or me.get("username") or me.get("publicName") or "—"
        message = f"Подключено как {name} · пространство «{space.get('name') or space_key}» ({space_key})"
        warnings = []
        if self.config.get("parent_id"):
            if parent is None:
                warnings.append(f"родительская страница {self.config['parent_id']} не найдена или недоступна")
            elif (parent.get("space") or {}).get("key") not in (None, space_key):
                warnings.append(f"родительская страница {self.config['parent_id']} — в другом пространстве")
            else:
                message += f" · родительская страница «{parent.get('title') or parent.get('id')}»"
        if self.config.get("root"):
            warnings += metrics.diagnose([], [self.config["root"]])
        return CheckResult(True, message, {"user": name, "space": space_key, "space_name": space.get("name")},
                           warnings)

    # --- запуск
    def page_title(self, period_label: str, period_key: str, root: str) -> str:
        title = metrics.render(self.config.get("title") or DEFAULT_TITLE,
                               {"period": period_label, "period_key": period_key, "root": root})
        if self.config.get("mode") == "weekly":
            day = local_now().date()
            monday = day - timedelta(days=day.weekday())
            sunday = monday + timedelta(days=6)
            title += f" — неделя {day.isocalendar()[1]} ({monday:%d.%m}–{sunday:%d.%m.%Y})"
        return title[:255]

    def report(self, ctx: RunContext) -> tuple[dict, str, str]:
        st = reports.state(ctx.db)
        period = reports.add_months(reports.current_period(), -1 - int(self.config.get("period_offset") or 0))
        root_id = None
        if self.config.get("root"):
            root_id, problem = metrics.Units(st.snap).find(self.config["root"])
            if root_id is None:
                raise IntegrationError(f"Вершина отчёта: {problem}", code="config",
                                       short="Вершина отчёта в подключении не найдена")
        hide = bool(self.config.get("hide_financial", True))
        classes = [c for c in DATA_CLASSES if not (hide and c == "financial")]
        data = reports.company_scorecard(ctx.db, period, root_id, classes=classes)
        root_name = st.snap.units[root_id].name if root_id else (
            st.snap.units[st.snap.roots()[0]].name if len(st.snap.roots()) == 1 else "вся компания")
        scope = f"«{root_name}» с вложенными подразделениями" if root_id else "вся компания"
        if hide:
            scope += ", финансовые показатели скрыты"
        return data, root_name, scope

    def run(self, action: str, ctx: RunContext) -> RunResult:
        self.action(action)
        data, root_name, scope = self.report(ctx)
        title = self.page_title(data["period_label"], data["period"], root_name)
        body = report_storage(data, scope_text=scope, updated=local_now().strftime("%d.%m.%Y %H:%M"),
                              app_url=settings.public_url)
        space, mode = self.config["space"], self.config.get("mode") or "single"
        saved = ctx.state
        stored_id = saved.get("page_id") if mode == "single" and saved.get("space") == space and \
            saved.get("mode") == mode else None
        with self.client() as client:
            pages = Pages(client)
            page = pages.get(stored_id) if stored_id else None
            how = "по сохранённому id"
            if page is not None and (page.get("space") or {}).get("key") not in (None, space):
                page = None
            if page is None:
                page, how = pages.find(space, title), "по названию"
            if page is not None:
                result, created = pages.update(page, space, title, body), False
            else:
                result, created, how = pages.create(space, title, body, self.config.get("parent_id") or None), True, ""
            url = pages.url(result)
        version = int((result.get("version") or {}).get("number") or 1)
        page_id = str(result.get("id") or (page or {}).get("id") or "")
        ctx.state.update(page_id=page_id, page_url=url, space=space,
                         mode=mode, title=title, version=version, period=data["period"],
                         published_at=local_now().isoformat(timespec="seconds"))
        summary = data["summary"]
        verb = "Создана" if created else f"Обновлена (найдена {how})"
        message = (f"{verb} страница «{title}», версия {version}: отчёт за {data['period_label'].lower()}, "
                   f"статус «{summary['status_label']}», подразделений {len(data['units'])}, показателей "
                   f"{len(data['indicators'])}, нарушений полноты {summary['missing_total']}")
        counters = {"version": version, "created": int(created), "units": len(data["units"]),
                    "indicators": len(data["indicators"]), "violations": summary["missing_total"]}
        return RunResult.ok(message, counters=counters, details={"url": url, "page_id": page_id, "title": title,
                                                                  "period": data["period"]})

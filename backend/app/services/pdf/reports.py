"""PDF-отчёты служб."""
from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models import ColorPalette, NaumenTicket, TpWeeklyReport
from .. import hr as hr_service
from .. import naumen as naumen_service
from .. import partnerships as p_service
from .. import tp as tp_service
from .. import traffic_light
from .base import Report, fmt

LIGHT_TEXT = traffic_light.LIGHT_LABELS


def _palette(db: Session) -> dict | None:
    """Активная палитра. Вызывается последним обращением к базе: дальше отчёт только рисует,
    поэтому соединение сразу возвращается в пул (построение графиков занимает процессор)."""
    p = db.scalar(select(ColorPalette).where(ColorPalette.is_active.is_(True)).limit(1))
    colors = p.colors if p else None
    db.commit()
    return colors


def _filters_line(parts: dict[str, str | None]) -> str:
    shown = [f"{k}: {v}" for k, v in parts.items() if v]
    return " · ".join(shown) if shown else "Все данные"


# ---------------------------------------------------------------- служба персонала

def hr_dashboard(db: Session, months: list[str], scope: set[str] | None) -> bytes:
    data = hr_service.dashboard(db, months, scope)
    series = data["series"]
    period = f"{series[0]['label']} — {series[-1]['label']}" if len(series) > 1 else (series[0]["label"] if series
                                                                                      else "нет данных")
    rep = Report("Служба персонала — дашборд", f"Период: {period}", palette=_palette(db))
    if not series:
        return rep.build()
    # Как на экране: «последний» — последний месяц выборки с данными (пустой новый месяц не обнуляет отчёт)
    latest = data["latest"] or series[-1]
    totals = data["totals"]
    kpis = [("Принято за период", fmt(totals["hired"]), None), ("Уволено за период", fmt(totals["fired"]), None),
            ("Чистый прирост", fmt(totals["net"]), None)]
    for m in latest["metrics"]:
        if m["light"] != "gray" and m["value"] is not None:
            kpis.append((m["label"], fmt(m["value"], m["unit"]), m["light"]))
    rep.kpis(kpis[:12])

    colors = rep.series_colors()
    fig, ax = rep.figure()
    labels = [s["label"] for s in series]
    x = range(len(labels))
    ax.bar([i - 0.2 for i in x], [s["hired"] for s in series], 0.4, label="Принято", color=rep.light_hex("green"))
    ax.bar([i + 0.2 for i in x], [s["fired"] for s in series], 0.4, label="Уволено", color=rep.light_hex("red"))
    ax.set_xticks(list(x), labels, rotation=0 if len(labels) < 8 else 45, ha="center" if len(labels) < 8 else "right")
    rep.legend(ax)
    ax.set_title("Приём и увольнение", fontsize=10, loc="left")
    rep.chart(fig, 62)

    turnover = [next((m["value"] for m in s["metrics"] if m["key"] == "turnover"), None) for s in series]
    if any(v is not None for v in turnover):
        fig, ax = rep.figure(height=3)
        ax.plot(labels, turnover, marker="o", color=colors[0], linewidth=2)
        target = next((m["target"] for m in latest["metrics"] if m["key"] == "turnover"), None)
        if target is not None:
            ax.axhline(target, color=rep.light_hex("red"), linestyle="--", linewidth=1,
                       label=f"Цель {fmt(target, '%')}")
            rep.legend(ax)
        ax.set_title("Текучесть кадров, %", fontsize=10, loc="left")
        rep.chart(fig, 55)

    rep.h2(f"Метрики за {latest['label']}")
    rows, lights = [], []
    for m in latest["metrics"]:
        rows.append([m["label"], fmt(m["value"], m["unit"]), fmt(m["previous"], m["unit"]),
                     fmt(m["target"], m["unit"]), LIGHT_TEXT[m["light"]]])
        lights.append(m["light"])
    rep.table(["Метрика", "Значение", "Прошлый месяц", "Цель", "Оценка"], rows, [44, 14, 14, 12, 16], lights,
              align_right_from=1)
    return rep.build()


def hr_summary(db: Session, period_type: str, scope: set[str] | None) -> bytes:
    periods = hr_service.period_summary(db, period_type, scope)
    names = {"month": "месяцам", "quarter": "кварталам", "half": "полугодиям", "year": "годам"}
    defs = hr_service.definitions(db)
    rep = Report("Служба персонала — сводка", f"Сводка по {names.get(period_type, period_type)}", wide=True,
                 palette=_palette(db))
    if not periods:
        return rep.build()
    header = ["Показатель", *[p["label"] for p in periods]]
    rows = [["Принято", *[fmt(p["hired"]) for p in periods]], ["Уволено", *[fmt(p["fired"]) for p in periods]],
            ["Прирост", *[fmt(p["net"]) for p in periods]]]
    for d in defs:
        rows.append([d.label, *[fmt(p["metrics"].get(d.key), d.unit) for p in periods]])
    rep.table(header, rows, [30] + [12] * len(periods), align_right_from=1)
    fig, ax = rep.figure(width=12)
    labels = [p["label"] for p in periods]
    # Светофор — цветами светофора палитры, как на экране (а не цветами рядов графиков)
    ax.bar(labels, [p["light_counts"]["green"] for p in periods], color=rep.light_hex("green"), label="Норма")
    ax.bar(labels, [p["light_counts"]["yellow"] for p in periods],
           bottom=[p["light_counts"]["green"] for p in periods], color=rep.light_hex("yellow"), label="Внимание")
    ax.bar(labels, [p["light_counts"]["red"] for p in periods],
           bottom=[p["light_counts"]["green"] + p["light_counts"]["yellow"] for p in periods],
           color=rep.light_hex("red"), label="Критично")
    rep.legend(ax)
    ax.set_title("Светофор метрик по периодам", fontsize=10, loc="left")
    rep.spacer()
    rep.chart(fig, 60)
    return rep.build()


def hr_registry(db: Session, events: Sequence, filters: dict[str, str | None]) -> bytes:
    rep = Report("Служба персонала — реестр приёмов и увольнений", _filters_line(filters), wide=True,
                 palette=_palette(db))
    hired = sum(1 for e in events if e.event_type == "hired")
    rep.kpis([("Записей", fmt(len(events)), None), ("Приёмов", fmt(hired), "green"),
              ("Увольнений", fmt(len(events) - hired), "red")])
    rows = [[e.event_date.strftime("%d.%m.%Y"), "Приём" if e.event_type == "hired" else "Увольнение", e.full_name,
             e.position, e.department, e.employment_type] for e in events]
    rep.table(["Дата", "Событие", "ФИО", "Должность", "Подразделение", "Тип занятости"], rows,
              [10, 10, 26, 30, 22, 12], ["green" if e.event_type == "hired" else "red" for e in events])
    return rep.build()


def hr_targets(db: Session) -> bytes:
    rep = Report("Служба персонала — цели и бенчмарки", "Последнее фактическое значение в сравнении с целью",
                 palette=_palette(db))
    rows, lights = [], []
    for t in hr_service.target_rows(db):
        rows.append([t["metric_label"], t["year"], fmt(t["reference_value"], t["unit"]),
                     fmt(t["target_value"], t["unit"]), fmt(t["current_value"], t["unit"]), t["current_month"],
                     LIGHT_TEXT[t["status"]]])
        lights.append(t["status"])
    rep.table(["Метрика", "Год", "Справочно", "Цель", "Факт", "Месяц факта", "Оценка"], rows,
              [34, 8, 12, 12, 12, 14, 12], lights, align_right_from=1)
    return rep.build()


# ---------------------------------------------------------------- техподдержка

def _tp_rows(db: Session, year: int | None, weeks: int | None, week_from: int | None = None,
             week_to: int | None = None) -> list[TpWeeklyReport]:
    stmt = select(TpWeeklyReport).order_by(TpWeeklyReport.year, TpWeeklyReport.week)
    if year:
        stmt = stmt.where(TpWeeklyReport.year == year)
        if week_from:
            stmt = stmt.where(TpWeeklyReport.week >= week_from)
        if week_to:
            stmt = stmt.where(TpWeeklyReport.week <= week_to)
    rows = list(db.scalars(stmt))
    return rows[-weeks:] if weeks else rows


def tp_dashboard(db: Session, year: int | None, weeks: int | None, week_from: int | None = None,
                 week_to: int | None = None) -> bytes:
    rows = _tp_rows(db, year, weeks, week_from, week_to)
    period = f"{rows[0].period} — {rows[-1].period}" if rows else "нет данных"
    rules = traffic_light.rules_for(db, "tech")
    rep = Report("Техническая поддержка — недельный отчёт", f"Период: {period} · недель: {len(rows)}", wide=True,
                 palette=_palette(db))
    if not rows:
        return rep.build()
    last = rows[-1]
    kpis = []
    for key, rule in rules.items():
        if rule.enabled and key in tp_service.META_BY_KEY:
            meta = tp_service.META_BY_KEY[key]
            value = getattr(last, key)
            kpis.append((meta["label"], fmt(value, meta["unit"]), traffic_light.evaluate(value, rule)))
    rep.h2(f"Светофор — неделя {last.period}")
    rep.kpis(kpis)

    colors = rep.series_colors()
    labels = [r.period for r in rows]
    step = max(1, len(labels) // 14)
    fig, ax = rep.figure(width=12)
    ax.plot(labels, [r.new_received for r in rows], color=colors[1], linewidth=1.8, label="Принято новых")
    ax.plot(labels, [r.total_solved_week for r in rows], color=colors[2], linewidth=1.8, label="Решено")
    ax.plot(labels, [r.total_in_work for r in rows], color=colors[0], linewidth=1.4, linestyle="--",
            label="В работе")
    ax.set_xticks(range(0, len(labels), step), labels[::step], rotation=45, ha="right")
    rep.legend(ax, ncol=3)
    ax.set_title("Поток заявок по неделям", fontsize=10, loc="left")
    rep.chart(fig, 62)

    clients = ["rushydro_hours", "transneft_hours", "roscosmos_hours", "bryansk_hours", "mchs_hours",
               "internal_sales_hours"]
    totals = [sum(getattr(r, c) or 0 for r in rows) for c in clients]
    if any(totals):
        fig, ax = rep.figure(width=12, height=3)
        names = [tp_service.META_BY_KEY[c]["label"] for c in clients]
        ax.barh(names, totals, color=colors[: len(clients)])
        ax.invert_yaxis()
        ax.set_title("Трудозатраты по клиентам за период, ч", fontsize=10, loc="left")
        rep.chart(fig, 55)

    rep.h2("Детализация по неделям")
    keys = ["total_in_work", "avail_total", "new_received", "total_solved_week", "ratio_solved_received",
            "altos_avg_time", "altoffice_avg_time"]
    header = ["Неделя", *[tp_service.META_BY_KEY[k]["label"] for k in keys]]
    body = [[r.period, *[fmt(getattr(r, k)) for k in keys]] for r in reversed(rows)]
    rep.table(header, body, [10] + [12] * len(keys), align_right_from=1)
    return rep.build()


def naumen_report(db: Session, year: int | None, org: str | None, months: int | None) -> bytes:
    stmt = select(NaumenTicket).order_by(NaumenTicket.registered_at)
    tickets = [t for t in db.scalars(stmt)
               if (not year or (t.registered_at and t.registered_at.year == year)) and (not org or t.org == org)]
    if months:
        tickets = naumen_service.last_months_filter(tickets, months)
    data = naumen_service.summary(tickets)
    filters = _filters_line({"Год": str(year) if year else None, "Организация": org,
                             "Последние месяцы": str(months) if months else None})
    rep = Report("Техническая поддержка — заявки Naumen", filters, wide=True, palette=_palette(db))
    if data.get("empty"):
        return rep.build()
    rep.kpis([("Всего заявок", fmt(data["total"]), None), ("Закрыто", fmt(data["closed"]), "green"),
              ("В работе", fmt(data["in_progress"]), None),
              ("Просрочено", f"{fmt(data['overdue'])} ({fmt(data['overdue_pct'], '%')})", "red"),
              ("Возобновлено", f"{fmt(data['reopened'])} ({fmt(data['reopened_pct'], '%')})", "yellow"),
              ("Среднее время обработки", fmt(data["avg_proc_hours"], "ч"), None)])
    colors = rep.series_colors()
    months_data = data["months"]
    labels = [m["month"] for m in months_data]
    step = max(1, len(labels) // 16)
    fig, ax = rep.figure(width=12)
    x = range(len(labels))
    ax.bar([i - 0.2 for i in x], [m["registered"] for m in months_data], 0.4, color=colors[1], label="Принято")
    ax.bar([i + 0.2 for i in x], [m["solved"] for m in months_data], 0.4, color=colors[2], label="Решено")
    ax.set_xticks(list(x)[::step], labels[::step], rotation=45, ha="right")
    rep.legend(ax)
    ax.set_title("Принято и решено по месяцам", fontsize=10, loc="left")
    rep.chart(fig, 62)
    rep.h2("Организации")
    rows = [[o["org"], fmt(o["total"]), fmt(o["closed"]), fmt(o["overdue"]), fmt(o["overdue_pct"], "%"),
             fmt(o["avg_proc_hours"], "ч")] for o in data["orgs"][:25]]
    rep.table(["Организация", "Всего", "Закрыто", "Просрочено", "Доля просрочки", "Ср. обработка"], rows,
              [40, 10, 10, 10, 12, 12], align_right_from=1)
    return rep.build()


# ---------------------------------------------------------------- партнёрства

def partnerships_registry(db: Session, rows: Sequence[dict], filters: dict[str, str | None]) -> bytes:
    rep = Report("Технологические партнёрства — реестр", _filters_line(filters), wide=True, palette=_palette(db))
    rep.kpis([("Записей", fmt(len(rows)), None),
              ("Норма", fmt(sum(1 for r in rows if r["light"] == "green")), "green"),
              ("Внимание", fmt(sum(1 for r in rows if r["light"] == "yellow")), "yellow"),
              ("Критично", fmt(sum(1 for r in rows if r["light"] == "red")), "red")])
    body = [[r["partner"], r["product"], r["direction"], r["almi_product"], r["almi_version"], r["status"],
             r["cert_date"].strftime("%d.%m.%Y") if r["cert_date"] else "—", "да" if r["nda"] else "нет",
             "да" if r["agreement"] else "нет"] for r in rows]
    rep.table(["Партнёр", "Продукт", "Направление", "Продукт АЛМИ", "Версия", "Статус", "Сертификат", "NDA",
               "Соглашение"], body, [20, 18, 18, 12, 12, 10, 10, 5, 8], [r["light"] for r in rows])
    return rep.build()


def partnerships_summary(db: Session) -> bytes:
    rules = p_service.rule_map(db)
    from ...models import Partnership

    all_rows = list(db.scalars(select(Partnership)))
    rep = Report("Технологические партнёрства — сводка", "Сертификации по годам и светофор", palette=_palette(db))
    stats = p_service.analytics(all_rows)
    rep.kpis([("Всего", fmt(stats["total"]), None), ("NDA подписано", fmt(stats["nda_count"]), None),
              ("Соглашений", fmt(stats["agreement_count"]), None),
              ("Продуктов АЛМИ", fmt(len(stats["by_almi_product"])), None)])
    years = p_service.summary_by_year(all_rows, rules)
    if years:
        colors = rep.series_colors()
        fig, ax = rep.figure()
        labels = [str(y["year"]) for y in years]
        ax.bar(labels, [y["total"] for y in years], color=colors[1])
        ax.set_title("Сертификаты по годам", fontsize=10, loc="left")
        rep.chart(fig, 58)
        rep.h2("По годам")
        rep.table(["Год", "Всего", "Норма", "Внимание", "Критично", "NDA", "Соглашения"],
                  [[y["year"], y["total"], y["green"], y["yellow"], y["red"], y["nda_count"], y["agreement_count"]]
                   for y in years], align_right_from=1)
    rep.h2("Светофор")
    lights = p_service.light_rows(all_rows, rules)
    rep.table(["Группа", "Категория", "Записей", "Доля"],
              [[r["group"], r["label"], r["count"], fmt(r["share"], "%")] for r in lights], [20, 40, 12, 12],
              [r["light"] for r in lights], align_right_from=2)
    return rep.build()

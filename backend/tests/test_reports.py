"""Сквозные отчёты (ADR-0010): расчёт (свёртка, правила светофора, пропуски, статус подразделения,
объяснение), доступ по уровням сотрудников на демо-пользователях, «Обзор», периоды, PDF, кэш, скорость.

Демо-отчёт за июль 2026 (последний месяц данных служб): красные — затраты Технической службы и группы
AlterOS, заявки в работе Технической службы, план работ группы AlterOffice; жёлтые — выручка и план
работ Коммерческой службы, ФОТ Службы маркетинга, исполнение бюджета Коммерческой дирекции,
удовлетворённость клиентов группы AlterOS; «Выполнение плана работ» Службы маркетинга не заполнено.
"""
import statistics
import time
from dataclasses import replace
from datetime import date

import pytest
from sqlalchemy import event, insert, select, update

from app.models import Department, Indicator, IndicatorValue, ReportRevision
from app.schemas.reports import PeriodsOut, ReportSummaryOut, ScorecardOut, UnitReportOut
from app.services import reports as R
from app.services.org import OrgSnapshot, Unit

PASSWORDS = {"ceo": "ceo12345", "tech_dir": "td123456", "engineer": "en123456"}
FINANCIAL_WORDS = ("Выручка", "Затраты", "ФОТ", "Исполнение бюджета", "fin.", "млн ₽", '"financial"')
JULY = date(2026, 7, 1)


def _as(login, username):
    return login(username, PASSWORDS.get(username))


def _codes(admin) -> tuple[dict[str, int], dict[int, str]]:
    units = admin.get("/api/departments").json()
    return {u["code"]: u["id"] for u in units if u["code"]}, {u["id"]: u["code"] for u in units}


# ================================================================ расчёт: без базы

class _NoDb:
    """Сессия-заглушка: отчёт берёт значения из подготовленных слоёв, заметок нет."""

    def execute(self, *_args, **_kwargs):
        return []


ORG = (  # id, название, родитель, тип
    (1, "Компания", None, "company"),
    (2, "Дирекция А", 1, "division"),
    (4, "Отдел А1", 2, "department"),
    (5, "Отдел А2", 2, "department"),
    (3, "Дирекция Б", 1, "division"),
    (6, "Отдел Б1", 3, "department"),
    (7, "Группа Б1-1", 6, "group"),
)


def _snap() -> OrgSnapshot:
    snap = OrgSnapshot(revision=1)
    for order, (uid, name, parent, kind) in enumerate(ORG):
        snap.units[uid] = Unit(uid, name, parent, kind, order, None, None)
    for unit in sorted(snap.units.values(), key=lambda u: u.sort_order):
        snap.children.setdefault(unit.parent_id, []).append(unit.id)
    return snap


def _ind(ind_id: int, key: str, **fields) -> R.IndicatorDef:
    base = dict(id=ind_id, key=key, name=key, description="", unit="", data_class="operational",
                direction="higher_is_better", rollup="sum", rule_type="threshold", green_threshold=None,
                yellow_threshold=None, green_deviation=None, yellow_deviation=None, default_target=None,
                source_type="manual", source_key=None, owner_service="apparat_gd", expected_kinds=(), sort_order=ind_id,
                is_active=True, created=date(2025, 1, 1), since=date(2025, 1, 1))
    base.update(fields)
    return R.IndicatorDef(**base)


def _state(indicators, rows: dict, computed: dict | None = None) -> R.ReportState:
    snap = _snap()
    order = snap.ordered_units()
    by_kind: dict[str, list[int]] = {}
    for unit_id in order:
        by_kind.setdefault(snap.units[unit_id].kind, []).append(unit_id)
    st = R.ReportState(key=("test",), snap=snap, order=order, catalog=tuple(indicators),
                       active=[i for i in indicators if i.is_active], data=R.ServiceData(), service_units={},
                       kind_labels={}, units_by_kind=by_kind, sources=set())
    periods = set(rows) | {R.add_months(p, -1) for p in rows}
    for period in periods:
        st._layers[period] = R.build_layer(period, st.active, snap, order, rows.get(period, []),
                                           (computed or {}).get(period, {}))
    return st


def _row(ind_id, unit_id, value, target=None, comment=""):
    return (ind_id, unit_id, value, target, comment, "manual")


def _report(indicators, rows, period=JULY, computed=None):
    st = _state(indicators, rows, computed)
    return st, st.report(_NoDb(), period)


def test_rollup_sum_and_average():
    revenue, plan = _ind(1, "revenue"), _ind(2, "plan", rollup="avg")
    rows = {JULY: [_row(1, 4, 10), _row(1, 5, 5), _row(1, 7, 7), _row(2, 4, 80), _row(2, 5, 100), _row(2, 7, 90)]}
    _st, rep = _report([revenue, plan], rows)
    cells = rep.cells
    assert cells[2][1]["value"] == 15 and cells[2][1]["source"] == "rollup"
    assert cells[2][1]["source_label"] == "сумма по 2 подразделениям"
    assert cells[6][1]["value"] == 7 and cells[3][1]["source_label"] == "сумма по 1 подразделению"
    assert cells[1][1]["value"] == 22 and cells[1][1]["rollup_count"] == 2
    assert cells[2][2]["value"] == 90 and cells[1][2]["value"] == 90
    assert cells[1][2]["source_label"] == "среднее по 2 подразделениям"
    assert cells[4][1]["source_label"] == "введено"


def test_rollup_none_keeps_only_own_values():
    turnover = _ind(1, "turnover", rollup="none")
    _st, rep = _report([turnover], {JULY: [_row(1, 4, 3.5)]})
    assert rep.cells[4][1]["value"] == 3.5
    assert 1 not in rep.cells.get(2, {}) and 1 not in rep.cells.get(1, {})


def test_own_value_beats_rollup_and_targets_roll_up():
    revenue = _ind(1, "revenue", rule_type="target", green_deviation=5, yellow_deviation=10)
    rows = {JULY: [_row(1, 4, 10, 12), _row(1, 5, 5, 6), _row(1, 2, 20), _row(1, 7, 7)]}
    _st, rep = _report([revenue], rows)
    assert rep.cells[2][1]["value"] == 20 and rep.cells[2][1]["source"] == "manual"
    assert rep.cells[1][1]["value"] == 27, "у родителя свёртка собственных значений дочерних"
    # Цель свёрнутого значения — свёртка целей, если они заданы у всех свёрнутых подразделений
    _st, rep = _report([revenue], {JULY: [_row(1, 4, 10, 12), _row(1, 5, 5, 6)]})
    assert rep.cells[2][1]["target"] == 18 and rep.cells[2][1]["status"] == "red"
    _st, rep = _report([revenue], {JULY: [_row(1, 4, 10, 12), _row(1, 5, 5)]})
    assert rep.cells[2][1]["target"] is None and rep.cells[2][1]["status"] == "gray"


def test_computed_values_are_own_values():
    in_work = _ind(1, "tech.in_work", source_type="computed", source_key="tech.in_work",
                   direction="lower_is_better", green_threshold=180, yellow_threshold=220)
    _st, rep = _report([in_work], {JULY: [_row(1, 6, 999)]}, computed={JULY: {"tech.in_work": {6: 274.0}}})
    cell = rep.cells[6][1]
    assert cell["value"] == 274 and cell["source_label"] == "из данных службы" and cell["status"] == "red"
    assert rep.cells[1][1]["value"] == 274 and rep.cells[1][1]["source"] == "rollup"


def test_threshold_rule():
    higher = _ind(1, "x", green_threshold=90, yellow_threshold=75)
    lower = _ind(2, "y", direction="lower_is_better", green_threshold=5, yellow_threshold=8)
    assert [R.evaluate(higher, v, None)[0] for v in (95, 90, 80, 75, 70)] == ["green", "green", "yellow", "yellow",
                                                                              "red"]
    assert [R.evaluate(lower, v, None)[0] for v in (4, 6, 8, 9)] == ["green", "yellow", "yellow", "red"]
    assert R.evaluate(higher, None, None) == ("gray", None)
    assert R.evaluate(_ind(3, "z", direction="neutral", green_threshold=1, yellow_threshold=0), 5, None)[0] == "gray"
    assert R.evaluate(_ind(4, "w"), 5, None)[0] == "gray", "без границ — без оценки"


def test_target_deviation_rule():
    plan = _ind(1, "plan", rule_type="target", green_deviation=5, yellow_deviation=10, default_target=100)
    assert R.evaluate(plan, 97, 100) == ("green", 3.0)
    assert R.evaluate(plan, 92, 100) == ("yellow", 8.0)
    assert R.evaluate(plan, 85, 100) == ("red", 15.0)
    assert R.evaluate(plan, 105, 100) == ("green", 0.0), "перевыполнение — не отклонение"
    costs = replace(plan, direction="lower_is_better", green_deviation=3, yellow_deviation=8)
    assert [R.evaluate(costs, v, 10)[0] for v in (9, 10.2, 10.5, 11)] == ["green", "green", "yellow", "red"]
    assert R.evaluate(costs, 11, 10)[1] == 10.0
    assert R.evaluate(plan, 90, None) == ("gray", None), "без цели — без оценки"
    assert R.evaluate(plan, 1, 0)[0] == "green" and R.evaluate(plan, -1, 0) == ("red", None)
    # В отчёте цель по умолчанию — из каталога, цель уровня и периода — вместе со значением
    _st, rep = _report([plan], {JULY: [_row(1, 4, 92), _row(1, 5, 92, 95)]})
    assert (rep.cells[4][1]["target"], rep.cells[4][1]["status"]) == (100, "yellow")
    assert (rep.cells[5][1]["target"], rep.cells[5][1]["status"]) == (95, "green")


def test_missing_expected_value_is_no_data_and_violation():
    plan = _ind(1, "plan", rollup="avg", rule_type="target", green_deviation=5, yellow_deviation=10,
                default_target=100, expected_kinds=("department",), since=date(2026, 6, 1))
    rows = {JULY: [_row(1, 4, 99), _row(1, 6, 98)], date(2026, 5, 1): [_row(1, 4, 99)]}
    st, rep = _report([plan], rows)
    cell = rep.cells[5][1]
    assert cell["missing"] and cell["status"] == "gray" and cell["status_label"] == "Нет данных"
    assert cell["value"] is None and cell["target"] == 100
    view = rep.view(frozenset({"operational"}))
    assert view.status[5] == "gray" and view.status[2] == "green", "«Нет данных» статус не ухудшает"
    assert view.missing_total[2] == 1 and view.missing_total[1] == 1 and view.missing_total[3] == 0
    assert 1 not in rep.cells.get(7, {}), "у группы значение не ожидается"
    # До начала показателя пропуск не отмечается
    may = st.report(_NoDb(), date(2026, 5, 1))
    assert not may.cells.get(5, {}).get(1, {}).get("missing", False)
    viewer = R.Viewer(0, "company", (1,), None, frozenset({"operational"}), (), True, True, False)
    data = R.scorecard_data(_NoDb(), st, viewer, JULY)
    assert data["summary"]["violations"] == [{"unit_id": 5, "unit_name": "Отдел А2",
                                              "path": "Компания / Дирекция А / Отдел А2", "indicator": "plan",
                                              "indicator_name": "plan"}]
    assert next(u for u in data["units"] if u["id"] == 5)["missing"] == [{"indicator": "plan", "name": "plan"}]


def test_unit_status_is_worst_of_indicators_and_children():
    quality = _ind(1, "quality", green_threshold=90, yellow_threshold=75)
    speed = _ind(2, "speed", rollup="none", green_threshold=90, yellow_threshold=75)
    rows = {JULY: [_row(1, 7, 70), _row(1, 4, 95), _row(1, 5, 80), _row(2, 1, 95), _row(2, 3, 95)]}
    _st, rep = _report([quality, speed], rows)
    view = rep.view(frozenset({"operational"}))
    assert view.status[7] == "red" and view.status[6] == "red", "свёртка группы — красная"
    assert view.status[3] == "red", "собственный зелёный не перекрывает красное дочернее"
    assert view.status[4] == "green" and view.status[5] == "yellow" and view.status[2] == "yellow"
    assert view.status[1] == "red"
    _st, rep = _report([_ind(3, "neutral", direction="neutral")], {JULY: [_row(3, 4, 1)]})
    assert rep.view(frozenset({"operational"})).status[1] == "gray"


def test_explanation_names_origins_and_respects_classes_and_depth():
    turnover = _ind(1, "turnover", name="Текучесть кадров", unit="%", rollup="avg", direction="lower_is_better",
                    green_threshold=5, yellow_threshold=8)
    costs = _ind(2, "costs", name="Затраты", unit="млн ₽", data_class="financial", direction="lower_is_better",
                 rule_type="target", green_deviation=3, yellow_deviation=8)
    rows = {JULY: [_row(1, 7, 14), _row(1, 4, 4), _row(2, 4, 13.2, 12)]}
    _st, rep = _report([turnover, costs], rows)
    everything = frozenset({"operational", "personal", "financial"})
    budget = R.window(rep.state.snap, rep.state.snap.ordered_units(), [1], None)
    full = R.explain(rep, rep.view(everything), 1, budget, 10)
    texts = [i["text"] for i in full["items"]]
    assert texts == ["Красный: Затраты в «Отдел А1» — 13,2 млн ₽ при цели 12 млн ₽ (отклонение 10%)",
                     "Красный: Текучесть кадров в «Группа Б1-1» — 14% при границе жёлтого 8%"], \
        "свёрнутые значения «Дирекции Б» и «Отдела Б1» не повторяются — названа причина"
    assert full["status"] == "red" and full["text"].startswith("Красный: Затраты") and full["text"].endswith("ещё 1")
    # Без финансовых: ни статуса, ни упоминания затрат
    operational = rep.view(frozenset({"operational"}))
    assert operational.status[4] == "green" and operational.status[2] == "green"
    limited = R.explain(rep, operational, 1, budget, 10)
    assert [i["indicator"] for i in limited["items"]] == ["turnover"] and "Затраты" not in str(limited)
    # Глубина 1: «Отдел Б1» и группа не называются — «во вложенных подразделениях»
    shallow = R.window(rep.state.snap, rep.state.snap.ordered_units(), [1], 1)
    assert set(shallow) == {1, 2, 3} and shallow[3] == 0
    locked = R.explain(rep, operational, 1, shallow, 10)
    assert locked["items"] == [{
        "indicator": "turnover", "indicator_name": "Текучесть кадров", "unit_id": 3, "unit_name": "Дирекция Б",
        "status": "red", "value": 14, "target": None, "measure": "%", "detail_locked": False,
        "text": "Красный: Текучесть кадров в «Дирекция Б» — 14% при границе жёлтого 8%"}], \
        "свёрнутое значение последнего видимого уровня называется вместо скрытой причины"
    green = R.explain(rep, operational, 2, budget, 10)
    assert green == {"status": "green", "text": "Зелёный: все оценённые показатели в норме", "items": [], "more": 0}


def test_explanation_hidden_cause_at_drill_boundary():
    quality = _ind(1, "quality", name="Качество", rollup="none", green_threshold=90, yellow_threshold=75)
    _st, rep = _report([quality], {JULY: [_row(1, 7, 50), _row(1, 3, 95)]})
    view = rep.view(frozenset({"operational"}))
    budget = R.window(rep.state.snap, rep.state.snap.ordered_units(), [1], 1)
    items = R.explain(rep, view, 1, budget, 10)["items"]
    assert items == [{"indicator": "quality", "indicator_name": "Качество", "unit_id": 3, "unit_name": "Дирекция Б",
                      "status": "red", "value": None, "target": None, "measure": "", "detail_locked": True,
                      "text": "Красный: Качество — во вложенных подразделениях «Дирекция Б» (детализация недоступна)"}]


def test_window_merges_scope_roots():
    snap = _snap()
    order = snap.ordered_units()
    assert R.window(snap, order, [2, 7], 0) == {2: 0, 7: 0}
    assert set(R.window(snap, order, [3], None)) == {3, 6, 7}
    merged = R.window(snap, order, [1, 6], 1)
    assert merged == {1: 1, 2: 0, 3: 0, 6: 1, 7: 0}, "вторая вершина глубже окна первой — со своим окном"


# ================================================================ доступ по уровням (демо-пользователи)

def test_ceo_sees_company_and_one_level_with_financial(login, admin):
    by_code, code_of = _codes(admin)
    data = _as(login, "ceo").get("/api/reports/scorecard").json()
    assert data["period"] == "2026-07" and data["period_label"] == "Июль 2026"
    assert [code_of[u["id"]] for u in data["units"]] == ["ALMI", "ADMIN", "COMMDIR", "TECHDIR", "PROJ"]
    assert {code_of[u["id"]] for u in data["units"] if u["drill_locked"]} == {"ADMIN", "COMMDIR", "TECHDIR"}
    assert data["roots"] == [by_code["ALMI"]] and data["units"][0]["child_ids"] == [
        by_code["ADMIN"], by_code["COMMDIR"], by_code["TECHDIR"], by_code["PROJ"]]
    assert data["access"]["scope"] == "company" and data["access"]["drill_depth"] == 1
    assert data["access"]["hidden_classes"] == [] and "детализация на 1 уровень" in data["access"]["text"]
    keys = [i["key"] for i in data["indicators"]]
    assert {"fin.revenue", "fin.costs", "fin.payroll", "fin.budget"} <= set(keys)
    company = data["units"][0]
    assert company["status"] == "red" and company["cells"]["fin.revenue"]["source_label"] == "сумма по 3 подразделениям"
    techdir = next(u for u in data["units"] if u["id"] == by_code["TECHDIR"])
    assert any(i["detail_locked"] for i in techdir["explanation"]["items"])
    assert "Группа поддержки" not in str(techdir["explanation"])
    # Нарушение полноты Службы маркетинга — глубже детализации: не называется, но учтено
    assert data["summary"]["violations"] == [] and data["summary"]["hidden_violations"] == 1
    assert next(u for u in data["units"] if u["id"] == by_code["COMMDIR"])["missing_total"] == 1
    # Без исходных записей — без ссылок на реестры; с просмотром служб — ссылка на дашборд
    hr = next(i for i in data["indicators"] if i["key"] == "hr.turnover")
    assert hr["dashboard_url"] == "/hr" and hr["records_url"] is None
    assert data["me"]["note_units"] == sorted([by_code["ALMI"], by_code["ADMIN"]]) and data["me"]["can_export"]


def test_engineer_sees_only_own_unit_without_financial(login, admin):
    by_code, code_of = _codes(admin)
    response = _as(login, "engineer").get("/api/reports/scorecard")
    data = response.json()
    assert [code_of[u["id"]] for u in data["units"]] == ["SUP-OS"]
    assert data["access"]["scope"] == "unit" and data["access"]["drill_depth"] == 0
    assert data["access"]["hidden_classes"] == ["Персональные", "Финансовые"]
    assert {i["data_class"] for i in data["indicators"]} == {"operational"}
    unit = data["units"][0]
    assert set(unit["cells"]) == {"ops.plan", "ops.csat"} and not unit["drill_locked"]
    # Статус — по доступным показателям: жёлтая удовлетворённость; красные затраты группы не учитываются
    assert unit["status"] == "yellow" and unit["indicator_count"] == 2
    assert unit["explanation"]["text"].startswith("Жёлтый: Удовлетворённость клиентов в «Группа поддержки AlterOS»")
    full = next(u for u in admin.get("/api/reports/scorecard").json()["units"] if u["id"] == by_code["SUP-OS"])
    assert full["status"] == "red" and full["cells"]["fin.costs"]["status"] == "red"
    for word in FINANCIAL_WORDS:
        assert word not in response.text, word
    assert data["me"] == {"can_manage": False, "can_export": False, "can_enter": False, "can_note_all": False,
                          "note_units": []}


def test_tech_dir_sees_branch_two_levels_and_drill_lock(login, admin):
    by_code, code_of = _codes(admin)
    created = admin.post("/api/departments", json={"name": "Сектор третьей линии", "parent_id": by_code["SUP-OS"],
                                                   "kind": "sector"})
    assert created.status_code == 201, created.text
    sector = created.json()["id"]
    c = _as(login, "tech_dir")
    data = c.get("/api/reports/scorecard").json()
    assert [code_of.get(u["id"]) for u in data["units"]] == ["TECHDIR", "TECH", "SUP-OS", "SUP-OFFICE", "IT"]
    assert [u["depth"] for u in data["units"]] == [0, 1, 2, 2, 1]
    assert {code_of[u["id"]] for u in data["units"] if u["drill_locked"]} == {"SUP-OS"}
    assert sector not in {u["id"] for u in data["units"]}
    assert data["access"]["drill_depth"] == 2 and data["access"]["roots"][0]["name"] == "Техническая дирекция"
    assert "fin.costs" in data["units"][0]["cells"]
    denied = c.get(f"/api/reports/units/{sector}")
    assert denied.status_code == 403 and denied.json()["code"] == "unit_out_of_scope"
    assert c.get(f"/api/reports/scorecard?root={by_code['COMM']}").status_code == 403
    branch = c.get(f"/api/reports/scorecard?root={by_code['TECH']}").json()
    assert [code_of[u["id"]] for u in branch["units"]] == ["TECH", "SUP-OS", "SUP-OFFICE"]
    assert branch["units"][0]["depth"] == 0 and branch["units"][0]["parent_id"] is None
    detail = c.get(f"/api/reports/units/{by_code['SUP-OS']}").json()
    assert detail["unit"]["drill_locked"] and detail["children"] == []
    assert [b["id"] for b in detail["breadcrumbs"]] == [by_code["TECHDIR"], by_code["TECH"]]


def test_tp_lead_has_no_financial(login, admin):
    by_code, code_of = _codes(admin)
    response = login("tp_lead").get("/api/reports/scorecard")
    data = response.json()
    assert [code_of[u["id"]] for u in data["units"]] == ["TECH", "SUP-OS", "SUP-OFFICE"]
    assert data["access"]["hidden_classes"] == ["Финансовые"] and data["access"]["drill_depth"] is None
    assert not any(i["data_class"] == "financial" for i in data["indicators"])
    tech = data["units"][0]
    assert tech["status"] == "red" and tech["cells"]["tech.in_work"]["source_label"] == "из данных службы"
    assert tech["note"]["status_label"] == "Под контролем" and tech["note"]["author"]["full_name"]
    for word in FINANCIAL_WORDS:
        assert word not in response.text, word


@pytest.mark.parametrize("username", ["engineer", "tp_lead", "it_viewer"])
def test_hidden_classes_never_leak(login, admin, username):
    by_code, _ = _codes(admin)
    c = _as(login, username)
    root = c.get("/api/reports/scorecard").json()["roots"][0]
    responses = [c.get("/api/reports/scorecard"), c.get(f"/api/reports/units/{root}"),
                 c.get("/api/reports/summary"), c.get("/api/reports/indicators"), c.get("/api/reports/periods"),
                 c.get("/api/reports/scorecard?period=2026-06")]
    for response in responses:
        assert response.status_code == 200, response.text
        for word in FINANCIAL_WORDS:
            assert word not in response.text, f"{response.url}: {word}"


def test_unit_detail_trend_and_links(login, admin):
    by_code, _ = _codes(admin)
    data = admin.get(f"/api/reports/units/{by_code['TECH']}?period=2026-07").json()
    assert data["unit"]["status"] == "red" and data["unit"]["explanation"]["items"]
    keys = [i["key"] for i in data["indicators"]]
    assert "fin.costs" in keys and "fin.revenue" in keys and "pp.green_share" not in keys
    costs = next(i for i in data["indicators"] if i["key"] == "fin.costs")
    assert [t["period"] for t in costs["trend"]][0] == "2025-08" and costs["trend"][-1]["period"] == "2026-07"
    assert len(costs["trend"]) == 12 and all(t["value"] is not None for t in costs["trend"])
    assert costs["trend"][-1]["status"] == "red" and costs["cell"]["comment"]
    in_work = next(i for i in data["indicators"] if i["key"] == "tech.in_work")
    assert in_work["trend"][-1]["value"] == 274 and in_work["dashboard_url"] == "/tp"
    assert [c["id"] for c in data["children"]] == [by_code["SUP-OS"], by_code["SUP-OFFICE"]]
    assert {link["service"] for link in data["links"]} == {"hr", "tech"}
    assert data["me"]["can_note"]
    assert admin.get("/api/reports/units/999999").status_code == 404
    # Месяц без значений: введённые ожидаются — «Нет данных»
    later = admin.get(f"/api/reports/units/{by_code['TECH']}?period=2026-09").json()
    plan = next(i for i in later["indicators"] if i["key"] == "ops.plan")
    assert plan["cell"]["missing"] and plan["trend"][-1]["missing"] and not plan["trend"][-3]["missing"]


def test_summary_card(login, admin):
    ceo = _as(login, "ceo").get("/api/reports/summary").json()
    assert ceo["period"] == "2026-07" and ceo["status"] == "red" and ceo["status_label"] == "Критично"
    assert [r["name"] for r in ceo["roots"]] == ["АЛМИ Партнер"] and ceo["missing_total"] == 1
    assert len(ceo["top"]) == 3 and all(item["status"] == "red" for item in ceo["top"])
    assert sum(ceo["counts"].values()) == 5 and not ceo["empty"]
    engineer = _as(login, "engineer").get("/api/reports/summary").json()
    assert engineer["status"] == "yellow" and engineer["roots"][0]["name"] == "Группа поддержки AlterOS"
    assert engineer["indicators"] == 10


def test_periods(login, admin):
    data = _as(login, "ceo").get("/api/reports/periods").json()
    assert data["latest"] == "2026-07" and data["periods"][0] == {"period": "2026-07", "label": "Июль 2026"}
    periods = [p["period"] for p in data["periods"]]
    assert periods == sorted(periods, reverse=True) and "2025-08" in periods
    assert "2026-08" not in periods, "доля партнёрств «в норме» считается за любой месяц и периодов не добавляет"
    assert admin.get("/api/reports/scorecard?period=2026-13").status_code == 422
    assert admin.get("/api/reports/scorecard?period=2030-01").json()["period"] == "2030-01"


@pytest.mark.parametrize("username", ["admin", "ceo", "engineer", "tech_dir"])
def test_responses_match_documented_schemas(login, admin, username):
    """Ответы отчёта отдаются готовыми байтами — схемы OpenAPI сверяются с ними здесь."""
    c = admin if username == "admin" else _as(login, username)
    scorecard = c.get("/api/reports/scorecard").json()
    ScorecardOut.model_validate(scorecard)
    ReportSummaryOut.model_validate(c.get("/api/reports/summary").json())
    PeriodsOut.model_validate(c.get("/api/reports/periods").json())
    UnitReportOut.model_validate(c.get(f"/api/reports/units/{scorecard['roots'][0]}").json())
    paths = c.get("/api/openapi.json").json()["paths"]
    assert {"/api/reports/scorecard", "/api/reports/units/{unit_id}", "/api/reports/values/import",
            "/api/reports/units/{unit_id}/note", "/api/pdf/reports/scorecard"} <= set(paths)


def test_reports_require_login(client):
    for url in ("/api/reports/scorecard", "/api/reports/summary", "/api/reports/periods", "/api/reports/indicators",
                "/api/pdf/reports/scorecard"):
        assert client.get(url).status_code == 401, url


# ================================================================ PDF

@pytest.mark.parametrize(("username", "status"), [("ceo", 200), ("tp_lead", 200), ("engineer", 403), ("admin", 200)])
def test_scorecard_pdf_needs_export_right(login, username, status):
    response = _as(login, username).get("/api/pdf/reports/scorecard?period=2026-07")
    assert response.status_code == status, response.text
    if status == 200:
        assert response.headers["content-type"] == "application/pdf" and response.content[:4] == b"%PDF"
    else:
        assert response.json()["code"] == "export_forbidden"


# ================================================================ кэш и ревизия отчётов

def _cell(client, unit_id, key, period="2026-07"):
    data = client.get(f"/api/reports/scorecard?period={period}").json()
    return next(u for u in data["units"] if u["id"] == unit_id)["cells"].get(key)


def test_value_write_invalidates_cached_report(login, admin, db):
    by_code, _ = _codes(admin)
    ops_plan = db.scalar(select(Indicator.id).where(Indicator.key == "ops.plan"))
    assert _cell(admin, by_code["TECH"], "ops.plan")["value"] == 96
    assert _cell(admin, by_code["TECH"], "ops.plan")["value"] == 96, "повтор — из кэша"
    revision = db.scalar(select(ReportRevision.revision))
    director = _as(login, "tech_dir")
    response = director.put("/api/reports/values", json={"period": "2026-07", "items": [
        {"indicator_id": ops_plan, "department_id": by_code["TECH"], "value": 70, "comment": "Сорван срок"}]})
    assert response.status_code == 200, response.text
    db.expire_all()
    assert db.scalar(select(ReportRevision.revision)) == revision + 1
    cell = _cell(admin, by_code["TECH"], "ops.plan")
    assert (cell["value"], cell["status"], cell["comment"]) == (70, "red", "Сорван срок")
    assert _cell(admin, by_code["TECHDIR"], "ops.plan")["value"] == 84.5, "свёртка пересчитана"
    tp_lead = login("tp_lead").get("/api/reports/scorecard").json()
    assert tp_lead["units"][0]["cells"]["ops.plan"]["value"] == 70


def test_service_data_change_invalidates_report(admin):
    by_code, _ = _codes(admin)
    assert _cell(admin, by_code["TECH"], "tech.in_work")["value"] == 274
    week = next(w for w in admin.get("/api/tp/reports?year=2026").json() if w["week"] == 31)
    assert admin.patch(f"/api/tp/reports/{week['id']}", json={"total_in_work": 150}).status_code == 200
    cell = _cell(admin, by_code["TECH"], "tech.in_work")
    assert (cell["value"], cell["status"]) == (150, "green")


def test_note_and_catalog_changes_invalidate_report(admin, db):
    by_code, _ = _codes(admin)
    assert _cell(admin, by_code["COMM"], "ops.csat")["status"] == "green"
    csat = db.scalar(select(Indicator.id).where(Indicator.key == "ops.csat"))
    assert admin.patch(f"/api/reports/indicators/{csat}", json={"green_threshold": 4.8,
                                                                "yellow_threshold": 4.0}).status_code == 200
    assert _cell(admin, by_code["COMM"], "ops.csat")["status"] == "yellow"
    response = admin.put(f"/api/reports/units/{by_code['COMM']}/note",
                         json={"period": "2026-07", "status": "watch", "comment": "Разбираемся с оплатой"})
    assert response.status_code == 200
    data = admin.get("/api/reports/scorecard?period=2026-07").json()
    assert next(u for u in data["units"] if u["id"] == by_code["COMM"])["note"]["comment"] == "Разбираемся с оплатой"


# ================================================================ скорость: 300 подразделений, 10 показателей

def _synthetic_org(db) -> dict:
    """Компания → 6 дирекций → по 7 служб → по 6 групп (≈ 300 подразделений), 10 вводимых показателей,
    значения у групп и части служб за два месяца."""
    db.execute(update(Indicator).values(is_active=False))
    root = Department(name="Большая компания", code="BIG", kind="company", sort_order=99)
    db.add(root)
    db.flush()
    leaves, services, divisions = [], [], []
    for d in range(6):
        division = Department(name=f"Дирекция {d + 1}", parent_id=root.id, kind="division", sort_order=d)
        db.add(division)
        db.flush()
        divisions.append(division.id)
        for s in range(7):
            service = Department(name=f"Служба {d + 1}.{s + 1}", parent_id=division.id, kind="service", sort_order=s)
            db.add(service)
            db.flush()
            services.append(service.id)
            for g in range(6):
                group = Department(name=f"Группа {d + 1}.{s + 1}.{g + 1}", parent_id=service.id, kind="group",
                                   sort_order=g)
                db.add(group)
                leaves.append(group)
    db.flush()
    indicators = []
    for i in range(10):
        target_rule = i % 2 == 0
        row = Indicator(key=f"perf.k{i}", name=f"Показатель {i}", unit="%", data_class="financial" if i < 3
                        else "operational", direction="lower_is_better" if i % 3 == 0 else "higher_is_better",
                        rollup="sum" if i % 3 == 1 else "avg", rule_type="target" if target_rule else "threshold",
                        green_threshold=None if target_rule else (40 if i % 3 == 0 else 60),
                        yellow_threshold=None if target_rule else (60 if i % 3 == 0 else 40),
                        green_deviation=5 if target_rule else None, yellow_deviation=15 if target_rule else None,
                        default_target=50, source_type="manual", owner_service="apparat_gd",
                        expected_kinds=["group"] if i == 9 else [], sort_order=i)
        db.add(row)
        indicators.append(row)
    db.flush()
    rows = []
    for period in (date(2026, 6, 1), date(2026, 7, 1)):
        for n, leaf in enumerate(leaves):
            for k, ind in enumerate(indicators):
                if k == 9 and n % 17 == 0:
                    continue   # пропуски ожидаемого значения
                rows.append({"indicator_id": ind.id, "department_id": leaf.id, "period": period,
                             "value": float((n * 7 + k * 13) % 100), "target": 50.0 if k % 2 == 0 else None,
                             "comment": "", "source": "manual"})
        for n, service in enumerate(services[::3]):
            rows.append({"indicator_id": indicators[4].id, "department_id": service, "period": period,
                         "value": float(n), "target": None, "comment": "", "source": "manual"})
    db.execute(insert(IndicatorValue), rows)
    db.commit()
    return {"root": root.id, "divisions": divisions, "units": 1 + len(divisions) + len(services) + len(leaves)}


def test_scorecard_for_300_units_is_fast(admin, db, login, monkeypatch):
    org_info = _synthetic_org(db)
    assert org_info["units"] == 301
    url = "/api/reports/scorecard?period=2026-07"
    first = admin.get(url)
    assert first.status_code == 200
    data = first.json()
    assert len(data["units"]) == org_info["units"] + 13 and len(data["indicators"]) == 10
    big = next(u for u in data["units"] if u["id"] == org_info["root"])
    assert big["missing_total"] == 15 and big["status"] in ("red", "yellow")

    def timed(client, path, runs=7):
        samples = []
        for _ in range(runs):
            started = time.perf_counter()
            assert client.get(path).status_code == 200
            samples.append((time.perf_counter() - started) * 1000)
        return statistics.median(samples)

    statements: list[str] = []

    def count(_conn, _cursor, statement, *_args):
        statements.append(statement)

    engine = db.get_bind()
    event.listen(engine, "before_cursor_execute", count)
    try:
        cached = timed(admin, url)
        # Без кэша ответов: каждый запрос заново фильтрует рассчитанный отчёт под права и сериализует
        monkeypatch.setattr("app.core.config.settings.response_cache", False)
        statements.clear()
        assert admin.get(url).status_code == 200
        per_request = len(statements)
        filtered = timed(admin, url)
        ceo = _as(login, "ceo")
        ceo_ms = timed(ceo, url)
        engineer_ms = timed(_as(login, "engineer"), url)
    finally:
        event.remove(engine, "before_cursor_execute", count)
    assert per_request <= 12, f"запросов к базе на отчёт: {per_request} — не должно зависеть от числа подразделений"
    # После прогрева: готовый сжатый ответ из кэша — для всех 314 подразделений без ограничения глубины
    assert cached < 100, cached
    # Без кэша ответов — фильтр рассчитанного отчёта под права, сериализация и сжатие тела каждый раз
    assert ceo_ms < 100 and engineer_ms < 100, (ceo_ms, engineer_ms)
    assert filtered < 250, filtered


def test_company_scorecard_without_user_is_admin_view(admin, db):
    """Отчёт для публикаций (Confluence) — без пользователя, как у администратора: вся компания, все уровни;
    классы данных — по запросу."""
    full = admin.get("/api/reports/scorecard").json()
    period = R.parse_period(full["period"])
    data = R.company_scorecard(db, period)
    assert [u["id"] for u in data["units"]] == [u["id"] for u in full["units"]]
    assert data["summary"]["status"] == full["summary"]["status"] and data["roots"] == full["roots"]
    assert {i["key"] for i in data["indicators"]} == {i["key"] for i in full["indicators"]}
    assert data["access"]["scope"] == "company" and data["access"]["drill_depth"] is None
    hidden = R.company_scorecard(db, period, classes=["operational", "personal"])
    assert "fin.revenue" in {i["key"] for i in data["indicators"]}
    assert "fin.revenue" not in {i["key"] for i in hidden["indicators"]}
    assert hidden["access"]["hidden_classes"] == ["Финансовые"]
    branch = R.company_scorecard(db, period, root=full["units"][1]["id"])
    assert branch["roots"] == [full["units"][1]["id"]]
    viewer = R.company_viewer(R.state(db).snap)
    assert viewer.user_id == 0 and viewer.depth is None and viewer.can_manage and not viewer.can_export

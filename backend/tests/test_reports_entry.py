"""Сквозные отчёты (ADR-0010): каталог показателей, ввод значений по правам и области, загрузка Excel/CSV
(проверка → план → применение), заметки о статусе, подразделения служб, журнал изменений.

Демо: tech_dir — «Ввод данных» к Аппарату ГД (операционные показатели) по Технической дирекции;
финансовые показатели (служба-владелец — финансовая служба) вводит только администратор или
полномочие reports.manage.
"""
import io

from openpyxl import Workbook
from sqlalchemy import func, select

from app.models import AuditEntry, Indicator, IndicatorValue, User

PASSWORDS = {"ceo": "ceo12345", "tech_dir": "td123456", "engineer": "en123456"}
HEADER = "Подразделение;Показатель;Период;Значение;Цель;Комментарий"


def _as(login, username):
    return login(username, PASSWORDS.get(username))


def _codes(admin) -> dict[str, int]:
    return {u["code"]: u["id"] for u in admin.get("/api/departments").json() if u["code"]}


def _ids(db) -> dict[str, int]:
    return dict(db.execute(select(Indicator.key, Indicator.id)).all())


def _value(db, key: str, unit_id: int, period: str = "2026-07-01"):
    db.expire_all()
    return db.scalar(select(IndicatorValue).join(Indicator, Indicator.id == IndicatorValue.indicator_id)
                     .where(Indicator.key == key, IndicatorValue.department_id == unit_id,
                            IndicatorValue.period == period))


def _audit(db, entity_type: str) -> list[AuditEntry]:
    db.expire_all()
    return list(db.scalars(select(AuditEntry).where(AuditEntry.entity_type == entity_type)
                           .order_by(AuditEntry.id)))


# ================================================================ каталог

def test_catalog_read_by_classes(login, admin, db):
    everything = admin.get("/api/reports/indicators").json()
    assert len(everything) == 14 and everything[0]["key"] == "fin.revenue"
    revenue = everything[0]
    assert revenue["data_class_label"] == "Финансовые" and revenue["rule_label"] == "Отклонение от цели"
    assert revenue["owner_service_title"] == "Финансовая служба" and revenue["values_count"] == 36
    in_work = next(i for i in everything if i["key"] == "tech.in_work")
    assert in_work["source_type"] == "computed" and in_work["source_name"] == "Заявки в работе на конец месяца"
    engineer = _as(login, "engineer").get("/api/reports/indicators").json()
    assert {i["data_class"] for i in engineer} == {"operational"} and len(engineer) == 10
    assert all(i["values_count"] == 0 for i in engineer), "число значений — только для ведущих каталог"
    db.execute(Indicator.__table__.update().where(Indicator.key == "ops.csat").values(is_active=False))
    db.commit()
    assert "ops.csat" not in {i["key"] for i in _as(login, "engineer").get("/api/reports/indicators").json()}
    assert "ops.csat" in {i["key"] for i in admin.get("/api/reports/indicators").json()}


def test_meta(login):
    data = _as(login, "engineer").get("/api/reports/meta").json()
    assert [s["key"] for s in data["sources"]] == ["hr.hired", "hr.fired", "hr.turnover", "hr.time_to_fill",
                                                   "tech.in_work", "tech.solved", "tech.ratio", "pp.green_share"]
    assert {r["key"] for r in data["rule_types"]} == {"threshold", "target"}
    assert {k["value"] for k in data["unit_kinds"]} >= {"company", "division", "service", "group"}
    assert data["statuses"][-1] == {"key": "missing", "label": "Нет данных"}


def test_catalog_requires_reports_manage(login, admin, db):
    body = {"key": "ops.nps", "name": "Индекс лояльности", "unit": "", "owner_service": "apparat_gd",
            "direction": "higher_is_better", "green_threshold": 50, "yellow_threshold": 20}
    response = login("hr_head").post("/api/reports/indicators", json=body)
    assert response.status_code == 403 and "сквозные отчёты" in response.json()["detail"]
    hr_head = db.scalar(select(User).where(User.username == "hr_head"))
    assert admin.patch(f"/api/users/{hr_head.id}", json={"capabilities": ["reports.manage"]}).status_code == 200
    created = login("hr_head").post("/api/reports/indicators", json=body)
    assert created.status_code == 201, created.text
    data = created.json()
    assert data["source_type"] == "manual" and data["rollup"] == "sum" and data["data_class"] == "operational"
    entry = _audit(db, "indicator")[-1]
    assert entry.action == "create" and entry.username == "hr_head" and "Индекс лояльности" in entry.summary


def test_catalog_validation(admin):
    base = {"key": "x.test", "name": "Тестовый", "owner_service": "apparat_gd"}

    def post(**fields):
        return admin.post("/api/reports/indicators", json={**base, **fields})

    assert post(key="fin.revenue").status_code == 409
    assert post(name="  выручка ").json()["fields"] == {"name": "Название занято"}
    assert post(key="Bad Key").status_code == 422
    bad_order = post(direction="higher_is_better", green_threshold=10, yellow_threshold=20)
    assert bad_order.status_code == 422 and "Больше — лучше" in bad_order.json()["detail"]
    assert post(green_threshold=10).json()["detail"] == "Задайте обе границы светофора или ни одной"
    assert "допустимые отклонения" in post(rule_type="target", green_deviation=5).json()["detail"]
    assert post(rule_type="target", green_deviation=10, yellow_deviation=5).status_code == 422
    assert post(owner_service=None).json()["fields"] == {"owner_service": "Обязательное поле"}
    assert post(owner_service="nope").status_code == 422
    assert post(expected_kinds=["planet"]).json()["fields"]["expected_kinds"].startswith("Допустимо")
    assert post(source_type="computed").json()["fields"]["source_key"].startswith("Допустимо")
    assert post(source_key="tech.solved").status_code == 422, "у вводимого показателя нет источника"
    assert post(data_class="secret").status_code == 422
    computed = post(key="tech.solved2", name="Решено (копия)", source_type="computed", source_key="tech.solved",
                    owner_service="finance")
    assert computed.status_code == 201, computed.text
    item = computed.json()
    assert (item["owner_service"], item["unit"], item["direction"], item["rollup"]) == (
        "tech", "шт.", "higher_is_better", "sum"), "владелец и умолчания — из источника"


def test_catalog_update_and_delete(admin, db):
    ids = _ids(db)
    patched = admin.patch(f"/api/reports/indicators/{ids['ops.plan']}",
                          json={"yellow_deviation": 20, "expected_kinds": ["service"], "name": "План работ"})
    assert patched.status_code == 200, patched.text
    assert patched.json()["yellow_deviation"] == 20 and patched.json()["values_count"] > 0
    assert admin.patch(f"/api/reports/indicators/{ids['ops.plan']}", json={"source_type": "computed"}).status_code \
        == 422, "источник не меняется"
    assert admin.patch(f"/api/reports/indicators/{ids['ops.plan']}", json={"green_deviation": 30}).status_code == 422
    update = _audit(db, "indicator")[-1]
    assert update.action == "update" and update.after == {"name": "План работ", "yellow_deviation": 20,
                                                           "expected_kinds": ["service"]}
    conflict = admin.delete(f"/api/reports/indicators/{ids['fin.revenue']}")
    assert conflict.status_code == 409 and conflict.json()["code"] == "indicator_has_values"
    removed = admin.delete(f"/api/reports/indicators/{ids['fin.revenue']}?force=true")
    assert removed.status_code == 200 and "вместе с 36 значениями" in removed.json()["message"]
    assert db.scalar(select(func.count()).select_from(IndicatorValue)
                     .where(IndicatorValue.indicator_id == ids["fin.revenue"])) == 0
    assert admin.delete(f"/api/reports/indicators/{ids['tech.ratio']}").status_code == 200, "вычисляемый — без значений"
    assert admin.delete("/api/reports/indicators/99999").status_code == 404
    data = admin.get("/api/reports/scorecard").json()
    assert "fin.revenue" not in {i["key"] for i in data["indicators"]}


# ================================================================ ввод значений

def test_entry_form_for_tech_dir(login, admin):
    codes = _codes(admin)
    data = _as(login, "tech_dir").get("/api/reports/values?period=2026-07").json()
    assert [i["key"] for i in data["indicators"]] == ["ops.plan", "ops.csat"]
    branch = [codes[c] for c in ("TECHDIR", "TECH", "SUP-OS", "SUP-OFFICE", "IT")]
    assert [u["id"] for u in data["units"]] == branch and data["indicators"][0]["unit_ids"] == branch
    assert data["units"][0]["path"] == "АЛМИ Партнер / Техническая дирекция"
    plan_tech = next(v for v in data["values"]
                     if v["indicator_key"] == "ops.plan" and v["department_id"] == codes["TECH"])
    assert plan_tech["value"] == 96 and plan_tech["source_label"] == "введено"
    assert plan_tech["updated_by"]["full_name"] == "Администратор системы"
    everything = admin.get("/api/reports/values?period=2026-07").json()
    assert len(everything["indicators"]) == 6 and everything["indicators"][0]["unit_ids"] is None
    assert len(everything["units"]) == 13
    one = admin.get(f"/api/reports/values?period=2026-07&indicator=fin.costs&unit={codes['TECH']}").json()
    assert [v["value"] for v in one["values"]] == [12.4] and [u["id"] for u in one["units"]] == [codes["TECH"]]
    assert admin.get("/api/reports/values?period=2026-07&indicator=tech.in_work").status_code == 422
    assert admin.get("/api/reports/values?period=07-2026").status_code == 422


def test_entry_forbidden_without_editor(login):
    response = _as(login, "engineer").get("/api/reports/values?period=2026-07")
    assert response.status_code == 403 and response.json()["code"] == "entry_forbidden"
    assert _as(login, "ceo").get("/api/reports/values?period=2026-07").status_code == 403
    hidden = _as(login, "engineer").get("/api/reports/values?period=2026-07&indicator=fin.revenue")
    assert hidden.status_code == 404 and hidden.json()["detail"] == "Показатель не найден"


def test_tech_dir_enters_operational_values_in_branch_only(login, admin, db):
    codes, ids = _codes(admin), _ids(db)
    c = _as(login, "tech_dir")

    def put(*items, period="2026-07"):
        return c.put("/api/reports/values", json={"period": period, "items": list(items)})

    ok = put({"indicator_id": ids["ops.plan"], "department_id": codes["TECH"], "value": 99, "comment": "Догнали"},
             {"indicator_id": ids["ops.csat"], "department_id": codes["IT"], "value": 4.9})
    assert ok.status_code == 200, ok.text
    assert (ok.json()["created"], ok.json()["updated"]) == (1, 1)
    row = _value(db, "ops.plan", codes["TECH"])
    assert (row.value, row.comment, row.source) == (99, "Догнали", "manual")
    outside = put({"indicator_id": ids["ops.plan"], "department_id": codes["COMM"], "value": 50})
    assert outside.status_code == 403 and outside.json()["code"] == "entry_forbidden"
    assert "«Коммерческая служба» вне вашей области структуры" in outside.json()["detail"]
    finance = put({"indicator_id": ids["fin.revenue"], "department_id": codes["TECH"], "value": 1})
    assert finance.status_code == 403 and "«Финансовая служба»" in finance.json()["detail"]
    computed = put({"indicator_id": ids["tech.in_work"], "department_id": codes["TECH"], "value": 1})
    assert computed.status_code == 422 and "вычисляется из данных службы" in computed.json()["detail"]
    twice = put({"indicator_id": ids["ops.plan"], "department_id": codes["TECH"], "value": 1},
                {"indicator_id": ids["ops.plan"], "department_id": codes["TECH"], "value": 2})
    assert twice.status_code == 422
    assert put({"indicator_id": ids["ops.plan"], "department_id": 99999, "value": 1}).status_code == 404
    # Ничего из отклонённых запросов не записано
    assert _value(db, "ops.plan", codes["TECH"]).value == 99 and _value(db, "ops.plan", codes["COMM"]).value == 93
    entry = _audit(db, "indicator_value")[-1]
    assert entry.username == "tech_dir" and entry.entity_id == "2026-07" and "новых 1, изменено 1" in entry.summary
    assert {c["cell"] for c in entry.after["cells"]} == {"ops.plan / Техническая служба",
                                                         "ops.csat / ИТ-служба"}


def test_non_finite_numbers_are_rejected(admin, db):
    codes, ids = _codes(admin), _ids(db)
    for raw in ("NaN", "Infinity", "1e16"):
        item = f'{{"indicator_id": {ids["ops.plan"]}, "department_id": {codes["TECH"]}, "value": {raw}}}'
        body = f'{{"period": "2026-07", "items": [{item}]}}'
        response = admin.put("/api/reports/values", content=body, headers={"content-type": "application/json"})
        assert response.status_code == 422, raw
    threshold = admin.patch(f"/api/reports/indicators/{ids['ops.csat']}", content='{"green_threshold": NaN}',
                            headers={"content-type": "application/json"})
    assert threshold.status_code == 422
    plan = _import(admin, HEADER + "\nTECH;ops.plan;2026-07;nan;;\nTECH;ops.csat;2026-07;inf;;").json()
    assert plan["summary"]["errors"] == 2


def test_engineer_cannot_touch_hidden_class(login, admin, db):
    codes, ids = _codes(admin), _ids(db)
    response = _as(login, "engineer").put("/api/reports/values", json={"period": "2026-07", "items": [
        {"indicator_id": ids["fin.costs"], "department_id": codes["SUP-OS"], "value": 1}]})
    assert response.status_code == 404 and response.json()["detail"] == "Показатель не найден"


def test_reports_manage_enters_any_service_and_clears_cells(login, admin, db):
    codes, ids = _codes(admin), _ids(db)
    hr_head = db.scalar(select(User).where(User.username == "hr_head"))
    admin.patch(f"/api/users/{hr_head.id}", json={"capabilities": ["reports.manage"]})
    c = login("hr_head")
    saved = c.put("/api/reports/values", json={"period": "2026-08", "items": [
        {"indicator_id": ids["fin.revenue"], "department_id": codes["COMM"], "value": 61.5, "target": 63},
        {"indicator_id": ids["ops.plan"], "department_id": codes["MKT"], "target": 90}]})
    assert saved.status_code == 200, saved.text
    assert saved.json()["created"] == 2 and saved.json()["values"][1]["value"] is None
    data = admin.get("/api/reports/scorecard?period=2026-08").json()
    mkt = next(u for u in data["units"] if u["id"] == codes["MKT"])
    assert mkt["cells"]["ops.plan"]["target"] == 90 and mkt["cells"]["ops.plan"]["missing"], \
        "цель без значения — пропуск ожидаемого значения"
    cleared = c.put("/api/reports/values", json={"period": "2026-08", "items": [
        {"indicator_id": ids["ops.plan"], "department_id": codes["MKT"], "value": None, "target": None}]})
    assert cleared.json()["deleted"] == 1 and _value(db, "ops.plan", codes["MKT"], "2026-08-01") is None
    unchanged = c.put("/api/reports/values", json={"period": "2026-08", "items": [
        {"indicator_id": ids["fin.revenue"], "department_id": codes["COMM"], "value": 61.5, "target": 63}]})
    assert unchanged.json()["unchanged"] == 1
    # reports.manage не открывает класс данных: без финансовых — финансовые недоступны
    hr_head = db.scalar(select(User).where(User.username == "hr_head"))
    hr_head.access_overrides = {"data_classes": ["operational"]}
    db.commit()
    hidden = login("hr_head").put("/api/reports/values", json={"period": "2026-08", "items": [
        {"indicator_id": ids["fin.revenue"], "department_id": codes["COMM"], "value": 1}]})
    assert hidden.status_code == 404


def test_editor_with_unit_scope_for_service(login, admin, db):
    """Своя область у службы: «Ввод данных» к финансовой службе только по своему подразделению."""
    codes, ids = _codes(admin), _ids(db)
    engineer = db.scalar(select(User).where(User.username == "engineer"))
    response = admin.put(f"/api/users/{engineer.id}/access", json={
        "profile_id": engineer.access_profile_id, "overrides": {"data_classes": ["financial"]},
        "services": [{"service_key": "finance", "level": "editor", "org_scope": "unit"}]})
    assert response.status_code == 200, response.text
    c = _as(login, "engineer")
    form = c.get("/api/reports/values?period=2026-07").json()
    assert {i["key"] for i in form["indicators"]} == {"fin.revenue", "fin.costs", "fin.payroll", "fin.budget"}
    assert [u["id"] for u in form["units"]] == [codes["SUP-OS"]]
    ok = c.put("/api/reports/values", json={"period": "2026-07", "items": [
        {"indicator_id": ids["fin.costs"], "department_id": codes["SUP-OS"], "value": 6.0, "target": 6.0}]})
    assert ok.status_code == 200
    denied = c.put("/api/reports/values", json={"period": "2026-07", "items": [
        {"indicator_id": ids["fin.costs"], "department_id": codes["TECH"], "value": 6.0}]})
    assert denied.status_code == 403


# ================================================================ загрузка значений

def _import(client, content: str, apply: bool = False):
    return client.post("/api/reports/values/import", json={"content": content, "apply": apply})


def test_import_plan_lists_errors_and_apply_is_refused(login, admin, db):
    c = _as(login, "tech_dir")
    content = "\n".join([
        HEADER,
        "АЛМИ Партнер / Техническая дирекция / Техническая служба;ops.plan;2026-07;97;;Уточнено",
        "SUP-OS;Выполнение плана работ;2026-08;95,5;;",
        "TECH;ops.plan;2026-07;98;;",
        "Нет такого;ops.plan;2026-07;1;;",
        "TECH;nope;2026-07;1;;",
        "TECH;ops.plan;07.2026x;1;;",
        "TECH;ops.plan;2026-06;abc;;",
        "TECH;tech.in_work;2026-07;5;;",
        "COMM;ops.plan;2026-07;90;;",
        "TECH;Выручка;2026-07;5;;",
        "IT;ops.csat;2026-07;;;",
        "IT;ops.plan;2026-07;99;;",
    ])
    plan = _import(c, content)
    assert plan.status_code == 200, plan.text
    data = plan.json()
    assert data["summary"] == {"rows": 12, "create": 1, "update": 1, "unchanged": 1, "errors": 9}
    assert not data["can_apply"] and not data["applied"]
    rows = {r["line"]: r for r in data["rows"]}
    assert rows[2]["action"] == "update" and rows[2]["before"]["value"] == 96 and rows[2]["after"]["value"] == 97
    assert rows[2]["department_path"] == "АЛМИ Партнер / Техническая дирекция / Техническая служба"
    assert rows[3]["action"] == "create" and rows[3]["value"] == 95.5 and rows[3]["indicator_key"] == "ops.plan"
    assert rows[4]["errors"] == ["Повтор: это значение уже задано в строке 2"]
    assert "не найдено" in rows[5]["errors"][0]
    assert rows[6]["errors"][0].startswith("Показатель «nope» не найден")
    assert rows[7]["errors"] == ["Период — в формате ГГГГ-ММ"]
    assert rows[8]["errors"] == ["«Значение» — не число: abc"]
    assert "вычисляется из данных службы" in rows[9]["errors"][0]
    assert "вне вашей области структуры" in rows[10]["errors"][0]
    assert "«Финансовая служба»" in rows[11]["errors"][0], "финансовые tech_dir видит, но не вводит"
    assert rows[12]["errors"] == ["Нет значения, цели и комментария"]
    assert rows[13]["action"] == "unchanged"
    refused = _import(c, content, apply=True)
    assert refused.status_code == 409 and refused.json()["code"] == "import_has_errors"
    assert refused.json()["summary"]["errors"] == 9 and refused.json()["applied"] is False
    assert _value(db, "ops.plan", _codes(admin)["TECH"]).value == 96, "при ошибках ничего не записано"


def test_import_apply_writes_values(login, admin, db):
    codes = _codes(admin)
    c = _as(login, "tech_dir")
    content = "\n".join([HEADER, "TECH;ops.plan;2026-07;97;;Уточнено", "SUP-OS;ops.csat;2026-08;4,4;4,5;",
                         "SUP-OFFICE;Выполнение плана работ;2026-07;;;Перенос сроков согласован"])
    result = _import(c, content, apply=True)
    assert result.status_code == 200, result.text
    assert result.json()["applied"] and result.json()["summary"]["update"] == 2
    row = _value(db, "ops.plan", codes["TECH"])
    assert (row.value, row.comment, row.source) == (97, "Уточнено", "import")
    created = _value(db, "ops.csat", codes["SUP-OS"], "2026-08-01")
    assert (created.value, created.target) == (4.4, 4.5)
    office = _value(db, "ops.plan", codes["SUP-OFFICE"])
    assert (office.value, office.comment) == (78, "Перенос сроков согласован"), "пустая ячейка не стирает значение"
    entry = _audit(db, "indicator_value")[-1]
    assert entry.action == "import" and entry.after["periods"] == ["2026-07", "2026-08"]
    form = c.get("/api/reports/values?period=2026-07").json()
    assert next(v for v in form["values"] if v["department_id"] == codes["TECH"]
                and v["indicator_key"] == "ops.plan")["source_label"] == "загружено из файла"


def test_import_xlsx_upload(admin, db):
    codes = _codes(admin)
    wb = Workbook()
    ws = wb.active
    ws.append(["Подразделение", "Показатель", "Период", "Значение", "Цель", "Комментарий"])
    ws.append(["COMM", "fin.revenue", "2026-08", 63.2, 64, "Оплата поступила"])
    ws.append(["АЛМИ Партнер / Коммерческая дирекция", "Исполнение бюджета", "2026-08", 101, None, None])
    buf = io.BytesIO()
    wb.save(buf)
    files = {"file": ("Показатели.xlsx", buf.getvalue(),
                      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    plan = admin.post("/api/reports/values/import", files=files, data={"apply": "false"})
    assert plan.status_code == 200, plan.text
    assert plan.json()["summary"]["create"] == 2 and plan.json()["can_apply"]
    applied = admin.post("/api/reports/values/import", files=files, data={"apply": "true"})
    assert applied.status_code == 200 and applied.json()["applied"]
    assert _value(db, "fin.revenue", codes["COMM"], "2026-08-01").comment == "Оплата поступила"
    assert "«Показатели.xlsx»" in _audit(db, "indicator_value")[-1].summary


def test_import_file_format_errors(admin):
    assert _import(admin, "Подразделение;Значение\nTECH;1").json()["detail"].startswith("Нужен столбец «Показатель»")
    assert _import(admin, "Подразделение;Показатель;Период\nTECH;ops.plan;2026-07").status_code == 422
    assert _import(admin, HEADER + "\n").json()["detail"] == "В файле нет ни одной строки со значениями"
    response = admin.post("/api/reports/values/import", files={"file": ("x.pdf", b"%PDF", "application/pdf")})
    assert response.status_code == 422


# ================================================================ заметки о статусе

def test_unit_note_by_head_or_reports_manage(login, admin, db):
    codes = _codes(admin)
    lead = login("tp_lead")
    url = f"/api/reports/units/{codes['TECH']}/note"
    saved = lead.put(url, json={"period": "2026-06", "status": "watch", "comment": "Следим за очередью"})
    assert saved.status_code == 200, saved.text
    note = saved.json()["note"]
    assert note["status_label"] == "Под контролем" and note["author"]["full_name"] == "Руководитель техподдержки"
    card = admin.get("/api/reports/scorecard?period=2026-06").json()
    assert next(u for u in card["units"] if u["id"] == codes["TECH"])["note"]["comment"] == "Следим за очередью"
    assert next(u for u in card["units"] if u["id"] == codes["TECH"])["status"] == "red", "статус не меняется"
    denied = lead.put(f"/api/reports/units/{codes['SUP-OS']}/note", json={"period": "2026-06", "comment": "x"})
    assert denied.status_code == 403 and denied.json()["code"] == "note_forbidden"
    assert _as(login, "engineer").put(f"/api/reports/units/{codes['SUP-OS']}/note",
                                      json={"period": "2026-06", "comment": "x"}).status_code == 403
    assert lead.put(url, json={"period": "2026-06", "status": "watch", "comment": " "}).status_code == 422
    assert admin.put(f"/api/reports/units/{codes['COMM']}/note",
                     json={"period": "2026-06", "comment": "Контроль оплаты"}).status_code == 200
    removed = lead.put(url, json={"period": "2026-06", "status": None})
    assert removed.status_code == 200 and removed.json() == {"note": None}
    card = admin.get("/api/reports/scorecard?period=2026-06").json()
    assert next(u for u in card["units"] if u["id"] == codes["TECH"])["note"] is None
    actions = [(e.action, e.username) for e in _audit(db, "unit_status_note")]
    assert actions == [("create", "tp_lead"), ("create", "admin"), ("delete", "tp_lead")]
    assert admin.put("/api/reports/units/99999/note", json={"period": "2026-06", "comment": "x"}).status_code == 404


# ================================================================ подразделения служб

def test_service_units_setting(login, admin, db):
    codes = _codes(admin)
    data = login("tp_lead").get("/api/reports/settings").json()
    assert data["report_service_units"] == {"hr": None, "tech": None, "project_product": None}
    tech = next(s for s in data["services"] if s["key"] == "tech")
    assert tech["unit"]["id"] == codes["TECH"] and tech["default_code"] == "TECH"
    assert tech["sources"] == ["tech.in_work", "tech.solved", "tech.ratio"]
    assert login("tp_lead").put("/api/reports/settings", json={"report_service_units": {"tech": codes["IT"]}}) \
        .status_code == 403
    assert admin.put("/api/reports/settings", json={"report_service_units": {"tech": 99999}}).status_code == 422
    assert admin.put("/api/reports/settings", json={"report_service_units": {"finance": 1}}).status_code == 422
    saved = admin.put("/api/reports/settings", json={"report_service_units": {"tech": codes["IT"]}})
    assert saved.status_code == 200 and saved.json()["report_service_units"]["tech"] == codes["IT"]
    units = {u["id"]: u for u in admin.get("/api/reports/scorecard").json()["units"]}
    assert units[codes["IT"]]["cells"]["tech.in_work"]["value"] == 274
    assert "tech.in_work" not in units[codes["TECH"]]["cells"]
    assert _audit(db, "report_settings")[-1].after == {"tech": codes["IT"]}
    back = admin.put("/api/reports/settings", json={"report_service_units": {"tech": None}})
    assert next(s for s in back.json()["services"] if s["key"] == "tech")["unit"]["id"] == codes["TECH"]

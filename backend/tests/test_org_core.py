"""Ядро 0.2.0: снимок структуры, правила подчинения, действующий доступ (ADR-0007, ADR-0009)."""
import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models import AccessProfile, Department, DepartmentHead, ServiceAccess, User
from app.services import access, org


def _user(db, username: str) -> User:
    return db.scalar(select(User).where(User.username == username))


def _unit(db, code: str) -> Department:
    return db.scalar(select(Department).where(Department.code == code))


def test_demo_structure_is_a_tree(db):
    snap = org.snapshot(db)
    root = snap.roots()
    assert [snap.units[r].name for r in root] == ["АЛМИ Партнер"]
    assert snap.depth() == 4
    tech = _unit(db, "TECH")
    assert snap.path_names(tech.id) == ["АЛМИ Партнер", "Техническая дирекция", "Техническая служба"]
    assert {snap.units[c].code for c in snap.children[tech.id]} == {"SUP-OS", "SUP-OFFICE"}


def test_direct_manager_rules(db):
    snap = org.snapshot(db)
    ids = {u.username: u.id for u in db.scalars(select(User))}
    # группа без руководителя → руководитель родителя
    assert snap.direct_manager(ids["engineer"]) == (ids["tp_lead"], "structure")
    # руководитель подразделения подчиняется руководителю уровня выше
    assert snap.direct_manager(ids["tp_lead"]) == (ids["tech_dir"], "structure")
    assert snap.direct_manager(ids["tech_dir"]) == (ids["ceo"], "structure")
    # «первое лицо»
    assert snap.direct_manager(ids["ceo"]) == (None, "top")
    assert snap.chain(ids["engineer"]) == [ids["tp_lead"], ids["tech_dir"], ids["ceo"]]
    assert ids["engineer"] in snap.subordinates(ids["tech_dir"])
    assert snap.direct_reports(ids["tp_lead"]) == [ids["engineer"]]


def test_explicit_manager_wins_and_revision_bumps(db):
    before = org.current_revision(db)
    engineer, product = _user(db, "engineer"), _user(db, "product")
    engineer.manager_id = product.id
    db.commit()
    assert org.current_revision(db) == before + 1
    snap = org.snapshot(db)
    assert snap.revision == before + 1
    assert snap.direct_manager(engineer.id) == (product.id, "explicit")
    # отключённый явный руководитель не учитывается
    product.is_active = False
    db.commit()
    assert org.snapshot(db).direct_manager(engineer.id)[1] == "structure"


def test_unrelated_user_change_does_not_bump_revision(db):
    before = org.current_revision(db)
    user = _user(db, "viewer")
    user.phone = "+7 900 000-00-00"
    db.commit()
    assert org.current_revision(db) == before


def test_sibling_names_are_unique_case_insensitive(db):
    tech = _unit(db, "TECH")
    db.add(Department(name="  группа   поддержки alteros ", parent_id=tech.id))
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()
    # то же имя в другой ветке допустимо
    it = _unit(db, "IT")
    db.add(Department(name="Группа поддержки AlterOS", parent_id=it.id))
    db.commit()


def test_one_primary_head_per_unit(db):
    tech = _unit(db, "TECH")
    db.add(DepartmentHead(department_id=tech.id, user_id=_user(db, "viewer").id, is_primary=True))
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_effective_access_by_profile(db):
    ceo = access.effective(_user(db, "ceo"))
    assert ceo.profile_key == "executive" and ceo.org_scope == "company" and ceo.drill_depth == 1
    assert ceo.allows("financial") and not ceo.can_view_records
    assert set(ceo.services) == {"hr", "tech", "project_product"} and ceo.sources["org_scope"] == "profile"

    engineer = access.effective(_user(db, "engineer"))
    assert engineer.profile_key == "employee" and engineer.services == {}
    assert not engineer.allows("financial") and not engineer.allows("personal") and engineer.allows("operational")
    assert engineer.drill_depth == 0 and not engineer.can_export


def test_personal_overrides_and_service_none(db):
    user = _user(db, "tech_dir")
    user.access_overrides = {"drill_depth": None, "data_classes": ["operational"], "can_export": False}
    db.add(ServiceAccess(user_id=user.id, service_key="hr", level="none"))
    db.commit()
    db.refresh(user)
    eff = access.compute(user)
    assert eff.drill_depth is None and eff.sources["drill_depth"] == "personal"
    assert eff.data_classes == frozenset({"operational"}) and not eff.can_export
    assert "hr" not in eff.services and eff.sources["service:hr"] == "personal"
    assert eff.services["tech"] == "viewer" and eff.sources["service:tech"] == "profile"
    assert eff.org_scope == "branch" and eff.sources["org_scope"] == "profile"


def test_individual_user_keeps_0_1_0_behaviour(db):
    viewer = access.effective(_user(db, "viewer"))
    assert viewer.profile_key is None and viewer.org_scope == "company"
    assert viewer.allows("financial") and viewer.can_view_records and viewer.can_export
    assert viewer.sources["org_scope"] == "default"


def test_scope_units(db):
    snap = org.snapshot(db)
    names = lambda units: {snap.units[u].code for u in units}  # noqa: E731
    assert access.scope_units(db, _user(db, "ceo")) is None
    assert names(access.scope_units(db, _user(db, "tech_dir"))) == {"TECHDIR", "TECH", "SUP-OS", "SUP-OFFICE", "IT"}
    assert names(access.scope_units(db, _user(db, "engineer"))) == {"SUP-OS"}
    # область службы: «свои подразделения» у it_viewer для службы персонала
    assert access.department_scope(db, _user(db, "it_viewer"), "hr") == {"ИТ-служба", "IT"}


def test_extra_units_extend_scope(db):
    engineer = _user(db, "engineer")
    engineer.access_units = [_unit(db, "MKT")]
    db.commit()
    db.refresh(engineer)
    snap = org.snapshot(db)
    assert {snap.units[u].code for u in access.scope_units(db, engineer)} == {"SUP-OS", "MKT"}


def test_system_profiles_are_seeded(db):
    keys = [p.key for p in db.scalars(select(AccessProfile).order_by(AccessProfile.sort_order))]
    assert keys == ["executive", "director", "head", "specialist", "employee"]


# ---------------------------------------------------------------- отключение сотрудников синхронизацией

def _person(db, username, email, source, *, external_id=None, active=True):
    user = User(username=username, full_name=username.title(), email=email, role="user", is_active=active,
                org_source=source, external_id=external_id, auth_source="local", must_change_password=False)
    db.add(user)
    db.commit()
    return user


def test_import_deactivates_only_people_of_the_same_source(db):
    from app.services import org_import
    from app.services.org_import import Row

    unit = ["АЛМИ Партнер", "Техническая дирекция"]
    kept = _person(db, "kept", "kept@company.ru", "podelu", external_id="p-1")
    gone = _person(db, "gone", "gone@company.ru", "podelu", external_id="p-2")
    service = _person(db, "svc", "svc@company.ru", "podelu", external_id="u-svc")
    from_ad = _person(db, "from.ad", "ad@company.ru", "ad", external_id="guid")
    rows = [Row(line=1, email="kept@company.ru", name="Kept", department=unit, external_id="p-1")]
    plan = org_import.plan_import(db, rows, source="podelu", deactivate_missing=True, keep={"SVC@company.ru"})
    assert [d["user_id"] for d in plan.deactivate] == [gone.id], \
        "отключается только отсутствующий из «По Делу»: не служебная учётная запись, не сотрудник AD, не заведённые " \
        "вручную"
    assert org_import.plan_import(db, rows, source="podelu").deactivate == [], "без deactivate_missing — никого"
    assert org_import.plan_import(db, rows, source="csv", deactivate_missing=True).deactivate == [], \
        "загрузка списком не отключает"
    ad_plan = org_import.plan_import(db, [], source="ad", deactivate_missing=True)
    assert from_ad.id in [d["user_id"] for d in ad_plan.deactivate] and gone.id not in \
        [d["user_id"] for d in ad_plan.deactivate], "AD отключает только своих"
    result, applied = org_import.apply_import(db, None, rows, source="podelu", deactivate_missing=True,
                                              keep={"svc"})
    db.commit()
    assert applied and result["summary"]["deactivate_users"] == 1
    db.expire_all()
    assert not db.get(User, gone.id).is_active
    assert db.get(User, kept.id).is_active and db.get(User, service.id).is_active and db.get(User, from_ad.id).is_active


def test_disabled_row_deactivates_same_source_only(db):
    from app.services import org_import
    from app.services.org_import import Row

    unit = ["АЛМИ Партнер", "Техническая дирекция"]
    mine = _person(db, "mine", "mine@company.ru", "podelu", external_id="p-1")
    other = _person(db, "other", "other@company.ru", "ad", external_id="guid-2")
    service = _person(db, "svc", "svc@company.ru", "podelu", external_id="u-svc")
    rows = [Row(line=1, email="mine@company.ru", name="Mine", department=unit, external_id="p-1", disabled=True),
            Row(line=2, email="other@company.ru", name="Other", department=unit, disabled=True),
            Row(line=3, email="svc@company.ru", name="Svc", department=unit, external_id="u-svc", disabled=True)]
    plan = org_import.plan_import(db, rows, source="podelu", keep={"svc@company.ru"})
    by_line = {u["line"]: u for u in plan.users}
    assert plan.targets[mine.id]["disabled"] and not plan.targets[other.id]["disabled"]
    assert "создана не синхронизацией с «По Делу»" in by_line[2]["warnings"][0]
    assert not plan.targets[service.id]["disabled"] and "служебная" in by_line[3]["warnings"][0]
    assert not plan.targets[other.id]["adopt"], "отключённый в «По Делу» сотрудник AD не переходит к «По Делу»"

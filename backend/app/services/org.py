"""Структура компании: снимок дерева подразделений и подчинения (ADR-0007).

Снимок строится одним проходом по таблицам и хранится в памяти процесса, пока не изменится
ревизия структуры (org_revision). Ревизия увеличивается в той же транзакции, что и любое
изменение подразделений, руководителей и полей подчинения пользователей (событие сессии ниже),
поэтому все процессы сервера видят изменения согласованно. Правила подчинения — как в
todo-planner (ADR-0044/0046 там): явный руководитель, «первое лицо», подъём по дереву.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass, field

from sqlalchemy import event, inspect, select, update
from sqlalchemy.orm import Session

from ..core.db import utcnow
from ..models import Department, DepartmentHead, OrgRevision, User

# Поля пользователя, от которых зависит снимок структуры (и то, что оргсхема показывает о сотруднике)
USER_ORG_FIELDS = ("department_id", "manager_id", "reports_to_none", "is_active", "full_name", "position",
                   "role", "email", "username", "avatar", "external_id", "org_source")


@dataclass(frozen=True)
class Unit:
    id: int
    name: str
    parent_id: int | None
    kind: str
    sort_order: int
    code: str | None
    external_id: str | None
    org_source: str = "manual"


@dataclass(frozen=True)
class Person:
    id: int
    username: str
    full_name: str
    email: str | None
    position: str | None
    department_id: int | None
    manager_id: int | None
    reports_to_none: bool
    is_active: bool
    is_admin: bool
    external_id: str | None = None
    org_source: str | None = None
    has_avatar: bool = False


@dataclass
class OrgSnapshot:
    revision: int
    units: dict[int, Unit] = field(default_factory=dict)
    children: dict[int | None, list[int]] = field(default_factory=dict)
    heads: dict[int, list[int]] = field(default_factory=dict)      # подразделение → руководители (основной первым)
    primary: dict[int, int] = field(default_factory=dict)          # подразделение → основной руководитель
    headed: dict[int, list[int]] = field(default_factory=dict)     # пользователь → руководимые подразделения
    people: dict[int, Person] = field(default_factory=dict)

    # ------------------------------------------------------------ дерево

    def roots(self) -> list[int]:
        return self.children.get(None, [])

    def path(self, unit_id: int) -> list[int]:
        """Путь от корня до подразделения (включительно); устойчив к циклам в данных."""
        chain: list[int] = []
        seen: set[int] = set()
        current: int | None = unit_id
        while current is not None and current in self.units and current not in seen:
            seen.add(current)
            chain.append(current)
            current = self.units[current].parent_id
        return list(reversed(chain))

    def path_names(self, unit_id: int) -> list[str]:
        return [self.units[u].name for u in self.path(unit_id)]

    def level(self, unit_id: int) -> int:
        return len(self.path(unit_id)) - 1

    def descendants(self, unit_ids: Iterable[int], depth: int | None = None) -> set[int]:
        """Подразделения и их потомки не глубже depth уровней (None — все)."""
        result: set[int] = set()
        queue = deque((u, 0) for u in unit_ids if u in self.units)
        while queue:
            unit, d = queue.popleft()
            if unit in result:
                continue
            result.add(unit)
            if depth is None or d < depth:
                queue.extend((child, d + 1) for child in self.children.get(unit, []))
        return result

    def height(self, unit_id: int) -> int:
        """Уровней в ветке ниже подразделения (0 — нет дочерних)."""
        children = self.children.get(unit_id, [])
        return 1 + max(self.height(c) for c in children) if children else 0

    def depth(self) -> int:
        """Уровней в структуре (1 — только корни)."""
        return max((self.level(u) + 1 for u in self.units), default=0)

    # ------------------------------------------------------------ люди

    def usable(self, user_id: int | None) -> bool:
        person = self.people.get(user_id) if user_id is not None else None
        return person is not None and person.is_active

    def home_unit(self, user_id: int) -> int | None:
        """Основное подразделение: своё, а без него — руководимое (сначала где основной)."""
        person = self.people.get(user_id)
        if person is None:
            return None
        if person.department_id in self.units:
            return person.department_id
        headed = self.headed.get(user_id, [])
        primary = [u for u in headed if self.primary.get(u) == user_id]
        return (primary or headed or [None])[0]

    def unit_heads(self, unit_id: int) -> list[int]:
        return [h for h in self.heads.get(unit_id, []) if self.usable(h)]

    def direct_manager(self, user_id: int) -> tuple[int | None, str]:
        """Непосредственный руководитель и источник: none · explicit · structure · top."""
        person = self.people.get(user_id)
        if person is None:
            return None, "none"
        if person.reports_to_none:
            return None, "top"
        if person.manager_id and person.manager_id != user_id and self.usable(person.manager_id):
            return person.manager_id, "explicit"
        start = person.department_id if person.department_id in self.units else None
        if start is None:
            headed = self.headed.get(user_id, [])
            start = self.units[headed[0]].parent_id if headed else None
        seen: set[int] = set()
        unit = start
        while unit is not None and unit in self.units and unit not in seen:
            seen.add(unit)
            heads = self.unit_heads(unit)
            if user_id not in self.heads.get(unit, []) and heads:
                return heads[0], "structure"
            unit = self.units[unit].parent_id
        return None, "none"

    def members(self, unit_id: int) -> list[int]:
        """Сотрудники, для которых подразделение основное (активные), по имени."""
        ids = [p.id for p in self.people.values() if p.is_active and self.home_unit(p.id) == unit_id]
        return sorted(ids, key=lambda i: self.people[i].full_name.casefold())

    def direct_reports(self, user_id: int) -> list[int]:
        ids = [p.id for p in self.people.values()
               if p.is_active and p.id != user_id and self.direct_manager(p.id)[0] == user_id]
        return sorted(ids, key=lambda i: self.people[i].full_name.casefold())

    def subordinates(self, user_id: int, depth: int | None = None) -> set[int]:
        reports = self._reports_index()
        result: set[int] = set()
        queue = deque((r, 1) for r in reports.get(user_id, []))
        while queue:
            uid, d = queue.popleft()
            if uid in result or uid == user_id:
                continue
            result.add(uid)
            if depth is None or d < depth:
                queue.extend((r, d + 1) for r in reports.get(uid, []))
        return result

    def chain(self, user_id: int) -> list[int]:
        """Цепочка руководителей снизу вверх (без самого сотрудника)."""
        result: list[int] = []
        seen = {user_id}
        manager, _ = self.direct_manager(user_id)
        while manager is not None and manager not in seen and len(result) < 50:
            result.append(manager)
            seen.add(manager)
            manager, _ = self.direct_manager(manager)
        return result

    def _reports_index(self) -> dict[int, list[int]]:
        cached = getattr(self, "_reports", None)
        if cached is None:
            cached = {}
            for person in self.people.values():
                if not person.is_active:
                    continue
                manager, _ = self.direct_manager(person.id)
                if manager is not None:
                    cached.setdefault(manager, []).append(person.id)
            self._reports = cached
        return cached

    # ------------------------------------------------------------ оргсхема, проверки, «что будет, если»

    def path_text(self, unit_id: int | None) -> str:
        """Путь подразделения через « / » («Компания / Дирекция / Отдел»)."""
        return " / ".join(self.path_names(unit_id)) if unit_id in self.units else ""

    def ordered_units(self) -> list[int]:
        """Подразделения в порядке дерева: родители раньше детей, соседи — по порядку и названию."""
        result: list[int] = []
        seen: set[int] = set()
        stack = list(reversed(self.roots()))
        while stack:
            unit = stack.pop()
            if unit in seen:
                continue
            seen.add(unit)
            result.append(unit)
            stack.extend(reversed(self.children.get(unit, [])))
        # Подразделения вне дерева (цикл в повреждённых данных) — в конце, чтобы не потерялись
        rest = sorted((u for u in self.units if u not in seen), key=lambda u: self.units[u].name.casefold())
        return result + rest

    def structure_manager(self, user_id) -> int | None:
        """Руководитель по структуре — без учёта явного руководителя и «первого лица»
        (то же правило подъёма по дереву, что в direct_manager)."""
        person = self.people.get(user_id)
        if person is None:
            return None
        start = person.department_id if person.department_id in self.units else None
        if start is None:
            headed = self.headed.get(user_id, [])
            start = self.units[headed[0]].parent_id if headed else None
        seen: set = set()
        unit = start
        while unit is not None and unit in self.units and unit not in seen:
            seen.add(unit)
            heads = self.unit_heads(unit)
            if user_id not in self.heads.get(unit, []) and heads:
                return heads[0]
            unit = self.units[unit].parent_id
        return None

    def manager_of(self, user_id):
        """Непосредственный руководитель (кэш на снимок)."""
        cached = getattr(self, "_managers", None)
        if cached is None:
            cached = self._managers = {}
        if user_id not in cached:
            cached[user_id] = self.direct_manager(user_id)[0]
        return cached[user_id]

    def cycles(self) -> set:
        """Сотрудники, на которых замыкается цепочка руководителей (цикл подчинения)."""
        state: dict = {}
        cyclic: set = set()
        for start in self.people:
            if start in state:
                continue
            path: list = []
            index: dict = {}
            node = start
            while node is not None and node not in state:
                state[node] = 1
                index[node] = len(path)
                path.append(node)
                node = self.manager_of(node)
            if node is not None and node in index:
                cyclic.update(path[index[node]:])
            for item in path:
                state[item] = 2
        return cyclic

    def branch_counts(self) -> dict:
        """Размер ветки подчинения (все подчинённые, без самого руководителя) — за один проход."""
        reports = self._reports_index()
        cyclic = self.cycles()
        sizes: dict = {}
        for root in reports:
            if root in sizes or root in cyclic:
                continue
            stack = [(root, False)]
            while stack:
                node, done = stack.pop()
                if done:
                    sizes[node] = sum(1 + sizes.get(child, 0) for child in reports.get(node, []))
                    continue
                if node in sizes:
                    continue
                stack.append((node, True))
                stack.extend((child, False) for child in reports.get(node, []) if child not in sizes)
        # Внутри цикла подчинения ветка — множество достижимых (ветки ниже цикла — обычные деревья)
        for node in cyclic:
            if node in reports:
                sizes[node] = len(self.subordinates(node))
        return sizes

    def copy(self) -> OrgSnapshot:
        """Копия для расчёта «что будет после изменения»: снимок в кэше остаётся прежним."""
        return OrgSnapshot(
            revision=self.revision, units=dict(self.units),
            children={k: list(v) for k, v in self.children.items()},
            heads={k: list(v) for k, v in self.heads.items()}, primary=dict(self.primary),
            headed={k: list(v) for k, v in self.headed.items()}, people=dict(self.people),
        )

    def add_unit(self, unit: Unit) -> None:
        """Подразделение в копию снимка (новое — с временным ключом вида «new:1»)."""
        self.units[unit.id] = unit
        self.children.setdefault(unit.parent_id if unit.parent_id in self.units else None, []).append(unit.id)

    def set_heads(self, unit_id, user_ids: Iterable, primary=None) -> None:
        """Руководители подразделения в копии снимка (основной первым, затем по имени)."""
        for old in self.heads.get(unit_id, []):
            self.headed[old] = [u for u in self.headed.get(old, []) if u != unit_id]
        ids = list(dict.fromkeys(user_ids))
        self.primary.pop(unit_id, None)
        if primary is not None and primary in ids:
            self.primary[unit_id] = primary

        def name(uid) -> str:
            person = self.people.get(uid)
            return person.full_name.casefold() if person else ""

        ids.sort(key=lambda uid: (uid != self.primary.get(unit_id), name(uid)))
        self.heads[unit_id] = ids
        for uid in ids:
            self.headed.setdefault(uid, []).append(unit_id)
        self.forget()

    def forget(self) -> None:
        """Сбросить вычисленное по копии (после её изменения)."""
        self.__dict__.pop("_reports", None)
        self.__dict__.pop("_managers", None)


# ---------------------------------------------------------------- построение и кэш

def build_snapshot(db: Session, revision: int | None = None) -> OrgSnapshot:
    if revision is None:
        revision = current_revision(db)
    snap = OrgSnapshot(revision=revision)
    for d in db.scalars(select(Department)):
        snap.units[d.id] = Unit(d.id, d.name, d.parent_id, d.kind, d.sort_order, d.code, d.external_id,
                                d.org_source or "manual")
    for unit in sorted(snap.units.values(), key=lambda u: (u.sort_order, u.name.casefold())):
        snap.children.setdefault(unit.parent_id if unit.parent_id in snap.units else None, []).append(unit.id)
    rows = db.execute(select(User.id, User.username, User.full_name, User.email, User.position, User.department_id,
                             User.manager_id, User.reports_to_none, User.is_active, User.role, User.external_id,
                             User.org_source, User.avatar.isnot(None).label("has_avatar"))).all()
    for r in rows:
        snap.people[r.id] = Person(r.id, r.username, r.full_name, r.email, r.position, r.department_id, r.manager_id,
                                   bool(r.reports_to_none), bool(r.is_active), r.role == "admin", r.external_id,
                                   r.org_source, bool(r.has_avatar))
    links = db.execute(select(DepartmentHead.department_id, DepartmentHead.user_id, DepartmentHead.is_primary)).all()
    for link in sorted(links, key=lambda h: (not h.is_primary, snap.people[h.user_id].full_name.casefold()
                                             if h.user_id in snap.people else "")):
        if link.department_id not in snap.units or link.user_id not in snap.people:
            continue
        snap.heads.setdefault(link.department_id, []).append(link.user_id)
        snap.headed.setdefault(link.user_id, []).append(link.department_id)
        if link.is_primary:
            snap.primary[link.department_id] = link.user_id
    return snap


def current_revision(db: Session) -> int:
    return db.scalar(select(OrgRevision.revision).where(OrgRevision.id == 1)) or 0


_lock = threading.Lock()
_cache: dict[str, object] = {"snapshot": None, "checked": 0.0}
# Как часто процесс сверяет ревизию с базой; изменения своего процесса видны сразу
CHECK_INTERVAL = 1.0


def snapshot(db: Session) -> OrgSnapshot:
    now = time.monotonic()
    cached = _cache["snapshot"]
    if isinstance(cached, OrgSnapshot) and now - float(_cache["checked"]) < CHECK_INTERVAL:
        return cached
    revision = current_revision(db)
    if isinstance(cached, OrgSnapshot) and cached.revision == revision:
        _cache["checked"] = now
        return cached
    with _lock:
        fresh = build_snapshot(db, revision)
        _cache.update(snapshot=fresh, checked=now)
    return fresh


def invalidate() -> None:
    _cache.update(snapshot=None, checked=0.0)


def mark_changed(session: Session) -> None:
    """Изменение структуры, которое не видят события сессии (настройки структуры): ревизия
    увеличится при commit этой транзакции."""
    session.info["org_changed"] = True


# ---------------------------------------------------------------- ревизия структуры

def _touches_org(session: Session) -> bool:
    for obj in (*session.new, *session.deleted):
        if isinstance(obj, (Department, DepartmentHead, User)):
            return True
    for obj in session.dirty:
        if isinstance(obj, (Department, DepartmentHead)):
            return True
        if isinstance(obj, User):
            state = inspect(obj)
            if any(state.attrs[name].history.has_changes() for name in USER_ORG_FIELDS):
                return True
    return False


@event.listens_for(Session, "before_flush")
def _mark_org_change(session: Session, _context, _instances) -> None:
    if _touches_org(session):
        session.info["org_changed"] = True


@event.listens_for(Session, "before_commit")
def _bump_org_revision(session: Session) -> None:
    if session.info.get("org_changed") or _touches_org(session):
        session.flush()
        session.execute(update(OrgRevision).where(OrgRevision.id == 1)
                        .values(revision=OrgRevision.revision + 1, updated_at=utcnow()))
        session.info["org_committed"] = True
    session.info.pop("org_changed", None)


@event.listens_for(Session, "after_commit")
def _drop_local_snapshot(session: Session) -> None:
    if session.info.pop("org_committed", False):
        invalidate()


@event.listens_for(Session, "after_rollback")
def _forget_org_change(session: Session) -> None:
    session.info.pop("org_changed", None)
    session.info.pop("org_committed", None)

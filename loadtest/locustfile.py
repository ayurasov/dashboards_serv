"""Нагрузочный сценарий «Дашбордов компании»: сотрудники открывают страницы служб.

Каждый виртуальный пользователь входит один раз (сессия в cookie) и дальше открывает
страницы с паузой на чтение 5–20 с. «Страница» — тот же набор запросов API, что делает
интерфейс. Смесь страниц отражает ожидаемую работу: обзор и дашборды чаще всего,
PDF и ввод данных — редко. С 0.4.0 — «Входящие данные» и «Интеграции» для тех, у кого они есть,
и внешние системы (1С, скрипты), которые раз в 30–60 с присылают файл значений показателей
по API с ключом интеграции (InboundSystem, 2 экземпляра).

    locust -f loadtest/locustfile.py --host http://127.0.0.1:8000 \
        --users 1000 --spawn-rate 25 --run-time 6m --headless --csv loadtest/results/u1000

Учётные записи — демонстрационные (DEMO_DATA=true): несколько сессий на один логин допустимы.
"""
from __future__ import annotations

import random
import uuid

from locust import HttpUser, between, events, task

# логин, пароль, службы с доступом, право на исходные записи (как у демо-пользователей 0.2.0)
ALL = {"hr", "tech", "project_product"}
USERS = [("admin", "admin123", ALL, True), ("hr_head", "hr123456", ALL, True), ("viewer", "view1234", ALL, True),
         ("tp_lead", "tp123456", {"tech"}, True), ("product", "pp123456", {"project_product"}, True),
         # уровни сотрудников: высшее руководство (без исходных записей), руководитель направления, сотрудник
         ("ceo", "ceo12345", ALL, False), ("tech_dir", "td123456", ALL, True), ("engineer", "en123456", set(), False)]
MONTHS = ["2026-03", "2026-04", "2026-05", "2026-06", "2026-07"]


class Employee(HttpUser):
    wait_time = between(5, 20)

    def on_start(self):
        self.username, password, self.services, self.records = random.choice(USERS)
        self.csrf = ""
        with self.client.post("/api/auth/login", json={"username": self.username, "password": password},
                              name="POST /api/auth/login", catch_response=True) as r:
            if r.status_code != 200:
                r.failure(f"вход: {r.status_code}")
                return
            self.csrf = r.json()["csrf_token"]
        self.client.get("/api/auth/me", name="GET /api/auth/me")
        self.client.get("/api/services", name="GET /api/services")
        self.client.get("/api/palette/active", name="GET /api/palette/active")
        # «Входящие данные» в меню — у кого есть хотя бы один набор (403 для остальных ожидаем)
        self.inbox = False
        with self.client.get("/api/inbox/datasets", name="GET /api/inbox/datasets", catch_response=True) as r:
            if r.status_code == 200:
                data = r.json()
                self.inbox = bool(data.get("can_manage") or any(d.get("can_apply") for d in data.get("datasets", [])))
            elif r.status_code == 403:
                r.success()

    def page(self, *paths):
        service = {"hr": "hr", "tp": "tech", "partnerships": "project_product"}.get(paths[0].split("?")[0].split("/")[2])
        if service and service not in self.services:
            return  # страницы чужих служб пользователь не открывает (у него их нет в меню)
        for path in paths:
            name = path.split("?")[0]
            self.client.get(path, name=f"GET {name}")

    # --- обзор и персонал
    @task(10)
    def overview(self):
        self.page("/api/overview")
        self.client.get("/api/reports/summary", name="GET /api/reports/summary")

    # --- сквозной отчёт (доступен всем; объём и глубина — по правам пользователя)
    @task(6)
    def cross_report(self):
        self.client.get("/api/reports/periods", name="GET /api/reports/periods")
        with self.client.get("/api/reports/scorecard", name="GET /api/reports/scorecard",
                             catch_response=True) as r:
            if r.status_code != 200:
                r.failure(f"отчёт: {r.status_code}")
                return
            units = [u["id"] for u in r.json().get("units", [])]
        if units:
            self.client.get(f"/api/reports/units/{random.choice(units)}", name="GET /api/reports/units/{id}")

    @task(8)
    def hr_dashboard(self):
        months = ",".join(random.sample(MONTHS, k=random.randint(1, 5)))
        self.page("/api/hr/months", f"/api/hr/analytics/dashboard?months={months}", "/api/layouts/hr")

    @task(4)
    def hr_registry(self):
        if not self.records:
            return  # реестров нет в меню у тех, кому они недоступны
        self.page("/api/hr/months", "/api/hr/departments", f"/api/hr/events?month={random.choice(MONTHS)}")

    @task(2)
    def hr_summary(self):
        self.page("/api/hr/metrics", f"/api/hr/analytics/summary?period_type={random.choice(['month', 'quarter'])}")

    @task(1)
    def hr_targets(self):
        self.page("/api/hr/targets")

    # --- техподдержка
    @task(8)
    def tp_dashboard(self):
        self.page("/api/tp/reports", "/api/tp/columns", "/api/traffic-light/tech", "/api/layouts/tech")

    @task(5)
    def naumen(self):
        query = random.choice(["", "?year=2024", "?year=2025", "?year=2026", "?months=12"])
        self.page("/api/tp/naumen/filters", f"/api/tp/naumen/summary{query}")

    @task(2)
    def cross_analytics(self):
        self.page("/api/tp/naumen/match")

    # --- партнёрства
    @task(5)
    def partnerships_dashboard(self):
        self.page("/api/partnerships/options", "/api/partnerships/analytics", "/api/layouts/project_product")

    @task(4)
    def partnerships_registry(self):
        if not self.records:
            return
        query = random.choice(["", "?status=Завершено", "?status=В работе", "?light=red"])
        self.page(f"/api/partnerships{query}")

    @task(2)
    def partnerships_summary(self):
        self.page("/api/partnerships/summary")
        if self.records:
            self.page("/api/partnerships/timeline")

    # --- структура компании (доступна всем)
    @task(4)
    def org_chart(self):
        self.client.get("/api/org/tree", name="GET /api/org/tree")

    @task(1)
    def org_person(self):
        self.client.get(f"/api/org/people/{random.randint(1, 9)}", name="GET /api/org/people/{id}")

    # --- 0.4.0: входящие данные и интеграции
    @task(2)
    def inbox(self):
        if not self.inbox:
            return
        status = random.choice(["", "pending", "applied,error"])
        self.client.get(f"/api/inbox?page=1&page_size=50{'&status=' + status if status else ''}",
                        name="GET /api/inbox")

    @task(1)
    def integrations(self):
        if self.username != "admin":
            return
        for path in ("/api/integrations", "/api/integrations/kinds", "/api/integrations/keys"):
            self.client.get(path, name=f"GET {path}")

    # --- редкие тяжёлые операции
    @task(1)
    def pdf(self):
        report = random.choice(["hr/dashboard", "tp/dashboard?weeks=13", "partnerships/summary", "tp/naumen"])
        service = {"hr": "hr", "tp": "tech", "partnerships": "project_product"}[report.split("/")[0]]
        if service not in self.services:
            return
        self.client.get(f"/api/pdf/{report}", name=f"GET /api/pdf/{report.split('?')[0]}")

    @task(1)
    def edit_metrics(self):
        if self.username not in ("admin", "hr_head"):
            return
        value = round(random.uniform(1.5, 4.5), 2)
        self.client.put("/api/hr/months/2026-07/metrics", json=[{"metric_key": "turnover", "value": value}],
                        headers={"X-CSRF-Token": self.csrf}, name="PUT /api/hr/months/{key}/metrics")


class InboundSystem(HttpUser):
    """Внешняя система (1С, скрипт): ключ интеграции и файл значений показателей раз в 30–60 с."""

    fixed_count = 2
    wait_time = between(30, 60)

    def on_start(self):
        self.key = ""
        r = self.client.post("/api/auth/login", json={"username": "admin", "password": "admin123"},
                             name="POST /api/auth/login")
        csrf = r.json().get("csrf_token", "") if r.status_code == 200 else ""
        r = self.client.post("/api/integrations/keys", json={"name": f"Нагрузка {uuid.uuid4().hex[:6]}",
                                                             "scopes": ["files", "status"]},
                             headers={"X-CSRF-Token": csrf}, name="POST /api/integrations/keys")
        if r.status_code == 201:
            self.key = r.json()["key"]
        self.client.cookies.clear()  # дальше — только ключ, без сессии

    @task
    def send_values(self):
        if not self.key:
            return
        value = f"{random.uniform(50, 70):.1f}".replace(".", ",")
        body = f"\ufeffПодразделение;Показатель;Период;Значение;Комментарий\nCOMM;fin.revenue;{random.choice(MONTHS)};" \
               f"{value};из 1С ({uuid.uuid4().hex[:8]})\n"
        r = self.client.post("/api/inbound/v1/files", headers={"Authorization": f"Bearer {self.key}"},
                             files={"file": ("values.csv", body.encode("utf-8"), "text/csv")},
                             data={"dataset": "indicators", "apply": "true"}, name="POST /api/inbound/v1/files")
        if r.status_code in (200, 201):
            self.client.get(f"/api/inbound/v1/files/{r.json()['id']}", headers={"Authorization": f"Bearer {self.key}"},
                            name="GET /api/inbound/v1/files/{id}")


@events.quitting.add_listener
def _(environment, **_kw):
    stats = environment.stats.total
    if stats.fail_ratio > 0.01 or stats.get_response_time_percentile(0.95) > 1500:
        environment.process_exit_code = 1

"""Нагрузочный сценарий «Дашбордов компании»: сотрудники открывают страницы служб.

Каждый виртуальный пользователь входит один раз (сессия в cookie) и дальше открывает
страницы с паузой на чтение 5–20 с. «Страница» — тот же набор запросов API, что делает
интерфейс. Смесь страниц отражает ожидаемую работу: обзор и дашборды чаще всего,
PDF и ввод данных — редко.

    locust -f loadtest/locustfile.py --host http://127.0.0.1:8000 \
        --users 1000 --spawn-rate 25 --run-time 6m --headless --csv loadtest/results/u1000

Учётные записи — демонстрационные (DEMO_DATA=true): несколько сессий на один логин допустимы.
"""
from __future__ import annotations

import random

from locust import HttpUser, between, events, task

# логин, пароль, службы с доступом (как у демо-пользователей)
ALL = {"hr", "tech", "project_product"}
USERS = [("admin", "admin123", ALL), ("hr_head", "hr123456", ALL), ("viewer", "view1234", ALL),
         ("tp_lead", "tp123456", {"tech"}), ("product", "pp123456", {"project_product"})]
MONTHS = ["2026-03", "2026-04", "2026-05", "2026-06", "2026-07"]


class Employee(HttpUser):
    wait_time = between(5, 20)

    def on_start(self):
        self.username, password, self.services = random.choice(USERS)
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

    @task(8)
    def hr_dashboard(self):
        months = ",".join(random.sample(MONTHS, k=random.randint(1, 5)))
        self.page("/api/hr/months", f"/api/hr/analytics/dashboard?months={months}", "/api/layouts/hr")

    @task(4)
    def hr_registry(self):
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
        query = random.choice(["", "?status=Завершено", "?status=В работе", "?light=red"])
        self.page(f"/api/partnerships{query}")

    @task(2)
    def partnerships_summary(self):
        self.page("/api/partnerships/summary", "/api/partnerships/timeline")

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


@events.quitting.add_listener
def _(environment, **_kw):
    stats = environment.stats.total
    if stats.fail_ratio > 0.01 or stats.get_response_time_percentile(0.95) > 1500:
        environment.process_exit_code = 1

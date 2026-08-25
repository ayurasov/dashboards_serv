<template>
  <div class="naumen-org-dashboard">
    <!-- Page header with filters (same pattern as TpNaumenDashboard) -->
    <div class="page-header">
      <div class="page-header__left">
        <h1>Аналитика по организациям и продуктам</h1>
        <span class="data-badge">Данные по 06.08.2026</span>
      </div>
      <div class="filters">
        <select v-model="selectedYear" @change="onYearChange">
          <option value="">Все годы</option>
          <option v-for="y in availableYears" :key="y" :value="y">{{ y }}</option>
        </select>
        <select v-model="selectedQuarter">
          <option value="">Все кварталы</option>
          <option value="Q1">Q1</option>
          <option value="Q2">Q2</option>
          <option value="Q3">Q3</option>
          <option value="Q4">Q4</option>
        </select>
        <select v-model="selectedOrg">
          <option value="">Все организации</option>
          <option v-for="o in ORG_KEYS" :key="o" :value="o">{{ o }}</option>
        </select>
      </div>
    </div>

    <!-- KPI cards -->
    <div class="kpi-grid">
      <div class="kpi-card light-gray">
        <div class="kpi-label">Организаций</div>
        <div class="kpi-value">{{ fmt(ORG_COUNT) }}</div>
        <div class="kpi-sub">за весь период</div>
      </div>
      <div class="kpi-card light-gray">
        <div class="kpi-label">Специалистов</div>
        <div class="kpi-value">{{ fmt(SPEC_COUNT) }}</div>
        <div class="kpi-sub">закрывали заявки</div>
      </div>
      <div class="kpi-card" :class="overdueClass(filteredKpi.overdue_pct, 10, 20)">
        <div class="kpi-label">Заявок за период</div>
        <div class="kpi-value">{{ fmt(filteredKpi.total) }}</div>
        <div class="kpi-sub">{{ filteredKpi.overdue_pct }}% просрочено</div>
      </div>
      <div class="kpi-card" :class="overdueClass(topOrgKpi.overdue_pct, 10, 20)">
        <div class="kpi-label">{{ topOrgKpi.name || '—' }}</div>
        <div class="kpi-value">{{ fmt(topOrgKpi.total) }}</div>
        <div class="kpi-sub">лидер по объёму заявок</div>
      </div>
      <div class="kpi-card" :class="overdueClass(topProdKpi.overdue_pct, 10, 20)">
        <div class="kpi-label">{{ topProdKpi.name || '—' }}</div>
        <div class="kpi-value">{{ fmt(topProdKpi.total) }}</div>
        <div class="kpi-sub">лидер по продукту/сервису</div>
      </div>
    </div>

    <!-- Row 2: Org monthly stacked trend -->
    <div class="section-card">
      <div class="card-header">
        <h2>Динамика заявок по организациям, шт.</h2>
        <div class="legend">
          <span v-for="(o, i) in ORG_KEYS" :key="o" class="legend-item">
            <span class="legend-dot" :style="{background: CHART_COLORS[i % CHART_COLORS.length]}"></span>{{ o }}
          </span>
        </div>
      </div>
      <canvas ref="orgTrendCanvas" height="90"></canvas>
    </div>

    <!-- Row 3: Org totals bar + Product doughnut -->
    <div class="charts-row">
      <div class="section-card chart-main">
        <h2>Топ организаций по объёму заявок</h2>
        <canvas ref="orgBarCanvas" height="90"></canvas>
      </div>
      <div class="section-card chart-side">
        <h2>Распределение по продуктам/сервисам</h2>
        <canvas ref="prodDoughnutCanvas" height="160"></canvas>
        <div class="channel-legend">
          <div v-for="(p, i) in PROD_TOTALS" :key="p.name" class="channel-item">
            <span class="legend-dot" :style="{background: CHART_COLORS[i % CHART_COLORS.length]}"></span>
            <span class="channel-name">{{ p.name }}</span>
            <span class="channel-val">{{ fmt(p.total) }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Row 4: Overdue % by org + Product monthly trend -->
    <div class="charts-row">
      <div class="section-card chart-half">
        <h2>Просрочка по организациям, %</h2>
        <canvas ref="orgOverdueCanvas" height="100"></canvas>
      </div>
      <div class="section-card chart-half">
        <h2>Динамика заявок по продуктам, шт.</h2>
        <canvas ref="prodTrendCanvas" height="100"></canvas>
      </div>
    </div>

    <!-- Row 5: Specialist workload table -->
    <div class="section-card">
      <h2>Загрузка специалистов (топ-10 по числу заявок)</h2>
      <table class="spec-table">
        <thead>
          <tr>
            <th>Специалист</th>
            <th>Заявок</th>
            <th>Медиана решения, дн.</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="s in SPEC_TOP" :key="s.name">
            <td>{{ s.name }}</td>
            <td class="num">{{ fmt(s.total) }}</td>
            <td class="num" :class="specTimeClass(s.avg_days)">{{ s.avg_days }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Nav tiles (same pattern as TpDashboard / TpNaumenDashboard) -->
    <div class="nav-cards">
      <router-link to="/tp" class="nav-card">
        <span class="nav-icon">📊</span>
        <span>Еженедельный дашборд</span>
      </router-link>
      <router-link to="/tp/naumen" class="nav-card">
        <span class="nav-icon">📈</span>
        <span>Аналитика заявок (Naumen)</span>
      </router-link>
      <router-link to="/tp/registry" class="nav-card">
        <span class="nav-icon">📋</span>
        <span>Реестр данных</span>
      </router-link>
      <router-link to="/tp/summary" class="nav-card">
        <span class="nav-icon">📈</span>
        <span>Сводная аналитика</span>
      </router-link>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch, nextTick } from 'vue'
import Chart from 'chart.js/auto'

// ── Static data extracted from Naumen full export ("Все заявки Наумен по 06.08.2026.csv") ──
const ORG_KEYS = ["ДЗО", "ПАО \"РусГидро\"", "АЛМИ Партнер", "АО «ДРСК»", "Нижегородская ГЭС", "Каскад Кубанских ГЭС", "Саяно-Шушенская ГЭС"]
const PROD_KEYS = ["AMail", "AlterOS", "AlterOffice", "Импортозамещение (общее)", "АЛМИ Партнёр (портал)"]

// Monthly breakdown by top-7 organizations (+ "Прочие") — same shape used for stacking
const ORG_MONTHLY = [{"period": "2023-06", "ДЗО": 0, "ПАО \"РусГидро\"": 0, "АЛМИ Партнер": 0, "АО «ДРСК»": 0, "Нижегородская ГЭС": 0, "Каскад Кубанских ГЭС": 0, "Саяно-Шушенская ГЭС": 1, "Прочие": 0}, {"period": "2023-07", "ДЗО": 3, "ПАО \"РусГидро\"": 2, "АЛМИ Партнер": 15, "АО «ДРСК»": 0, "Нижегородская ГЭС": 1, "Каскад Кубанских ГЭС": 0, "Саяно-Шушенская ГЭС": 0, "Прочие": 3}, {"period": "2023-08", "ДЗО": 8, "ПАО \"РусГидро\"": 0, "АЛМИ Партнер": 0, "АО «ДРСК»": 0, "Нижегородская ГЭС": 0, "Каскад Кубанских ГЭС": 0, "Саяно-Шушенская ГЭС": 1, "Прочие": 5}, {"period": "2023-09", "ДЗО": 7, "ПАО \"РусГидро\"": 0, "АЛМИ Партнер": 1, "АО «ДРСК»": 0, "Нижегородская ГЭС": 0, "Каскад Кубанских ГЭС": 1, "Саяно-Шушенская ГЭС": 0, "Прочие": 12}, {"period": "2023-10", "ДЗО": 6, "ПАО \"РусГидро\"": 0, "АЛМИ Партнер": 1, "АО «ДРСК»": 0, "Нижегородская ГЭС": 1, "Каскад Кубанских ГЭС": 1, "Саяно-Шушенская ГЭС": 3, "Прочие": 14}, {"period": "2023-11", "ДЗО": 17, "ПАО \"РусГидро\"": 50, "АЛМИ Партнер": 7, "АО «ДРСК»": 12, "Нижегородская ГЭС": 2, "Каскад Кубанских ГЭС": 0, "Саяно-Шушенская ГЭС": 1, "Прочие": 14}, {"period": "2023-12", "ДЗО": 16, "ПАО \"РусГидро\"": 7, "АЛМИ Партнер": 1, "АО «ДРСК»": 4, "Нижегородская ГЭС": 1, "Каскад Кубанских ГЭС": 0, "Саяно-Шушенская ГЭС": 2, "Прочие": 12}, {"period": "2024-01", "ДЗО": 18, "ПАО \"РусГидро\"": 20, "АЛМИ Партнер": 1, "АО «ДРСК»": 10, "Нижегородская ГЭС": 0, "Каскад Кубанских ГЭС": 0, "Саяно-Шушенская ГЭС": 2, "Прочие": 9}, {"period": "2024-02", "ДЗО": 16, "ПАО \"РусГидро\"": 4, "АЛМИ Партнер": 2, "АО «ДРСК»": 1, "Нижегородская ГЭС": 1, "Каскад Кубанских ГЭС": 1, "Саяно-Шушенская ГЭС": 1, "Прочие": 15}, {"period": "2024-03", "ДЗО": 9, "ПАО \"РусГидро\"": 7, "АЛМИ Партнер": 3, "АО «ДРСК»": 3, "Нижегородская ГЭС": 6, "Каскад Кубанских ГЭС": 0, "Саяно-Шушенская ГЭС": 3, "Прочие": 7}, {"period": "2024-04", "ДЗО": 10, "ПАО \"РусГидро\"": 3, "АЛМИ Партнер": 0, "АО «ДРСК»": 4, "Нижегородская ГЭС": 4, "Каскад Кубанских ГЭС": 0, "Саяно-Шушенская ГЭС": 3, "Прочие": 11}, {"period": "2024-05", "ДЗО": 7, "ПАО \"РусГидро\"": 8, "АЛМИ Партнер": 1, "АО «ДРСК»": 2, "Нижегородская ГЭС": 2, "Каскад Кубанских ГЭС": 0, "Саяно-Шушенская ГЭС": 2, "Прочие": 8}, {"period": "2024-06", "ДЗО": 10, "ПАО \"РусГидро\"": 3, "АЛМИ Партнер": 2, "АО «ДРСК»": 0, "Нижегородская ГЭС": 7, "Каскад Кубанских ГЭС": 0, "Саяно-Шушенская ГЭС": 8, "Прочие": 9}, {"period": "2024-07", "ДЗО": 7, "ПАО \"РусГидро\"": 3, "АЛМИ Партнер": 0, "АО «ДРСК»": 1, "Нижегородская ГЭС": 7, "Каскад Кубанских ГЭС": 0, "Саяно-Шушенская ГЭС": 3, "Прочие": 11}, {"period": "2024-08", "ДЗО": 9, "ПАО \"РусГидро\"": 11, "АЛМИ Партнер": 1, "АО «ДРСК»": 1, "Нижегородская ГЭС": 1, "Каскад Кубанских ГЭС": 0, "Саяно-Шушенская ГЭС": 3, "Прочие": 10}, {"period": "2024-09", "ДЗО": 8, "ПАО \"РусГидро\"": 16, "АЛМИ Партнер": 1, "АО «ДРСК»": 2, "Нижегородская ГЭС": 2, "Каскад Кубанских ГЭС": 21, "Саяно-Шушенская ГЭС": 3, "Прочие": 10}, {"period": "2024-10", "ДЗО": 9, "ПАО \"РусГидро\"": 13, "АЛМИ Партнер": 38, "АО «ДРСК»": 5, "Нижегородская ГЭС": 8, "Каскад Кубанских ГЭС": 18, "Саяно-Шушенская ГЭС": 5, "Прочие": 20}, {"period": "2024-11", "ДЗО": 14, "ПАО \"РусГидро\"": 8, "АЛМИ Партнер": 32, "АО «ДРСК»": 2, "Нижегородская ГЭС": 5, "Каскад Кубанских ГЭС": 16, "Саяно-Шушенская ГЭС": 7, "Прочие": 31}, {"period": "2024-12", "ДЗО": 7, "ПАО \"РусГидро\"": 8, "АЛМИ Партнер": 22, "АО «ДРСК»": 2, "Нижегородская ГЭС": 7, "Каскад Кубанских ГЭС": 10, "Саяно-Шушенская ГЭС": 3, "Прочие": 29}, {"period": "2025-01", "ДЗО": 17, "ПАО \"РусГидро\"": 8, "АЛМИ Партнер": 19, "АО «ДРСК»": 2, "Нижегородская ГЭС": 3, "Каскад Кубанских ГЭС": 2, "Саяно-Шушенская ГЭС": 1, "Прочие": 20}, {"period": "2025-02", "ДЗО": 23, "ПАО \"РусГидро\"": 5, "АЛМИ Партнер": 21, "АО «ДРСК»": 6, "Нижегородская ГЭС": 6, "Каскад Кубанских ГЭС": 0, "Саяно-Шушенская ГЭС": 3, "Прочие": 28}, {"period": "2025-03", "ДЗО": 15, "ПАО \"РусГидро\"": 8, "АЛМИ Партнер": 19, "АО «ДРСК»": 3, "Нижегородская ГЭС": 5, "Каскад Кубанских ГЭС": 2, "Саяно-Шушенская ГЭС": 1, "Прочие": 18}, {"period": "2025-04", "ДЗО": 22, "ПАО \"РусГидро\"": 5, "АЛМИ Партнер": 15, "АО «ДРСК»": 4, "Нижегородская ГЭС": 2, "Каскад Кубанских ГЭС": 3, "Саяно-Шушенская ГЭС": 4, "Прочие": 18}, {"period": "2025-05", "ДЗО": 18, "ПАО \"РусГидро\"": 9, "АЛМИ Партнер": 10, "АО «ДРСК»": 6, "Нижегородская ГЭС": 4, "Каскад Кубанских ГЭС": 2, "Саяно-Шушенская ГЭС": 4, "Прочие": 12}, {"period": "2025-06", "ДЗО": 12, "ПАО \"РусГидро\"": 6, "АЛМИ Партнер": 6, "АО «ДРСК»": 2, "Нижегородская ГЭС": 2, "Каскад Кубанских ГЭС": 3, "Саяно-Шушенская ГЭС": 1, "Прочие": 9}, {"period": "2025-07", "ДЗО": 17, "ПАО \"РусГидро\"": 7, "АЛМИ Партнер": 9, "АО «ДРСК»": 3, "Нижегородская ГЭС": 4, "Каскад Кубанских ГЭС": 2, "Саяно-Шушенская ГЭС": 2, "Прочие": 12}, {"period": "2025-08", "ДЗО": 15, "ПАО \"РусГидро\"": 6, "АЛМИ Партнер": 4, "АО «ДРСК»": 2, "Нижегородская ГЭС": 4, "Каскад Кубанских ГЭС": 2, "Саяно-Шушенская ГЭС": 2, "Прочие": 22}, {"period": "2025-09", "ДЗО": 14, "ПАО \"РусГидро\"": 8, "АЛМИ Партнер": 5, "АО «ДРСК»": 3, "Нижегородская ГЭС": 3, "Каскад Кубанских ГЭС": 2, "Саяно-Шушенская ГЭС": 1, "Прочие": 15}, {"period": "2025-10", "ДЗО": 10, "ПАО \"РусГидро\"": 4, "АЛМИ Партнер": 3, "АО «ДРСК»": 2, "Нижегородская ГЭС": 1, "Каскад Кубанских ГЭС": 1, "Саяно-Шушенская ГЭС": 1, "Прочие": 14}, {"period": "2025-11", "ДЗО": 6, "ПАО \"РусГидро\"": 3, "АЛМИ Партнер": 2, "АО «ДРСК»": 1, "Нижегородская ГЭС": 1, "Каскад Кубанских ГЭС": 0, "Саяно-Шушенская ГЭС": 1, "Прочие": 10}, {"period": "2025-12", "ДЗО": 7, "ПАО \"РусГидро\"": 3, "АЛМИ Партнер": 1, "АО «ДРСК»": 1, "Нижегородская ГЭС": 1, "Каскад Кубанских ГЭС": 0, "Саяно-Шушенская ГЭС": 1, "Прочие": 9}, {"period": "2026-01", "ДЗО": 9, "ПАО \"РусГидро\"": 4, "АЛМИ Партнер": 1, "АО «ДРСК»": 1, "Нижегородская ГЭС": 1, "Каскад Кубанских ГЭС": 0, "Саяно-Шушенская ГЭС": 1, "Прочие": 10}, {"period": "2026-02", "ДЗО": 12, "ПАО \"РусГидро\"": 6, "АЛМИ Партнер": 0, "АО «ДРСК»": 2, "Нижегородская ГЭС": 1, "Каскад Кубанских ГЭС": 0, "Саяно-Шушенская ГЭС": 1, "Прочие": 15}, {"period": "2026-03", "ДЗО": 13, "ПАО \"РусГидро\"": 5, "АЛМИ Партнер": 0, "АО «ДРСК»": 3, "Нижегородская ГЭС": 1, "Каскад Кубанских ГЭС": 0, "Саяно-Шушенская ГЭС": 1, "Прочие": 14}, {"period": "2026-04", "ДЗО": 18, "ПАО \"РусГидро\"": 9, "АЛМИ Партнер": 0, "АО «ДРСК»": 4, "Нижегородская ГЭС": 1, "Каскад Кубанских ГЭС": 0, "Саяно-Шушенская ГЭС": 1, "Прочие": 21}, {"period": "2026-05", "ДЗО": 11, "ПАО \"РусГидро\"": 6, "АЛМИ Партнер": 0, "АО «ДРСК»": 3, "Нижегородская ГЭС": 0, "Каскад Кубанских ГЭС": 0, "Саяно-Шушенская ГЭС": 0, "Прочие": 15}, {"period": "2026-06", "ДЗО": 15, "ПАО \"РусГидро\"": 13, "АЛМИ Партнер": 0, "АО «ДРСК»": 8, "Нижегородская ГЭС": 0, "Каскад Кубанских ГЭС": 0, "Саяно-Шушенская ГЭС": 0, "Прочие": 11}, {"period": "2026-07", "ДЗО": 20, "ПАО \"РусГидро\"": 8, "АЛМИ Партнер": 0, "АО «ДРСК»": 3, "Нижегородская ГЭС": 1, "Каскад Кубанских ГЭС": 0, "Саяно-Шушенская ГЭС": 0, "Прочие": 18}, {"period": "2026-08", "ДЗО": 1, "ПАО \"РусГидро\"": 3, "АЛМИ Партнер": 0, "АО «ДРСК»": 0, "Нижегородская ГЭС": 0, "Каскад Кубанских ГЭС": 0, "Саяно-Шушенская ГЭС": 0, "Прочие": 2}]

// Monthly breakdown by top-5 products/services (+ "Прочее")
const PROD_MONTHLY = [{"period": "2023-06", "AMail": 0, "AlterOS": 0, "AlterOffice": 0, "Импортозамещение (общее)": 0, "АЛМИ Партнёр (портал)": 0, "Прочее": 1}, {"period": "2023-07", "AMail": 0, "AlterOS": 2, "AlterOffice": 0, "Импортозамещение (общее)": 1, "АЛМИ Партнёр (портал)": 1, "Прочее": 20}, {"period": "2023-08", "AMail": 1, "AlterOS": 6, "AlterOffice": 0, "Импортозамещение (общее)": 1, "АЛМИ Партнёр (портал)": 0, "Прочее": 6}, {"period": "2023-09", "AMail": 6, "AlterOS": 3, "AlterOffice": 1, "Импортозамещение (общее)": 3, "АЛМИ Партнёр (портал)": 1, "Прочее": 7}, {"period": "2023-10", "AMail": 8, "AlterOS": 4, "AlterOffice": 3, "Импортозамещение (общее)": 1, "АЛМИ Партнёр (портал)": 0, "Прочее": 10}, {"period": "2023-11", "AMail": 10, "AlterOS": 11, "AlterOffice": 7, "Импортозамещение (общее)": 3, "АЛМИ Партнёр (портал)": 1, "Прочее": 71}, {"period": "2023-12", "AMail": 5, "AlterOS": 8, "AlterOffice": 4, "Импортозамещение (общее)": 1, "АЛМИ Партнёр (портал)": 0, "Прочее": 25}, {"period": "2024-01", "AMail": 10, "AlterOS": 7, "AlterOffice": 2, "Импортозамещение (общее)": 2, "АЛМИ Партнёр (портал)": 1, "Прочее": 38}, {"period": "2024-02", "AMail": 14, "AlterOS": 3, "AlterOffice": 2, "Импортозамещение (общее)": 3, "АЛМИ Партнёр (портал)": 1, "Прочее": 18}, {"period": "2024-03", "AMail": 13, "AlterOS": 1, "AlterOffice": 3, "Импортозамещение (общее)": 1, "АЛМИ Партнёр (портал)": 1, "Прочее": 19}, {"period": "2024-04", "AMail": 11, "AlterOS": 0, "AlterOffice": 5, "Импортозамещение (общее)": 0, "АЛМИ Партнёр (портал)": 1, "Прочее": 18}, {"period": "2024-05", "AMail": 4, "AlterOS": 4, "AlterOffice": 3, "Импортозамещение (общее)": 2, "АЛМИ Партнёр (портал)": 1, "Прочее": 16}, {"period": "2024-06", "AMail": 8, "AlterOS": 2, "AlterOffice": 5, "Импортозамещение (общее)": 1, "АЛМИ Партнёр (портал)": 1, "Прочее": 22}, {"period": "2024-07", "AMail": 3, "AlterOS": 6, "AlterOffice": 4, "Импортозамещение (общее)": 1, "АЛМИ Партнёр (портал)": 0, "Прочее": 18}, {"period": "2024-08", "AMail": 9, "AlterOS": 4, "AlterOffice": 5, "Импортозамещение (общее)": 0, "АЛМИ Партнёр (портал)": 1, "Прочее": 16}, {"period": "2024-09", "AMail": 9, "AlterOS": 8, "AlterOffice": 4, "Импортозамещение (общее)": 1, "АЛМИ Партнёр (портал)": 1, "Прочее": 40}, {"period": "2024-10", "AMail": 12, "AlterOS": 7, "AlterOffice": 6, "Импортозамещение (общее)": 3, "АЛМИ Партнёр (портал)": 1, "Прочее": 87}, {"period": "2024-11", "AMail": 8, "AlterOS": 6, "AlterOffice": 8, "Импортозамещение (общее)": 3, "АЛМИ Партнёр (портал)": 1, "Прочее": 89}, {"period": "2024-12", "AMail": 5, "AlterOS": 4, "AlterOffice": 5, "Импортозамещение (общее)": 1, "АЛМИ Партнёр (портал)": 1, "Прочее": 72}, {"period": "2025-01", "AMail": 9, "AlterOS": 5, "AlterOffice": 6, "Импортозамещение (общее)": 2, "АЛМИ Партнёр (портал)": 1, "Прочее": 49}, {"period": "2025-02", "AMail": 12, "AlterOS": 6, "AlterOffice": 7, "Импортозамещение (общее)": 3, "АЛМИ Партнёр (портал)": 2, "Прочее": 55}, {"period": "2025-03", "AMail": 9, "AlterOS": 5, "AlterOffice": 5, "Импортозамещение (общее)": 2, "АЛМИ Партнёр (портал)": 1, "Прочее": 44}, {"period": "2025-04", "AMail": 10, "AlterOS": 5, "AlterOffice": 6, "Импортозамещение (общее)": 2, "АЛМИ Партнёр (портал)": 1, "Прочее": 45}, {"period": "2025-05", "AMail": 7, "AlterOS": 4, "AlterOffice": 4, "Импортозамещение (общее)": 1, "АЛМИ Партнёр (портал)": 1, "Прочее": 33}, {"period": "2025-06", "AMail": 5, "AlterOS": 3, "AlterOffice": 3, "Импортозамещение (общее)": 1, "АЛМИ Партнёр (портал)": 0, "Прочее": 24}, {"period": "2025-07", "AMail": 6, "AlterOS": 4, "AlterOffice": 4, "Импортозамещение (общее)": 1, "АЛМИ Партнёр (портал)": 1, "Прочее": 30}, {"period": "2025-08", "AMail": 5, "AlterOS": 4, "AlterOffice": 3, "Импортозамещение (общее)": 1, "АЛМИ Партнёр (портал)": 0, "Прочее": 22}, {"period": "2025-09", "AMail": 4, "AlterOS": 3, "AlterOffice": 3, "Импортозамещение (общее)": 1, "АЛМИ Партнёр (портал)": 0, "Прочее": 20}, {"period": "2025-10", "AMail": 3, "AlterOS": 2, "AlterOffice": 2, "Импортозамещение (общее)": 1, "АЛМИ Партнёр (портал)": 0, "Прочее": 13}, {"period": "2025-11", "AMail": 2, "AlterOS": 1, "AlterOffice": 1, "Импортозамещение (общее)": 0, "АЛМИ Партнёр (портал)": 0, "Прочее": 10}, {"period": "2025-12", "AMail": 2, "AlterOS": 1, "AlterOffice": 1, "Импортозамещение (общее)": 0, "АЛМИ Партнёр (портал)": 0, "Прочее": 9}, {"period": "2026-01", "AMail": 2, "AlterOS": 1, "AlterOffice": 1, "Импортозамещение (общее)": 0, "АЛМИ Партнёр (портал)": 0, "Прочее": 12}, {"period": "2026-02", "AMail": 3, "AlterOS": 1, "AlterOffice": 1, "Импортозамещение (общее)": 0, "АЛМИ Партнёр (портал)": 0, "Прочее": 17}, {"period": "2026-03", "AMail": 3, "AlterOS": 1, "AlterOffice": 1, "Импортозамещение (общее)": 0, "АЛМИ Партнёр (портал)": 0, "Прочее": 17}, {"period": "2026-04", "AMail": 5, "AlterOS": 2, "AlterOffice": 2, "Импортозамещение (общее)": 0, "АЛМИ Партнёр (портал)": 0, "Прочее": 24}, {"period": "2026-05", "AMail": 3, "AlterOS": 1, "AlterOffice": 1, "Импортозамещение (общее)": 0, "АЛМИ Партнёр (портал)": 0, "Прочее": 15}, {"period": "2026-06", "AMail": 0, "AlterOS": 4, "AlterOffice": 21, "Импортозамещение (общее)": 0, "АЛМИ Партнёр (портал)": 0, "Прочее": 22}, {"period": "2026-07", "AMail": 0, "AlterOS": 8, "AlterOffice": 7, "Импортозамещение (общее)": 1, "АЛМИ Партнёр (портал)": 0, "Прочее": 34}, {"period": "2026-08", "AMail": 0, "AlterOS": 0, "AlterOffice": 2, "Импортозамещение (общее)": 0, "АЛМИ Партнёр (портал)": 0, "Прочее": 4}]

// All-time totals per organization (top 15), used for the bar chart + overdue %
const ORG_TOTALS = [{"name": "ДЗО", "total": 478, "overdue": 94, "avg_days": 2.3, "overdue_pct": 19.7}, {"name": "ПАО \"РусГидро\"", "total": 336, "overdue": 37, "avg_days": 1.6, "overdue_pct": 11.0}, {"name": "АЛМИ Партнер", "total": 228, "overdue": 10, "avg_days": 2.7, "overdue_pct": 4.4}, {"name": "АО «ДРСК»", "total": 92, "overdue": 2, "avg_days": 1.0, "overdue_pct": 2.2}, {"name": "Нижегородская ГЭС", "total": 89, "overdue": 10, "avg_days": 3.9, "overdue_pct": 11.2}, {"name": "Каскад Кубанских ГЭС", "total": 74, "overdue": 3, "avg_days": 1.6, "overdue_pct": 4.1}, {"name": "Саяно-Шушенская ГЭС", "total": 68, "overdue": 7, "avg_days": 4.0, "overdue_pct": 10.3}, {"name": "ПАО «Якутскэнерго»", "total": 52, "overdue": 6, "avg_days": 1.0, "overdue_pct": 11.5}, {"name": "ПАО «Магаданэнерго»", "total": 45, "overdue": 4, "avg_days": 1.0, "overdue_pct": 8.9}, {"name": "АО «ДГК»", "total": 39, "overdue": 14, "avg_days": 0.9, "overdue_pct": 35.9}, {"name": "АО \"Сахаэнерго\"", "total": 34, "overdue": 1, "avg_days": 1.2, "overdue_pct": 2.9}, {"name": "Волжская ГЭС", "total": 30, "overdue": 4, "avg_days": 2.1, "overdue_pct": 13.3}, {"name": "Жигулевская ГЭС", "total": 29, "overdue": 7, "avg_days": 2.1, "overdue_pct": 24.1}, {"name": "Новосибирская ГЭС", "total": 26, "overdue": 6, "avg_days": 1.5, "overdue_pct": 23.1}, {"name": "ПАО «Камчатскэнерго»", "total": 25, "overdue": 1, "avg_days": 1.0, "overdue_pct": 4.0}]

// All-time totals per product/service, used for the doughnut + trend legend
const PROD_TOTALS = [{"name": "Прочее", "total": 1051, "overdue": 147, "overdue_pct": 14.0}, {"name": "AMail", "total": 261, "overdue": 27, "overdue_pct": 10.3}, {"name": "AlterOS", "total": 237, "overdue": 37, "overdue_pct": 15.6}, {"name": "AlterOffice", "total": 219, "overdue": 23, "overdue_pct": 10.5}, {"name": "Импортозамещение (общее)", "total": 51, "overdue": 11, "overdue_pct": 21.6}, {"name": "АЛМИ Партнёр (портал)", "total": 44, "overdue": 1, "overdue_pct": 2.3}, {"name": "Nextcloud", "total": 5, "overdue": 0, "overdue_pct": 0.0}]

// Top-10 specialists by ticket volume with median resolution time (days)
const SPEC_TOP = [{"name": "Тимкачев Антон Владимирович", "total": 329, "avg_days": 1.4}, {"name": "Долгополова Анастасия Александровна", "total": 176, "avg_days": 2.0}, {"name": "Яковлев Павел Евгеньевич", "total": 145, "avg_days": 5.8}, {"name": "Нейферт Владимир Владиславович", "total": 140, "avg_days": 5.0}, {"name": "Колпаков Даниил Юрьевич", "total": 132, "avg_days": 1.5}, {"name": "Иванов Егор Николаевич", "total": 122, "avg_days": 1.1}, {"name": "Беспалов Иван Сергеевич", "total": 114, "avg_days": 3.1}, {"name": "Луговой Михаил Александрович", "total": 104, "avg_days": 3.3}, {"name": "Худяков Андрей Сергеевич", "total": 99, "avg_days": 8.1}, {"name": "Осенчугов Александр Николаевич", "total": 88, "avg_days": 10.9}]

const ORG_COUNT = 40
const SPEC_COUNT = 24
const CHART_COLORS = ['#2980b9','#27ae60','#e67e22','#8e44ad','#e74c3c','#1abc9c','#f1c40f','#7f8c8d']

// ── Filters ──
const selectedYear = ref('')
const selectedQuarter = ref('')
const selectedOrg = ref('')

const availableYears = computed(() => {
  return [...new Set(ORG_MONTHLY.map(r => r.period.slice(0, 4)))].sort()
})

const QUARTER_MAP = { Q1: ['01','02','03'], Q2: ['04','05','06'], Q3: ['07','08','09'], Q4: ['10','11','12'] }

function periodMatches(period) {
  const [y, m] = period.split('-')
  if (selectedYear.value && y !== selectedYear.value) return false
  if (selectedQuarter.value && !QUARTER_MAP[selectedQuarter.value].includes(m)) return false
  return true
}

const filteredOrgMonthly = computed(() => ORG_MONTHLY.filter(r => periodMatches(r.period)))
const filteredProdMonthly = computed(() => PROD_MONTHLY.filter(r => periodMatches(r.period)))

const filteredKpi = computed(() => {
  const rows = filteredOrgMonthly.value
  if (!rows.length) return { total: 0, overdue: 0, overdue_pct: 0 }
  let total = 0
  let overdue = 0
  const keys = selectedOrg.value ? [selectedOrg.value] : [...ORG_KEYS, 'Прочие']
  rows.forEach(r => {
    keys.forEach(k => { total += r[k] || 0 })
  })
  // Overdue % is approximated from all-time org overdue ratio when a single org is selected,
  // otherwise from the global filtered total using the dataset-wide overdue share.
  if (selectedOrg.value) {
    const org = ORG_TOTALS.find(o => o.name === selectedOrg.value)
    overdue = org ? Math.round(total * (org.overdue_pct / 100)) : 0
  } else {
    overdue = Math.round(total * 0.132) // dataset-wide overdue share (246/1868)
  }
  return {
    total,
    overdue,
    overdue_pct: total ? +(overdue / total * 100).toFixed(1) : 0,
  }
})

const topOrgKpi = computed(() => {
  const sorted = [...ORG_TOTALS].sort((a, b) => b.total - a.total)
  return sorted[0] || {}
})
const topProdKpi = computed(() => {
  const sorted = [...PROD_TOTALS].sort((a, b) => b.total - a.total)
  return sorted[0] || {}
})

// ── Chart refs ──
const orgTrendCanvas = ref(null)
const orgBarCanvas = ref(null)
const prodDoughnutCanvas = ref(null)
const orgOverdueCanvas = ref(null)
const prodTrendCanvas = ref(null)

const charts = {}

function fmt(v) { return v != null ? Number(v).toLocaleString('ru-RU') : '—' }

function overdueClass(val, green, yellow) {
  if (val == null) return 'light-gray'
  if (val <= green) return 'light-green'
  if (val <= yellow) return 'light-yellow'
  return 'light-red'
}
function specTimeClass(days) {
  if (days == null) return ''
  if (days <= 2) return 'txt-green'
  if (days <= 5) return 'txt-yellow'
  return 'txt-red'
}

function onYearChange() { selectedQuarter.value = '' }

function destroyAll() {
  Object.values(charts).forEach(c => { try { c.destroy() } catch {} })
}

function renderAll() {
  destroyAll()
  const orgRows = filteredOrgMonthly.value
  const prodRows = filteredProdMonthly.value
  if (!orgRows.length && !prodRows.length) return

  // 1. Org monthly stacked bar
  if (orgTrendCanvas.value && orgRows.length) {
    const labels = orgRows.map(r => r.period)
    const keys = selectedOrg.value ? [selectedOrg.value] : [...ORG_KEYS, 'Прочие']
    charts.orgTrend = new Chart(orgTrendCanvas.value, {
      type: 'bar',
      data: {
        labels,
        datasets: keys.map((k, i) => ({
          label: k,
          data: orgRows.map(r => r[k] || 0),
          backgroundColor: CHART_COLORS[i % CHART_COLORS.length],
          borderRadius: 2,
        })),
      },
      options: {
        responsive: true, maintainAspectRatio: true,
        plugins: { legend: { display: false }, tooltip: { mode: 'index' } },
        scales: {
          x: { stacked: true, ticks: { font: { size: 10 }, maxRotation: 45 } },
          y: { stacked: true, beginAtZero: true, ticks: { font: { size: 11 } } },
        },
      },
    })
  }

  // 2. Org totals horizontal bar (top 12)
  if (orgBarCanvas.value) {
    const top = [...ORG_TOTALS].sort((a, b) => b.total - a.total).slice(0, 12)
    charts.orgBar = new Chart(orgBarCanvas.value, {
      type: 'bar',
      data: {
        labels: top.map(o => o.name),
        datasets: [{
          label: 'Заявок',
          data: top.map(o => o.total),
          backgroundColor: 'rgba(41,128,185,0.6)', borderColor: '#2980b9', borderWidth: 1, borderRadius: 3,
        }],
      },
      options: {
        indexAxis: 'y',
        responsive: true, maintainAspectRatio: true,
        plugins: { legend: { display: false } },
        scales: { x: { beginAtZero: true, ticks: { font: { size: 11 } } }, y: { ticks: { font: { size: 10 } } } },
      },
    })
  }

  // 3. Product doughnut
  if (prodDoughnutCanvas.value) {
    charts.prodDoughnut = new Chart(prodDoughnutCanvas.value, {
      type: 'doughnut',
      data: {
        labels: PROD_TOTALS.map(p => p.name),
        datasets: [{ data: PROD_TOTALS.map(p => p.total), backgroundColor: CHART_COLORS, borderWidth: 2 }],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false }, tooltip: { callbacks: { label: ctx => `${ctx.label}: ${ctx.raw}` } } },
        cutout: '62%',
      },
    })
  }

  // 4. Overdue % by organization (top 12 by volume)
  if (orgOverdueCanvas.value) {
    const top = [...ORG_TOTALS].sort((a, b) => b.total - a.total).slice(0, 12)
    charts.orgOverdue = new Chart(orgOverdueCanvas.value, {
      type: 'bar',
      data: {
        labels: top.map(o => o.name),
        datasets: [{
          label: 'Просрочено, %',
          data: top.map(o => o.overdue_pct),
          backgroundColor: top.map(o => o.overdue_pct > 20 ? 'rgba(231,76,60,0.65)' : o.overdue_pct > 10 ? 'rgba(241,196,15,0.65)' : 'rgba(39,174,96,0.65)'),
          borderRadius: 3,
        }],
      },
      options: {
        responsive: true, maintainAspectRatio: true,
        plugins: { legend: { display: false } },
        scales: {
          y: { beginAtZero: true, max: 40, ticks: { callback: v => v + '%', font: { size: 11 } } },
          x: { ticks: { font: { size: 9 }, maxRotation: 60 } },
        },
      },
    })
  }

  // 5. Product monthly trend (line, multi-series)
  if (prodTrendCanvas.value && prodRows.length) {
    const labels = prodRows.map(r => r.period)
    charts.prodTrend = new Chart(prodTrendCanvas.value, {
      type: 'line',
      data: {
        labels,
        datasets: PROD_KEYS.map((k, i) => ({
          label: k,
          data: prodRows.map(r => r[k] || 0),
          borderColor: CHART_COLORS[i % CHART_COLORS.length],
          backgroundColor: 'transparent',
          tension: 0.3, pointRadius: 2,
        })),
      },
      options: {
        responsive: true, maintainAspectRatio: true,
        plugins: { legend: { display: true, position: 'bottom', labels: { font: { size: 10 } } } },
        scales: { y: { beginAtZero: true, ticks: { font: { size: 11 } } }, x: { ticks: { font: { size: 9 }, maxRotation: 45 } } },
      },
    })
  }
}

watch([selectedYear, selectedQuarter, selectedOrg], () => nextTick(renderAll))
onMounted(() => nextTick(renderAll))
</script>

<style scoped>
.naumen-org-dashboard { padding: var(--space-6); display: flex; flex-direction: column; gap: var(--space-5); }

/* Header */
.page-header { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: var(--space-3); }
.page-header__left { display: flex; align-items: baseline; gap: var(--space-3); }
.page-header h1 { font-size: var(--text-xl); font-weight: 700; }
.data-badge { font-size: var(--text-xs); color: var(--color-text-muted); background: var(--color-surface-offset); border: 1px solid var(--color-border); padding: 2px var(--space-2); border-radius: var(--radius-full); }
.filters { display: flex; gap: var(--space-2); flex-wrap: wrap; }
.filters select { padding: var(--space-2) var(--space-3); border: 1px solid var(--color-border); border-radius: var(--radius-md); background: var(--color-surface); color: var(--color-text); font-size: var(--text-sm); }

/* KPI grid */
.kpi-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(170px, 1fr)); gap: var(--space-3); }
.kpi-card { background: var(--color-surface); border: 1px solid var(--color-border); border-radius: var(--radius-lg); padding: var(--space-4); text-align: center; position: relative; overflow: hidden; }
.kpi-card::before { content: ''; position: absolute; top: 0; left: 0; right: 0; height: 3px; }
.kpi-card.light-green::before { background: #27ae60; }
.kpi-card.light-yellow::before { background: #f1c40f; }
.kpi-card.light-red::before { background: #e74c3c; }
.kpi-card.light-gray::before { background: var(--color-border); }
.kpi-label { font-size: var(--text-xs); color: var(--color-text-muted); margin-bottom: var(--space-2); text-transform: uppercase; letter-spacing: .03em; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.kpi-value { font-size: var(--text-xl); font-weight: 700; font-variant-numeric: tabular-nums; }
.kpi-sub { font-size: var(--text-xs); color: var(--color-text-muted); margin-top: var(--space-1); }

/* Section cards */
.section-card { background: var(--color-surface); border: 1px solid var(--color-border); border-radius: var(--radius-lg); padding: var(--space-5); }
.section-card h2 { font-size: var(--text-base); font-weight: 600; margin-bottom: var(--space-4); }
.card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--space-4); flex-wrap: wrap; gap: var(--space-2); }
.card-header h2 { margin-bottom: 0; }

/* Chart layout */
.charts-row { display: grid; grid-template-columns: 1fr 280px; gap: var(--space-3); }
@media (max-width: 800px) { .charts-row { grid-template-columns: 1fr; } }
.chart-main { min-width: 0; }
.chart-side { display: flex; flex-direction: column; }
.chart-half { min-width: 0; }
.charts-row:has(.chart-half) { grid-template-columns: 1fr 1fr; }
@media (max-width: 700px) { .charts-row:has(.chart-half) { grid-template-columns: 1fr; } }

/* Legend */
.legend { display: flex; gap: var(--space-3); align-items: center; font-size: var(--text-xs); color: var(--color-text-muted); flex-wrap: wrap; }
.legend-item { display: inline-flex; align-items: center; }
.legend-dot { display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: var(--space-1); }

/* Channel / product legend */
.channel-legend { display: flex; flex-direction: column; gap: var(--space-2); margin-top: var(--space-3); }
.channel-item { display: flex; align-items: center; gap: var(--space-2); font-size: var(--text-xs); }
.channel-name { flex: 1; color: var(--color-text-muted); }
.channel-val { font-weight: 600; font-variant-numeric: tabular-nums; }

/* Specialist table */
.spec-table { width: 100%; border-collapse: collapse; font-size: var(--text-sm); }
.spec-table th { text-align: left; padding: var(--space-2) var(--space-3); border-bottom: 1px solid var(--color-border); color: var(--color-text-muted); font-weight: 600; font-size: var(--text-xs); text-transform: uppercase; letter-spacing: .03em; }
.spec-table td { padding: var(--space-2) var(--space-3); border-bottom: 1px solid var(--color-divider); }
.spec-table td.num { text-align: right; font-variant-numeric: tabular-nums; }
.spec-table tr:last-child td { border-bottom: none; }
.txt-green { color: #27ae60; font-weight: 600; }
.txt-yellow { color: #d19900; font-weight: 600; }
.txt-red { color: #e74c3c; font-weight: 600; }

/* Nav cards — identical to TpDashboard / TpNaumenDashboard */
.nav-cards { display: flex; gap: var(--space-3); flex-wrap: wrap; }
.nav-card { display: flex; align-items: center; gap: var(--space-2); padding: var(--space-4) var(--space-5); background: var(--color-surface); border: 1px solid var(--color-border); border-radius: var(--radius-lg); text-decoration: none; color: var(--color-text); font-weight: 500; font-size: var(--text-sm); transition: all var(--transition-interactive); }
.nav-card:hover { background: var(--color-primary); color: #fff; border-color: var(--color-primary); }
.nav-icon { font-size: 1.2rem; }
</style>

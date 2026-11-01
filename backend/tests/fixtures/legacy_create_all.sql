-- База «Дашбордов» версии до 0.1.0, созданная create_all() без Alembic (выборка строк).
-- Используется в tests/test_migrations.py для проверки миграции 0012.
PRAGMA foreign_keys=OFF;
BEGIN;
CREATE TABLE audit_logs (
	id INTEGER NOT NULL, 
	user_id INTEGER, 
	username VARCHAR(100), 
	entity_type VARCHAR(60) NOT NULL, 
	entity_id VARCHAR(100), 
	action VARCHAR(30) NOT NULL, 
	before_json JSON, 
	after_json JSON, 
	ip_address VARCHAR(50), 
	timestamp DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
);
CREATE TABLE benchmarks (
	id INTEGER NOT NULL, 
	metric_key VARCHAR(80) NOT NULL, 
	label VARCHAR(200), 
	year INTEGER NOT NULL, 
	value FLOAT NOT NULL, 
	target_value FLOAT, 
	description TEXT, 
	source VARCHAR(300), 
	PRIMARY KEY (id), 
	CONSTRAINT uq_benchmark_metric_year UNIQUE (metric_key, year)
);
CREATE TABLE color_palettes (
	id INTEGER NOT NULL, 
	scope VARCHAR(30) NOT NULL, 
	module_key VARCHAR(80), 
	name VARCHAR(200) NOT NULL, 
	colors_json TEXT NOT NULL, 
	is_active BOOLEAN, 
	PRIMARY KEY (id)
);
CREATE TABLE custom_dashboards (
	id INTEGER NOT NULL, 
	name VARCHAR(200) NOT NULL, 
	owner_id INTEGER, 
	is_shared BOOLEAN, 
	created_at DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(owner_id) REFERENCES users (id)
);
CREATE TABLE dashboard_modules (
	id INTEGER NOT NULL, 
	"key" VARCHAR(80) NOT NULL, 
	title VARCHAR(200) NOT NULL, 
	subtitle VARCHAR(200), 
	icon VARCHAR(2000), 
	route_prefix VARCHAR(120) NOT NULL, 
	enabled BOOLEAN, 
	sort_order INTEGER, 
	PRIMARY KEY (id)
);
CREATE TABLE dashboard_widgets (
	id INTEGER NOT NULL, 
	dashboard_id INTEGER NOT NULL, 
	widget_type VARCHAR(40) NOT NULL, 
	title VARCHAR(200), 
	config JSON, 
	sort_order INTEGER, 
	PRIMARY KEY (id), 
	FOREIGN KEY(dashboard_id) REFERENCES custom_dashboards (id) ON DELETE CASCADE
);
CREATE TABLE departments (
	id INTEGER NOT NULL, 
	name VARCHAR(200) NOT NULL, 
	code VARCHAR(50) NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (name), 
	UNIQUE (code)
);
CREATE TABLE employee_events (
	id INTEGER NOT NULL, 
	month_record_id INTEGER NOT NULL, 
	event_type VARCHAR(10) NOT NULL, 
	event_date DATE NOT NULL, 
	full_name VARCHAR(300) NOT NULL, 
	position VARCHAR(300), 
	department VARCHAR(200), 
	employment_type VARCHAR(100), 
	created_at DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(month_record_id) REFERENCES month_records (id) ON DELETE CASCADE
);
CREATE TABLE metric_definitions (
	id INTEGER NOT NULL, 
	"key" VARCHAR(80) NOT NULL, 
	label VARCHAR(200) NOT NULL, 
	unit VARCHAR(30), 
	category VARCHAR(80), 
	value_type VARCHAR(20), 
	aggregation VARCHAR(30), 
	direction VARCHAR(30), 
	description TEXT, 
	sort_order INTEGER, 
	PRIMARY KEY (id)
);
CREATE TABLE metric_values (
	id INTEGER NOT NULL, 
	month_record_id INTEGER NOT NULL, 
	metric_key VARCHAR(80) NOT NULL, 
	numeric_value FLOAT, 
	text_value TEXT, 
	source_note TEXT, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_month_metric UNIQUE (month_record_id, metric_key), 
	FOREIGN KEY(month_record_id) REFERENCES month_records (id) ON DELETE CASCADE
);
CREATE TABLE month_records (
	id INTEGER NOT NULL, 
	year INTEGER NOT NULL, 
	month INTEGER NOT NULL, 
	notes TEXT, 
	created_at DATETIME, 
	updated_at DATETIME, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_year_month UNIQUE (year, month)
);
CREATE TABLE naumen_tickets (
	id INTEGER NOT NULL, 
	number INTEGER, 
	name VARCHAR(50), 
	registered_at DATETIME, 
	solved_at DATETIME, 
	deadline_at DATETIME, 
	status VARCHAR(100), 
	org VARCHAR(300), 
	responsible VARCHAR(300), 
	team VARCHAR(200), 
	first_line VARCHAR(300), 
	channel VARCHAR(100), 
	overdue BOOLEAN NOT NULL, 
	reopened BOOLEAN NOT NULL, 
	processing_hours FLOAT, 
	created_at DATETIME, 
	PRIMARY KEY (id)
);
CREATE TABLE notes (
	id INTEGER NOT NULL, 
	month_record_id INTEGER NOT NULL, 
	author_id INTEGER, 
	content TEXT NOT NULL, 
	created_at DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(month_record_id) REFERENCES month_records (id) ON DELETE CASCADE, 
	FOREIGN KEY(author_id) REFERENCES users (id)
);
CREATE TABLE partnership_light_rules (
	id INTEGER NOT NULL, 
	"key" VARCHAR(80) NOT NULL, 
	group_key VARCHAR(40) NOT NULL, 
	label VARCHAR(200) NOT NULL, 
	light VARCHAR(20) NOT NULL, 
	threshold FLOAT, 
	sort_order INTEGER, 
	PRIMARY KEY (id)
);
CREATE TABLE partnerships (
	id INTEGER NOT NULL, 
	partner VARCHAR(300) NOT NULL, 
	product VARCHAR(300) NOT NULL, 
	direction VARCHAR(300) NOT NULL, 
	almi_product VARCHAR(200) NOT NULL, 
	almi_version VARCHAR(200) NOT NULL, 
	status VARCHAR(60) NOT NULL, 
	cert_date DATE, 
	nda BOOLEAN, 
	agreement BOOLEAN, 
	bitrix VARCHAR(500), 
	website VARCHAR(500), 
	comment TEXT, 
	type VARCHAR(30) NOT NULL, 
	last_modified DATE, 
	PRIMARY KEY (id)
);
CREATE TABLE tp_report_rows (
	id INTEGER NOT NULL, 
	year FLOAT, 
	week FLOAT, 
	period VARCHAR(50), 
	total_in_work FLOAT, 
	avail_total FLOAT, 
	rushydro_hours FLOAT, 
	transneft_hours FLOAT, 
	roscosmos_hours FLOAT, 
	bryansk_hours FLOAT, 
	mchs_hours FLOAT, 
	internal_sales_hours FLOAT, 
	new_received FLOAT, 
	renewed FLOAT, 
	ratio_solved_received FLOAT, 
	altos_rusg_email FLOAT, 
	altos_rusg_tf FLOAT, 
	altos_other_email FLOAT, 
	altos_other_tf FLOAT, 
	altoffice_rusg_email FLOAT, 
	altoffice_rusg_tf FLOAT, 
	altoffice_other_email FLOAT, 
	altoffice_other_tf FLOAT, 
	projserver_taken FLOAT, 
	projserver_solved FLOAT, 
	projserver_avail FLOAT, 
	total_solved_week FLOAT, 
	altos_avg_time FLOAT, 
	altos_total FLOAT, 
	altos_1_2line FLOAT, 
	altos_3line FLOAT, 
	altoffice_avg_time FLOAT, 
	altoffice_total FLOAT, 
	altoffice_1_2line FLOAT, 
	altoffice_3line FLOAT, 
	altos_avail_total FLOAT, 
	altos_avail_1_3 FLOAT, 
	altos_avail_4_7 FLOAT, 
	altos_avail_8_10 FLOAT, 
	altoffice_avail_total FLOAT, 
	altoffice_avail_1_3 FLOAT, 
	altoffice_avail_4_7 FLOAT, 
	altoffice_avail_8_10 FLOAT, 
	extra TEXT, 
	created_at DATETIME, 
	updated_at DATETIME, 
	PRIMARY KEY (id)
);
CREATE TABLE tp_settings (
	"key" VARCHAR(80) NOT NULL, 
	value TEXT NOT NULL, 
	PRIMARY KEY ("key")
);
CREATE TABLE traffic_light_rules (
	id INTEGER NOT NULL, 
	metric_key VARCHAR(80) NOT NULL, 
	green_threshold FLOAT, 
	yellow_threshold FLOAT, 
	direction VARCHAR(30), 
	enabled BOOLEAN, 
	PRIMARY KEY (id)
);
CREATE TABLE user_dashboard_preferences (
	id INTEGER NOT NULL, 
	user_id INTEGER NOT NULL, 
	service_key VARCHAR(80) NOT NULL, 
	preferences_json JSON, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_user_service_prefs UNIQUE (user_id, service_key), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);
CREATE TABLE user_departments (
	user_id INTEGER NOT NULL, 
	department_id INTEGER NOT NULL, 
	PRIMARY KEY (user_id, department_id), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
	FOREIGN KEY(department_id) REFERENCES departments (id) ON DELETE CASCADE
);
CREATE TABLE user_service_access (
	id INTEGER NOT NULL, 
	user_id INTEGER NOT NULL, 
	service_key VARCHAR(80) NOT NULL, 
	access_level VARCHAR(30) NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_user_service UNIQUE (user_id, service_key), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);
CREATE TABLE users (
	id INTEGER NOT NULL, 
	username VARCHAR(100) NOT NULL, 
	full_name VARCHAR(200) NOT NULL, 
	email VARCHAR(200), 
	position VARCHAR(200), 
	phone VARCHAR(50), 
	avatar TEXT, 
	role VARCHAR(11) NOT NULL, 
	hashed_password VARCHAR(255) NOT NULL, 
	is_active BOOLEAN, 
	must_change_password BOOLEAN, 
	created_at DATETIME, 
	PRIMARY KEY (id), 
	UNIQUE (email)
);
CREATE INDEX ix_benchmarks_metric_key ON benchmarks (metric_key);
CREATE UNIQUE INDEX ix_dashboard_modules_key ON dashboard_modules ("key");
CREATE UNIQUE INDEX ix_metric_definitions_key ON metric_definitions ("key");
CREATE INDEX ix_metric_values_metric_key ON metric_values (metric_key);
CREATE INDEX ix_naumen_tickets_number ON naumen_tickets (number);
CREATE INDEX ix_naumen_tickets_org ON naumen_tickets (org);
CREATE INDEX ix_naumen_tickets_registered_at ON naumen_tickets (registered_at);
CREATE INDEX ix_naumen_tickets_solved_at ON naumen_tickets (solved_at);
CREATE UNIQUE INDEX ix_partnership_light_rules_key ON partnership_light_rules ("key");
CREATE UNIQUE INDEX ix_traffic_light_rules_metric_key ON traffic_light_rules (metric_key);
CREATE INDEX ix_user_dashboard_preferences_service_key ON user_dashboard_preferences (service_key);
CREATE INDEX ix_user_dashboard_preferences_user_id ON user_dashboard_preferences (user_id);
CREATE INDEX ix_user_service_access_service_key ON user_service_access (service_key);
CREATE INDEX ix_user_service_access_user_id ON user_service_access (user_id);
CREATE UNIQUE INDEX ix_users_username ON users (username);
INSERT INTO "audit_logs" ("id", "user_id", "username", "entity_type", "entity_id", "action", "before_json", "after_json", "ip_address", "timestamp") VALUES (1, 1, 'admin', 'user', '1', 'update', '{"password": "***"}', '{"password": "***"}', '', '2026-11-01 07:50:51.175833');
INSERT INTO "benchmarks" ("id", "metric_key", "label", "year", "value", "target_value", "description", "source") VALUES (1, 'turnover', '2025 год', 2025, 5.17, NULL, 'Фактическая текучесть кадров за 2025 год', 'Годовой отчёт службы персонала за 2025 год');
INSERT INTO "benchmarks" ("id", "metric_key", "label", "year", "value", "target_value", "description", "source") VALUES (2, 'turnover', 'Цель 2026', 2026, 5.0, 5.0, 'Целевой уровень текучести кадров', 'План службы персонала на 2026 год');
INSERT INTO "benchmarks" ("id", "metric_key", "label", "year", "value", "target_value", "description", "source") VALUES (3, 'avg_time_to_fill', 'Цель 2026', 2026, 30.0, 30.0, 'Среднее время закрытия вакансии (дни)', 'План службы персонала на 2026 год');
INSERT INTO "benchmarks" ("id", "metric_key", "label", "year", "value", "target_value", "description", "source") VALUES (4, 'offers_accepted_pct', 'Цель 2026', 2026, 90.0, 90.0, 'Доля принятых офферов (%)', 'План службы персонала на 2026 год');
INSERT INTO "benchmarks" ("id", "metric_key", "label", "year", "value", "target_value", "description", "source") VALUES (5, 'probation_pass_rate', 'Цель 2026', 2026, 95.0, 95.0, 'Процент прохождения испытательного срока (%)', 'План службы персонала на 2026 год');
INSERT INTO "benchmarks" ("id", "metric_key", "label", "year", "value", "target_value", "description", "source") VALUES (6, 'probation_pass_rate_adaptation', 'Цель 2026', 2026, 90.0, 90.0, 'Доля неудач адаптации не более 10% — прохождение ИС не ниже 90%', 'План службы персонала на 2026 год');
INSERT INTO "color_palettes" ("id", "scope", "module_key", "name", "colors_json", "is_active") VALUES (1, 'global', NULL, 'Мягкая', '{"traffic_light": {"green": "#5a9e68", "yellow": "#c9974a", "red": "#c97171", "neutral": "#b8bec7"}, "charts": ["#5a9e68", "#6F8FBF", "#c9974a", "#8BBE9F", "#c97171", "#A9B2C3"], "brand": {"primary": "#c0392b", "muted": "#6b6a65"}}', 1);
INSERT INTO "color_palettes" ("id", "scope", "module_key", "name", "colors_json", "is_active") VALUES (2, 'global', NULL, 'Классическая', '{"traffic_light": {"green": "#4caf50", "yellow": "#ffc107", "red": "#f44336", "neutral": "#9E9E9E"}, "charts": ["#4caf50", "#1F77B4", "#ffc107", "#8E44AD", "#f44336", "#7F8C8D"], "brand": {"primary": "#f44336", "muted": "#6B6A65"}}', 0);
INSERT INTO "color_palettes" ("id", "scope", "module_key", "name", "colors_json", "is_active") VALUES (3, 'global', NULL, 'Холодная', '{"traffic_light": {"green": "#26a69a", "yellow": "#42a5f5", "red": "#ff7043", "neutral": "#8FA3B0"}, "charts": ["#26a69a", "#42a5f5", "#6FB1E0", "#8E7CC3", "#ff7043", "#8FA3B0"], "brand": {"primary": "#26a69a", "muted": "#5A6B78"}}', 0);
INSERT INTO "color_palettes" ("id", "scope", "module_key", "name", "colors_json", "is_active") VALUES (4, 'global', NULL, 'Контрастная', '{"traffic_light": {"green": "#2e7d32", "yellow": "#ef6c00", "red": "#c62828", "neutral": "#6E7378"}, "charts": ["#2e7d32", "#0B5FA5", "#ef6c00", "#7B2FA0", "#c62828", "#5A6570"], "brand": {"primary": "#c62828", "muted": "#5A6570"}}', 0);
INSERT INTO "dashboard_modules" ("id", "key", "title", "subtitle", "icon", "route_prefix", "enabled", "sort_order") VALUES (1, 'apparat_gd', 'Аппарат ГД', 'Аппарат ГД', '🏛', '/apparat_gd', 0, 0);
INSERT INTO "dashboard_modules" ("id", "key", "title", "subtitle", "icon", "route_prefix", "enabled", "sort_order") VALUES (2, 'tech', 'Техническая поддержка', 'Техподдержка', '🎧', '/tp', 1, 1);
INSERT INTO "dashboard_modules" ("id", "key", "title", "subtitle", "icon", "route_prefix", "enabled", "sort_order") VALUES (3, 'it', 'ИТ служба', 'ИТ', '💻', '/it', 0, 2);
INSERT INTO "dashboard_modules" ("id", "key", "title", "subtitle", "icon", "route_prefix", "enabled", "sort_order") VALUES (4, 'commercial', 'Коммерческая служба', 'Коммерческая', '💼', '/commercial', 0, 3);
INSERT INTO "dashboard_modules" ("id", "key", "title", "subtitle", "icon", "route_prefix", "enabled", "sort_order") VALUES (5, 'marketing', 'Служба маркетинга', 'Маркетинг', '📣', '/marketing', 0, 4);
INSERT INTO "dashboard_modules" ("id", "key", "title", "subtitle", "icon", "route_prefix", "enabled", "sort_order") VALUES (6, 'hr', 'Служба персонала', 'Персонал', '📊', '/', 1, 5);
INSERT INTO "dashboard_modules" ("id", "key", "title", "subtitle", "icon", "route_prefix", "enabled", "sort_order") VALUES (7, 'project_product', 'Проектный и продуктовый офис', 'Технологические партнёрства', '🤝', '/product', 1, 6);
INSERT INTO "dashboard_modules" ("id", "key", "title", "subtitle", "icon", "route_prefix", "enabled", "sort_order") VALUES (8, 'finance', 'Финансовая служба', 'Финансы', '💰', '/finance', 0, 7);
INSERT INTO "dashboard_modules" ("id", "key", "title", "subtitle", "icon", "route_prefix", "enabled", "sort_order") VALUES (9, 'legal', 'Юридическая служба', 'Юристы', '⚖', '/legal', 0, 8);
INSERT INTO "departments" ("id", "name", "code") VALUES (1, 'ИТ-служба', 'IT');
INSERT INTO "departments" ("id", "name", "code") VALUES (2, 'Техническая служба', 'TECH');
INSERT INTO "departments" ("id", "name", "code") VALUES (3, 'Служба маркетинга', 'MKT');
INSERT INTO "departments" ("id", "name", "code") VALUES (4, 'Коммерческая служба', 'COMM');
INSERT INTO "departments" ("id", "name", "code") VALUES (5, 'АХО', 'AHO');
INSERT INTO "departments" ("id", "name", "code") VALUES (6, 'Аппарат генерального директора', 'ADMIN');
INSERT INTO "departments" ("id", "name", "code") VALUES (7, 'Проектная служба', 'PROJ');
INSERT INTO "employee_events" ("id", "month_record_id", "event_type", "event_date", "full_name", "position", "department", "employment_type", "created_at") VALUES (1, 1, 'hired', '2026-06-08', 'Райманов Савелий Александрович', 'Разработчик 1С', 'ИТ-служба', 'Самозанятый', '2026-11-01 07:45:04.914101');
INSERT INTO "employee_events" ("id", "month_record_id", "event_type", "event_date", "full_name", "position", "department", "employment_type", "created_at") VALUES (2, 1, 'hired', '2026-06-23', 'Лапин Максим Витальевич', 'Инженер-программист 1 категории', 'Техническая служба', 'ТД', '2026-11-01 07:45:04.914106');
INSERT INTO "employee_events" ("id", "month_record_id", "event_type", "event_date", "full_name", "position", "department", "employment_type", "created_at") VALUES (3, 1, 'fired', '2026-06-05', 'Тарасов Иван Михайлович', 'Разработчик 1С', 'ИТ-служба', '', '2026-11-01 07:45:04.914107');
INSERT INTO "employee_events" ("id", "month_record_id", "event_type", "event_date", "full_name", "position", "department", "employment_type", "created_at") VALUES (4, 1, 'fired', '2026-06-19', 'Пономарева Злата Михайловна', 'PR-менеджер', 'Служба маркетинга', '', '2026-11-01 07:45:04.914109');
INSERT INTO "employee_events" ("id", "month_record_id", "event_type", "event_date", "full_name", "position", "department", "employment_type", "created_at") VALUES (5, 1, 'fired', '2026-06-23', 'Андреев Александр Александрович', 'Менеджер по работе с ключевыми клиентами', 'Коммерческая служба', '', '2026-11-01 07:45:04.914111');
INSERT INTO "employee_events" ("id", "month_record_id", "event_type", "event_date", "full_name", "position", "department", "employment_type", "created_at") VALUES (6, 1, 'fired', '2026-06-29', 'Черкашина Дарья Владимировна', 'Бекенд разработчик', 'Техническая служба', '', '2026-11-01 07:45:04.914113');
INSERT INTO "metric_definitions" ("id", "key", "label", "unit", "category", "value_type", "aggregation", "direction", "description", "sort_order") VALUES (1, 'total_employees', 'Всего сотрудников', 'чел.', 'headcount', 'numeric', 'latest', 'higher_is_better', 'Общее число сотрудников', 0);
INSERT INTO "metric_definitions" ("id", "key", "label", "unit", "category", "value_type", "aggregation", "direction", "description", "sort_order") VALUES (2, 'projects_count', 'Проекты найма', 'шт.', 'hiring', 'numeric', 'sum', 'neutral', 'Количество проектов (вакансий) в работе', 10);
INSERT INTO "metric_definitions" ("id", "key", "label", "unit", "category", "value_type", "aggregation", "direction", "description", "sort_order") VALUES (3, 'resumes_screened', 'Отобрано резюме', 'чел.', 'hiring', 'numeric', 'sum', 'neutral', 'Количество отобранных резюме', 20);
INSERT INTO "metric_definitions" ("id", "key", "label", "unit", "category", "value_type", "aggregation", "direction", "description", "sort_order") VALUES (4, 'interviews_hr', 'Интервью с HR', 'чел.', 'hiring', 'numeric', 'sum', 'neutral', 'Количество проведённых интервью с HR', 30);
INSERT INTO "metric_definitions" ("id", "key", "label", "unit", "category", "value_type", "aggregation", "direction", "description", "sort_order") VALUES (5, 'interviews_hm', 'Интервью с заказчиком', 'чел.', 'hiring', 'numeric', 'sum', 'neutral', 'Количество интервью с нанимающими менеджерами', 40);
INSERT INTO "metric_definitions" ("id", "key", "label", "unit", "category", "value_type", "aggregation", "direction", "description", "sort_order") VALUES (6, 'offers_accepted_pct', 'Принятые офферы', '%', 'hiring', 'numeric', 'latest', 'higher_is_better', 'Доля принятых офферов от выставленных', 50);
INSERT INTO "metric_definitions" ("id", "key", "label", "unit", "category", "value_type", "aggregation", "direction", "description", "sort_order") VALUES (7, 'hired_count', 'Нанято (по списку)', 'чел.', 'hiring', 'numeric', 'sum', 'neutral', 'Количество принятых сотрудников по списку', 60);
INSERT INTO "metric_definitions" ("id", "key", "label", "unit", "category", "value_type", "aggregation", "direction", "description", "sort_order") VALUES (8, 'avg_time_to_fill', 'Среднее время закрытия позиций', 'дн.', 'hiring', 'numeric', 'avg', 'lower_is_better', 'Среднее время от открытия вакансии до выхода кандидата', 70);
INSERT INTO "metric_definitions" ("id", "key", "label", "unit", "category", "value_type", "aggregation", "direction", "description", "sort_order") VALUES (9, 'on_adaptation_count', 'Сотрудников на адаптации', 'чел.', 'adaptation', 'numeric', 'latest', 'neutral', 'Численность сотрудников на испытательном сроке', 80);
INSERT INTO "metric_definitions" ("id", "key", "label", "unit", "category", "value_type", "aggregation", "direction", "description", "sort_order") VALUES (10, 'adaptation_meetings', 'Встречи по адаптации', 'шт.', 'adaptation', 'numeric', 'sum', 'neutral', 'Количество встреч по адаптации', 90);
INSERT INTO "metric_definitions" ("id", "key", "label", "unit", "category", "value_type", "aggregation", "direction", "description", "sort_order") VALUES (11, 'probation_completed', 'Завершили ИС', 'чел.', 'adaptation', 'numeric', 'sum', 'neutral', 'Количество завершённых испытательных сроков', 100);
INSERT INTO "metric_definitions" ("id", "key", "label", "unit", "category", "value_type", "aggregation", "direction", "description", "sort_order") VALUES (12, 'probation_pass_rate', 'Процент прохождения ИС (общий)', '%', 'adaptation', 'numeric', 'latest', 'higher_is_better', 'Доля сотрудников, прошедших испытательный срок', 110);
INSERT INTO "metric_definitions" ("id", "key", "label", "unit", "category", "value_type", "aggregation", "direction", "description", "sort_order") VALUES (13, 'probation_pass_rate_adaptation', 'Процент прохождения ИС (по адаптации)', '%', 'adaptation', 'numeric', 'latest', 'higher_is_better', 'Процент прошедших ИС среди сотрудников на адаптации', 120);
INSERT INTO "metric_definitions" ("id", "key", "label", "unit", "category", "value_type", "aggregation", "direction", "description", "sort_order") VALUES (14, 'adaptation_dismissals', 'Увольнения на адаптации', 'чел.', 'adaptation', 'numeric', 'sum', 'lower_is_better', 'Увольнения в период испытательного срока', 130);
INSERT INTO "metric_definitions" ("id", "key", "label", "unit", "category", "value_type", "aggregation", "direction", "description", "sort_order") VALUES (15, 'turnover', 'Текучесть кадров', '%', 'turnover', 'numeric', 'latest', 'lower_is_better', 'Текучесть накопительно с начала года', 140);
INSERT INTO "metric_definitions" ("id", "key", "label", "unit", "category", "value_type", "aggregation", "direction", "description", "sort_order") VALUES (16, 'turnover_company', 'Текучесть по инициативе компании', '%', 'turnover', 'numeric', 'latest', 'lower_is_better', 'Доля увольнений по инициативе компании', 150);
INSERT INTO "metric_values" ("id", "month_record_id", "metric_key", "numeric_value", "text_value", "source_note") VALUES (1, 1, 'avg_time_to_fill', 35.0, '', '');
INSERT INTO "metric_values" ("id", "month_record_id", "metric_key", "numeric_value", "text_value", "source_note") VALUES (2, 1, 'turnover', 3.87, '', 'на момент июня 2026');
INSERT INTO "metric_values" ("id", "month_record_id", "metric_key", "numeric_value", "text_value", "source_note") VALUES (3, 1, 'turnover_company', 2.58, '', '');
INSERT INTO "metric_values" ("id", "month_record_id", "metric_key", "numeric_value", "text_value", "source_note") VALUES (4, 1, 'offers_accepted_pct', 100.0, '', '');
INSERT INTO "metric_values" ("id", "month_record_id", "metric_key", "numeric_value", "text_value", "source_note") VALUES (5, 1, 'resumes_screened', 249.0, '', '');
INSERT INTO "metric_values" ("id", "month_record_id", "metric_key", "numeric_value", "text_value", "source_note") VALUES (6, 1, 'interviews_hr', 53.0, '', '');
INSERT INTO "metric_values" ("id", "month_record_id", "metric_key", "numeric_value", "text_value", "source_note") VALUES (7, 1, 'interviews_hm', 5.0, '', '');
INSERT INTO "metric_values" ("id", "month_record_id", "metric_key", "numeric_value", "text_value", "source_note") VALUES (8, 1, 'projects_count', 8.0, '', '');
INSERT INTO "metric_values" ("id", "month_record_id", "metric_key", "numeric_value", "text_value", "source_note") VALUES (9, 1, 'adaptation_meetings', 4.0, '', '');
INSERT INTO "metric_values" ("id", "month_record_id", "metric_key", "numeric_value", "text_value", "source_note") VALUES (10, 1, 'probation_pass_rate', 99.35, '', 'общий по компании');
INSERT INTO "metric_values" ("id", "month_record_id", "metric_key", "numeric_value", "text_value", "source_note") VALUES (11, 1, 'probation_pass_rate_adaptation', 93.33, '', 'изначально посчитано от всех сотрудников на адаптации');
INSERT INTO "metric_values" ("id", "month_record_id", "metric_key", "numeric_value", "text_value", "source_note") VALUES (12, 1, 'on_adaptation_count', 15.0, '', '');
INSERT INTO "metric_values" ("id", "month_record_id", "metric_key", "numeric_value", "text_value", "source_note") VALUES (13, 1, 'adaptation_dismissals', 1.0, '', '');
INSERT INTO "metric_values" ("id", "month_record_id", "metric_key", "numeric_value", "text_value", "source_note") VALUES (14, 1, 'probation_completed', 5.0, '', '');
INSERT INTO "metric_values" ("id", "month_record_id", "metric_key", "numeric_value", "text_value", "source_note") VALUES (15, 1, 'hired_count', 2.0, '', '');
INSERT INTO "metric_values" ("id", "month_record_id", "metric_key", "numeric_value", "text_value", "source_note") VALUES (16, 2, 'offers_accepted_pct', 100.0, '', '');
INSERT INTO "metric_values" ("id", "month_record_id", "metric_key", "numeric_value", "text_value", "source_note") VALUES (17, 2, 'resumes_screened', 282.0, '', '');
INSERT INTO "metric_values" ("id", "month_record_id", "metric_key", "numeric_value", "text_value", "source_note") VALUES (18, 2, 'interviews_hr', 72.0, '', '');
INSERT INTO "metric_values" ("id", "month_record_id", "metric_key", "numeric_value", "text_value", "source_note") VALUES (19, 2, 'interviews_hm', 16.0, '', '');
INSERT INTO "metric_values" ("id", "month_record_id", "metric_key", "numeric_value", "text_value", "source_note") VALUES (20, 2, 'projects_count', 9.0, '', '');
INSERT INTO "metric_values" ("id", "month_record_id", "metric_key", "numeric_value", "text_value", "source_note") VALUES (21, 2, 'probation_pass_rate', 100.0, '', '');
INSERT INTO "metric_values" ("id", "month_record_id", "metric_key", "numeric_value", "text_value", "source_note") VALUES (22, 2, 'adaptation_meetings', 10.0, '', '');
INSERT INTO "metric_values" ("id", "month_record_id", "metric_key", "numeric_value", "text_value", "source_note") VALUES (23, 2, 'turnover', 2.0, '', 'всего уволено 3 человека; в июле 2025: 1,65%');
INSERT INTO "metric_values" ("id", "month_record_id", "metric_key", "numeric_value", "text_value", "source_note") VALUES (24, 2, 'hired_count', 4.0, '', 'по списку 4 найма; в тексте отчёта указано «нанято 3» — расхождение');
INSERT INTO "metric_values" ("id", "month_record_id", "metric_key", "numeric_value", "text_value", "source_note") VALUES (25, 2, 'on_adaptation_count', 14.0, '', '');
INSERT INTO "metric_values" ("id", "month_record_id", "metric_key", "numeric_value", "text_value", "source_note") VALUES (26, 2, 'adaptation_dismissals', 0.0, '', '');
INSERT INTO "metric_values" ("id", "month_record_id", "metric_key", "numeric_value", "text_value", "source_note") VALUES (27, 2, 'probation_completed', 3.0, '', '');
INSERT INTO "month_records" ("id", "year", "month", "notes", "created_at", "updated_at") VALUES (1, 2026, 6, 'Подписано соглашение с Дмитриевой Евгенией с 29.06.2026 по 27.08.2026 — отпуск без сохранения заработной платы.', '2026-11-01 07:45:04.911636', '2026-11-01 07:45:04.911641');
INSERT INTO "month_records" ("id", "year", "month", "notes", "created_at", "updated_at") VALUES (2, 2026, 7, 'Расхождение в отчёте: текст указывает «нанято 3 человека», по списку найма — 4 записи. Текучесть за июль 2025 составила 1,65%.', '2026-11-01 07:45:04.917480', '2026-11-01 07:45:04.917485');
INSERT INTO "naumen_tickets" ("id", "number", "name", "registered_at", "solved_at", "deadline_at", "status", "org", "responsible", "team", "first_line", "channel", "overdue", "reopened", "processing_hours", "created_at") VALUES (1, 885948, 'SD885948', '2023-06-27 07:38:40.711000', '2023-09-22 09:55:49.145000', '2023-09-21 12:02:23.937000', 'Закрыта', 'Саяно-Шушенская ГЭС', 'Осенчугов Александр Николаевич', 'АЛМИ', 'Лушпа Наталья Владимировна', 'По телефону', 1, 0, 503.97, '2026-11-01 07:45:05.070536');
INSERT INTO "naumen_tickets" ("id", "number", "name", "registered_at", "solved_at", "deadline_at", "status", "org", "responsible", "team", "first_line", "channel", "overdue", "reopened", "processing_hours", "created_at") VALUES (2, 895518, 'SD895518', '2023-07-04 13:32:16.893000', '2023-07-07 16:38:32.504000', '2023-09-29 12:32:53.709000', 'Закрыта', 'АЛМИ Партнер', 'Осенчугов Александр Николаевич', 'АЛМИ', NULL, 'Личный кабинет', 0, 0, 26.63, '2026-11-01 07:45:05.070542');
INSERT INTO "naumen_tickets" ("id", "number", "name", "registered_at", "solved_at", "deadline_at", "status", "org", "responsible", "team", "first_line", "channel", "overdue", "reopened", "processing_hours", "created_at") VALUES (3, 895779, 'SD895779', '2023-07-04 17:24:08.019000', '2023-07-07 16:39:25.256000', '2023-09-29 16:26:02.183000', 'Закрыта', 'АЛМИ Партнер', 'Осенчугов Александр Николаевич', 'АЛМИ', NULL, 'Личный кабинет', 0, 0, 23.75, '2026-11-01 07:45:05.070544');
INSERT INTO "naumen_tickets" ("id", "number", "name", "registered_at", "solved_at", "deadline_at", "status", "org", "responsible", "team", "first_line", "channel", "overdue", "reopened", "processing_hours", "created_at") VALUES (4, 897682, 'SD897682', '2023-07-06 00:03:06.004000', '2023-07-07 16:38:49.641000', '2023-10-02 16:33:26.228000', 'Закрыта', 'АЛМИ Партнер', 'Осенчугов Александр Николаевич', 'АЛМИ', NULL, 'Личный кабинет', 0, 0, 15.63, '2026-11-01 07:45:05.070545');
INSERT INTO "naumen_tickets" ("id", "number", "name", "registered_at", "solved_at", "deadline_at", "status", "org", "responsible", "team", "first_line", "channel", "overdue", "reopened", "processing_hours", "created_at") VALUES (5, 897830, 'SD897830', '2023-07-06 01:55:13.859000', '2023-07-07 16:37:52.098000', '2023-10-02 16:34:54.587000', 'Закрыта', 'АЛМИ Партнер', 'Осенчугов Александр Николаевич', 'АЛМИ', NULL, 'Личный кабинет', 0, 0, 15.62, '2026-11-01 07:45:05.070547');
INSERT INTO "naumen_tickets" ("id", "number", "name", "registered_at", "solved_at", "deadline_at", "status", "org", "responsible", "team", "first_line", "channel", "overdue", "reopened", "processing_hours", "created_at") VALUES (6, 897848, 'SD897848', '2023-07-06 02:03:32.327000', '2023-07-07 16:37:32.832000', '2023-10-02 16:35:38.828000', 'Закрыта', 'АЛМИ Партнер', 'Осенчугов Александр Николаевич', 'АЛМИ', NULL, 'Личный кабинет', 0, 0, 15.62, '2026-11-01 07:45:05.070548');
INSERT INTO "partnership_light_rules" ("id", "key", "group_key", "label", "light", "threshold", "sort_order") VALUES (1, 'status:Завершено', 'status', 'Завершено', 'green', NULL, 0);
INSERT INTO "partnership_light_rules" ("id", "key", "group_key", "label", "light", "threshold", "sort_order") VALUES (2, 'status:В работе', 'status', 'В работе', 'yellow', NULL, 1);
INSERT INTO "partnership_light_rules" ("id", "key", "group_key", "label", "light", "threshold", "sort_order") VALUES (3, 'status:Отложено', 'status', 'Отложено', 'yellow', NULL, 2);
INSERT INTO "partnership_light_rules" ("id", "key", "group_key", "label", "light", "threshold", "sort_order") VALUES (4, 'status:Не подписывают', 'status', 'Не подписывают', 'red', NULL, 3);
INSERT INTO "partnership_light_rules" ("id", "key", "group_key", "label", "light", "threshold", "sort_order") VALUES (5, 'nda:yes', 'nda', 'NDA подписан', 'green', NULL, 4);
INSERT INTO "partnership_light_rules" ("id", "key", "group_key", "label", "light", "threshold", "sort_order") VALUES (6, 'nda:no', 'nda', 'NDA не подписан', 'yellow', NULL, 5);
INSERT INTO "partnership_light_rules" ("id", "key", "group_key", "label", "light", "threshold", "sort_order") VALUES (7, 'agreement:yes', 'agreement', 'Соглашение подписано', 'green', NULL, 6);
INSERT INTO "partnership_light_rules" ("id", "key", "group_key", "label", "light", "threshold", "sort_order") VALUES (8, 'agreement:no', 'agreement', 'Соглашение не подписано', 'yellow', NULL, 7);
INSERT INTO "partnership_light_rules" ("id", "key", "group_key", "label", "light", "threshold", "sort_order") VALUES (9, 'cert_age:fresh', 'cert_age', 'Сертификат актуален', 'green', 2.0, 8);
INSERT INTO "partnership_light_rules" ("id", "key", "group_key", "label", "light", "threshold", "sort_order") VALUES (10, 'cert_age:aging', 'cert_age', 'Сертификат устаревает', 'yellow', 4.0, 9);
INSERT INTO "partnership_light_rules" ("id", "key", "group_key", "label", "light", "threshold", "sort_order") VALUES (11, 'cert_age:stale', 'cert_age', 'Сертификат устарел', 'red', NULL, 10);
INSERT INTO "partnerships" ("id", "partner", "product", "direction", "almi_product", "almi_version", "status", "cert_date", "nda", "agreement", "bitrix", "website", "comment", "type", "last_modified") VALUES (1, 'ООО ЭСТИ', 'ГИС Аксиома', 'Геоинформационные система', 'АльтерОС', 'АльтерОС 7.5', 'Завершено', '2003-07-06', 0, 0, NULL, NULL, 'РГ', 'ПО', NULL);
INSERT INTO "partnerships" ("id", "partner", "product", "direction", "almi_product", "almi_version", "status", "cert_date", "nda", "agreement", "bitrix", "website", "comment", "type", "last_modified") VALUES (2, 'ООО Спайдер Проджект', 'Spider Project', 'Управление проектами', 'АльтерОС', 'АльтерОС 7.5', 'Завершено', '2023-09-07', 0, 0, NULL, NULL, 'РГ', 'ПО', NULL);
INSERT INTO "partnerships" ("id", "partner", "product", "direction", "almi_product", "almi_version", "status", "cert_date", "nda", "agreement", "bitrix", "website", "comment", "type", "last_modified") VALUES (3, 'ООО Промт', 'PROMT Neural Translation Server', 'Перевод', 'АльтерОС', 'АльтерОС 7.5', 'Завершено', '2021-11-19', 0, 0, NULL, NULL, 'РГ', 'ПО', NULL);
INSERT INTO "partnerships" ("id", "partner", "product", "direction", "almi_product", "almi_version", "status", "cert_date", "nda", "agreement", "bitrix", "website", "comment", "type", "last_modified") VALUES (4, 'ООО Монитор Электрик', 'СК-11', 'Инженерное ПО', 'АльтерОС', 'АльтерОС 7.5', 'Завершено', '2024-01-31', 0, 0, NULL, NULL, 'РГ', 'ПО', NULL);
INSERT INTO "tp_report_rows" ("id", "year", "week", "period", "total_in_work", "avail_total", "rushydro_hours", "transneft_hours", "roscosmos_hours", "bryansk_hours", "mchs_hours", "internal_sales_hours", "new_received", "renewed", "ratio_solved_received", "altos_rusg_email", "altos_rusg_tf", "altos_other_email", "altos_other_tf", "altoffice_rusg_email", "altoffice_rusg_tf", "altoffice_other_email", "altoffice_other_tf", "projserver_taken", "projserver_solved", "projserver_avail", "total_solved_week", "altos_avg_time", "altos_total", "altos_1_2line", "altos_3line", "altoffice_avg_time", "altoffice_total", "altoffice_1_2line", "altoffice_3line", "altos_avail_total", "altos_avail_1_3", "altos_avail_4_7", "altos_avail_8_10", "altoffice_avail_total", "altoffice_avail_1_3", "altoffice_avail_4_7", "altoffice_avail_8_10", "extra", "created_at", "updated_at") VALUES (1, 2024.0, 24.0, '2024-W24', 168.0, 416.0, NULL, NULL, NULL, NULL, NULL, NULL, 20.0, NULL, 0.7, 8.0, 3.0, 2.0, 0.0, 3.0, 1.0, 3.0, 0.0, NULL, NULL, NULL, 14.0, NULL, 10.0, 10.0, NULL, NULL, 4.0, 4.0, NULL, 100.0, NULL, NULL, NULL, 68.0, NULL, NULL, NULL, NULL, '2026-11-01 07:45:04.981399', '2026-11-01 07:45:04.981405');
INSERT INTO "tp_report_rows" ("id", "year", "week", "period", "total_in_work", "avail_total", "rushydro_hours", "transneft_hours", "roscosmos_hours", "bryansk_hours", "mchs_hours", "internal_sales_hours", "new_received", "renewed", "ratio_solved_received", "altos_rusg_email", "altos_rusg_tf", "altos_other_email", "altos_other_tf", "altoffice_rusg_email", "altoffice_rusg_tf", "altoffice_other_email", "altoffice_other_tf", "projserver_taken", "projserver_solved", "projserver_avail", "total_solved_week", "altos_avg_time", "altos_total", "altos_1_2line", "altos_3line", "altoffice_avg_time", "altoffice_total", "altoffice_1_2line", "altoffice_3line", "altos_avail_total", "altos_avail_1_3", "altos_avail_4_7", "altos_avail_8_10", "altoffice_avail_total", "altoffice_avail_1_3", "altoffice_avail_4_7", "altoffice_avail_8_10", "extra", "created_at", "updated_at") VALUES (2, 2024.0, 25.0, '2024-W25', 171.0, 449.0, NULL, NULL, NULL, NULL, NULL, NULL, 29.0, NULL, 0.59, 10.0, 0.0, 0.0, 0.0, 5.0, 1.0, 13.0, 0.0, NULL, NULL, NULL, 17.0, NULL, 11.0, 11.0, 0.0, NULL, 6.0, 6.0, 0.0, 104.0, NULL, NULL, 6.0, 67.0, NULL, NULL, 13.0, NULL, '2026-11-01 07:45:04.981407', '2026-11-01 07:45:04.981408');
INSERT INTO "tp_report_rows" ("id", "year", "week", "period", "total_in_work", "avail_total", "rushydro_hours", "transneft_hours", "roscosmos_hours", "bryansk_hours", "mchs_hours", "internal_sales_hours", "new_received", "renewed", "ratio_solved_received", "altos_rusg_email", "altos_rusg_tf", "altos_other_email", "altos_other_tf", "altoffice_rusg_email", "altoffice_rusg_tf", "altoffice_other_email", "altoffice_other_tf", "projserver_taken", "projserver_solved", "projserver_avail", "total_solved_week", "altos_avg_time", "altos_total", "altos_1_2line", "altos_3line", "altoffice_avg_time", "altoffice_total", "altoffice_1_2line", "altoffice_3line", "altos_avail_total", "altos_avail_1_3", "altos_avail_4_7", "altos_avail_8_10", "altoffice_avail_total", "altoffice_avail_1_3", "altoffice_avail_4_7", "altoffice_avail_8_10", "extra", "created_at", "updated_at") VALUES (3, 2024.0, 28.0, '2024-W28', 197.0, 325.0, NULL, NULL, NULL, NULL, NULL, NULL, 45.0, NULL, 0.62, 25.0, 1.0, 0.0, 1.0, 14.0, 1.0, 3.0, 0.0, NULL, NULL, NULL, 28.0, NULL, 18.0, 18.0, NULL, NULL, 10.0, 10.0, NULL, 114.0, NULL, NULL, NULL, 83.0, NULL, NULL, NULL, NULL, '2026-11-01 07:45:04.981410', '2026-11-01 07:45:04.981411');
INSERT INTO "tp_report_rows" ("id", "year", "week", "period", "total_in_work", "avail_total", "rushydro_hours", "transneft_hours", "roscosmos_hours", "bryansk_hours", "mchs_hours", "internal_sales_hours", "new_received", "renewed", "ratio_solved_received", "altos_rusg_email", "altos_rusg_tf", "altos_other_email", "altos_other_tf", "altoffice_rusg_email", "altoffice_rusg_tf", "altoffice_other_email", "altoffice_other_tf", "projserver_taken", "projserver_solved", "projserver_avail", "total_solved_week", "altos_avg_time", "altos_total", "altos_1_2line", "altos_3line", "altoffice_avg_time", "altoffice_total", "altoffice_1_2line", "altoffice_3line", "altos_avail_total", "altos_avail_1_3", "altos_avail_4_7", "altos_avail_8_10", "altoffice_avail_total", "altoffice_avail_1_3", "altoffice_avail_4_7", "altoffice_avail_8_10", "extra", "created_at", "updated_at") VALUES (4, 2024.0, 29.0, '2024-W29', 211.0, 360.0, NULL, NULL, NULL, NULL, NULL, NULL, 20.0, NULL, 1.05, 11.0, 0.0, 1.0, 0.0, 4.0, 2.0, 2.0, 0.0, NULL, NULL, NULL, 21.0, NULL, 10.0, 10.0, NULL, NULL, 11.0, 10.0, NULL, 113.0, NULL, NULL, NULL, 98.0, NULL, NULL, NULL, NULL, '2026-11-01 07:45:04.981412', '2026-11-01 07:45:04.981413');
INSERT INTO "tp_report_rows" ("id", "year", "week", "period", "total_in_work", "avail_total", "rushydro_hours", "transneft_hours", "roscosmos_hours", "bryansk_hours", "mchs_hours", "internal_sales_hours", "new_received", "renewed", "ratio_solved_received", "altos_rusg_email", "altos_rusg_tf", "altos_other_email", "altos_other_tf", "altoffice_rusg_email", "altoffice_rusg_tf", "altoffice_other_email", "altoffice_other_tf", "projserver_taken", "projserver_solved", "projserver_avail", "total_solved_week", "altos_avg_time", "altos_total", "altos_1_2line", "altos_3line", "altoffice_avg_time", "altoffice_total", "altoffice_1_2line", "altoffice_3line", "altos_avail_total", "altos_avail_1_3", "altos_avail_4_7", "altos_avail_8_10", "altoffice_avail_total", "altoffice_avail_1_3", "altoffice_avail_4_7", "altoffice_avail_8_10", "extra", "created_at", "updated_at") VALUES (5, 2024.0, 30.0, '2024-W30', 220.0, 376.0, NULL, NULL, NULL, NULL, NULL, NULL, 27.0, NULL, 0.89, 16.0, 0.0, 0.0, 0.0, 8.0, 2.0, 1.0, 0.0, NULL, NULL, NULL, 24.0, NULL, 16.0, 14.0, 2.0, NULL, 8.0, 8.0, 0.0, 119.0, NULL, NULL, 4.0, 101.0, NULL, NULL, 16.0, NULL, '2026-11-01 07:45:04.981414', '2026-11-01 07:45:04.981415');
INSERT INTO "tp_report_rows" ("id", "year", "week", "period", "total_in_work", "avail_total", "rushydro_hours", "transneft_hours", "roscosmos_hours", "bryansk_hours", "mchs_hours", "internal_sales_hours", "new_received", "renewed", "ratio_solved_received", "altos_rusg_email", "altos_rusg_tf", "altos_other_email", "altos_other_tf", "altoffice_rusg_email", "altoffice_rusg_tf", "altoffice_other_email", "altoffice_other_tf", "projserver_taken", "projserver_solved", "projserver_avail", "total_solved_week", "altos_avg_time", "altos_total", "altos_1_2line", "altos_3line", "altoffice_avg_time", "altoffice_total", "altoffice_1_2line", "altoffice_3line", "altos_avail_total", "altos_avail_1_3", "altos_avail_4_7", "altos_avail_8_10", "altoffice_avail_total", "altoffice_avail_1_3", "altoffice_avail_4_7", "altoffice_avail_8_10", "extra", "created_at", "updated_at") VALUES (6, 2024.0, 31.0, '2024-W31', 244.0, 360.0, NULL, NULL, NULL, NULL, NULL, NULL, 35.0, NULL, 0.74, 19.0, 0.0, 1.0, 0.0, 7.0, 1.0, 7.0, 0.0, NULL, NULL, NULL, 26.0, NULL, 9.0, 9.0, 0.0, NULL, 17.0, 17.0, 0.0, 115.0, NULL, NULL, 8.0, 129.0, NULL, NULL, NULL, NULL, '2026-11-01 07:45:04.981416', '2026-11-01 07:45:04.981417');
INSERT INTO "tp_settings" ("key", "value") VALUES ('traffic_rules', '{"total_in_work": {"direction": "less", "green": 180, "yellow": 220, "enabled": true}, "avail_total": {"direction": "less", "green": 350, "yellow": 420, "enabled": true}, "new_received": {"direction": "less", "green": 25, "yellow": 35, "enabled": false}, "total_solved_week": {"direction": "more", "green": 25, "yellow": 18, "enabled": true}, "ratio_solved_received": {"direction": "more", "green": 1, "yellow": 0.8, "enabled": true}, "altos_avg_time": {"direction": "less", "green": 24, "yellow": 48, "enabled": true}, "altoffice_avg_time": {"direction": "less", "green": 36, "yellow": 72, "enabled": true}, "altos_avail_total": {"direction": "more", "green": 90, "yellow": 70, "enabled": false}, "altoffice_avail_total": {"direction": "more", "green": 110, "yellow": 90, "enabled": false}}');
INSERT INTO "tp_settings" ("key", "value") VALUES ('block_settings', '{}');
INSERT INTO "tp_settings" ("key", "value") VALUES ('color_palette', '{}');
INSERT INTO "traffic_light_rules" ("id", "metric_key", "green_threshold", "yellow_threshold", "direction", "enabled") VALUES (1, 'turnover', 5.0, 8.0, 'lower_is_better', 1);
INSERT INTO "traffic_light_rules" ("id", "metric_key", "green_threshold", "yellow_threshold", "direction", "enabled") VALUES (2, 'turnover_company', 3.5, 5.5, 'lower_is_better', 1);
INSERT INTO "traffic_light_rules" ("id", "metric_key", "green_threshold", "yellow_threshold", "direction", "enabled") VALUES (3, 'avg_time_to_fill', 40.0, 60.0, 'lower_is_better', 1);
INSERT INTO "traffic_light_rules" ("id", "metric_key", "green_threshold", "yellow_threshold", "direction", "enabled") VALUES (4, 'offers_accepted_pct', 85.0, 65.0, 'higher_is_better', 1);
INSERT INTO "traffic_light_rules" ("id", "metric_key", "green_threshold", "yellow_threshold", "direction", "enabled") VALUES (5, 'probation_pass_rate', 90.0, 75.0, 'higher_is_better', 1);
INSERT INTO "traffic_light_rules" ("id", "metric_key", "green_threshold", "yellow_threshold", "direction", "enabled") VALUES (6, 'probation_pass_rate_adaptation', 85.0, 70.0, 'higher_is_better', 1);
INSERT INTO "traffic_light_rules" ("id", "metric_key", "green_threshold", "yellow_threshold", "direction", "enabled") VALUES (7, 'adaptation_dismissals', 1.0, 3.0, 'lower_is_better', 1);
INSERT INTO "user_departments" ("user_id", "department_id") VALUES (4, 1);
INSERT INTO "user_service_access" ("id", "user_id", "service_key", "access_level") VALUES (1, 1, 'apparat_gd', 'admin');
INSERT INTO "user_service_access" ("id", "user_id", "service_key", "access_level") VALUES (2, 1, 'tech', 'admin');
INSERT INTO "user_service_access" ("id", "user_id", "service_key", "access_level") VALUES (3, 1, 'it', 'admin');
INSERT INTO "user_service_access" ("id", "user_id", "service_key", "access_level") VALUES (4, 1, 'commercial', 'admin');
INSERT INTO "user_service_access" ("id", "user_id", "service_key", "access_level") VALUES (5, 1, 'marketing', 'admin');
INSERT INTO "user_service_access" ("id", "user_id", "service_key", "access_level") VALUES (6, 1, 'hr', 'admin');
INSERT INTO "user_service_access" ("id", "user_id", "service_key", "access_level") VALUES (7, 1, 'project_product', 'admin');
INSERT INTO "user_service_access" ("id", "user_id", "service_key", "access_level") VALUES (8, 1, 'finance', 'admin');
INSERT INTO "user_service_access" ("id", "user_id", "service_key", "access_level") VALUES (9, 1, 'legal', 'admin');
INSERT INTO "user_service_access" ("id", "user_id", "service_key", "access_level") VALUES (10, 2, 'hr', 'admin');
INSERT INTO "user_service_access" ("id", "user_id", "service_key", "access_level") VALUES (11, 2, 'project_product', 'read');
INSERT INTO "user_service_access" ("id", "user_id", "service_key", "access_level") VALUES (12, 2, 'tech', 'read');
INSERT INTO "user_service_access" ("id", "user_id", "service_key", "access_level") VALUES (13, 3, 'hr', 'read');
INSERT INTO "user_service_access" ("id", "user_id", "service_key", "access_level") VALUES (14, 3, 'project_product', 'read');
INSERT INTO "user_service_access" ("id", "user_id", "service_key", "access_level") VALUES (15, 3, 'tech', 'read');
INSERT INTO "user_service_access" ("id", "user_id", "service_key", "access_level") VALUES (16, 4, 'it', 'read');
INSERT INTO "user_service_access" ("id", "user_id", "service_key", "access_level") VALUES (17, 4, 'hr', 'read');
INSERT INTO "users" ("id", "username", "full_name", "email", "position", "phone", "avatar", "role", "hashed_password", "is_active", "must_change_password", "created_at") VALUES (1, 'admin', 'Администратор системы', NULL, NULL, NULL, NULL, 'ADMIN', '$2b$12$E7.eGPHcpuLY0P2/2W4WAOQOhC.4Lg36kqrJgZ0hKaVjKsSrds/U.', 1, 0, '2026-11-01 07:45:03.949514');
INSERT INTO "users" ("id", "username", "full_name", "email", "position", "phone", "avatar", "role", "hashed_password", "is_active", "must_change_password", "created_at") VALUES (2, 'hr_head', 'Начальник службы персонала', NULL, NULL, NULL, NULL, 'HR_HEAD', '$2b$12$XlBduWax0JD0nzfY6dhI..qaQ50WPTV1DwVGT0fbr3BpJA3lO0AEe', 1, 0, '2026-11-01 07:45:04.265460');
INSERT INTO "users" ("id", "username", "full_name", "email", "position", "phone", "avatar", "role", "hashed_password", "is_active", "must_change_password", "created_at") VALUES (3, 'viewer', 'Пользователь (просмотр)', NULL, NULL, NULL, NULL, 'VIEWER', '$2b$12$zOBvvY96V.PrzpdAudCGY.Mbz2Z.m1QCG6wXzKBkgjmpH3znDcT/m', 1, 0, '2026-11-01 07:45:04.573230');
INSERT INTO "users" ("id", "username", "full_name", "email", "position", "phone", "avatar", "role", "hashed_password", "is_active", "must_change_password", "created_at") VALUES (4, 'it_viewer', 'Пользователь ИТ-отдела', NULL, NULL, NULL, NULL, 'DEPT_VIEWER', '$2b$12$ay51WCN99FBt9l1B9QmvNOL0h8JKoG808OS7Mig1E9ZCdwXuOcwB.', 1, 0, '2026-11-01 07:45:04.903366');
INSERT INTO naumen_tickets (number, name, registered_at, status, org, overdue, reopened) SELECT number, name, registered_at, 'Выполнена', org, 0, 1 FROM naumen_tickets ORDER BY id LIMIT 1;
INSERT INTO tp_report_rows (year, week, period, total_in_work) SELECT year, week, period, 999 FROM tp_report_rows ORDER BY id LIMIT 1;
INSERT INTO tp_report_rows (year, week, period, total_in_work) VALUES (NULL, NULL, 'мусор', 1);
COMMIT;

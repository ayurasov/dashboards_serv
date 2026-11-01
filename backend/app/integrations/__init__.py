"""Интеграции с корпоративными системами (ADR-0011) — руководство автора коннектора.

Устройство:
    base.py        Connector, Field, Action, CheckResult, RunResult, RunContext, реестр (@register)
    http.py        HttpClient и сетевые правила: адрес, <ВИД>_ALLOWED_HOSTS, без перенаправлений, таймауты
                   5/30 с, 20 МБ, повтор 429/503, IntegrationError с подробным и кратким текстом
    runner.py      экземпляр коннектора с секретами, проверка, запуск с журналом, расписание, атомарный claim
    connectors/    встроенные коннекторы (folder — пример); новый модуль импортируйте в connectors/__init__.py
Секреты — app/core/secrets.py; администрирование и ключи — app/services/integration_admin.py;
входящие — app/services/inbox.py; наборы данных — app/services/inbox_datasets.py.

1. Коннектор. Подкласс Connector с атрибутами kind (латиница: podelu, puls, jira, confluence, bitrix24,
   exchange, onec), title, description, fields, actions, url_field (поле адреса, к нему привязаны секреты;
   None — без адреса), singleton. Методы:
   - check() → CheckResult(ok, message, details): адрес, доступ, версия. Сеть — только через self.http();
     ошибки — IntegrationError (каркас превращает их в {ok: false, message}: подробно — администратору);
   - run(action, ctx) → RunResult.ok(message, counters={…}, items=[…]) / RunResult.partial(…) /
     RunResult.failed(error). Исключение IntegrationError или AppError — запуск «ошибка» с текстом.
   - validate_config(config) (classmethod) — переопределите для связей полей (вызовите super()).
   self.config — настройки (без секретов), self.secrets — расшифрованные секреты (только для адреса,
   для которого их ввели), self.detailed — подробные ли ошибки.

2. Настройки — кортеж Field(key, label, type, hint, required, secret, options, default, placeholder,
   min, max, show_if). Типы: string · text · url · password · int · bool · select · multiselect · list ·
   time. secret=True — поле шифруется, в API не возвращается (только secret_fields: какие заданы).
   Поле verify_tls (bool, default True) по соглашению управляет проверкой сертификата в self.http().
   Пример: Field("instance", "Тип", "select", options=(Option("cloud", "Cloud"), Option("server", "Server")),
   required=True), Field("login", "Email", show_if={"instance": ("cloud",)}),
   Field("token", "API-токен", "password", required=True, secret=True).

3. HTTP. self.http(auth=(логин, пароль) | None, headers={…}, cookies=True|False, timeout=(5, 30)) →
   HttpClient: get_json(path, kind=dict|list, params=…), post_json(path, body), get_bytes(path),
   request(method, path, expect=(200, 204), not_found="текст"). path — относительно адреса подключения.
   Сессионный вход (служебная учётная запись «По Делу» / «Пульса»): тот же клиент с cookies=True,
   CSRF-токен — заголовком; выход — в finally.

4. Контекст ctx (RunContext): db; integration; trigger (manual · schedule · webhook · folder · cli); user
   (None — по расписанию); state — словарь между запусками (курсоры, «последнее обработанное»; сохраняется
   после действия); log; actor — «источник данных» от имени подключения для движков;
   - ctx.inbox.add(content: bytes, filename, dataset=None, source_ref="…", content_type="", options=None,
     apply=None) → InboxItem: файл во входящие (повтор по SHA-256 распознаётся; «применять сразу» — по
     правилу источника «Подключение» и набора; apply=False — только план). Каждый элемент фиксируется
     сразу. ctx.inbox.seen(source_ref) — элемент этого подключения с тем же source_ref (уже забирали);
   - ctx.plans.structure(bundle, apply=False, apply_settings=False), ctx.plans.employees(document, apply=…,
     new_users="no_access", decisions=None), ctx.plans.org_list(rows, apply=…, create_missing=…,
     deactivate_missing=…), ctx.plans.indicator_values(rows, apply=…) — те же движки, что у ручной загрузки:
     план без записи или применение одной транзакцией (commit при успехе). Предпочтительный путь —
     ctx.inbox (элемент виден на экране «Входящие» с планом и итогом).

5. Чужие форматы JSON (podelu.org-structure, podelu.employees) — inbox_datasets.register_json_format(
   "podelu.org-structure", "structure", convert): документ распознаётся как набор, convert переводит его
   в dashboards.org-structure / dashboards.employees до плана.

6. Новый набор входящих — подкласс inbox_datasets.Dataset с @register: key (= подпапка во «Входящих»),
   label, service_key, apply_level / capability / data_class, patterns, sniff(peek), parse, plan, apply
   (движок службы с plan/apply, как app/services/tp.py), option_fields.

7. Тесты — поддельный сервер на http.server в потоке (tests/fake_http.py), как поддельные Jira и
   Confluence в burndown_tool; поддельный коннектор для каркаса — tests/test_integrations.py.
"""

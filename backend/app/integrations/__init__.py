"""Интеграции с корпоративными системами (ADR-0011) — руководство автора коннектора.

Устройство:
    base.py        Connector, Field, Action, CheckResult, RunResult, RunContext, реестр (@register)
    http.py        HttpClient и сетевые правила: адрес, <ВИД>_ALLOWED_HOSTS, без перенаправлений, таймауты
                   5/30 с, 20 МБ, повтор 429/503 (только GET/HEAD/OPTIONS или retry=True), IntegrationError
                   с подробным и кратким текстом, вычистка секретов (scrub)
    runner.py      экземпляр коннектора с секретами, проверка, запуск с журналом, расписание, атомарный claim;
                   тексты проверки и запуска и журнал сервера — без секретов
    connectors/    встроенные коннекторы (folder — пример); новый модуль импортируйте в connectors/__init__.py
Секреты — app/core/secrets.py; администрирование и ключи — app/services/integration_admin.py;
входящие — app/services/inbox.py; наборы данных — app/services/inbox_datasets.py.

1. Коннектор. Подкласс Connector с атрибутами kind (латиница: podelu, puls, jira, confluence, bitrix24,
   exchange, onec), title, description, fields, actions, url_field (поле адреса для self.http(); None — без
   адреса), singleton, order (место в выборе вида и среди карточек: «По Делу» 10, «Пульс» 20, Jira 30,
   Confluence 40, Bitrix24 50, Exchange 60, 1С 70, папка 80), counter_labels ({"tasks": "задач в списке"} —
   подписи счётчиков RunResult.counters для журнала запусков; общие — значения, файлы во «Входящие», статусы —
   подписаны каркасом base.COMMON_COUNTER_LABELS; счётчик без подписи интерфейс не показывает), admin_only и
   admin_only_reason (вид, который отдаёт наружу данные, недоступные пользователю с integrations.manage, —
   Confluence публикует полный отчёт: создаёт, настраивает, проверяет, запускает и удаляет только
   администратор, остальным карточка видна только для чтения с «Только администратор: <причина>»).
   Секреты привязаны к адресу Connector.secret_url(config) — по умолчанию значение
   url_field. Если секрет уходит на несколько адресов или адрес зависит от режима, переопределите
   classmethod secret_url (у «По Делу» — «адрес → адрес для запросов сервера», у Exchange — адрес выбранного
   способа подключения) и перечислите поля, от которых он зависит, в secret_url_fields: /kinds отдаёт их,
   и форма предупреждает до сохранения, что после их изменения секреты нужно ввести заново. Методы:
   - check() → CheckResult(ok, message, details): адрес, доступ, версия. Сеть — только через self.http();
     ошибки — IntegrationError (каркас превращает их в {ok: false, message}: подробно — администратору);
   - run(action, ctx) → RunResult.ok(message, counters={…}, items=[…]) / RunResult.partial(…) /
     RunResult.failed(error). Исключение IntegrationError или AppError — запуск «ошибка» с текстом.
   - validate_config(config) (classmethod) — переопределите для связей полей (вызовите super()).
   self.config — настройки (без секретов), self.secrets — расшифрованные секреты (только для адреса,
   для которого их ввели), self.detailed — подробные ли ошибки. secret_values() — что вычищать из текстов
   (по умолчанию значения секретов): переопределите, если секрет уходит в запрос в производном виде (код
   вебхука в пути адреса у Bitrix24) — HttpClient и runner заменят эти части на «…».

2. Настройки — кортеж Field(key, label, type, hint, required, secret, options, default, placeholder,
   min, max, show_if). Типы: string · text · url · password · int · bool · select · multiselect · list ·
   time · json (разобранный JSON: списки правил и запросов, до 64 КБ). secret=True — поле шифруется,
   в API не возвращается (только secret_fields: какие заданы).
   Поле verify_tls (bool, default True) по соглашению управляет проверкой сертификата в self.http().
   Пример: Field("instance", "Тип", "select", options=(Option("cloud", "Cloud"), Option("server", "Server")),
   required=True), Field("login", "Email", show_if={"instance": ("cloud",)}),
   Field("token", "API-токен", "password", required=True, secret=True).

3. HTTP. self.http(auth=(логин, пароль) | None, headers={…}, cookies=True|False, timeout=(5, 30)) →
   HttpClient: get_json(path, kind=dict|list, params=…), post_json(path, body), get_bytes(path),
   request(method, path, expect=(200, 204), not_found="текст", retry=None). path — относительно адреса
   подключения. При 429/503 повторяются только GET, HEAD, OPTIONS; POST, PUT, PATCH, DELETE — только
   с retry=True (передавайте его для чтения через POST, как у REST Bitrix24; вход и изменения у партнёра
   не повторяются: повтор тратит его ограничение попыток входа и может выполнить действие дважды).
   Секреты подключения, пароль Basic, токен Authorization, логин:пароль@ в адресе и сегменты пути, равные
   секрету, не попадают в тексты IntegrationError клиента; client.scrub(text) — для своих сообщений из
   ответа. Неожиданное исключение runner пишет в журнал сервера вычищенным (сообщение и трассировка).
   Сессионный вход (служебная учётная запись «По Делу» / «Пульса»): тот же клиент с cookies=True,
   CSRF-токен — заголовком; выход — в finally.

4. Контекст ctx (RunContext): db; integration; trigger (manual · schedule · webhook · folder · cli); user
   (None — по расписанию); state — словарь между запусками (курсоры, «последнее обработанное»; сохраняется
   после действия); log; actor — «источник данных» от имени подключения для движков;
   - ctx.inbox.add(content: bytes, filename, dataset=None, source_ref="…", content_type="", options=None,
     apply=None, note="") → InboxItem: файл во входящие (повтор по SHA-256 распознаётся; «применять сразу» —
     по правилу источника «Подключение» и набора; apply=False — только план). note — откуда файл для
     человека, до 500 символов («Задача «…» · автор», «Письмо «…» от …»): виден под именем файла в списке
     «Входящих» и в карточке элемента — не дублируйте его в подробностях запуска. Каждый элемент фиксируется
     сразу. ctx.inbox.seen(source_ref) — элемент этого подключения с тем же source_ref (уже забирали);
   - ctx.plans.structure(bundle, apply=False, apply_settings=False), ctx.plans.employees(document, apply=…,
     new_users="no_access", decisions=None), ctx.plans.org_list(rows, apply=…, create_missing=…,
     deactivate_missing=…, keep={служебные логины и email}), ctx.plans.indicator_values(rows, apply=…) — те
     же движки, что у ручной загрузки: план без записи или применение одной транзакцией (commit при успехе).
     Предпочтительный путь — ctx.inbox (элемент виден на экране «Входящие» с планом и итогом).
     deactivate_missing отключает только сотрудников того же источника (org_source = вид подключения; умеют
     ad и podelu), никогда — служебные учётные записи из keep, запустившего и последнего администратора.
     Строка значений {"clear": True} без value/target/comment удаляет сохранённое значение показателя за месяц
     (действие clear, в сводке cleared) — например, когда показатель за месяц больше не определён; пустое
     значение без clear ничего не стирает. Повтор с теми же значениями ничего не пишет и не засоряет журнал;
   - коннектор показателей с действием «Проверить без записи» (connectors/_metrics.py): значения показателей,
     которых ещё нет в каталоге, план загрузки построить не может — Pending.of() считает их отдельно
     («показатель «…» будет создан при запуске: значений N»);
   - ctx.plans.ensure_indicator(body) → reports.IndicatorDef: показатель каталога по ключу body["key"] —
     существующий как есть, недостающий создаётся report_admin.create_indicator от имени подключения
     (body — поля IndicatorCreateIn; ошибки ValidationFailed / Conflict). Созданный показатель фиксируется
     сразу — единственный разрешённый commit коннектора вне ctx.inbox и движков: каталог для плана значений
     (reports.state) берётся по ревизии отчётов, а она растёт только при фиксации. Свои записи в таблицы
     каталога и служб коннектор не делает.

5. Чужие форматы JSON (podelu.org-structure, podelu.employees) — inbox_datasets.register_json_format(
   "podelu.org-structure", "structure", convert) на уровне модуля коннектора: документ распознаётся как
   набор, convert переводит его в dashboards.org-structure / dashboards.employees до плана. Распознавание
   само загружает модули коннекторов (base.load_connectors) — формат действует в любом процессе (сервер,
   планировщик, командная строка) и для файлов из папки и загрузки, без обращения к подключениям.

6. Новый набор входящих — подкласс inbox_datasets.Dataset с @register: key (= подпапка во «Входящих»),
   label, service_key, apply_level / capability / data_class, patterns, sniff(peek), parse, plan, apply
   (движок службы с plan/apply, как app/services/tp.py), option_fields.

7. Тесты — поддельный сервер на http.server в потоке (tests/fake_http.py), как поддельные Jira и
   Confluence в burndown_tool; поддельный коннектор для каркаса — tests/test_integrations.py.
"""

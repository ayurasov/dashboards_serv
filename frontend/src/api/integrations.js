/**
 * API интеграций (ADR-0011): виды подключений и их поля, подключения, проверка, запуск, журнал
 * запусков, ключи для входящих вызовов. Пути совпадают с backend/app/api/routers/integrations.py.
 * Секреты подключений сервер не возвращает: только secret_fields (какие заданы) и secret_problem.
 */
import { api } from './client'

/**
 * Ошибки, которые экран показывает сам, рядом с местом: check_required — «Сначала проверьте» с
 * кнопкой «Проверить», secret_rebind_required — адрес изменён, секреты ввести заново.
 */
export const HANDLED_ERRORS = ['check_required', 'secret_rebind_required', 'singleton']

export const integrationsApi = {
  /**
   * [{ kind, title, description, fields, actions, url_field, secret_url_fields, singleton, allowed_hosts_env }];
   * secret_url_fields — поля адреса привязки секретов: их изменение требует ввести секреты заново.
   */
  kinds: () => api.get('/integrations/kinds'),
  list: () => api.get('/integrations'),
  get: (id) => api.get(`/integrations/${id}`),
  /** { kind, name, config, secrets, schedule } — создаётся выключенным. */
  create: (body) => api.post('/integrations', body, { handled: HANDLED_ERRORS }),
  /** Проверка ещё не сохранённого подключения: { kind, config, secrets } → { ok, message, details }. */
  checkDraft: (body) => api.post('/integrations/check', body),
  /** { name, enabled, config (объединяется), secrets, clear_secrets, schedule }. */
  update: (id, body) => api.patch(`/integrations/${id}`, body, { handled: HANDLED_ERRORS }),
  remove: (id) => api.del(`/integrations/${id}`),
  /** Без тела — сохранённые настройки (успех отмечает проверенным); с config/secrets — несохранённые. */
  check: (id, body) => api.post(`/integrations/${id}/check`, body),
  /** Действие выполняется сразу; ответ — запись журнала запусков. */
  run: (id, action) => api.post(`/integrations/${id}/run`, { action }),
  runs: (id, limit = 50) => api.get(`/integrations/${id}/runs`, { limit }),

  /** Ключи без значений; rate_limit — сколько запросов в минуту разрешено ключу (INBOUND_RATE_LIMIT). */
  keys: () => api.get('/integrations/keys'),
  /** { name, scopes: ['files', 'status'] } → ключ с полем key (показывается один раз). */
  issueKey: (body) => api.post('/integrations/keys', body),
  reissueKey: (id) => api.post(`/integrations/keys/${id}/reissue`),
  revokeKey: (id) => api.post(`/integrations/keys/${id}/revoke`),
}

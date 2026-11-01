/**
 * API модели доступа 2.0 и входа по домену (ADR-0008, ADR-0009): справочник измерений, профили
 * доступа, доступ пользователя, «Выдать доступ», состояние и проверка входа по домену.
 * Пути совпадают с backend/app/api/routers/{access,users,auth,system}.py.
 */
import { api } from './client'

export const accessApi = {
  /** Справочник: классы данных, области, измерения, уровни, полномочия, службы (любой вошедший). */
  meta: () => api.get('/access/meta'),
  profiles: () => api.get('/access/profiles'),
  profile: (id) => api.get(`/access/profiles/${id}`),
  createProfile: (body) => api.post('/access/profiles', body),
  updateProfile: (id, body) => api.patch(`/access/profiles/${id}`, body),
  deleteProfile: (id) => api.del(`/access/profiles/${id}`),
  /** Доступ пользователя: профиль, личные значения, строки служб, доп. подразделения, действующий доступ. */
  userAccess: (userId) => api.get(`/users/${userId}/access`),
  /** Меняются только переданные части: profile_id, overrides, services, extra_unit_ids. */
  setUserAccess: (userId, body) => api.put(`/users/${userId}/access`, body),
}

export const usersApi = {
  /** ?search&role&status&department_id&profile_id&auth_source → { items, total, summary }. */
  list: (params) => api.get('/users', params),
  get: (id) => api.get(`/users/${id}`),
  create: (body) => api.post('/users', body),
  update: (id, body) => api.patch(`/users/${id}`, body),
  grantAccess: (id, method) => api.post(`/users/${id}/grant-access`, { method }),
  resetPassword: (id) => api.post(`/users/${id}/reset-password`),
  remove: (id) => api.del(`/users/${id}`),
  /** Журнал по пользователю (администратор): изменения карточки и доступа. */
  history: (params) => api.get('/audit', params, { silent: true }),
}

export const directoryApi = {
  /** Способы входа для страницы входа (без входа в систему). */
  loginConfig: () => api.get('/auth/config', null, { silent: true }),
  /** Состояние входа по домену и настройки без секретов (администратор). */
  ldapStatus: () => api.get('/system/ldap'),
  /** Без логина — подключение и служебная привязка; с логином — ещё и поиск записи. Пароль не проверяется. */
  ldapTest: (login = '') => api.post('/system/ldap/test', login ? { login } : {}),
}

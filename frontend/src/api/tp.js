import { api } from './client.js'

export const tpApi = {
  rows:        ()      => api.get('/tp/rows'),
  columns:     ()      => api.get('/tp/columns'),
  summary:     (w=8)   => api.get(`/tp/summary?weeks=${w}`),
  export:      ()      => api.get('/tp/export', { responseType: 'blob' }),
  createRow:   (body)  => api.post('/tp/rows', body),
  updateRow:   (id, b) => api.put(`/tp/rows/${id}`, b),
  deleteRow:   (id)    => api.del(`/tp/rows/${id}`),
  bulkImport:  (rows)  => api.post('/tp/rows/bulk_import', { rows }),
  getSetting:  (key)   => api.get(`/tp/settings/${key}`),
  putSetting:  (key,v) => api.put(`/tp/settings/${key}`, v),
  naumenSummary: ()    => api.get('/tp/naumen/summary'),
  naumenMatch:   ()    => api.get('/tp/naumen/match'),
  naumenImport:  async (file) => {
    const token = localStorage.getItem('hr_token')
    const body = new FormData()
    body.append('file', file)
    const res = await fetch('/api/tp/naumen/import', {
      method: 'POST',
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      body,
    })
    if (!res.ok) {
      let msg = 'Ошибка импорта'
      try { msg = (await res.json())?.detail || msg } catch {}
      throw new Error(msg)
    }
    return res.json()
  },
}

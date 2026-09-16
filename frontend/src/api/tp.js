import { api } from './client.js'

async function uploadFile(url, file) {
  const token = localStorage.getItem('hr_token')
  const body = new FormData()
  body.append('file', file)
  const res = await fetch(url, {
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
}

async function downloadFile(url, filename) {
  const token = localStorage.getItem('hr_token')
  const res = await fetch(url, { headers: token ? { Authorization: `Bearer ${token}` } : {} })
  if (!res.ok) throw new Error('Ошибка экспорта')
  const blob = await res.blob()
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = filename
  a.click()
  URL.revokeObjectURL(a.href)
}

export const tpApi = {
  rows:        ()      => api.get('/tp/rows'),
  columns:     ()      => api.get('/tp/columns'),
  summary:     (w=8)   => api.get(`/tp/summary?weeks=${w}`),
  export:      ()      => api.get('/tp/export', { responseType: 'blob' }),
  exportXlsx:  ()      => downloadFile('/api/tp/export/xlsx', 'Итоговый отчет ТП по неделям.xlsx'),
  createRow:   (body)  => api.post('/tp/rows', body),
  updateRow:   (id, b) => api.put(`/tp/rows/${id}`, b),
  deleteRow:   (id)    => api.del(`/tp/rows/${id}`),
  bulkImport:  (rows)  => api.post('/tp/rows/bulk_import', { rows }),
  tpImport:    (file)  => uploadFile('/api/tp/rows/import', file),
  getSetting:  (key)   => api.get(`/tp/settings/${key}`),
  putSetting:  (key,v) => api.put(`/tp/settings/${key}`, v),
  naumenSummary: (params) => {
    const q = new URLSearchParams()
    if (params?.year)   q.set('year', params.year)
    if (params?.org)    q.set('org', params.org)
    if (params?.months) q.set('months', params.months)
    const qs = q.toString()
    return api.get(`/tp/naumen/summary${qs ? '?' + qs : ''}`)
  },
  naumenMatch:   ()    => api.get('/tp/naumen/match'),
  naumenImport:  (file) => uploadFile('/api/tp/naumen/import', file),
}
